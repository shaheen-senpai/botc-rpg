"""Random, rules-valid role dealing for any script."""

import random
from types import ModuleType

from scripts import DEMON, MINION, OUTSIDER, SETUP_COUNTS, TOWNSFOLK, ids_of


def pick_characters(script: ModuleType, players: int, rng: random.Random) -> list[str]:
    """Choose which characters are in play for a player count.

    Algorithm: draw the Minions first, let the script adjust the counts for them (Baron, Godfather),
    then draw that many Townsfolk and Outsiders and the Demon(s) without replacement.

    Args:
        script (ModuleType): the script module.
        players (int): 5-15.
        rng (random.Random): randomness source.

    Returns:
        list[str]: character ids, one per player, unshuffled.
    """
    if players not in SETUP_COUNTS:
        raise ValueError(f"{script.NAME} supports 5-15 players, got {players}")
    chars = script.CHARACTERS
    minions = rng.sample(ids_of(chars, MINION), SETUP_COUNTS[players][2])
    tf, out, _, dm = script.expected_counts(players, minions)
    return (rng.sample(ids_of(chars, TOWNSFOLK), tf) + rng.sample(ids_of(chars, OUTSIDER), out)
            + minions + rng.sample(ids_of(chars, DEMON), dm))


def deal(script: ModuleType, pids: list[str], rng: random.Random) -> dict:
    """Deal characters to players and make the script's hidden setup choices.

    Returns:
        dict with keys characters (pid -> true character id) plus the script's deal_extras:
        believed (pid -> character the player is told), red_herring (pid | None), bluffs (3 ids).
    """
    chars = pick_characters(script, len(pids), rng)
    rng.shuffle(chars)
    characters = dict(zip(pids, chars))
    return {"characters": characters, **script.deal_extras(characters, rng)}


if __name__ == "__main__":
    from scripts import SCRIPTS

    tb = SCRIPTS["tb"]
    result = deal(tb, [f"p{i}" for i in range(1, 10)], random.Random())
    for pid, c in result["characters"].items():
        shown = result["believed"][pid]
        note = f" (thinks {tb.CHARACTERS[shown]['name']})" if shown != c else ""
        print(f"{pid}: {tb.CHARACTERS[c]['name']}{note}")
    print("red herring:", result["red_herring"])
    print("bluffs:", [tb.CHARACTERS[b]["name"] for b in result["bluffs"]])
