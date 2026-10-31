"""Script registry and data-schema tests. Run: uv run --with pytest pytest -q"""

import pytest

import scripts
from scripts import trouble_brewing as tb

USES = {"each_night", "once_per_game", "passive", "day", "on_death", "on_nomination", "none"}


def test_registry_has_tb():
    assert scripts.SCRIPTS["tb"] is tb
    assert tb.ID == "tb" and tb.NAME == "Trouble Brewing"


@pytest.mark.parametrize("mod", list(scripts.SCRIPTS.values()), ids=lambda m: m.ID)
def test_every_character_declares_the_schema(mod):
    for cid, c in mod.CHARACTERS.items():
        assert c["uses"] in USES, cid
        assert isinstance(c["reminders"], list) and isinstance(c["hint"], str), cid
        n = c["night"]
        assert n is None or n["kind"] in {"info", "choose", "storyteller", "meeting"}, cid
        if n and n["kind"] == "choose":
            assert {"kind", "count", "allow_self", "prompt"} <= set(n), cid


@pytest.mark.parametrize("mod", list(scripts.SCRIPTS.values()), ids=lambda m: m.ID)
def test_night_order_keys_exist(mod):
    for key in mod.FIRST_NIGHT + mod.OTHER_NIGHTS:
        assert key in mod.CHARACTERS or key in mod.MEETINGS


def test_game_exposes_script_and_refuses_unknown():
    from game import Game, GameError
    g = Game(script="tb")
    assert g.public_view()["script"] == {"id": "tb", "name": "Trouble Brewing"}
    with pytest.raises(GameError):
        g.set_script("nope")
