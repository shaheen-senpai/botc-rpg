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
