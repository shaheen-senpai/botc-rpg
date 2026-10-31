"""Trouble Brewing: character data and rule hooks (reference implementation of the script surface)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from scripts import DEMON, MINION, OUTSIDER, SETUP_COUNTS, TOWNSFOLK, char_name as _char_name, ids_of, is_good

if TYPE_CHECKING:
    from game import Game, Player

ID, NAME = "tb", "Trouble Brewing"


def _c(name, ctype, summary, ability, uses, hint="", night=None, reminders=(), **extra):
    return {"name": name, "type": ctype, "summary": summary, "ability": ability, "uses": uses,
            "hint": hint, "night": night, "reminders": list(reminders), **extra}


def _choose(count, allow_self, prompt):
    return {"kind": "choose", "count": count, "allow_self": allow_self, "prompt": prompt}


INFO = {"kind": "info"}

CHARACTERS = {
    # --- townsfolk ---
    "washerwoman": _c("Washerwoman", TOWNSFOLK, "Learns that one of two players is a specific Townsfolk.",
                      "On the first night, you are shown a Townsfolk character, then shown two players. "
                      "One of those two players is that character.",
                      "each_night", "One Townsfolk and two players. A Spy may register as Townsfolk.", INFO),
    "librarian": _c("Librarian", TOWNSFOLK, "Learns that one of two players is a specific Outsider.",
                    "On the first night, you are shown an Outsider character, then shown two players. "
                    "One of those two players is that character - or, if there are no Outsiders in this "
                    "game, you are told that instead.",
                    "each_night", "One Outsider and two players. A Spy may register as an Outsider.", INFO),
    "investigator": _c("Investigator", TOWNSFOLK, "Learns that one of two players is a specific Minion.",
                       "On the first night, you are shown a Minion character, then shown two players. "
                       "One of those two players is that character.",
                       "each_night", "One Minion and two players. The Recluse may register as a Minion.", INFO),
    "chef": _c("Chef", TOWNSFOLK, "Learns how many pairs of evil players are sitting next to each other.",
               "On the first night, you learn how many pairs of evil players there are. A pair is two "
               "evil players seated directly beside one another; three evil players in a row counts "
               "as two pairs.",
               "each_night", "Adjacent evil pairs. A Spy may register good, the Recluse evil.", INFO),
    "empath": _c("Empath", TOWNSFOLK, "Learns how many of their living neighbours are evil.",
                 "Every night, you learn how many of your two living neighbours are evil. Your neighbours "
                 "are the nearest living players seated to your left and right.",
                 "each_night", "Evil living neighbours. A Spy may register good, the Recluse evil.", INFO),
    "fortune_teller": _c("Fortune Teller", TOWNSFOLK, "Each night, checks two players for the Demon.",
                         "Every night, choose two players - you learn whether either of them is the Demon. "
                         "One good player always registers as the Demon to you.",
                         "each_night", "Yes if either pick is the Demon or the red herring. The Recluse may register as the Demon.",
                         _choose(2, True, "Choose two players to check for the Demon."), ["red herring"]),
    "undertaker": _c("Undertaker", TOWNSFOLK, "Learns the character of whoever was executed that day.",
                     "Every night except the first, if a player was executed that day, you learn their character.",
                     "each_night", "Only if someone was executed today. Sent automatically at dawn unless you send or skip it first.", INFO),
    "monk": _c("Monk", TOWNSFOLK, "Protects one player from the Demon each night.",
               "Every night except the first, choose a player other than yourself. They cannot be "
               "killed by the Demon that night.",
               "each_night", "Their pick cannot be killed by the Demon tonight.",
               _choose(1, False, "Choose a player to protect from the Demon tonight."), ["protected"]),
    "ravenkeeper": _c("Ravenkeeper", TOWNSFOLK, "If killed at night, learns one player's character.",
                      "If you are killed during the night, you wake immediately to choose a player, and you "
                      "learn their character.",
                      "each_night", "Only if they died tonight. They pick during the second round and learn that character at dawn.",
                      _choose(1, True, "You died tonight. Choose a player to learn their character.")),
    "virgin": _c("Virgin", TOWNSFOLK, "The first Townsfolk to nominate them is executed instantly.",
                 "The first time you are nominated, if your nominator is a Townsfolk, they are executed "
                 "immediately. Your ability is spent on that first nomination, whatever the outcome.",
                 "on_nomination", "Fires on their first nomination.", None, ["no ability"]),
    "slayer": _c("Slayer", TOWNSFOLK, "Once per game, can publicly attempt to kill the Demon.",
                 "Once per game, during the day, publicly choose a player. If they are the Demon, they die. "
                 "Your ability is spent either way.",
                 "day", "Public shot, once per game.", None, ["no ability"]),
    "soldier": _c("Soldier", TOWNSFOLK, "Cannot be killed by the Demon.",
                  "You cannot be killed by the Demon. You can still be executed, and killed by other means.",
                  "passive", "Safe from the Demon while sober."),
    "mayor": _c("Mayor", TOWNSFOLK, "May win the game outright, and may survive the Demon's attack.",
                "If only three players are alive and no execution happens that day, your team wins. If the "
                "Demon tries to kill you at night, the Storyteller may choose for a different player to die instead.",
                "passive", "Three alive and no execution: good wins. A Demon attack on them may land elsewhere."),
    # --- outsiders ---
    "butler": _c("Butler", OUTSIDER, "Can only vote when their chosen Master also votes.",
                 "Every night, choose another player to be your Master for the next day. The next day, you may "
                 "only vote on a nomination if your Master also votes on it. You may still nominate freely.",
                 "each_night", "Their pick is their Master tomorrow.",
                 _choose(1, False, "Choose your Master for tomorrow."), ["master"]),
    "drunk": _c("Drunk", OUTSIDER, "Believes they're a Townsfolk, but their ability doesn't work.",
                "You do not know you are the Drunk. You believe you are a specific Townsfolk, but that "
                "ability does not work, and anything it seems to tell you may be false.",
                "passive", "Thinks they are a Townsfolk; that ability never works.", None, ["drunk"], fake=TOWNSFOLK),
    "recluse": _c("Recluse", OUTSIDER, "May appear evil to other players' abilities.",
                  "You may appear evil, and even as a specific Minion or Demon, to other players' abilities, "
                  "even though you are good.",
                  "passive", "May register as evil, a Minion or the Demon."),
    "saint": _c("Saint", OUTSIDER, "If executed, good instantly loses the game.",
                "If you are executed, your team loses the game immediately. Dying any other way is harmless.",
                "passive", "Executed: evil wins."),
    # --- minions ---
    "poisoner": _c("Poisoner", MINION, "Each night, makes one player's ability malfunction.",
                   "Every night, choose a player. Their ability malfunctions for the rest of that night and the "
                   "following day - anything they learn may be false, and they will not be told.",
                   "each_night", "Their pick is poisoned tonight and tomorrow.",
                   _choose(1, True, "Choose a player to poison."), ["poisoned"]),
    "spy": _c("Spy", MINION, "Sees the full truth of every player, every night.",
              "Every night, you see the Grimoire. You may also appear as good, and as a specific Townsfolk "
              "or Outsider, to other players' abilities.",
              "each_night", "Show them the grimoire.", INFO),
    "scarlet_woman": _c("Scarlet Woman", MINION, "May inherit the Demon's power if it dies.",
                        "If the Demon dies while five or more players are alive, you become the new Demon.",
                        "passive", "Becomes the Imp if the Demon dies with five or more alive."),
    "baron": _c("Baron", MINION, "Adds extra Outsiders to the game.",
                "There are two extra Outsiders in this game, in place of two Townsfolk.",
                "passive", "Two extra Outsiders."),
    # --- demon ---
    "imp": _c("Imp", DEMON, "Kills a player each night - and can pass on the role.",
              "Every night except the first, choose a player to kill. You may choose yourself instead - "
              "if you do, a Minion becomes the new Imp.",
              "each_night", "Picking themselves passes the Imp to a Minion. An attack on the Mayor may land elsewhere. Applying this starts the second round.",
              _choose(1, True, "Choose a player to kill (choosing yourself passes the Imp to a Minion)."), ["dead"]),
}

MEETINGS = {
    "minion_info": {"name": "Minions meet the Demon", "hint": "Wake every Minion together and point out the Demon."},
    "demon_info": {"name": "Demon meets the Minions", "hint": "Wake the Demon, point out their Minions, show the three bluffs."},
}

# meetings only exist in games of this size or larger
EVIL_INFO_MIN_PLAYERS = 7

FIRST_NIGHT = ["minion_info", "demon_info", "poisoner", "washerwoman", "librarian", "investigator",
               "chef", "empath", "fortune_teller", "butler", "spy"]
OTHER_NIGHTS = ["poisoner", "monk", "imp", "ravenkeeper", "empath", "fortune_teller", "undertaker",
                "butler", "spy"]

IMPAIRED_CHARACTERS = {"drunk"}


def cname(cid: str) -> str:
    return _char_name(CHARACTERS, cid)


# --- setup ---

def expected_counts(players: int, chars: list[str]) -> tuple[int, int, int, int]:
    """(townsfolk, outsiders, minions, demons) for a player count, after the Baron's +2/-2 swap."""
    tf, out, mn, dm = SETUP_COUNTS[players]
    return (tf - 2, out + 2, mn, dm) if "baron" in chars else (tf, out, mn, dm)


def deal_extras(characters: dict[str, str], rng: random.Random) -> dict:
    """The Drunk's believed Townsfolk, a random good red herring, three legal Demon bluffs."""
    in_play = set(characters.values())
    drunk_as = rng.choice([t for t in ids_of(CHARACTERS, TOWNSFOLK) if t not in in_play]) if "drunk" in in_play else None
    believed = {pid: (drunk_as if c == "drunk" else c) for pid, c in characters.items()}
    red_herring = rng.choice([pid for pid, c in characters.items() if is_good(CHARACTERS, c)])
    # nobody knowingly claims Drunk, so it is never a useful bluff
    bluff_pool = [c for c in CHARACTERS if is_good(CHARACTERS, c) and c not in in_play | {drunk_as, "drunk"}]
    return {"believed": believed, "red_herring": red_herring, "bluffs": rng.sample(bluff_pool, 3)}


# --- night ---

def step_applies(game: Game, step: dict) -> bool | None:
    if step["key"] == "ravenkeeper":
        return step["pids"][0] in game.night_deaths
    if step["key"] == "undertaker" and not game.executed_today:
        return False
    return None


def apply(game: Game, step: dict, actor: Player, targets: list[Player], options: dict) -> None:
    """Effects of a choose step: Poisoner poisons, Monk protects if working, Butler sets Master, Imp attacks."""
    key = step["key"]
    if key == "poisoner":
        game.poisoned = targets[0].pid
        game._log(f"Poisoner poisons {targets[0].name}")
    elif key == "monk":
        game.protected = None if game.impaired(actor) else targets[0].pid
        game._log(f"Monk protects {targets[0].name}{' (no effect: impaired)' if game.impaired(actor) else ''}")
    elif key == "butler":
        game.master = targets[0].pid
        game._log(f"Butler chooses {targets[0].name} as Master")
    elif key == "imp":
        _demon_attack(game, actor, targets[0], options.get("redirect"), options.get("new_demon"))


def _demon_attack(game: Game, imp: Player, target: Player, redirect: str | None, new_demon: str | None) -> None:
    """Imp kill: poisoned Imp fails; self-target star-passes; Mayor may redirect; may_die handles the rest."""
    if game.impaired(imp):
        game._log(f"Imp attacks {target.name}: no effect, Imp is poisoned")
        return
    if target is imp:
        _star_pass(game, imp, new_demon)
        return
    if redirect:
        if not game._working(target, "mayor"):
            raise game.error("Only an attack on a working Mayor can be redirected")
        game._log(f"Imp attacks the Mayor; Storyteller redirects to {game.get(redirect).name}")
        target = game.get(redirect)
    if not target.alive:
        game._log(f"Imp attacks {target.name}: already dead")
        return
    game._die(target, "demon")


def _star_pass(game: Game, imp: Player, new_demon: str | None) -> None:
    """Imp kills themselves: a living Minion (Scarlet Woman preferred) becomes the Imp."""
    minions = [p for p in game.players if p.alive and game._type_of(p) == MINION]
    heir = game.get(new_demon) if new_demon else (
        next((p for p in minions if p.character == "scarlet_woman"), None)
        or (game.rng.choice(minions) if minions else None))
    if heir and heir not in minions:
        raise game.error("The new Imp must be a living Minion")
    if heir:
        _promote(game, heir, f"{imp.name} killed themselves")
    game._die(imp, "demon")


def _promote(game: Game, heir: Player, why: str) -> None:
    heir.character = heir.believed = "imp"
    game._notify(heir.pid, "You are now the Imp.")
    game._log(f"{heir.name} becomes the Imp ({why})")


# --- information ---

def one_of_two(game: Game, actor: Player, wanted_type: str) -> str:
    """Washerwoman / Librarian / Investigator: a random holder of the type plus a random decoy."""
    hits = [p for p in game.players if p is not actor and CHARACTERS[p.character]["type"] == wanted_type]
    if not hits:
        return f"There are no {wanted_type.title()}s in play."
    hit = game.rng.choice(hits)
    decoy = game.rng.choice([p for p in game.players if p not in (actor, hit)])
    pair = [hit, decoy]
    game.rng.shuffle(pair)
    return f"One of {pair[0].name} and {pair[1].name} is the {cname(hit.character)}."


def evil_pairs(game: Game) -> int:
    """Chef count: adjacent evil seat pairs around the full circle, dead or alive."""
    evil = [not is_good(CHARACTERS, p.character) for p in game.players]
    n = len(evil)
    return sum(evil[i] and evil[(i + 1) % n] for i in range(n))


def living_neighbours(game: Game, actor: Player) -> list[Player]:
    """Nearest living player clockwise and anticlockwise of the actor (one entry if they coincide)."""
    seats = game.players
    i = seats.index(actor)
    found = []
    for direction in (-1, 1):
        for step in range(1, len(seats)):
            p = seats[(i + direction * step) % len(seats)]
            if p.alive and p is not actor:
                if p not in found:
                    found.append(p)
                break
    return found


def grimoire_text(game: Game) -> str:
    """Spy view: every seat with true character, Drunk's belief, and status markers."""
    lines = []
    for seat, p in enumerate(game.players, 1):
        marks = []
        if p.character != p.believed:
            marks.append(f"thinks {cname(p.believed)}")
        if not p.alive:
            marks.append("dead")
        if game.poisoned == p.pid:
            marks.append("poisoned")
        if game.red_herring == p.pid:
            marks.append("Fortune Teller red herring")
        suffix = f" ({', '.join(marks)})" if marks else ""
        lines.append(f"{seat}. {p.name}: {cname(p.character)}{suffix}")
    return "\n".join(lines)


def suggest(game: Game, key: str, actor: Player | None, targets: list[Player]) -> str | None:
    """Truthful info text for a night step, or None for steps that only change state."""
    if key == "washerwoman":
        return one_of_two(game, actor, TOWNSFOLK)
    if key == "librarian":
        return one_of_two(game, actor, OUTSIDER)
    if key == "investigator":
        return one_of_two(game, actor, MINION)
    if key == "chef":
        return f"There are {evil_pairs(game)} pairs of evil players sitting next to each other."
    if key == "empath":
        evil = sum(not is_good(CHARACTERS, p.character) for p in living_neighbours(game, actor))
        return f"{evil} of your living neighbours are evil."
    if key == "fortune_teller":
        hit = any(CHARACTERS[t.character]["type"] == DEMON or t.pid == game.red_herring for t in targets)
        return f"{' and '.join(t.name for t in targets)}: {'YES, one of them is' if hit else 'NO, neither is'} the Demon."
    if key == "undertaker":
        executed = game.get(game.executed_today)
        return f"{executed.name}, executed today, was the {cname(executed.character)}."
    if key == "ravenkeeper":
        return f"{targets[0].name} is the {cname(targets[0].character)}."
    if key == "spy":
        return grimoire_text(game)
    if key == "minion_info":
        demon = ", ".join(p.name for p in game.players if CHARACTERS[p.character]["type"] == DEMON)
        minions = ", ".join(p.name for p in game.players if CHARACTERS[p.character]["type"] == MINION)
        return f"The Demon is {demon}. The Minions are {minions}."
    if key == "demon_info":
        minions = ", ".join(p.name for p in game.players if CHARACTERS[p.character]["type"] == MINION)
        bluffs = ", ".join(cname(b) for b in game.bluffs)
        return f"Your Minions are {minions}. These good characters are not in play (safe bluffs): {bluffs}."
    return None


# --- deaths, days, abilities ---

def may_die(game: Game, p: Player, cause: str) -> bool | str:
    """The Monk's charge and a working Soldier survive the Demon."""
    if cause == "demon":
        if game.protected == p.pid:
            game._log(f"Demon attacks {p.name}: saved by the Monk")
            return False
        if game._working(p, "soldier"):
            game._log(f"Demon attacks {p.name}: the Soldier survives")
            return False
    return True


def on_death(game: Game, p: Player, cause: str) -> None:
    """A dead Poisoner's poison ends; the Scarlet Woman may become the Imp."""
    if p.character == "poisoner":
        game.poisoned = None
    if game._type_of(p) == DEMON and not game._alive_demon() and game.alive_count() + 1 >= 5:
        sw = next((q for q in game.players if game._working(q, "scarlet_woman")), None)
        if sw:
            _promote(game, sw, "the Demon died")


def on_execution(game: Game, p: Player) -> None:
    """Called after the executed player died, so check the character, not _working."""
    if p.character == "saint" and not game.impaired(p):
        game._win("evil", "The Saint was executed.")


def on_nomination(game: Game, nominator: Player, nominee: Player, options: dict) -> None:
    """The Virgin's first nomination executes a Townsfolk nominator (a Spy may register as one)."""
    if nominee.character == "virgin" and not game.virgin_spent:
        game.virgin_spent = True
        townsfolk = game._type_of(nominator) == TOWNSFOLK or (nominator.character == "spy" and options.get("spy_as_townsfolk"))
        if townsfolk and not game.impaired(nominee):
            game._execute(nominator)


def day_ability(game: Game, p: Player, options: dict) -> None:
    """Public Slayer claim: kills the target only if p is a working, unspent Slayer and the target is the Demon."""
    t = game.get(options.get("target"))
    game._announce(f"{p.name} claims Slayer and shoots {t.name}.")
    hit = False
    if p.alive and p.character == "slayer" and not game.slayer_spent:
        game.slayer_spent = True
        is_demon = game._type_of(t) == DEMON or (t.character == "recluse" and options.get("recluse_as_demon"))
        hit = not game.impaired(p) and is_demon and t.alive
    if hit:
        game._announce(f"{t.name} dies.")
        game._die(t, "slayer")
    else:
        game._announce("Nothing happens.")


def before_dawn(game: Game) -> None:
    """Hold the truthful Undertaker info for dawn unless the Storyteller already sent or skipped it."""
    for s in game.steps:
        if s["key"] != "undertaker" or s["done"] or not game.step_applies(s):
            continue
        actor = game.get(s["pids"][0])
        text = suggest(game, "undertaker", actor, [])
        game._notify(actor.pid, text)
        s["suggestion"], s["sent"], s["done"] = text, text, True
        impaired = " (sent true info although they are drunk or poisoned)" if game.impaired(actor) else ""
        game._log(f"Undertaker info sent automatically to {actor.name}: {text}{impaired}")


def day_end(game: Game) -> None:
    """Three alive, no execution, a working Mayor: good wins."""
    if not game.winner and not game.executed_today and game.alive_count() == 3 \
            and any(game._working(p, "mayor") for p in game.players):
        game._win("good", "Three players remain with no execution, and the Mayor lives.")
