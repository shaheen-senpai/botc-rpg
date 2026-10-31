"""HTTP surface tests. Run: uv run --with pytest --with httpx pytest -q"""

from fastapi.testclient import TestClient

from game import Game
from server import create_app


def client():
    g = Game(script="tb")
    return TestClient(create_app(g, "key", "http://x/")), g


def test_scripts_and_state_keys():
    c, g = client()
    assert c.get("/api/scripts").json()[0]["id"] == "tb"
    assert "server_time" in c.get("/api/state").json()
    st = c.get("/api/st?key=key").json()
    for k in ("night_check", "threads", "hands", "unread", "clock"):
        assert k in st


def test_hand_and_message_routes_and_st_actions():
    c, g = client()
    tok = c.post("/api/join", json={"name": "Asha"}).json()["token"]
    assert c.post("/api/message", json={"token": tok, "text": "hi"}).status_code == 200
    assert c.post("/api/st/set_night_check?key=key", json={"on": False}).json()["night_check"] is False
    assert c.post("/api/st/read_thread?key=key", json={"pid": "p1"}).status_code == 200
    assert c.post("/api/hand", json={"token": tok, "up": True}).status_code == 400   # lobby: day only


def test_lobby_action_is_not_marked_seen_by_phones():
    c, g = client()
    c.post("/api/join", json={"name": "Asha"})
    c.post("/api/join", json={"name": "Ben"})
    st = c.post("/api/st/set_night_check?key=key", json={"on": False}).json()
    assert st["undo"]["seen"] is False


def test_every_storyteller_action_has_a_label():
    from server import ACTION_LABELS, NO_UNDO, ST_ACTIONS
    assert set(ST_ACTIONS) - NO_UNDO <= set(ACTION_LABELS)
