"""Bad Moon Rising: character data and rule hooks.

Ability one-liners (summary) are the official sheet's (bad-moon-rising-almanac.pdf); night order, reminder
chips and hints follow the official night sheet. * in the sheet means "not the first night".
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from scripts import DEMON, MINION, OUTSIDER, SETUP_COUNTS, TOWNSFOLK, char_name as _char_name, ids_of, is_good

if TYPE_CHECKING:
    from game import Game, Player

ID, NAME = "bmr", "Bad Moon Rising"


def _c(name, ctype, summary, ability, uses, hint="", night=None, reminders=(), **extra):
    return {"name": name, "type": ctype, "summary": summary, "ability": ability, "uses": uses,
            "hint": hint, "night": night, "reminders": list(reminders), **extra}


def _choose(count, allow_self, prompt, **extra):
    return {"kind": "choose", "count": count, "allow_self": allow_self, "prompt": prompt, **extra}


def _ask(question):
    return {"kind": "storyteller", "question": question}


INFO = {"kind": "info"}

CHARACTERS = {
    # --- townsfolk ---
    "grandmother": _c("Grandmother", TOWNSFOLK,
                      "You start knowing a good player & their character. If the Demon kills them, you die too.",
                      "On the first night you learn one good player and their character: your grandchild. If the "
                      "Demon kills your grandchild, you die as well.",
                      "each_night", "Show the grandchild's character and point to them. If the Demon kills the grandchild, "
                      "the Grandmother dies too.", INFO, ["grandchild"]),
    "sailor": _c("Sailor", TOWNSFOLK,
                 "Each night, choose an alive player: either you or they are drunk until dusk. You can't die.",
                 "Every night, choose a living player. Either you or that player is drunk until dusk; the Storyteller "
                 "decides which. While you are sober you cannot die.",
                 "each_night", "Either the Sailor or their pick is drunk until dusk: choose which. A sober Sailor cannot die.",
                 _choose(1, False, "Choose a living player: one of you will be drunk until dusk."), ["drunk"]),
    "chambermaid": _c("Chambermaid", TOWNSFOLK,
                      "Each night, choose 2 alive players (not yourself): you learn how many woke tonight due to their ability.",
                      "Every night, choose two living players other than yourself. You learn how many of them woke "
                      "tonight because of their ability.",
                      "each_night", "Counted from the steps that woke tonight. Edit if the Chambermaid is drunk or poisoned.",
                      _choose(2, False, "Choose two living players: you learn how many of them woke tonight.")),
    "exorcist": _c("Exorcist", TOWNSFOLK,
                   "Each night*, choose a player (different to last night): the Demon, if chosen, learns who you are then doesn't wake tonight.",
                   "Every night except the first, choose a player, not the same as last night. If you chose the "
                   "Demon, the Demon learns who you are and does not act tonight.",
                   "each_night", "If they pick the Demon, the Demon learns who the Exorcist is and does not act tonight.",
                   _choose(1, False, "Choose a player, different from last night."), ["chosen"]),
    "innkeeper": _c("Innkeeper", TOWNSFOLK,
                    "Each night*, choose 2 players: they can't die tonight, but 1 is drunk until dusk.",
                    "Every night except the first, choose two players. Neither can die tonight, but one of them is "
                    "drunk until dusk; the Storyteller decides which.",
                    "each_night", "Both picks are safe tonight; one of them is drunk until dusk: choose which.",
                    _choose(2, False, "Choose two players to keep safe tonight."), ["protected", "drunk"]),
    "gambler": _c("Gambler", TOWNSFOLK,
                  "Each night*, choose a player & guess their character: if you guess wrong, you die.",
                  "Every night except the first, choose a player and guess their character. If you guess wrong, you die.",
                  "each_night", "They name a character as well. A wrong guess kills the Gambler.",
                  _choose(1, False, "Choose a player and guess their character.", guess=True), ["dead"]),
    "gossip": _c("Gossip", TOWNSFOLK,
                 "Each day, you may make a public statement. Tonight, if it was true, a player dies.",
                 "Each day you may make one public statement. That night, if the statement was true, a player of "
                 "the Storyteller's choice dies.",
                 "day", "If today's statement was true, choose a player to die tonight.",
                 _ask("The Gossip's statement was true: who dies?"), ["dead"]),
    "courtier": _c("Courtier", TOWNSFOLK,
                   "Once per game, at night, choose a character: they are drunk for 3 nights & 3 days.",
                   "Once per game, at night, name a character. If it is in play, that player is drunk for three "
                   "nights and three days.",
                   "once_per_game", "They name a character. If it is in play, that player gets 'drunk 3', counting down at each dawn.",
                   _ask("Which character does the Courtier name tonight?"), ["drunk 3", "drunk 2", "drunk 1", "no ability"]),
    "professor": _c("Professor", TOWNSFOLK,
                    "Once per game, at night*, choose a dead player: if they are a Townsfolk, they are resurrected.",
                    "Once per game, at night except the first, choose a dead player. If they are a Townsfolk, they "
                    "come back to life.",
                    "once_per_game", "Only a dead Townsfolk comes back; the ability is spent either way.",
                    _choose(1, False, "Choose a dead player to bring back."), ["alive", "no ability"]),
    "minstrel": _c("Minstrel", TOWNSFOLK,
                   "When a Minion dies by execution, all other players (except Travellers) are drunk until dusk tomorrow.",
                   "If a Minion is executed, every other player is drunk until dusk the next day.",
                   "passive", "A Minion executed: everyone else is drunk until tomorrow's dusk.", None, ["everyone drunk"]),
    "tealady": _c("Tea Lady", TOWNSFOLK,
                  "If both your alive neighbors are good, they can't die.",
                  "While both of your living neighbours are good, neither of them can die.",
                  "passive", "Both living neighbours good: neither can die.", None, ["can not die"]),
    "pacifist": _c("Pacifist", TOWNSFOLK,
                   "Executed good players might not die.",
                   "When a good player is executed, the Storyteller may decide they do not die.",
                   "passive", "You decide whether an executed good player dies."),
    "fool": _c("Fool", TOWNSFOLK,
               "The 1st time you die, you don't.",
               "The first time you would die, you do not.",
               "passive", "Survives their first death.", None, ["no ability"]),
    # --- outsiders ---
    "goon": _c("Goon", OUTSIDER,
               "Each night, the 1st player to choose you with their ability is drunk until dusk. You become their alignment.",
               "Every night, the first player to choose you with their ability becomes drunk until dusk, and you "
               "join their team.",
               "passive", "The first player to pick the Goon tonight is drunk until dusk; the Goon joins their team.",
               None, ["drunk"]),
    "lunatic": _c("Lunatic", OUTSIDER,
                  "You think you are a Demon, but you are not. The Demon knows who you are & who you choose at night.",
                  "You believe you are a Demon, but you are not. The real Demon knows who you are and whom you choose "
                  "each night.",
                  "each_night", "Show the real Demon who the Lunatic attacked; nobody dies from it.", None,
                  ["attack 1", "attack 2", "attack 3"], fake=DEMON),
    "tinker": _c("Tinker", OUTSIDER,
                 "You might die at any time.",
                 "You might die at any time, for no reason at all.",
                 "passive", "Dies whenever you decide.", _ask("Does the Tinker die tonight?"), ["dead"]),
    "moonchild": _c("Moonchild", OUTSIDER,
                    "When you learn that you died, publicly choose 1 alive player. Tonight, if it was a good player, they die.",
                    "When you learn you have died, publicly choose a living player. That night, if they are good, they die.",
                    "on_death", "When they die, they choose a living player; tonight that player dies if good.",
                    _ask("The Moonchild's chosen player dies tonight if they are good."), ["dead"]),
    # --- minions ---
    "godfather": _c("Godfather", MINION,
                    "You start knowing which Outsiders are in play. If 1 died today, choose a player tonight: they die. [-1 or +1 Outsider]",
                    "On the first night you learn which Outsiders are in play. On any night after an Outsider died "
                    "that day, choose a player: they die.",
                    "each_night", "First night: show the Outsiders. Other nights, only if an Outsider died today: their pick dies.",
                    _choose(1, False, "An Outsider died today: choose a player to kill.", first=INFO), ["died today", "dead"]),
    "devilsadvocate": _c("Devil's Advocate", MINION,
                         "Each night, choose a living player (different to last night): if executed tomorrow, they don't die.",
                         "Every night, choose a living player, not the same as last night. If they are executed "
                         "tomorrow, they do not die.",
                         "each_night", "Their pick survives execution tomorrow.",
                         _choose(1, True, "Choose a living player, different from last night: they survive execution tomorrow."),
                         ["survives execution"]),
    "assassin": _c("Assassin", MINION,
                   "Once per game, at night*, choose a player: they die, even if for some reason they could not.",
                   "Once per game, at night except the first, choose a player. They die, even if something would "
                   "normally stop it.",
                   "once_per_game", "The kill ignores protection. Skip keeps the ability for another night.",
                   _choose(1, False, "Choose a player to kill. This works once per game."), ["dead", "no ability"]),
    "mastermind": _c("Mastermind", MINION,
                     "If the Demon dies by execution (ending the game), play for 1 more day. If a player is then executed, their team loses.",
                     "If the Demon is executed, the game goes on for one more day. If anyone is executed that day, "
                     "their team loses; otherwise good wins.",
                     "passive", "Demon executed: one more day. An execution then loses for the executed player's team."),
    # --- demons ---
    "zombuul": _c("Zombuul", DEMON,
                  "Each night*, if no-one died today, choose a player: they die. The 1st time you die, you live but register as dead.",
                  "Every night except the first, if nobody died today, choose a player: they die. The first time "
                  "you die you survive, but you appear dead to everyone.",
                  "each_night", "Only acts when nobody died today. Their first death is fake: they register as dead but keep acting.",
                  _choose(1, False, "Nobody died today: choose a player to kill."), ["died today", "dead"]),
    "pukka": _c("Pukka", DEMON,
                "Each night, choose a player: they are poisoned. The previously poisoned player dies then becomes healthy.",
                "Every night, choose a player: they are poisoned. The player you poisoned the night before dies and "
                "is then healthy again.",
                "each_night", "Their pick is poisoned; last night's pick dies at dawn and is cured.",
                _choose(1, False, "Choose a player to poison."), ["poisoned", "dead"]),
    "shabaloth": _c("Shabaloth", DEMON,
                    "Each night*, choose 2 players: they die. A dead player you chose last night might be regurgitated.",
                    "Every night except the first, choose two players: they die. One of the players you killed the "
                    "night before might come back to life.",
                    "each_night", "Two kills. One of last night's victims may be regurgitated (revived).",
                    _choose(2, False, "Choose two players to kill."), ["dead", "alive"]),
    "po": _c("Po", DEMON,
             "Each night*, you may choose a player: they die. If your last choice was no-one, choose 3 players tonight.",
             "Every night except the first, you may choose a player: they die. If you chose nobody last night, "
             "you must choose three players tonight.",
             "each_night", "Pick nobody or one player; after a night of nobody, three players.",
             _choose(3, False, "Choose a player to kill, or nobody. After a night of nobody: three players.", variable=True),
             ["dead", "3 attacks"]),
}

MEETINGS = {
    "minion_info": {"name": "Minions meet the Demon", "hint": "Wake every Minion together and point out the Demon."},
    "demon_info": {"name": "Demon meets the Minions", "hint": "Wake the Demon, point out their Minions, show the three bluffs."},
}

EVIL_INFO_MIN_PLAYERS = 7

FIRST_NIGHT = ["minion_info", "demon_info", "lunatic", "sailor", "courtier", "godfather", "devilsadvocate", "pukka",
               "grandmother", "chambermaid"]
OTHER_NIGHTS = ["sailor", "courtier", "innkeeper", "gambler", "devilsadvocate", "lunatic", "exorcist", "zombuul", "pukka",
                "shabaloth", "po", "assassin", "godfather", "gossip", "professor", "tinker", "moonchild", "grandmother",
                "chambermaid"]

IMPAIRED_CHARACTERS: set[str] = set()


def cname(cid: str) -> str:
    return _char_name(CHARACTERS, cid)


# --- setup ---

def expected_counts(players: int, chars: list[str]) -> tuple[int, int, int, int]:
    """(townsfolk, outsiders, minions, demons); the Godfather adds an Outsider (the Storyteller may remove one instead)."""
    tf, out, mn, dm = SETUP_COUNTS[players]
    return (tf - 1, out + 1, mn, dm) if "godfather" in chars else (tf, out, mn, dm)


def deal_extras(characters: dict[str, str], rng: random.Random) -> dict:
    """The Lunatic's believed Demon (one not in play), no red herring, three legal Demon bluffs."""
    in_play = set(characters.values())
    fake_demon = rng.choice([d for d in ids_of(CHARACTERS, DEMON) if d not in in_play]) if "lunatic" in in_play else None
    believed = {pid: (fake_demon if c == "lunatic" else c) for pid, c in characters.items()}
    bluff_pool = [c for c in CHARACTERS if is_good(CHARACTERS, c) and c not in in_play]
    return {"believed": believed, "red_herring": None, "bluffs": rng.sample(bluff_pool, 3)}


# --- hooks (rules fill in over Tasks 10-13) ---

def step_applies(game: Game, step: dict) -> bool | None:
    return None


def apply(game: Game, step: dict, actor: Player, targets: list[Player], options: dict) -> None:
    return None


def suggest(game: Game, key: str, actor: Player | None, targets: list[Player]) -> str | None:
    return None


def may_die(game: Game, p: Player, cause: str) -> bool | str:
    return True


def on_death(game: Game, p: Player, cause: str) -> None:
    return None


def on_execution(game: Game, p: Player) -> None:
    return None


def on_nomination(game: Game, nominator: Player, nominee: Player, options: dict) -> None:
    return None


def day_ability(game: Game, p: Player, options: dict) -> None:
    raise game.error("Nothing to do")


def before_dawn(game: Game) -> None:
    return None


def day_end(game: Game) -> None:
    return None
