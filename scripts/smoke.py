"""Exercise deployed health and a real chess turn through the public proxy."""

import asyncio
import json
import os
import urllib.request
from urllib.parse import urlsplit

import chess
from websockets.asyncio.client import connect

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")


async def main():
    with urllib.request.urlopen(BASE + "/api/health", timeout=10) as response:
        assert json.load(response)["status"] == "ok"
    parsed = urlsplit(BASE)
    url = ("wss" if parsed.scheme == "https" else "ws") + "://" + parsed.netloc + "/ws"
    async with connect(url, origin=BASE, max_size=2**22) as ws:
        hello = json.loads(await ws.recv())
        assert hello["graph"]["kind"] == "flywire-fafb-783"
        state = json.loads(await ws.recv())
        await ws.send(
            json.dumps({"type": "move", "uci": "e2e4", "revision": state["revision"]})
        )
        frames = []
        async with asyncio.timeout(20):
            while True:
                event = json.loads(await ws.recv())
                if event["type"] == "spikes":
                    frames.append(event)
                if event["type"] == "error":
                    raise AssertionError(event)
                if event["type"] == "state" and not event["thinking"]:
                    assert len(event["history"]) == 2
                    assert chess.Board(event["fen"]).turn == chess.WHITE
                    break
        assert len(frames) == 10 and frames[-1]["time_ms"] == 200
        assert event["stats"]["active_neurons"] > 0
        print(
            f"PASS: health, {len(hello['graph']['nodes'])} neurons, 10 spike frames, legal brain reply {event['history'][-1]['uci']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
