"""Script registry. A script is a module exposing character data and rule hooks.

Module surface (see trouble_brewing.py for the reference implementation):
    ID, NAME                      script id and display name
    CHARACTERS                    dict[id, {name, type, summary, ability, uses, reminders, hint, night, fake?}]
    MEETINGS                      dict[key, {name, hint}] for group steps such as minion_info / demon_info
    FIRST_NIGHT, OTHER_NIGHTS     ordered step keys (character ids or meeting keys)
    EVIL_INFO_MIN_PLAYERS         meetings only happen at this table size or larger
    IMPAIRED_CHARACTERS           characters whose ability never works (the Drunk)
    expected_counts(players, chars) -> (townsfolk, outsiders, minions, demons)
    deal_extras(characters, rng) -> {believed, red_herring, bluffs}
    step_applies(game, step) -> bool | None      None means the default: every pid in the step is alive
    apply(game, step, actor, targets, options)   state effects of a choose step
    suggest(game, key, actor, targets) -> str | None
    may_die(game, p, cause) -> bool | str        True, False, or "ask: <reason>"
    on_death(game, p, cause), on_execution(game, p), on_nomination(game, nominator, nominee, options)
    day_ability(game, p, options), before_dawn(game), day_end(game)
"""

TOWNSFOLK, OUTSIDER, MINION, DEMON = "townsfolk", "outsider", "minion", "demon"
TYPES = (TOWNSFOLK, OUTSIDER, MINION, DEMON)

# player count -> (townsfolk, outsiders, minions, demons) before any character's adjustment
SETUP_COUNTS = {
    5: (3, 0, 1, 1), 6: (3, 1, 1, 1), 7: (5, 0, 1, 1), 8: (5, 1, 1, 1), 9: (5, 2, 1, 1),
    10: (7, 0, 2, 1), 11: (7, 1, 2, 1), 12: (7, 2, 2, 1),
    13: (9, 0, 3, 1), 14: (9, 1, 3, 1), 15: (9, 2, 3, 1),
}


def is_good(chars: dict, cid: str) -> bool:
    """True for Townsfolk and Outsiders."""
    return chars[cid]["type"] in (TOWNSFOLK, OUTSIDER)


def ids_of(chars: dict, char_type: str) -> list[str]:
    """Character ids of one type, in almanac order."""
    return [cid for cid, c in chars.items() if c["type"] == char_type]


def char_name(chars: dict, cid: str) -> str:
    """Display name of a character id."""
    return chars[cid]["name"]


from scripts import trouble_brewing  # noqa: E402  (needs the constants above)

SCRIPTS = {"tb": trouble_brewing}
