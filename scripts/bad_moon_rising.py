"""Bad Moon Rising: character data and rule hooks.

Ability one-liners (summary) are the official sheet's (bad-moon-rising-almanac.pdf); night order, reminder
chips and hints follow the official night sheet. * in the sheet means "not the first night".
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from scripts import DEMON, MINION, OUTSIDER, SETUP_COUNTS, TOWNSFOLK, char_name as _char_name, ids_of, is_good
from scripts.trouble_brewing import living_neighbours

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


# --- night ---

DEMONS = ("zombuul", "pukka", "shabaloth", "po")


def step_applies(game: Game, step: dict) -> bool | None:
    actor, S = game.get(step["pids"][0]), game.script_state
    key = step["key"]
    if key == "zombuul" and game.died_today:
        return False
    if key in DEMONS and actor.character != "lunatic" and game.has(actor, "exorcised"):
        return False
    if key == "godfather" and game.night > 1:
        return actor.alive and any(CHARACTERS[game.get(pid).character]["type"] == OUTSIDER for pid in game.died_today)
    if key == "grandmother" and game.night > 1:
        return False   # learns the grandchild once; the linked death is a rule, not a step
    if key == "gossip":
        return actor.alive and bool(S.get("gossip_true"))
    if key == "moonchild":
        return bool(S.get("moonchild"))
    return None


def suggest(game: Game, key: str, actor: Player | None, targets: list[Player]) -> str | None:
    S = game.script_state
    if key == "grandmother":
        if "grandchild" not in S:
            child = game.rng.choice([q for q in game.players if q is not actor and game.good(q)])
            S["grandchild"] = child.pid
            game.mark(child, "grandchild")
        child = game.get(S["grandchild"])
        return f"Your grandchild is {child.name}, the {cname(child.character)}."
    if key == "godfather" and game.night == 1:
        outs = [cname(q.character) for q in game.players if CHARACTERS[q.character]["type"] == OUTSIDER]
        return f"The Outsiders in play are {' and '.join(outs)}." if outs else "There are no Outsiders in play."
    if key == "chambermaid":
        woke = sum(t.pid in game.woke_tonight for t in targets)
        return f"{woke} of them woke tonight."
    if key == "minion_info":
        demon = ", ".join(q.name for q in game.players if CHARACTERS[q.character]["type"] == DEMON)
        minions = ", ".join(q.name for q in game.players if CHARACTERS[q.character]["type"] == MINION)
        return f"The Demon is {demon}. The Minions are {minions}."
    if key == "demon_info":
        minions = ", ".join(q.name for q in game.players if CHARACTERS[q.character]["type"] == MINION)
        bluffs = ", ".join(cname(b) for b in game.bluffs)
        return f"Your Minions are {minions}. These good characters are not in play (safe bluffs): {bluffs}."
    return None


def _demon(game: Game) -> Player | None:
    return next((p for p in game.players if p.alive and CHARACTERS[p.character]["type"] == DEMON), None)


def _different_from_last_night(game: Game, key: str, target: Player) -> None:
    last = game.script_state.get(f"last_{key}")
    if last == target.pid:
        raise game.error(f"The {cname(key)} must choose someone different from last night")
    game.script_state[f"last_{key}"] = target.pid


def _goon(game: Game, actor: Player, targets: list[Player]) -> None:
    """The first player to choose the Goon tonight is drunk until dusk, and the Goon joins their team."""
    S = game.script_state
    for t in targets:
        if game._working(t, "goon") and S.get("goon_night") != game.night:
            S["goon_night"] = game.night
            game.mark(actor, "drunk", "night")
            S.setdefault("team", {})[t.pid] = "good" if game.good(actor) else "evil"
            game._log(f"{actor.name} chose the Goon: {actor.name} is drunk, the Goon is now {S['team'][t.pid]}")


def apply(game: Game, step: dict, actor: Player, targets: list[Player], options: dict) -> None:
    """State effects of a choose or storyteller step."""
    key, S = step["key"], game.script_state
    _goon(game, actor, targets)
    if actor.character == "lunatic":
        # the Lunatic acts as their believed Demon: nothing happens, the real Demon hears about it at dawn
        S["lunatic_picks"] = [t.name for t in targets]
        demon = _demon(game)
        if demon:
            game._notify(demon.pid, f"The Lunatic ({actor.name}) attacked {' and '.join(t.name for t in targets) or 'nobody'}.")
        game._log(f"Lunatic {actor.name} attacks {', '.join(t.name for t in targets) or 'nobody'}: no effect")
        return
    if key in DEMONS and game.impaired(actor):
        game._log(f"{cname(key)} acts: no effect, the Demon is drunk or poisoned")
        if key == "pukka" and S.get("pukka"):
            game.unmark(game.get(S.pop("pukka")), "poisoned")
        return
    if key == "pukka":
        if S.get("pukka"):
            victim = game.get(S.pop("pukka"))
            game._die(victim, "pukka")       # dies while still poisoned (a poisoned Sailor can die)
            game.unmark(victim, "poisoned")  # then becomes healthy
        game.mark(targets[0], "poisoned")
        S["pukka"] = targets[0].pid
        game._log(f"Pukka poisons {targets[0].name}")
    elif key == "po":
        if S.get("po_nobody") and len(targets) != 3:
            raise game.error("The Po chose nobody last night: choose three players tonight")
        if not S.get("po_nobody") and len(targets) > 1:
            raise game.error("The Po chooses one player, or nobody")
        S["po_nobody"] = not targets
        for t in targets:
            game._die(t, "demon")
    elif key == "shabaloth":
        back = options.get("regurgitate")
        if back and back in S.get("shabaloth_victims", []) and not game.get(back).alive:
            game.revive(back)
            game._log(f"Shabaloth regurgitates {game.get(back).name}")
        S["shabaloth_victims"] = [t.pid for t in targets]
        for t in targets:
            game._die(t, "demon")
    elif key == "zombuul":
        game._die(targets[0], "demon")
    elif key == "exorcist":
        _different_from_last_night(game, key, targets[0])
        if not game.impaired(actor) and CHARACTERS[targets[0].character]["type"] == DEMON:
            game.mark(targets[0], "exorcised", "dawn")
            # the Demon is woken and told now, and their kill prompt goes away
            game._say(targets[0], f"The Exorcist is {actor.name}. You do not act tonight.")
            if targets[0].prompt and targets[0].prompt["kind"] == "choose":
                targets[0].prompt = None
            game._log(f"Exorcist picks the Demon {targets[0].name}: the Demon sleeps tonight")
    elif key == "innkeeper":
        drunk = options.get("drunk") or targets[0].pid
        for t in targets:
            game.mark(t, "protected", "dawn")
        game.mark(game.get(drunk), "drunk", "night")
        game._log(f"Innkeeper protects {' and '.join(t.name for t in targets)}; {game.get(drunk).name} is drunk")
    elif key == "sailor":
        drunk = game.get(options.get("drunk") or targets[0].pid)
        game.mark(drunk, "drunk", "night")
        game._log(f"Sailor picks {targets[0].name}: {drunk.name} is drunk until dusk")
    elif key == "devilsadvocate":
        _different_from_last_night(game, key, targets[0])
        if not game.impaired(actor):
            game.mark(targets[0], "survives execution", "night")
        game._log(f"Devil's Advocate picks {targets[0].name}")
    elif key == "gambler":
        guess = options.get("guess")
        if guess not in CHARACTERS:
            raise game.error("The Gambler also guesses a character")
        if not game.impaired(actor) and guess != targets[0].character:
            game._log(f"Gambler guesses {targets[0].name} is the {cname(guess)}: wrong")
            game._die(actor, "gambler")
        else:
            game._log(f"Gambler guesses {targets[0].name} is the {cname(guess)}: {'right' if guess == targets[0].character else 'no effect, drunk or poisoned'}")
    elif key == "courtier":
        character = options.get("character")
        if character not in CHARACTERS:
            raise game.error("The Courtier names a character")
        actor.used = True
        holder = next((q for q in game.players if q.character == character and q.alive), None)
        if holder and not game.impaired(actor):
            game.mark(holder, "drunk 3")
            game._log(f"Courtier names the {cname(character)}: {holder.name} is drunk for three nights and days")
        else:
            game._log(f"Courtier names the {cname(character)}: {'not in play' if not holder else 'no effect, drunk or poisoned'}")
    elif key == "professor":
        actor.used = True
        t = targets[0]
        if not game.impaired(actor) and not t.alive and CHARACTERS[t.character]["type"] == TOWNSFOLK:
            game.revive(t.pid)
            game._notify(t.pid, "You are alive again.")
            game._log(f"Professor resurrects {t.name}")
        else:
            game._log(f"Professor picks {t.name}: nothing happens")
    elif key == "assassin":
        actor.used = True
        if game.impaired(actor):
            game._log("Assassin acts: no effect, drunk or poisoned")
        else:
            game._die(targets[0], "assassin")
    elif key == "godfather" and targets:   # night 1 is information only
        if not game.impaired(actor):
            game._die(targets[0], "godfather")
    elif key == "gossip":
        dies = options.get("dies")
        if dies and not game.impaired(actor):
            game._die(game.get(dies), "gossip")
        S["gossip_true"] = False
    elif key == "tinker":
        if options.get("dies"):
            game._die(actor, "tinker")
    elif key == "moonchild":
        pick = game.get(S.pop("moonchild", None))
        if game.good(pick) and not game.impaired(actor):
            game._die(pick, "moonchild")
        else:
            game._log(f"Moonchild's pick {pick.name} is evil (or the Moonchild is drunk): no death")


# --- deaths ---

NIGHT_KILLS = {"demon", "pukka", "assassin", "godfather", "gossip", "moonchild", "gambler", "tinker", "grandmother"}


def _tea_lady_shields(game: Game, p: Player) -> bool:
    """True if p sits beside a sober, living Tea Lady whose other living neighbour is also good."""
    for t in game.players:
        if game._working(t, "tealady"):
            neighbours = living_neighbours(game, t)
            if p in neighbours and all(game.is_good(n.character) for n in neighbours):
                return True
    return False


def may_die(game: Game, p: Player, cause: str) -> bool | str:
    """The script's saves: Sailor, Tea Lady, Fool, Innkeeper, Devil's Advocate, Zombuul; the Pacifist asks."""
    if p.character == "zombuul" and not p.used:
        p.used = True
        game.mark(p, "registers dead")
        if game.phase == "night":
            game.night_deaths.append({"pid": p.pid, "cause": cause, "linked": game._dying > 0})
        else:
            game.died_today.append(p.pid)
        game._log(f"{p.name} registers as dead: the Zombuul's first death")
        return False
    if cause == "assassin":
        return True   # "they die, even if for some reason they could not"
    if p.character == "sailor" and not game.impaired(p):
        game._log(f"{p.name} cannot die: a sober Sailor")
        return False
    if _tea_lady_shields(game, p):
        game._log(f"{p.name} cannot die: the Tea Lady's neighbour")
        return False
    if p.character == "fool" and not p.used and not game.impaired(p):
        p.used = True
        game._log(f"{p.name} does not die: the Fool's first death")
        return False
    if cause in NIGHT_KILLS and game.has(p, "protected"):
        game._log(f"{p.name} survives: protected by the Innkeeper")
        return False
    if cause == "executed" and game.has(p, "survives execution"):
        game._log(f"{p.name} survives execution: the Devil's Advocate")
        return False
    if cause == "executed" and game.is_good(p.character) and any(game._working(q, "pacifist") for q in game.players):
        return "ask: the Pacifist is in play; does the executed good player die?"
    return True


def on_death(game: Game, p: Player, cause: str) -> None:
    """The Grandmother dies with her grandchild; the Mastermind keeps the game going after the Demon's execution."""
    S = game.script_state
    if game.has(p, "grandchild") and cause in ("demon", "pukka"):
        gran = next((q for q in game.players if game._working(q, "grandmother")), None)
        if gran:
            game._die(gran, "grandmother")
    if CHARACTERS[p.character]["type"] == DEMON and cause == "executed" and not game._alive_demon() \
            and any(game._working(q, "mastermind") for q in game.players):
        S["extra_day"] = game.day + 1
        game._announce("The game goes on for one more day.")


def on_execution(game: Game, p: Player) -> None:
    """A Minion executed with a working Minstrel in play: everyone else is drunk until dusk tomorrow."""
    if CHARACTERS[p.character]["type"] == MINION and any(game._working(q, "minstrel") for q in game.players):
        for q in game.players:
            if q is not p and q.alive and q.character != "minstrel":
                game.mark(q, "drunk 2")
        game._log("A Minion was executed: the Minstrel makes everyone else drunk until tomorrow's dusk")


def on_nomination(game: Game, nominator: Player, nominee: Player, options: dict) -> None:
    return None


def day_ability(game: Game, p: Player, options: dict) -> None:
    """Gossip: was today's statement true. Moonchild (dead): who they chose."""
    S = game.script_state
    if p.character == "gossip":
        S["gossip_true"] = bool(options.get("true"))
        game._log(f"Gossip's statement was {'true' if S['gossip_true'] else 'false'}")
    elif p.character == "moonchild":
        if p.alive:
            raise game.error("The Moonchild chooses when they learn they died")
        if p.used:
            raise game.error("The Moonchild already chose")
        t = game.get(options.get("target"))
        p.used = True
        S["moonchild"] = t.pid
        game._announce(f"{p.name}, the Moonchild, chooses {t.name}.")
    else:
        raise game.error(f"The {cname(p.character)} has no daytime ability")


def before_dawn(game: Game) -> None:
    game.script_state["gossip_true"] = False


def _count_down_drunk(game: Game) -> None:
    for q in game.players:
        for r in list(q.reminders):
            if r["text"].startswith("drunk ") and r["text"].split()[1].isdigit():
                left = int(r["text"].split()[1]) - 1
                game.unmark(q, r["text"])
                if left > 0:
                    game.mark(q, f"drunk {left}")


def day_end(game: Game) -> None:
    """Dusk: the Mastermind's extra day resolves; timed drunkenness counts down."""
    S = game.script_state
    if S.get("extra_day") == game.day:
        S.pop("extra_day")
        if game.executed_today:
            executed = game.get(game.executed_today)
            loser_good = game.good(executed)
            game._win("evil" if loser_good else "good", f"{executed.name} was executed on the Mastermind's extra day.")
        else:
            game._win("good", "The Demon is dead and nobody was executed on the Mastermind's extra day.")
        return
    _count_down_drunk(game)
