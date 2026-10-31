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
    assert "Exorcist" in p(g, "Asha").thread[-1]["text"]   # told at once, not at dawn


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


# --- the rest of the script ---

def execute(g: Game, nominator: str, nominee: str) -> None:
    g.nominate(p(g, nominator).pid, p(g, nominee).pid)
    g.record_votes(len(g.nominations) - 1, [x.pid for x in g.players if g._publicly_alive(x)][:4])
    g.end_day()


def test_gambler_wrong_guess_dies():
    g = make(["po", "assassin", "gambler", "sailor", "gossip", "tinker", "fool"])
    to_night(g)
    g.resolve(step(g, "gambler"), [p(g, "Dev").pid], guess="sailor")
    assert p(g, "Chen").alive
    to_night(g)
    g.resolve(step(g, "gambler"), [p(g, "Ema").pid], guess="fool")
    assert not p(g, "Chen").alive


def test_courtier_drunk_counts_down():
    g = make(["po", "assassin", "courtier", "sailor", "gossip", "tinker", "fool"])
    g.resolve(step(g, "courtier"), [], character="sailor")
    assert g.has(p(g, "Dev"), "drunk 3") and p(g, "Chen").used
    to_night(g)
    assert g.has(p(g, "Dev"), "drunk 2") and g.impaired(p(g, "Dev"))
    to_night(g)
    assert g.has(p(g, "Dev"), "drunk 1")
    to_night(g)
    assert not g.impaired(p(g, "Dev"))
    assert g.step_applies(g.steps[step(g, "courtier")]) is False   # once per game


def test_professor_revives_townsfolk_once():
    g = make(["po", "assassin", "professor", "sailor", "gossip", "tinker", "fool"])
    to_night(g)
    g.kill(p(g, "Ema").pid)
    g.resolve(step(g, "professor"), [p(g, "Ema").pid])
    assert p(g, "Ema").alive and p(g, "Chen").used
    to_night(g)
    assert g.step_applies(g.steps[step(g, "professor")]) is False


def test_assassin_ignores_protection_and_is_once():
    g = make(["po", "assassin", "innkeeper", "sailor", "gossip", "tinker", "fool"])
    to_night(g)
    g.resolve(step(g, "innkeeper"), [p(g, "Ema").pid, p(g, "Finn").pid], drunk=p(g, "Finn").pid)
    g.resolve(step(g, "assassin"), [p(g, "Ema").pid])
    assert not p(g, "Ema").alive and p(g, "Ben").used
    to_night(g)
    assert g.step_applies(g.steps[step(g, "assassin")]) is False


def test_godfather_kills_only_after_outsider_death():
    g = make(["po", "godfather", "sailor", "gossip", "tinker", "goon", "fool"])
    g.resolve(step(g, "godfather"), [])
    assert "Tinker" in g.steps[step(g, "godfather")]["suggestion"] and "Goon" in g.steps[step(g, "godfather")]["suggestion"]
    to_night(g)
    assert g.step_applies(g.steps[step(g, "godfather")]) is False
    g.start_day()
    g.kill(p(g, "Ema").pid)   # the Tinker dies by day
    g.end_day()
    assert g.step_applies(g.steps[step(g, "godfather")]) is True
    g.resolve(step(g, "godfather"), [p(g, "Dev").pid])
    assert not p(g, "Dev").alive


def test_goon_drunks_first_chooser_and_changes_team():
    g = make(["po", "assassin", "sailor", "goon", "gossip", "tinker", "fool"])
    to_night(g)
    g.resolve(step(g, "po"), [p(g, "Dev").pid])
    assert g.has(p(g, "Asha"), "drunk") and p(g, "Dev").alive and not g.good(p(g, "Dev"))


def test_grandmother_dies_with_grandchild():
    g = make(["po", "assassin", "grandmother", "gossip", "gambler", "tinker", "tealady"])
    g.resolve(step(g, "grandmother"), [])
    child = g.get(g.script_state["grandchild"])
    assert child.name in g.steps[step(g, "grandmother")]["suggestion"] and g.has(child, "grandchild")
    to_night(g)
    g.resolve(step(g, "po"), [child.pid])
    assert not child.alive and not p(g, "Chen").alive


def test_minstrel_drunks_everyone_when_minion_executed():
    g = make(["po", "assassin", "minstrel", "sailor", "gossip", "tinker", "fool"])
    g.start_day()
    execute(g, "Chen", "Ben")
    assert not p(g, "Ben").alive
    assert all(g.impaired(x) for x in g.players if x.name not in ("Chen", "Ben"))
    g.start_day()
    assert g.impaired(p(g, "Dev"))
    g.end_day()
    assert not g.impaired(p(g, "Dev"))


def test_mastermind_gives_one_more_day():
    g = make(["po", "mastermind", "sailor", "gossip", "gambler", "tinker", "fool"])
    g.start_day()
    execute(g, "Chen", "Asha")
    assert not p(g, "Asha").alive and g.winner is None and g.phase == "night"
    g.start_day()
    execute(g, "Chen", "Dev")   # a good player executed on the extra day: good loses
    assert g.winner == "evil"


def test_mastermind_day_without_execution_is_a_good_win():
    g = make(["po", "mastermind", "sailor", "gossip", "gambler", "tinker", "fool"])
    g.start_day()
    execute(g, "Chen", "Asha")
    g.start_day()
    g.end_day()
    assert g.winner == "good"


def test_gossip_true_statement_kills_at_night():
    g = make(["po", "assassin", "gossip", "sailor", "gambler", "tinker", "fool"])
    to_night(g)
    assert g.step_applies(g.steps[step(g, "gossip")]) is False
    g.start_day()
    g.day_ability(p(g, "Chen").pid, {"true": True})
    g.end_day()
    assert g.step_applies(g.steps[step(g, "gossip")]) is True
    g.resolve(step(g, "gossip"), [], dies=p(g, "Ema").pid)
    assert not p(g, "Ema").alive


def test_moonchild_pick_dies_if_good():
    g = make(["po", "assassin", "moonchild", "sailor", "gambler", "tinker", "fool"])
    g.start_day()
    g.kill(p(g, "Chen").pid)
    g.day_ability(p(g, "Chen").pid, {"target": p(g, "Ema").pid})
    g.end_day()
    assert g.step_applies(g.steps[step(g, "moonchild")]) is True
    g.resolve(step(g, "moonchild"), [])
    assert not p(g, "Ema").alive


def test_chambermaid_counts_who_woke():
    g = make(["po", "assassin", "chambermaid", "sailor", "gossip", "tinker", "fool"])
    to_night(g)
    g.resolve(step(g, "sailor"), [p(g, "Ema").pid])
    g.resolve(step(g, "po"), [p(g, "Finn").pid])
    g.resolve(step(g, "chambermaid"), [p(g, "Dev").pid, p(g, "Asha").pid])
    assert g.steps[step(g, "chambermaid")]["suggestion"] == "2 of them woke tonight."
    g.resolve(step(g, "chambermaid"), [p(g, "Dev").pid, p(g, "Ema").pid])
    assert g.steps[step(g, "chambermaid")]["suggestion"] == "1 of them woke tonight."


# --- dawn ---

def test_dawn_announces_every_death():
    g = make(["po", "assassin", "sailor", "gossip", "gambler", "tinker", "fool"])
    to_night(g)
    g.resolve(step(g, "po"), [])
    to_night(g)
    g.resolve(step(g, "po"), [p(g, "Dev").pid, p(g, "Ema").pid, p(g, "Finn").pid])
    v = g.storyteller_view()["dawn"]
    assert [d["cause"] for d in v["deaths"]] == ["demon", "demon", "demon"] and v["held"] == 0 and v["pending"] == []
    g.start_day()
    assert g.announcements[0] == "Dawn. Dev, Ema and Finn died in the night."


def test_linked_death_is_marked_in_the_dawn_card():
    g = make(["po", "assassin", "grandmother", "gossip", "gambler", "tinker", "tealady"])
    g.resolve(step(g, "grandmother"), [])
    child = g.get(g.script_state["grandchild"])
    to_night(g)
    g.resolve(step(g, "po"), [child.pid])
    deaths = g.storyteller_view()["dawn"]["deaths"]
    assert [(d["pid"], d["linked"]) for d in deaths] == [(child.pid, False), (p(g, "Chen").pid, True)]


# --- review fixes ---

def test_po_phone_pick_accepts_one_or_nobody():
    g = make(["po", "assassin", "sailor", "gossip", "gambler", "tinker", "fool"])
    to_night(g)
    g.choose(p(g, "Asha").token, [p(g, "Dev").pid])
    assert g.steps[step(g, "po")]["answer"] == [p(g, "Dev").pid]
    g.ask(step(g, "po"))
    g.choose(p(g, "Asha").token, [])
    assert g.steps[step(g, "po")]["answer"] == []


def test_zombuul_night_death_is_hidden_until_dawn_and_announced():
    g = make(["zombuul", "assassin", "sailor", "gossip", "gambler"])
    g.kill(p(g, "Asha").pid)
    assert g.public_view()["seats"][0]["alive"] is True
    g.start_day()
    assert g.public_view()["seats"][0]["alive"] is False
    assert g.announcements[0] == "Dawn. Asha died in the night."


def test_exorcised_demon_is_told_at_once_and_cannot_act():
    g = make(["po", "assassin", "exorcist", "fool", "gossip", "tinker", "gambler"])
    to_night(g)
    g.resolve(step(g, "exorcist"), [p(g, "Asha").pid])
    assert p(g, "Asha").prompt is None and "Exorcist" in p(g, "Asha").thread[-1]["text"]
    with pytest.raises(GameError):
        g.resolve(step(g, "po"), [p(g, "Dev").pid])


def test_pukka_on_night_one_does_not_buzz_twice():
    g = make(["pukka", "assassin", "sailor", "fool", "gossip", "tinker", "gambler"])
    buzz = g.buzz
    g.resolve(step(g, "pukka"), [p(g, "Chen").pid])
    assert g.buzz == buzz and not g.second_round_done


def test_assassin_kills_the_sailor():
    g = make(["po", "assassin", "sailor", "gossip", "gambler", "tinker", "fool"])
    to_night(g)
    g.resolve(step(g, "assassin"), [p(g, "Chen").pid])
    assert not p(g, "Chen").alive


def test_pukka_killing_the_grandchild_kills_the_grandmother():
    g = make(["pukka", "assassin", "grandmother", "gossip", "gambler", "tinker", "tealady"])
    g.resolve(step(g, "grandmother"), [])
    child = g.get(g.script_state["grandchild"])
    g.resolve(step(g, "pukka"), [child.pid])
    to_night(g)
    other = next(x for x in g.players if x.alive and x not in (child, p(g, "Asha"), p(g, "Chen")))
    g.resolve(step(g, "pukka"), [other.pid])
    assert not child.alive and not p(g, "Chen").alive


def test_godfather_kill_step_is_done_after_resolving():
    g = make(["po", "godfather", "sailor", "gossip", "tinker", "goon", "fool"])
    to_night(g)
    g.start_day()
    g.kill(p(g, "Ema").pid)
    g.end_day()
    g.resolve(step(g, "godfather"), [p(g, "Dev").pid])
    assert g.steps[step(g, "godfather")]["done"] is True


def test_grandmother_only_learns_on_night_one():
    g = make(["po", "assassin", "grandmother", "gossip", "gambler", "tinker", "tealady"])
    to_night(g)
    assert g.step_applies(g.steps[step(g, "grandmother")]) is False


def test_chambermaid_ignores_storyteller_steps():
    g = make(["po", "assassin", "chambermaid", "sailor", "gossip", "tinker", "fool"])
    to_night(g)
    g.resolve(step(g, "tinker"), [], dies=False)
    g.resolve(step(g, "chambermaid"), [p(g, "Finn").pid, p(g, "Dev").pid])   # the Tinker did not wake; the Sailor has not acted
    assert g.steps[step(g, "chambermaid")]["suggestion"] == "0 of them woke tonight."
