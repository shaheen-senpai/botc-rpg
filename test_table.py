"""Table-level features shared by every script: reminders, abilities, night check, threads, hands, the clock.

Run: uv run --with pytest pytest -q
"""

import pytest

from game import GameError
from test_game import make, p, step, to_night2


# --- reminders ---

def test_mark_unmark_and_expiry():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.mark(p(g, "Dev"), "protected", until="dawn")
    g.mark(p(g, "Dev"), "poisoned", until="night")
    assert g.has(p(g, "Dev"), "protected") and g.impaired(p(g, "Dev"))
    g.start_day()
    assert not g.has(p(g, "Dev"), "protected") and g.has(p(g, "Dev"), "poisoned")
    g.end_day()
    assert not g.has(p(g, "Dev"), "poisoned")


def test_poisoner_pick_is_a_chip_and_old_view_key_still_works():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.resolve(step(g, "poisoner"), [p(g, "Dev").pid])
    assert g.has(p(g, "Dev"), "poisoned")
    assert g.storyteller_view()["poisoned"] == p(g, "Dev").pid
    assert "poisoned" in g.storyteller_view()["players"][3]["reminders"]


def test_set_reminder_is_a_storyteller_action():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.set_reminder(p(g, "Ema").pid, "red herring", True)
    assert g.has(p(g, "Ema"), "red herring")
    g.set_reminder(p(g, "Ema").pid, "red herring", False)
    assert not g.has(p(g, "Ema"), "red herring")


# --- ability state ---

def test_slayer_use_marks_player_used():
    g = make(["imp", "poisoner", "slayer", "empath", "soldier"])
    g.start_day()
    g.day_ability(p(g, "Chen").pid, {"target": p(g, "Dev").pid, "recluse_as_demon": False})
    assert p(g, "Chen").used
    assert g.ability_state(p(g, "Chen")) == {"uses": "day", "used": True, "label": "Used"}
    assert g.storyteller_view()["slayer_spent"] is True


def test_ability_state_in_views():
    g = make(["imp", "poisoner", "slayer", "empath", "soldier"])
    assert g.storyteller_view()["players"][0]["ability"] == {"uses": "each_night", "used": False, "label": "Acts each night"}
    assert g.player_view(p(g, "Chen").token)["me"]["ability"]["label"] == "Unused"


# --- night check ---

def test_night_check_off_means_no_tap_tasks_and_no_waiting():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    g.set_night_check(False)
    to_night2(g)
    assert all(not (x.prompt and x.prompt["kind"] == "tap") for x in g.players)
    assert g.phones_done() == (0, 0)
    g.resolve(step(g, "imp"), [p(g, "Dev").pid])   # would raise "Waiting for ..." with the check on


def test_night_check_off_unblocks_dawn():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    with pytest.raises(GameError):
        g.start_day()
    g.set_night_check(False)
    g.start_day()
    assert g.phase == "day"


def test_exempt_still_gets_choice_prompt():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    g.set_exempt(p(g, "Ben").pid, True)
    g.stop_waiting()   # night 1's tap tasks would block dawn
    to_night2(g)
    assert p(g, "Ben").prompt["kind"] == "choose"
    assert p(g, "Ben").pid not in [x["pid"] for x in g.storyteller_view()["phones"]]


def test_stop_waiting_releases_dawn_once():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    g.stop_waiting()
    g.start_day()
    g.end_day()
    with pytest.raises(GameError):
        g.start_day()


# --- threads ---

def test_thread_holds_both_directions_and_seen():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.message(p(g, "Dev").pid, "Hello")
    g.note_to_storyteller(p(g, "Dev").token, "Hi back")
    t = g.player_view(p(g, "Dev").token)["me"]["thread"]
    assert t[0] == {"from": "st", "text": "Nothing to report tonight.", "label": "Night 1", "seen": False}
    assert [(m["from"], m["text"], m["seen"]) for m in t[1:]] == [("st", "Hello", False), ("player", "Hi back", False)]
    assert g.storyteller_view()["unread"] == 1
    g.read_thread(p(g, "Dev").pid)
    assert g.player_view(p(g, "Dev").token)["me"]["thread"][2]["seen"] is True
    assert g.storyteller_view()["unread"] == 0


def test_compat_keys_still_derived():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.message(p(g, "Dev").pid, "Hello")
    g.note_to_storyteller(p(g, "Dev").token, "Hi back")
    me = g.player_view(p(g, "Dev").token)["me"]
    assert me["messages"][-1] == {"label": "Day 1", "text": "Hello"}
    assert me["notes"] == [{"label": "Day 1", "text": "Hi back"}]
    assert g.storyteller_view()["inbox"][0]["read"] is False


def test_player_messages_survive_undo():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    before = g.snapshot()
    g.message(p(g, "Dev").pid, "Hello")
    g.push_undo("Message Dev", before, seen=True)
    g.note_to_storyteller(p(g, "Dev").token, "Hi back")
    g.undo()
    assert [m["text"] for m in p(g, "Dev").thread] == ["Nothing to report tonight.", "Hi back"]


# --- hands ---

def test_hand_up_down_and_order():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.raise_hand(p(g, "Dev").token, True)
    g.raise_hand(p(g, "Asha").token, True)
    assert g.public_view()["hands"] == [p(g, "Asha").pid, p(g, "Dev").pid]
    assert g.storyteller_view()["hands"] == [p(g, "Dev").pid, p(g, "Asha").pid]
    g.nominate(p(g, "Dev").pid, p(g, "Ema").pid)
    assert g.public_view()["hands"] == [p(g, "Asha").pid]


def test_dead_cannot_raise_to_nominate():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.kill(p(g, "Dev").pid)
    with pytest.raises(GameError, match="Dead players cannot nominate"):
        g.raise_hand(p(g, "Dev").token, True)


# --- the vote clock ---

SEVEN = ["imp", "poisoner", "monk", "empath", "soldier", "butler", "mayor"]   # threshold 4


def vote_game():
    g = make(SEVEN)
    t = [1000.0]
    g.clock = lambda: t[0]
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Ben").pid)
    return g, t


def test_clock_locks_seats_in_order_and_records():
    g, t = vote_game()
    for n in ("Chen", "Dev", "Ema"):
        g.raise_hand(p(g, n).token, True)
    g.start_clock(0, seat_seconds=3)
    assert g.public_view()["clock"]["state"] == "countdown"
    t[0] += 3 + 3 * 1   # go, then one seat
    assert g.public_view()["clock"]["locked"] == {p(g, "Chen").pid: True}
    t[0] += 3 * 6       # the rest, nominee last
    v = g.public_view()
    assert v["clock"]["state"] == "done" and v["nominations"][0]["votes"] == 3


def test_toggle_after_lock_refused():
    g, t = vote_game()
    g.start_clock(0)
    t[0] += 3 + 3
    with pytest.raises(GameError, match="The clock has passed you"):
        g.raise_hand(p(g, "Chen").token, True)


def test_butler_locks_no_when_master_down():
    g = make(SEVEN)
    t = [1000.0]
    g.clock = lambda: t[0]
    g.resolve(step(g, "butler"), [p(g, "Asha").pid])   # night 1: Finn's Master is Asha
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Ben").pid)
    g.raise_hand(p(g, "Finn").token, True)             # Asha's hand stays down
    g.start_clock(0)
    t[0] += 3 + 3 * 7
    assert g.public_view()["clock"]["locked"][p(g, "Finn").pid] is False


def test_dead_without_ghost_vote_cannot_raise():
    g, t = vote_game()
    g.kill(p(g, "Dev").pid)
    g.set_ghost_vote(p(g, "Dev").pid, False)
    g.start_clock(0)
    with pytest.raises(GameError, match="No vote left"):
        g.raise_hand(p(g, "Dev").token, True)


def test_pause_freezes_and_restart_clears_locks():
    g, t = vote_game()
    g.raise_hand(p(g, "Chen").token, True)
    g.start_clock(0)
    t[0] += 3 + 3
    g.pause_clock()
    t[0] += 100
    assert g.public_view()["clock"]["locked"] == {p(g, "Chen").pid: True}
    g.resume_clock()
    g.restart_clock()
    v = g.public_view()["clock"]
    assert v["locked"] == {} and v["hands"] == [p(g, "Chen").pid]


def test_undo_start_clock_clears_clock():
    g, t = vote_game()
    before = g.snapshot()
    g.start_clock(0)
    g.push_undo("Start the clock", before, seen=True)
    t[0] += 3 + 3 * 7
    g.undo()
    assert g.public_view()["clock"] is None and all(x.ghost_vote for x in g.players)
