"""Single-process, bounded on-premise WebSocket service."""

import asyncio
from contextlib import asynccontextmanager, suppress
import json
import logging
import os
import secrets
import time

import chess
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .game import Game
from .neural import Connectome, Simulation, DATA, CONFIG

logger = logging.getLogger(__name__)
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "128"))
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
ORIGINS = set(os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(","))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.graph = Connectome()
    app.state.sessions = {}
    app.state.tasks = set()
    app.state.slots = asyncio.Semaphore(4)

    async def reap():
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            for token, game in list(app.state.sessions.items()):
                if not game.connected and not game.thinking and now - game.last_seen > SESSION_TTL:
                    del app.state.sessions[token]

    reaper = asyncio.create_task(reap())
    yield
    reaper.cancel()
    with suppress(asyncio.CancelledError):
        await reaper
    if app.state.tasks:
        await asyncio.gather(*app.state.tasks, return_exceptions=True)


app = FastAPI(title="Fly Brain Chess", version="1.0.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": "flywire-fafb-783", "neurons": app.state.graph.size}


@app.get("/api/model")
async def model():
    report = json.loads((DATA / "training_report.json").read_text())
    if report["reservoir_fingerprint"] != app.state.graph.fingerprint:
        raise RuntimeError("Training report does not match loaded reservoir")
    return {"provenance": app.state.graph.provenance, "configuration": CONFIG,
            "fingerprint": app.state.graph.fingerprint, "training": report}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin not in ORIGINS:
        await ws.close(code=1008)
        return
    await ws.accept()
    sessions = app.state.sessions
    token = ws.query_params.get("session", "")
    game = sessions.get(token)
    if game and game.connected:
        await ws.close(code=4009, reason="Session already open in another connection")
        return
    if game is None:
        if len(sessions) >= MAX_SESSIONS:
            await ws.close(code=1013, reason="Session capacity reached; try later")
            return
        token = secrets.token_urlsafe(32)
        game = sessions[token] = Game()
    game.connected = True
    send_lock = asyncio.Lock()
    alive = True

    async def send(event):
        nonlocal alive
        async with send_lock:
            if alive:
                try:
                    await asyncio.wait_for(ws.send_json(event), timeout=5)
                except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                    alive = False

    async def error(code, message):
        await send({"type": "error", "code": code, "message": message, "state": game.snapshot()})

    async def think():
        try:
            async with app.state.slots:
                sim = await asyncio.to_thread(Simulation, app.state.graph, game.board)
                start = time.monotonic()
                for _ in range(10):
                    frame = await asyncio.to_thread(sim.advance)
                    frame["revision"] = game.revision
                    await send(frame)
                    # Pace actual computed batches to wall time, without blocking the event loop.
                    await asyncio.sleep(max(0, start + sim.time_ms / 1000 - time.monotonic()))
                move = sim.decode()
                if move is not None:
                    game.push(move)
                game.stats = sim.summary()
        except Exception:
            logger.exception("Neural trial failed")
            await error("simulation_failed", "Simulation failed. Reconnect to retry, or start a new game.")
        finally:
            game.thinking = False
            game.last_seen = time.monotonic()
            await send(game.snapshot())

    def start_thinking():
        game.thinking = True
        task = asyncio.create_task(think())
        app.state.tasks.add(task)
        task.add_done_callback(app.state.tasks.discard)

    try:
        await send({"type": "hello", "session_id": token, "graph": app.state.graph.serialize()})
        if game.board.turn == chess.BLACK and not game.board.is_game_over(claim_draw=True) and not game.thinking:
            start_thinking()
        await send(game.snapshot())
        last_command = 0.0
        while alive:
            packet = await asyncio.wait_for(ws.receive(), timeout=90)
            if packet["type"] == "websocket.disconnect":
                break
            raw = packet.get("text")
            if raw is None or len(raw.encode()) > 2048:
                await ws.close(code=1009)
                break
            game.last_seen = time.monotonic()
            try:
                command = json.loads(raw)
            except ValueError:
                await error("invalid_message", "Send a JSON object.")
                continue
            if not isinstance(command, dict) or command.get("type") not in {"ping", "move", "reset"}:
                await error("invalid_message", "Unknown command.")
                continue
            if command["type"] == "ping":
                # Snapshot also heals reconnects during a trial owned by an old socket.
                await send({"type": "pong", "state": game.snapshot()})
                continue
            if game.thinking:
                await error("busy", "The brain is still thinking.")
                continue
            if type(command.get("revision")) is not int or command["revision"] != game.revision:
                await error("stale_revision", "Board changed; use the latest position.")
                continue
            if time.monotonic() - last_command < 0.1:
                await error("rate_limited", "Please wait a moment before the next command.")
                continue
            if command["type"] == "reset":
                game.reset()
                last_command = time.monotonic()
                await send(game.snapshot())
                continue
            if game.board.turn != chess.WHITE or game.board.is_game_over(claim_draw=True):
                await error("wrong_turn", "No human move is available in this position.")
                continue
            uci = command.get("uci")
            try:
                if not isinstance(uci, str) or len(uci) not in (4, 5):
                    raise ValueError
                move = chess.Move.from_uci(uci)
                if move not in game.board.legal_moves:
                    raise ValueError
            except ValueError:
                await error("illegal_move", "That move is not legal.")
                continue
            game.push(move)
            last_command = time.monotonic()
            if not game.board.is_game_over(claim_draw=True):
                start_thinking()
            await send(game.snapshot())
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        alive = False
        game.connected = False
        game.last_seen = time.monotonic()
