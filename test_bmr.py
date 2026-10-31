"""Bad Moon Rising rule tests. Run: uv run pytest -q"""

import random

import pytest

import scripts
from game import Game, GameError
from scripts import bad_moon_rising as bmr

NAMES = ["Asha", "Ben", "Chen", "Dev", "Ema", "Finn", "Gita", "Hari", "Ines"]


def make(chars: list[str], seed: int = 1, believed: dict | None = None) -> Game:
    """Seat len(chars) players, force their characters in seat order, start night 1."""
    g = Game(random.Random(seed), script="bmr")
    for n in NAMES[:len(chars)]:
        g.add_player(n)
    g.deal()
    for pl, c in zip(g.players, chars):
        g.set_character(pl.pid, c, (believed or {}).get(c))
    held = {x for pl in g.players for x in (pl.character, pl.believed)}
    g.bluffs = [c for c in bmr.CHARACTERS if scripts.is_good(bmr.CHARACTERS, c) and c not in held][:3]
    g.start_game()
    return g


def p(g: Game, name: str):
    return next(x for x in g.players if x.name == name)


def step(g: Game, key: str) -> int:
    return next(i for i, s in enumerate(g.steps) if s["key"] == key)


def to_night(g: Game) -> None:
    g.start_day()
    g.end_day()


# --- data and dealing ---

def test_night_orders_match_appendix_a():
    assert bmr.FIRST_NIGHT[2:] == ["lunatic", "sailor", "courtier", "godfather", "devilsadvocate", "pukka",
                                   "grandmother", "chambermaid"]
    assert bmr.OTHER_NIGHTS == ["sailor", "courtier", "innkeeper", "gambler", "devilsadvocate", "lunatic", "exorcist",
                                "zombuul", "pukka", "shabaloth", "po", "assassin", "godfather", "gossip", "professor",
                                "tinker", "moonchild", "grandmother", "chambermaid"]
    assert len(bmr.CHARACTERS) == 25   # 13 Townsfolk, 4 Outsiders, 4 Minions, 4 Demons
    assert [sum(c["type"] == t for c in bmr.CHARACTERS.values()) for t in scripts.TYPES] == [13, 4, 4, 4]


def test_deal_has_one_demon_and_godfather_adds_an_outsider():
    g = Game(random.Random(5), script="bmr")
    for n in NAMES:
        g.add_player(n)
    g.deal()
    chars = [x.character for x in g.players]
    assert sum(bmr.CHARACTERS[c]["type"] == "demon" for c in chars) == 1
    assert bmr.expected_counts(9, ["godfather"]) == (4, 3, 1, 1)


def test_lunatic_believes_a_demon_not_in_play():
    g = make(["po", "assassin", "lunatic", "sailor", "tealady"])
    lun = p(g, "Chen")
    assert bmr.CHARACTERS[lun.believed]["type"] == "demon" and lun.believed != "po"
