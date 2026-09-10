import chess
from fastapi.testclient import TestClient
from app.main import app


def read_ready(ws):
    messages = []
    while True:
        event = ws.receive_json()
        messages.append(event)
        if event["type"] == "state" and not event["thinking"]:
            return messages


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"


def test_game_validation_stream_and_reconnect():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            token = hello["session_id"]
            assert len(hello["graph"]["nodes"]) > 100
            state = ws.receive_json()
            ws.send_json({"type": "move", "uci": "e2e5", "revision": state["revision"]})
            assert ws.receive_json()["type"] == "error"
            ws.send_json({"type": "move", "uci": "e2e4", "revision": state["revision"]})
            events = read_ready(ws)
            frames = [e for e in events if e["type"] == "spikes"]
            assert len(frames) == 10
            final = events[-1]
            assert chess.Board(final["fen"]).turn == chess.WHITE
            assert len(final["history"]) == 2
            ws.send_json({"type": "move", "uci": "d2d4", "revision": 0})
            assert ws.receive_json()["code"] == "stale_revision"
        with client.websocket_connect("/ws?session=" + token) as ws:
            assert ws.receive_json()["session_id"] == token
            assert ws.receive_json()["fen"] == final["fen"]
            ws.send_json({"type": "reset", "revision": final["revision"]})
            reset = ws.receive_json()
            assert reset["fen"] == chess.STARTING_FEN
            assert reset["history"] == []


def test_bad_messages_and_session_isolation():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as first, client.websocket_connect("/ws") as second:
            assert first.receive_json()["session_id"] != second.receive_json()["session_id"]
            first.receive_json()
            second.receive_json()
            for raw in ["not json", "[]", '{"type":"unknown"}']:
                first.send_text(raw)
                assert first.receive_json()["type"] == "error"
            first.send_json({"type": "ping"})
            assert first.receive_json()["type"] == "pong"


def test_untrusted_browser_origin_is_rejected():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws", headers={"origin": "https://untrusted.example"}):
                pass
        assert exc.value.code == 1008


def test_disconnect_during_trial_recovers_completed_game():
    import time

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            token = ws.receive_json()["session_id"]
            ws.receive_json()
            ws.send_json({"type": "move", "uci": "e2e4", "revision": 0})
            assert ws.receive_json()["thinking"]
        time.sleep(0.5)
        with client.websocket_connect("/ws?session=" + token) as ws:
            ws.receive_json()
            state = ws.receive_json()
            assert not state["thinking"]
            assert len(state["history"]) == 2


def test_second_socket_cannot_own_same_session():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as first:
            token = first.receive_json()["session_id"]
            first.receive_json()
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/ws?session=" + token) as second:
                    second.receive_json()
            assert exc.value.code == 4009
