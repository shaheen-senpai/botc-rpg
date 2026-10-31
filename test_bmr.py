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


# --- deaths and protection ---

def test_sailor_cannot_die_and_fool_survives_once():
    g = make(["po", "assassin", "sailor", "fool", "gossip", "tinker", "tealady"])   # Tea Lady sits by the Po: no shield
    to_night(g)
    g.resolve(step(g, "po"), [p(g, "Chen").pid])
    assert p(g, "Chen").alive
    g.kill(p(g, "Dev").pid)
    assert p(g, "Dev").alive and p(g, "Dev").used
    g.kill(p(g, "Dev").pid)
    assert not p(g, "Dev").alive


def test_tea_lady_protects_good_neighbours():
    g = make(["po", "tealady", "gossip", "gambler", "sailor"])   # Ben's neighbours: Asha (evil), Chen (good)
    to_night(g)
    g.resolve(step(g, "po"), [p(g, "Chen").pid])
    assert p(g, "Chen").alive is False   # one neighbour is evil: no protection
    g2 = make(["gambler", "tealady", "gossip", "po", "sailor"])  # Ben's neighbours: Asha and Chen, both good
    to_night(g2)
    g2.resolve(step(g2, "po"), [p(g2, "Chen").pid])
    assert p(g2, "Chen").alive


def test_pacifist_execution_asks_then_confirm():
    g = make(["po", "assassin", "pacifist", "sailor", "gossip"])
    g.start_day()
    g.nominate(p(g, "Asha").pid, p(g, "Ema").pid)
    g.record_votes(0, [x.pid for x in g.players[:3]])
    g.end_day()
    assert g.phase == "day" and g.pending_deaths[0]["pid"] == p(g, "Ema").pid
    g.confirm_death(0, False)
    assert p(g, "Ema").alive
    g.end_day()
    assert g.phase == "night"


def test_zombuul_registers_dead_then_acts_after_a_quiet_day():
    g = make(["zombuul", "assassin", "sailor", "gossip", "gambler"])
    g.start_day()
    g.nominate(p(g, "Ben").pid, p(g, "Asha").pid)
    g.record_votes(0, [x.pid for x in g.players[:3]])
    g.end_day()                                   # Asha "dies" once: night 2
    assert p(g, "Asha").alive and g.has(p(g, "Asha"), "registers dead")
    assert g.public_view()["seats"][0]["alive"] is False and g.winner is None
    assert g.step_applies(g.steps[step(g, "zombuul")]) is False   # someone died today: sleeps
    g.start_day()
    g.end_day()                                   # nobody dies on day 2: night 3
    assert g.step_applies(g.steps[step(g, "zombuul")]) is True


# --- demons, Exorcist, Lunatic ---

def test_pukka_poisons_then_kills_next_night():
    g = make(["pukka", "assassin", "sailor", "fool", "gossip", "tinker", "gambler"])
    g.resolve(step(g, "pukka"), [p(g, "Chen").pid])
    assert g.impaired(p(g, "Chen"))
    to_night(g)
    g.resolve(step(g, "pukka"), [p(g, "Dev").pid])
    assert not p(g, "Chen").alive and not g.impaired(p(g, "Chen")) and g.impaired(p(g, "Dev"))


def test_po_three_kills_respect_protection():
    g = make(["po", "assassin", "innkeeper", "fool", "gossip", "tinker", "gambler"])
    to_night(g)
    g.resolve(step(g, "po"), [])           # nobody
    to_night(g)
    g.resolve(step(g, "innkeeper"), [p(g, "Ema").pid, p(g, "Finn").pid], drunk=p(g, "Finn").pid)
    with pytest.raises(GameError):
        g.resolve(step(g, "po"), [p(g, "Ema").pid])   # must pick 3
    g.resolve(step(g, "po"), [p(g, "Ema").pid, p(g, "Finn").pid, p(g, "Gita").pid])
    assert p(g, "Ema").alive and p(g, "Finn").alive and not p(g, "Gita").alive
    g.start_day()
    assert "Gita died" in g.announcements[0]


def test_exorcist_blocks_the_demon():
    g = make(["po", "assassin", "exorcist", "fool", "gossip", "tinker", "gambler"])
    to_night(g)
    g.resolve(step(g, "exorcist"), [p(g, "Asha").pid])
    assert g.step_applies(g.steps[step(g, "po")]) is False
    g.start_day()
    assert "Exorcist" in p(g, "Asha").thread[-1]["text"]


def test_exorcist_cannot_repeat_last_nights_pick():
    g = make(["po", "assassin", "exorcist", "fool", "gossip", "tinker", "gambler"])
    to_night(g)
    g.resolve(step(g, "exorcist"), [p(g, "Dev").pid])
    to_night(g)
    with pytest.raises(GameError, match="different"):
        g.resolve(step(g, "exorcist"), [p(g, "Dev").pid])


def test_shabaloth_regurgitates():
    g = make(["shabaloth", "assassin", "sailor", "gossip", "tinker", "gambler", "fool"])
    to_night(g)
    g.resolve(step(g, "shabaloth"), [p(g, "Dev").pid, p(g, "Ema").pid])
    to_night(g)
    g.resolve(step(g, "shabaloth"), [p(g, "Finn").pid, p(g, "Gita").pid], regurgitate=p(g, "Dev").pid)
    assert p(g, "Dev").alive


def test_lunatic_attacks_are_shown_to_the_demon_and_kill_nobody():
    g = make(["po", "assassin", "lunatic", "fool", "gossip", "tinker", "gambler"], believed={"lunatic": "shabaloth"})
    to_night(g)
    g.resolve(step(g, "shabaloth"), [p(g, "Dev").pid, p(g, "Ema").pid])
    assert p(g, "Dev").alive and p(g, "Ema").alive
    g.resolve(step(g, "po"), [])
    g.start_day()
    assert "Lunatic" in p(g, "Asha").thread[-1]["text"] and "Dev" in p(g, "Asha").thread[-1]["text"]
