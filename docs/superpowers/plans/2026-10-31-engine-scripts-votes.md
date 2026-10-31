# Engine, scripts and votes — implementation plan (1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the game engine script-driven (Trouble Brewing and Bad Moon Rising), and add everything the new screens need from the server: reminders, ability state, optional night check, per-player threads, hands and the server-timed vote clock.

**Architecture:** `game.py` keeps the generic machinery (seats, phases, steps, deaths, votes, undo, views) and calls a per-script module for everything character-specific through a fixed hook surface. Trouble Brewing's rules move out of `game.py` into `scripts/trouble_brewing.py` behind those hooks with every existing test still passing; Bad Moon Rising is then a second module. The HTTP API grows new actions; the two existing pages keep working on Trouble Brewing throughout because the old view keys stay (derived from the new state) until plans 2 and 3 replace the pages.

**Tech Stack:** Python 3.11, FastAPI, pytest (`uv run --with pytest pytest -q`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-31-ui-revamp-design.md` (§5, §6.6, §7, §8.4, §9, §10, Appendix A). Plans 2 and 3 cover the grimoire page and the player page.

## Global Constraints

- No new dependencies; the server stays `uv run server.py` with `fastapi`, `uvicorn`, `qrcode`.
- Every Storyteller action goes through `POST /api/st/<action>` and is undoable via the existing snapshot mechanism unless listed in `NO_UNDO`.
- `storyteller_view()` and `player_view()` keep every key they have today (values may be derived); new keys are added, none removed, until plans 2–3 land.
- Rule behaviour listed in `test_game.py` is preserved: all existing tests pass unchanged except for import lines.
- Time never comes from `time.time()` inside `Game`; it comes from the injected `clock` callable.
- Work on a branch `revamp/engine` off `main`; one commit per task.

## Review Focus

1. A phone's hand toggle that arrives after its seat locked must be refused with "The clock has passed you", not silently applied (Task 7 test `test_toggle_after_lock_refused`).
2. Undo of `start_clock` while the clock runs must leave no clock in any view and no ghost vote spent (Task 7 test `test_undo_start_clock_clears_clock`).
3. Turning the night check off mid-night must release a dawn that was blocked, and exempt players must still receive real choice prompts (Task 4 tests `test_night_check_off_unblocks_dawn`, `test_exempt_still_gets_choice_prompt`).
4. Several deaths in one night (Po's three) must each pass `may_die` and all be announced; a protected pick must not count as a death (Task 11 test `test_po_three_kills_respect_protection`).
5. A Butler whose Master's hand is down when the Butler locks must be locked as no even though their hand was up (Task 7 test `test_butler_locks_no_when_master_down`).

---

### Task 1: Script registry and Trouble Brewing as a script module

**Files:**
- Create: `scripts/__init__.py`, `scripts/trouble_brewing.py`
- Delete: `roles.py`, `info.py`
- Modify: `game.py`, `dealing.py`, `server.py`, `test_game.py` (imports only)
- Test: `test_game.py`, `test_scripts.py`

**Interfaces:**
- Produces `scripts/__init__.py`:
  - `TOWNSFOLK, OUTSIDER, MINION, DEMON = "townsfolk", "outsider", "minion", "demon"`
  - `SETUP_COUNTS: dict[int, tuple[int, int, int, int]]` (moved from roles.py)
  - `SCRIPTS: dict[str, ModuleType]` = `{"tb": trouble_brewing}` (Task 9 adds `"bmr"`)
  - `is_good(chars: dict, cid: str) -> bool`, `ids_of(chars: dict, t: str) -> list[str]`, `char_name(chars: dict, cid: str) -> str`
- Produces the script module surface, implemented by `scripts/trouble_brewing.py` and later `scripts/bad_moon_rising.py`:
  - `ID: str`, `NAME: str`, `CHARACTERS: dict[str, dict]`, `FIRST_NIGHT: list[str]`, `OTHER_NIGHTS: list[str]`, `EVIL_INFO_MIN_PLAYERS: int`
  - Each `CHARACTERS[cid]` has `name, type, summary, ability` (as today) plus `uses` (one of `"each_night" | "once_per_game" | "passive" | "day" | "on_death" | "on_nomination" | "none"`), `reminders: list[str]`, `hint: str` (today's `HINTS` text from `storyteller.html`, moved here), and `night`: `None`, `{"kind": "info"}`, `{"kind": "choose", "count": int, "allow_self": bool, "prompt": str}`, `{"kind": "storyteller", "question": str}` or `{"kind": "meeting"}`. Steps `minion_info` / `demon_info` are entries in `FIRST_NIGHT`, not characters.
  - `expected_counts(players: int, chars: list[str]) -> tuple[int, int, int, int]` (Baron +2/−2)
  - `deal_extras(characters: dict[str, str], rng: random.Random) -> dict` → `{"believed": {pid: cid}, "red_herring": pid | None, "bluffs": list[str]}`
  - `step_applies(game, step: dict) -> bool | None` (`None` = default rule: every pid in the step is alive)
  - `apply(game, step: dict, actor, targets: list, options: dict) -> None` (state effects of a choose step; TB: poisoner, monk, butler, imp with `options["redirect"]`, `options["new_demon"]`)
  - `suggest(game, key: str, actor, targets: list) -> str | None` (today's `info.suggest`)
  - `may_die(game, p, cause: str) -> bool | str` (`True`, `False`, or `"ask: <reason>"`; TB: Monk-protected and Soldier return `False` for `cause == "demon"`)
  - `on_death(game, p, cause: str) -> None` (TB: Poisoner clears poison, Scarlet Woman promotion)
  - `on_execution(game, p) -> None` (TB: Saint loses)
  - `on_nomination(game, nominator, nominee, options: dict) -> None` (TB: Virgin, `options["spy_as_townsfolk"]`)
  - `day_ability(game, p, options: dict) -> None` (TB: Slayer with `options["target"]`, `options["recluse_as_demon"]`)
  - `before_dawn(game) -> None` (TB: auto Undertaker)
  - `day_end(game) -> None` (TB: Mayor win at three alive)
- Produces on `Game`: `Game(rng=None, script="tb", clock=time.time)`; `self.script` (the module); `set_script(script_id: str) -> None` (lobby only, refuses unknown ids); `self.pending_deaths: list[dict]` (filled from Task 10 on; empty here); `_die(p, cause)` now runs `script.may_die` → `script.on_death`; `resolve(step, choices, **options)` passes `options` to `script.apply`; `slayer_shot(shooter, target, recluse_as_demon)` becomes a thin wrapper over `day_ability(pid, {"target", "recluse_as_demon"})`; `day_ability(pid: str, options: dict) -> None` is a new Storyteller action.
- Produces in views: `public_view()["script"] = {"id", "name"}`; `/api/characters` returns `game.script.CHARACTERS`; `GET /api/scripts` returns `[{"id", "name", "counts": {type: n}}]`.
- Causes passed to `may_die`/`on_death`: `"demon"`, `"executed"`, `"slayer"`, `"storyteller"` (Task 10+ adds `"assassin"`, `"godfather"`, `"gossip"`, `"moonchild"`, `"gambler"`, `"tinker"`, `"grandmother"`, `"pukka"`).

- [ ] **Step 1: Write the registry test**

```python
# test_scripts.py
import scripts
from scripts import trouble_brewing as tb

def test_registry_has_tb():
    assert scripts.SCRIPTS["tb"] is tb
    assert tb.ID == "tb" and tb.NAME == "Trouble Brewing"

def test_every_character_declares_the_schema():
    for cid, c in tb.CHARACTERS.items():
        assert c["uses"] in {"each_night", "once_per_game", "passive", "day", "on_death", "on_nomination", "none"}, cid
        assert isinstance(c["reminders"], list) and isinstance(c["hint"], str), cid
        n = c["night"]
        assert n is None or n["kind"] in {"info", "choose", "storyteller", "meeting"}, cid
        if n and n["kind"] == "choose":
            assert set(n) == {"kind", "count", "allow_self", "prompt"}

def test_night_order_keys_exist():
    for key in tb.FIRST_NIGHT + tb.OTHER_NIGHTS:
        assert key in tb.CHARACTERS or key in ("minion_info", "demon_info")

def test_game_exposes_script_and_refuses_unknown():
    from game import Game, GameError
    g = Game(script="tb")
    assert g.public_view()["script"] == {"id": "tb", "name": "Trouble Brewing"}
    import pytest
    with pytest.raises(GameError):
        g.set_script("nope")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest test_scripts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Create `scripts/__init__.py` and `scripts/trouble_brewing.py`**

Move `CHARACTERS`, `SETUP_COUNTS`, `FIRST_NIGHT`, `OTHER_NIGHTS`, `EVIL_INFO_MIN_PLAYERS` from `roles.py`; fold `NIGHT_CHOICES` into each character's `night` dict; add `uses`, `reminders`, `hint` per character. `uses`: `"each_night"` for every character with a `night` entry (poisoner, monk, imp, ravenkeeper, empath, fortune_teller, undertaker, butler, spy, washerwoman, librarian, investigator, chef — the order lists decide which nights), `"day"` for slayer, `"on_nomination"` for virgin, `"passive"` for soldier, mayor, recluse, saint, drunk, baron, scarlet_woman. The engine treats `day`, `on_nomination` and `once_per_game` as once per game (Task 3). `reminders`: poisoner `["poisoned"]`, monk `["protected"]`, butler `["master"]`, fortune_teller `["red herring"]`, drunk `["drunk"]`, virgin `["no ability"]`, slayer `["no ability"]`, imp `["dead"]`, others `[]`. Move `info.py`'s functions into `trouble_brewing.py` as `suggest` and helpers; move `_demon_attack`, `_star_pass`, `_promote`, Virgin, Saint, Scarlet Woman, Poisoner-clears-poison, Mayor, auto Undertaker, Slayer into the hook functions named in Interfaces. `is_good`/`ids_of`/`char_name` take the characters dict as their first argument.

- [ ] **Step 4: Make `game.py` generic**

`Game.__init__(self, rng=None, script="tb", clock=time.time)`; replace every `CHARACTERS`/`roles` reference with `self.script.CHARACTERS` and `scripts.is_good(...)`; `_build_steps` reads `self.script.FIRST_NIGHT/OTHER_NIGHTS` and each character's `night` dict; `step_applies` asks `self.script.step_applies` first and falls back to all-alive; `resolve(step, choices, **options)` calls `self.script.apply(...)` then `self.script.suggest(...)`; `_die(p, cause)` → `may_die` (a `False` logs "survives", `"ask: ..."` appends `{"pid", "cause", "why"}` to `self.pending_deaths` and returns, `True` kills) then `on_death`, then `_check_win`; `_execute` → `_die(p, "executed")` then `script.on_execution`; `nominate(nominator, nominee, **options)` → `script.on_nomination`; `end_day` → `script.day_end` before `start_night`; `start_day` → `script.before_dawn` before `_flush`. `dealing.deal(script, pids, rng)` uses `script.expected_counts` and `script.deal_extras`. `set_script` is allowed in `lobby` only.

- [ ] **Step 5: Fix imports in `test_game.py` and `server.py`**

`from scripts.trouble_brewing import CHARACTERS` and `from scripts import is_good` (call as `is_good(CHARACTERS, c)`); `server.py` `/api/characters` returns `game.script.CHARACTERS`, adds `GET /api/scripts`, adds `set_script` and `day_ability` to `ST_ACTIONS` with labels `"Choose the {body_script} script"` and `"Use {name}'s ability"`.

- [ ] **Step 6: Run the whole suite**

Run: `uv run --with pytest pytest -q`
Expected: all tests in `test_game.py` and `test_scripts.py` PASS; `roles.py` and `info.py` deleted; `uv run server.py --port 8010` starts and `curl localhost:8010/api/scripts` returns one entry.

- [ ] **Step 7: Commit**

```bash
git checkout -b revamp/engine
git add scripts/ game.py dealing.py server.py test_game.py test_scripts.py
git rm roles.py info.py
git commit -m "refactor: scripts as modules, Trouble Brewing behind rule hooks"
```

---

### Task 2: Reminders replace the single poisoned / protected / master fields

**Files:**
- Modify: `game.py`, `scripts/trouble_brewing.py`, `server.py`
- Test: `test_table.py` (new), `test_game.py`

**Interfaces:**
- Produces on `Player`: `reminders: list[dict]`, each `{"text": str, "until": "night" | "dawn" | None}` (`"night"` clears when the next night starts, `"dawn"` clears at dawn, `None` stays until removed).
- Produces on `Game`: `has(p, text: str) -> bool` (exact text match); `mark(p, text: str, until: str | None = None) -> None` (no duplicates); `unmark(p, text: str) -> None`; `set_reminder(pid: str, text: str, on: bool) -> None` (Storyteller action, `until=None`); `impaired(p) -> bool` is now `any(r["text"].split()[0] in ("poisoned", "drunk") for r in p.reminders)`.
- TB script: the Drunk gets `mark(p, "drunk", None)` at `start_game`; Poisoner's `apply` marks `"poisoned"` with `until="night"`; Monk marks `"protected"` with `until="dawn"`; Butler marks `"master"` with `until="night"`; Fortune Teller's red herring stays `game.red_herring` (setup data, not a chip).
- Views: `storyteller_view()["players"][i]["reminders"] = [text, ...]`; the old keys `poisoned`, `protected`, `master` are derived (first pid carrying that chip, else `None`); `set_poisoned(pid)` stays as a wrapper over `set_reminder`.

- [ ] **Step 1: Write the tests**

```python
# test_table.py
import random
from game import Game, GameError
from test_game import make, p, to_night2, step

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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --with pytest pytest test_table.py -q`
Expected: FAIL with `AttributeError: 'Game' object has no attribute 'mark'`

- [ ] **Step 3: Implement**

Add `reminders` to `Player` (reset in `_reset_round`); `has/mark/unmark/set_reminder` on `Game`; expiry in `start_night` (drop `until == "night"`) and `start_day` (drop `until == "dawn"`); delete `self.poisoned/protected/master` and the `_working` check reads `impaired`; TB `apply`/`may_die` use chips; `grimoire_text` (Spy) lists chip texts; views derive the old keys. `server.py`: add `set_reminder` to `ST_ACTIONS` with label `"Change {name}'s reminders"`.

- [ ] **Step 4: Run the suite**

Run: `uv run --with pytest pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add game.py scripts/trouble_brewing.py server.py test_table.py
git commit -m "feat: reminder chips replace single poison/protect/master fields"
```

---

### Task 3: Ability state on the player

**Files:**
- Modify: `game.py`, `scripts/trouble_brewing.py`
- Test: `test_table.py`, `test_game.py`

**Interfaces:**
- Produces on `Player`: `used: bool = False` (a once-per-game ability has been spent). Replaces `Game.virgin_spent` / `Game.slayer_spent`, which become derived view keys (`any(p.used and p.character == "virgin")`).
- Produces on `Game`: `ability_state(p) -> dict` → `{"uses": str, "used": bool, "label": str}` where `label` is `"Unused"` / `"Used"` for `day`, `on_nomination`, `once_per_game`; `"Acts each night"` for `each_night`; `"Passive"` for `passive`; `""` for `none`.
- Views: `storyteller_view()["players"][i]["ability"] = ability_state(p)`; `player_view()["me"]["ability"] = ability_state(p)` when the game has started.

- [ ] **Step 1: Write the tests**

```python
def test_slayer_use_marks_player_used():
    g = make(["imp", "poisoner", "slayer", "empath", "soldier"])
    g.start_day()
    g.day_ability(p(g, "Chen").pid, {"target": p(g, "Dev").pid, "recluse_as_demon": False})
    assert p(g, "Chen").used and g.ability_state(p(g, "Chen")) == {"uses": "day", "used": True, "label": "Used"}
    assert g.storyteller_view()["slayer_spent"] is True

def test_ability_state_in_views():
    g = make(["imp", "poisoner", "slayer", "empath", "soldier"])
    assert g.storyteller_view()["players"][0]["ability"] == {"uses": "each_night", "used": False, "label": "Acts each night"}
    assert g.player_view(p(g, "Chen").token)["me"]["ability"]["label"] == "Unused"
```

- [ ] **Step 2: Run to verify they fail** — `uv run --with pytest pytest test_table.py -q`, expected `AttributeError ... day_ability` / `used`.

- [ ] **Step 3: Implement** — add the field, `ability_state`, derive `virgin_spent`/`slayer_spent`; TB `on_nomination` and `day_ability` set `p.used`.

- [ ] **Step 4: Run the suite** — `uv run --with pytest pytest -q`, expected PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat: per-player ability state"`.

---

### Task 4: Night check is a setting; stop waiting

**Files:**
- Modify: `game.py`, `server.py`
- Test: `test_table.py`

**Interfaces:**
- Produces on `Game`: `night_check: bool = True`; `waiting_stopped: bool = False` (reset in `start_night`); `set_night_check(on: bool) -> None`; `set_exempt(pid: str, on: bool) -> None`; `stop_waiting() -> None` (night only).
- Produces on `Player`: `exempt: bool = False`.
- Behaviour: `_phone_players()` returns `[]` when `night_check` is off, otherwise phone players who are publicly alive and not exempt; `_hand_out_tap_tasks()` gives tap tasks only to `_phone_players()`; real choice prompts (`ask`) are unaffected by any of this; `_require_phones_done` is a no-op when `night_check` is off or `waiting_stopped`.
- Views: `storyteller_view()` gains `night_check`, `waiting_stopped`, and `players[i]["exempt"]`; `phones` already lists only waited-for players.
- `server.py`: `set_night_check` (label `"Night check {body_on}"`), `set_exempt` (`"Night check for {name}"`), `stop_waiting` (`"Stop waiting for phones"`) in `ST_ACTIONS`.

- [ ] **Step 1: Write the tests**

```python
def test_night_check_off_means_no_tap_tasks_and_no_waiting():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    g.set_night_check(False)
    to_night2(g)
    assert all(not (x.prompt and x.prompt["kind"] == "tap") for x in g.players)
    assert g.phones_done() == (0, 0)
    g.resolve(step(g, "imp"), [p(g, "Dev").pid])   # would raise "Waiting for ..." with the check on

def test_night_check_off_unblocks_dawn():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    with pytest.raises(GameError):
        g.start_day()
    g.set_night_check(False)
    g.start_day()
    assert g.phase == "day"

def test_exempt_still_gets_choice_prompt():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    g.set_exempt(p(g, "Ben").pid, True)
    g.stop_waiting()   # night 1's tap tasks would block dawn
    to_night2(g)
    assert p(g, "Ben").prompt["kind"] == "choose"
    assert p(g, "Ben").pid not in [x["pid"] for x in g.storyteller_view()["phones"]]

def test_stop_waiting_releases_dawn_once():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"], phones=True)
    g.stop_waiting()
    g.start_day()
    g.end_day()
    with pytest.raises(GameError):
        g.start_day()
```

(`to_night2` in `test_game.py` calls `start_day` then `end_day`; with phones on it needs `g.stop_waiting()` first, as above.)

- [ ] **Step 2: Run to verify they fail** — expected `AttributeError: set_night_check`.
- [ ] **Step 3: Implement** as described in Interfaces.
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: night check setting, per-player exemption, stop waiting"`.

---

### Task 5: One thread per player

**Files:**
- Modify: `game.py`, `server.py`
- Test: `test_table.py`

**Interfaces:**
- Produces on `Player`: `thread: list[dict]`, entries `{"from": "st" | "player", "text": str, "label": str, "seen": bool}`. Replaces `Player.messages` and `Game.inbox` as storage.
- Produces on `Game`: `message(pid, text, now=False)` appends `{"from": "st", ..., "seen": False}` (held until dawn at night unless `now`, as today); `note_to_storyteller(token, text)` appends `{"from": "player", ..., "seen": False}`; `read_thread(pid: str) -> None` marks that player's `"player"` entries seen; `read_inbox()` marks every player's; `_flush` appends `"st"` entries.
- Views: `player_view()["me"]["thread"] = p.thread`; compat `me["messages"]` = `[{"label", "text"}]` of `"st"` entries, `me["notes"]` = `[{"label", "text"}]` of `"player"` entries; `storyteller_view()["threads"] = {pid: thread}`; compat `inbox` = `[{"pid", "text", "label", "read"}]` from `"player"` entries (`read` = `seen`); `unread` count in `storyteller_view()["unread"]`.
- `_KEPT_ON_UNDO`: `inbox` is gone; player-written entries must survive undo: `undo()` re-attaches each restored player's `"player"` entries from the live thread (keep the newest list of `"player"` entries per pid, merge after restore).
- `server.py`: `read_thread` in `ST_ACTIONS` and `NO_UNDO`; `POST /api/message` with `NoteBody` doing the same as `/api/note` (keep `/api/note`).

- [ ] **Step 1: Write the tests**

```python
def test_thread_holds_both_directions_and_seen():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.message(p(g, "Dev").pid, "Hello")
    g.note_to_storyteller(p(g, "Dev").token, "Hi back")
    t = g.player_view(p(g, "Dev").token)["me"]["thread"]
    assert [(m["from"], m["text"], m["seen"]) for m in t] == [("st", "Hello", False), ("player", "Hi back", False)]
    assert g.storyteller_view()["unread"] == 1
    g.read_thread(p(g, "Dev").pid)
    assert g.player_view(p(g, "Dev").token)["me"]["thread"][1]["seen"] is True
    assert g.storyteller_view()["unread"] == 0

def test_compat_keys_still_derived():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.message(p(g, "Dev").pid, "Hello")
    g.note_to_storyteller(p(g, "Dev").token, "Hi back")
    me = g.player_view(p(g, "Dev").token)["me"]
    assert me["messages"] == [{"label": "Day 1", "text": "Hello"}]
    assert me["notes"] == [{"label": "Day 1", "text": "Hi back"}]
    assert g.storyteller_view()["inbox"][0]["read"] is False

def test_player_messages_survive_undo():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    before = g.snapshot()
    g.message(p(g, "Dev").pid, "Hello")
    g.push_undo("Message Dev", before, seen=True)
    g.note_to_storyteller(p(g, "Dev").token, "Hi back")
    g.undo()
    assert [m["text"] for m in p(g, "Dev").thread] == ["Hi back"]
```

- [ ] **Step 2: Run to verify they fail** — expected `KeyError: 'thread'`.
- [ ] **Step 3: Implement** per Interfaces; `inbox` leaves `_KEPT_ON_UNDO`, the merge in `undo()` replaces it.
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: per-player message thread with seen state"`.

---

### Task 6: Hands outside a vote

**Files:**
- Modify: `game.py`, `server.py`
- Test: `test_table.py`

**Interfaces:**
- Produces on `Player`: `hand: bool = False`.
- Produces on `Game`: `raise_hand(token: str, up: bool) -> None` (player; day only; refuses dead players with `"Dead players cannot nominate"` when no clock is running — Task 7 extends this to votes); `set_hand(pid: str, up: bool) -> None` (Storyteller, same rules minus the dead check); `nominate()` lowers the nominator's hand; `end_day()` lowers every hand.
- Views: `public_view()["hands"] = [pid, ...]` in seat order; `storyteller_view()["hands"]` the same list ordered by when raised (keep `self.hand_order: list[str]`).
- `server.py`: `POST /api/hand` with body `{"token": str, "up": bool}`; `set_hand` in `ST_ACTIONS` (label `"{name}'s hand"`).

- [ ] **Step 1: Write the tests**

```python
def test_hand_up_down_and_order():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.raise_hand(p(g, "Dev").token, True)
    g.raise_hand(p(g, "Asha").token, True)
    assert g.public_view()["hands"] == [p(g, "Asha").pid, p(g, "Dev").pid]
    assert g.storyteller_view()["hands"] == [p(g, "Dev").pid, p(g, "Asha").pid]
    g.nominate(p(g, "Dev").pid, p(g, "Ema").pid)
    assert g.public_view()["hands"] == [p(g, "Asha").pid]

def test_dead_cannot_raise_to_nominate():
    g = make(["imp", "poisoner", "monk", "empath", "soldier"])
    g.start_day()
    g.kill(p(g, "Dev").pid)
    with pytest.raises(GameError, match="Dead players cannot nominate"):
        g.raise_hand(p(g, "Dev").token, True)
```

- [ ] **Step 2: Run to verify they fail** — expected `AttributeError: raise_hand`.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: raised hands to nominate"`.

---

### Task 7: The vote clock

**Files:**
- Modify: `game.py`, `server.py`
- Test: `test_table.py`

**Interfaces:**
- Nomination dicts gain `"clock": None | dict` with `{"state": "countdown" | "running" | "paused" | "done", "go_at": float, "seat_seconds": int, "paused_at": float | None, "paused_total": float, "hands": {pid: bool}, "locked": {pid: bool | None}}`. At most one nomination has a non-`None`, non-`"done"` clock.
- Produces on `Game`:
  - `COUNTDOWN_SECONDS = 3`
  - `start_clock(nomination: int, seat_seconds: int = 3) -> None`: refuses if another clock is live or this nomination already has votes; `go_at = clock() + 3`; `hands` seeded from `p.hand` for every seat (hands raised before the clock carry over), `locked` all `None`; lowers `p.hand` for all.
  - `pause_clock()`, `resume_clock()`, `restart_clock()` (new `go_at`, clears `locked`, keeps `hands`), `stop_clock()` (sets `clock = None`, hands back to `False`).
  - `clock_elapsed(c: dict) -> float` = `now - go_at - paused_total - (now - paused_at if paused else 0)`; `hand_index(c) -> int` = `floor(elapsed / seat_seconds)` (negative during countdown).
  - `seat_offset(nominee_pid: str, pid: str) -> int` = `k` in 1..N clockwise from the nominee, nominee = N.
  - `_sync_clock() -> None`: called at the start of every public method and view; for the live clock locks every seat with `seat_offset <= hand_index` whose `locked` is `None`: value = `hands[pid]`, except a Butler locks `hands[pid] and hands[master]` (master = the pid with the `"master"` chip from that Butler's pick), and a dead player without a ghost vote locks `False`. When every seat is locked: `state = "done"`, `record_votes(nomination, [pids locked True])` (which spends ghost votes and announces as today).
  - During a live clock `raise_hand(token, up)` / `set_hand(pid, up)` toggle `c["hands"][pid]`; refused with `"The clock has passed you"` when `locked[pid]` is not `None`; a dead player without a ghost vote is refused with `"No vote left"`.
- Views: `public_view()["clock"]` = `None`, or the live or most recent `"done"` clock as `{"nomination": i, "nominator": pid, "nominee": pid, "state", "go_at", "seat_seconds", "paused_at", "paused_total", "hands": [pids whose hand is up, locked or not], "locked": {pid: bool, only seats that have locked}}`; `public_view()["server_time"] = clock()`; `storyteller_view()["nominations_full"][i]["clock"]` as stored.
- `server.py`: `start_clock` (label `"Start the clock"`), `pause_clock`, `resume_clock`, `restart_clock`, `stop_clock` in `ST_ACTIONS` with labels `"Pause the clock"`, `"Resume the clock"`, `"Restart the clock"`, `"Stop the clock"`.

- [ ] **Step 1: Write the tests** (inject a fake clock: `t = [1000.0]; g.clock = lambda: t[0]`)

```python
def vote_game():
    g = make(["imp", "poisoner", "monk", "empath", "soldier", "butler", "mayor"])   # 7 seats, threshold 4
    t = [1000.0]
    g.clock = lambda: t[0]
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Ben").pid)
    return g, t

def test_clock_locks_seats_in_order_and_records():
    g, t = vote_game()
    for n in ("Chen", "Dev", "Ema"):
        g.raise_hand(p(g, n).token, True)
    g.start_clock(0, seat_seconds=3)
    assert g.public_view()["clock"]["state"] == "countdown"
    t[0] += 3 + 3 * 1   # go, then one seat
    assert g.public_view()["clock"]["locked"] == {p(g, "Chen").pid: True}
    t[0] += 3 * 6       # the rest, nominee last
    v = g.public_view()
    assert v["clock"]["state"] == "done" and v["nominations"][0]["votes"] == 3

def test_toggle_after_lock_refused():
    g, t = vote_game()
    g.start_clock(0)
    t[0] += 3 + 3
    with pytest.raises(GameError, match="The clock has passed you"):
        g.raise_hand(p(g, "Chen").token, True)

def test_butler_locks_no_when_master_down():
    g = make(["imp", "poisoner", "monk", "empath", "soldier", "butler", "mayor"])
    t = [1000.0]; g.clock = lambda: t[0]
    g.resolve(step(g, "butler"), [p(g, "Asha").pid])   # night 1: Finn's Master is Asha
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Ben").pid)
    g.raise_hand(p(g, "Finn").token, True)             # Asha's hand stays down
    g.start_clock(0)
    t[0] += 3 + 3 * 7
    assert g.public_view()["clock"]["locked"][p(g, "Finn").pid] is False

def test_dead_without_ghost_vote_cannot_raise():
    g, t = vote_game()
    g.kill(p(g, "Dev").pid); g.set_ghost_vote(p(g, "Dev").pid, False)
    g.start_clock(0)
    with pytest.raises(GameError, match="No vote left"):
        g.raise_hand(p(g, "Dev").token, True)

def test_pause_freezes_and_restart_clears_locks():
    g, t = vote_game()
    g.raise_hand(p(g, "Chen").token, True)
    g.start_clock(0)
    t[0] += 3 + 3
    g.pause_clock(); t[0] += 100
    assert g.public_view()["clock"]["locked"] == {p(g, "Chen").pid: True}
    g.resume_clock(); g.restart_clock()
    assert g.public_view()["clock"]["locked"] == {} and g.public_view()["clock"]["hands"] == [p(g, "Chen").pid]

def test_undo_start_clock_clears_clock():
    g, t = vote_game()
    before = g.snapshot()
    g.start_clock(0)
    g.push_undo("Start the clock", before, seen=True)
    t[0] += 3 + 3 * 7
    g.undo()
    assert g.public_view()["clock"] is None and all(x.ghost_vote for x in g.players)
```

- [ ] **Step 2: Run to verify they fail** — expected `AttributeError: start_clock`.
- [ ] **Step 3: Implement** per Interfaces; `_sync_clock` is the only place locks are written.
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: server-timed vote clock with hand locking"`.

---

### Task 8: API surface and README

**Files:**
- Modify: `server.py`, `README.md`
- Test: `test_server.py` (new; FastAPI `TestClient` from `fastapi.testclient`, available with fastapi — `uv run --with pytest --with httpx pytest`)

**Interfaces:**
- Every Storyteller action added in Tasks 1–7 is in `ST_ACTIONS` with an `ACTION_LABELS` entry; `read_thread` is in `NO_UNDO`.
- Player routes: `POST /api/hand {token, up}`, `POST /api/message {token, text}` (alias of `/api/note`), `GET /api/scripts`.
- `GET /api/state` includes `server_time`; `GET /api/st` includes `night_check`, `threads`, `hands`, `unread`.

- [ ] **Step 1: Write the tests**

```python
# test_server.py
from fastapi.testclient import TestClient
from game import Game
from server import create_app

def client():
    g = Game(script="tb")
    return TestClient(create_app(g, "key", "http://x/")), g

def test_scripts_and_state_keys():
    c, g = client()
    assert c.get("/api/scripts").json()[0]["id"] == "tb"
    assert "server_time" in c.get("/api/state").json()
    st = c.get("/api/st?key=key").json()
    for k in ("night_check", "threads", "hands", "unread"):
        assert k in st

def test_hand_and_message_routes_and_st_actions():
    c, g = client()
    tok = c.post("/api/join", json={"name": "Asha"}).json()["token"]
    assert c.post("/api/message", json={"token": tok, "text": "hi"}).status_code == 200
    assert c.post("/api/st/set_night_check?key=key", json={"on": False}).json()["night_check"] is False
    assert c.post("/api/st/read_thread?key=key", json={"pid": "p1"}).status_code == 200
    assert c.post("/api/hand", json={"token": tok, "up": True}).status_code == 400   # lobby: day only
```

- [ ] **Step 2: Run to verify they fail** — expected 404s / KeyErrors.
- [ ] **Step 3: Implement** the routes and labels; update `README.md` "Files" (scripts/, deleted roles.py/info.py, new tests) and add a "Remote play" paragraph: night check setting, public link.
- [ ] **Step 4: Run** `uv run --with pytest --with httpx pytest -q` — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: API for scripts, night check, threads, hands and the clock"`.

---

### Task 9: Bad Moon Rising script data and dealing

**Files:**
- Create: `scripts/bad_moon_rising.py`
- Modify: `scripts/__init__.py`, `dealing.py`
- Test: `test_bmr.py` (new), `test_scripts.py`

**Interfaces:**
- `scripts/bad_moon_rising.py` implements the Task 1 module surface. `CHARACTERS`: the 23 characters of Appendix A / §9 with `summary` = the sheet's one-liner (`bad-moon-rising-almanac.pdf`), `ability` = a plain-English expansion, `night` per §9 (`choose` for sailor 1/allow_self, innkeeper 2, gambler 1 with the guess in `options["guess"]`, exorcist 1, devilsadvocate 1, pukka 1, shabaloth 2, po 0–3 handled as `count: 3, "variable": True`, assassin 1, godfather 1, professor 1, courtier 1 with `options["character"]`, lunatic 2 (`count` follows the believed demon), chambermaid 2; `info` for grandmother; `storyteller` for tinker (`question`: "Does the Tinker die tonight?"), gossip ("Was the Gossip's statement true? Who dies?"), moonchild; `None` for passives), `uses` (`once_per_game` for assassin, professor, courtier; `day` for gossip; `on_death` for moonchild; `passive` for minstrel, tealady, pacifist, fool, goon, mastermind, tinker; `each_night` otherwise), `reminders` and `hint` from the Townsquare role data (vendored by hand, not fetched).
- `FIRST_NIGHT = ["minion_info", "demon_info", "lunatic", "sailor", "courtier", "godfather", "devilsadvocate", "pukka", "grandmother", "chambermaid"]`; `OTHER_NIGHTS = ["sailor", "courtier", "innkeeper", "gambler", "devilsadvocate", "lunatic", "exorcist", "zombuul", "pukka", "shabaloth", "po", "assassin", "godfather", "gossip", "professor", "tinker", "moonchild", "grandmother", "chambermaid"]`.
- `expected_counts(players, chars)`: Godfather `+1` Outsider by default (the Storyteller may pick `−1` by changing characters in setup).
- `deal_extras(characters, rng)`: `believed` differs only for the Lunatic (a random Demon of the script not in play); `red_herring = None`; `bluffs` = three good characters not in play and not the Lunatic's believed Demon; one Demon is dealt, chosen at random from the four.
- `dealing.deal(script, pids, rng)` already generic from Task 1; `pick_characters(script, players, rng)` draws the Demon with `rng.choice(ids_of(DEMON))` instead of "all demons".
- `scripts.SCRIPTS["bmr"]` registered.

- [ ] **Step 1: Write the tests**

```python
# test_bmr.py
import random, pytest
import scripts
from scripts import bad_moon_rising as bmr
from game import Game, GameError
NAMES = ["Asha", "Ben", "Chen", "Dev", "Ema", "Finn", "Gita", "Hari", "Ines"]

def make(chars, seed=1, believed=None):
    g = Game(random.Random(seed), script="bmr")
    for n in NAMES[:len(chars)]: g.add_player(n)
    g.deal()
    for p, c in zip(g.players, chars): g.set_character(p.pid, c, (believed or {}).get(c))
    held = {x for p in g.players for x in (p.character, p.believed)}
    g.bluffs = [c for c in bmr.CHARACTERS if scripts.is_good(bmr.CHARACTERS, c) and c not in held][:3]
    g.start_game()
    return g

def p(g, name): return next(x for x in g.players if x.name == name)
def step(g, key): return next(i for i, s in enumerate(g.steps) if s["key"] == key)

def test_night_orders_match_appendix_a():
    assert bmr.FIRST_NIGHT[2:] == ["lunatic", "sailor", "courtier", "godfather", "devilsadvocate", "pukka", "grandmother", "chambermaid"]
    assert bmr.OTHER_NIGHTS == ["sailor", "courtier", "innkeeper", "gambler", "devilsadvocate", "lunatic", "exorcist", "zombuul", "pukka", "shabaloth", "po", "assassin", "godfather", "gossip", "professor", "tinker", "moonchild", "grandmother", "chambermaid"]
    assert len(bmr.CHARACTERS) == 23

def test_deal_has_one_demon_and_godfather_adds_an_outsider():
    g = Game(random.Random(5), script="bmr")
    for n in NAMES: g.add_player(n)
    g.deal()
    chars = [x.character for x in g.players]
    assert sum(bmr.CHARACTERS[c]["type"] == "demon" for c in chars) == 1
    assert bmr.expected_counts(9, ["godfather"]) == (4, 3, 1, 1)

def test_lunatic_believes_a_demon_not_in_play():
    g = make(["po", "assassin", "lunatic", "sailor", "tealady"])
    lun = p(g, "Chen")
    assert bmr.CHARACTERS[lun.believed]["type"] == "demon" and lun.believed != "po"
```

- [ ] **Step 2: Run to verify they fail** — expected `ImportError: cannot import name 'bad_moon_rising'`.
- [ ] **Step 3: Write the data module** with stub hooks (`apply`, `may_die` returning `True`, etc.) so the game runs; Tasks 10–13 fill them in.
- [ ] **Step 4: Run the suite** — PASS (the schema test from Task 1 must loop over both scripts: extend `test_every_character_declares_the_schema` to `for mod in scripts.SCRIPTS.values()`).
- [ ] **Step 5: Commit** — `git add scripts/bad_moon_rising.py test_bmr.py && git commit -am "feat: Bad Moon Rising script data and dealing"`.

---

### Task 10: Bad Moon Rising deaths and protection

**Files:**
- Modify: `scripts/bad_moon_rising.py`, `game.py` (pending deaths), `server.py`
- Test: `test_bmr.py`

**Interfaces:**
- `may_die(game, p, cause)` in BMR: Sailor → `False` for every cause but `"executed"`? No: the Sailor "can't die" at all while sober → `False` for every cause when `not game.impaired(p)`; Tea Lady neighbours: if `p` is a living neighbour of a sober Tea Lady and both of her living neighbours are good → `False`; Fool: first death → `p.used = True`, `False`; Innkeeper `"protected"` chip → `False` for night causes other than `"assassin"`; Devil's Advocate `"survives execution"` chip → `False` for `"executed"`; Pacifist: `cause == "executed"` and `is_good` → `"ask: the Pacifist is in play; does the executed good player die?"`; Zombuul first death → `p.used = True`, `mark(p, "registers dead", None)`, `False`; everything else `True`.
- Produces on `Game`: `confirm_death(index: int, dies: bool) -> None` (Storyteller action) resolving `pending_deaths[index]`: `dies` → `_die` bypassing `may_die` (`_die(p, cause, force=True)`), else log "survives". `start_day` refuses with `"Decide the pending deaths first"` while `pending_deaths` is non-empty (nothing has changed yet, so raising is safe). `end_day` never raises after an execution: when the execution leaves a pending death it announces `"Decide whether <name> dies, then end the day."` and returns with the phase still `day`; the next `end_day` skips the execution (`executed_today` is set) and starts the night. `_publicly_alive(p)` is `False` while `p` carries `"registers dead"`; such a player cannot be nominated and gets a ghost vote.
- Views: `storyteller_view()["pending_deaths"] = [{"pid", "cause", "why"}]`.
- `server.py`: `confirm_death` in `ST_ACTIONS`, label `"Decide a death"`.

- [ ] **Step 1: Write the tests**

```python
def test_sailor_cannot_die_and_fool_survives_once():
    g = make(["po", "assassin", "sailor", "fool", "tealady", "gossip", "tinker"])
    g.start_day(); g.end_day()
    g.resolve(step(g, "po"), [p(g, "Chen").pid])
    assert p(g, "Chen").alive
    g.kill(p(g, "Dev").pid); assert p(g, "Dev").alive and p(g, "Dev").used
    g.kill(p(g, "Dev").pid); assert not p(g, "Dev").alive

def test_tea_lady_protects_good_neighbours():
    g = make(["po", "tealady", "gossip", "gambler", "sailor"])   # Ben's neighbours: Asha (evil), Chen (good)
    g.start_day(); g.end_day()
    g.resolve(step(g, "po"), [p(g, "Chen").pid])
    assert p(g, "Chen").alive is False   # one neighbour is evil: no protection
    g2 = make(["gambler", "tealady", "gossip", "po", "sailor"])  # Ben's neighbours: Asha and Chen, both good
    g2.start_day(); g2.end_day()
    g2.resolve(step(g2, "po"), [p(g2, "Chen").pid])
    assert p(g2, "Chen").alive

def test_pacifist_execution_asks_then_confirm():
    g = make(["po", "assassin", "pacifist", "sailor", "gossip"])
    g.start_day()
    g.nominate(p(g, "Asha").pid, p(g, "Ema").pid); g.record_votes(0, [x.pid for x in g.players[:3]])
    g.end_day()
    assert g.phase == "day" and g.pending_deaths[0]["pid"] == p(g, "Ema").pid
    g.confirm_death(0, False)
    assert p(g, "Ema").alive
    g.end_day()
    assert g.phase == "night"

def test_zombuul_registers_dead_then_acts_after_a_quiet_day():
    g = make(["zombuul", "assassin", "sailor", "gossip", "gambler"])
    g.start_day()
    g.nominate(p(g, "Ben").pid, p(g, "Asha").pid); g.record_votes(0, [x.pid for x in g.players[:3]])
    g.end_day()                                   # Asha "dies" once: night 2
    assert p(g, "Asha").alive and g.has(p(g, "Asha"), "registers dead")
    assert g.public_view()["seats"][0]["alive"] is False and g.winner is None
    assert not any(s["key"] == "zombuul" for s in g.steps)   # someone died today
    g.start_day(); g.end_day()                    # nobody dies on day 2: night 3
    assert any(s["key"] == "zombuul" for s in g.steps)
```

- [ ] **Step 2: Run to verify they fail** — expected assertions on `alive`.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: BMR protection rules, pending deaths, Zombuul"`.

---

### Task 11: Bad Moon Rising demons, Exorcist and Lunatic

**Files:**
- Modify: `scripts/bad_moon_rising.py`, `game.py`
- Test: `test_bmr.py`

**Interfaces:**
- `apply` for: Pukka (`mark(target, "poisoned", None)` tagged `pukka`; the previously tagged player dies with cause `"pukka"` and is cured; the chip text is `"poisoned"`, the tag lives in a second key `"by": "pukka"` on the chip dict); Shabaloth (two kills, cause `"demon"`; `options["regurgitate"]` = pid of one of last night's victims to revive — `game.revive(pid)` then log); Po (`choices` of length 0, 1 or 3: 3 required when `game.po_chose_nobody` is set from the previous night, 0 or 1 otherwise; stores `game.po_chose_nobody = not choices`); Zombuul (one kill; `step_applies` returns `False` when someone died today: `game.died_today: list[str]` is filled by `_die` during the day and reset at `start_day`).
- Exorcist: `apply` checks `target` is the Demon → `mark(target, "exorcised", "dawn")`, notifies the Demon ("The Exorcist is <name>. You do not act tonight."); `step_applies` for a Demon step returns `False` while the Demon carries `"exorcised"`; `apply` refuses the same target as last night (`game.last_pick: dict[str, list[str]]` keyed by step key, kept across nights for exorcist, devilsadvocate, innkeeper? only the ones whose text says "different to last night": exorcist, devilsadvocate).
- Lunatic: `_build_steps` uses `p.believed` already, so the Lunatic appears under its believed Demon's key; `apply` for a step whose actor's true character is `"lunatic"` does nothing but record `game.lunatic_picks = choices` and notifies the real Demon at the next `_flush` ("The Lunatic attacked <names>."); the Lunatic's believed Demon step is not blocked by the Exorcist.
- Produces on `Game`: `revive(pid)` already exists; `po_chose_nobody: bool`, `died_today: list[str]`, `last_pick: dict`, `lunatic_picks: list[str]` reset in `_reset_round`; `resolve` accepts `len(choices)` in `step["counts"]` when the character's `night` has `"variable": True` (`counts = [0, 1, 3]` for Po, chosen by rule).

- [ ] **Step 1: Write the tests**

```python
def test_pukka_poisons_then_kills_next_night():
    g = make(["pukka", "assassin", "sailor", "fool", "gossip", "tinker", "gambler"])
    g.resolve(step(g, "pukka"), [p(g, "Chen").pid])
    assert g.impaired(p(g, "Chen"))
    g.start_day(); g.end_day()
    g.resolve(step(g, "pukka"), [p(g, "Dev").pid])
    assert not p(g, "Chen").alive and not g.impaired(p(g, "Chen")) and g.impaired(p(g, "Dev"))

def test_po_three_kills_respect_protection():
    g = make(["po", "assassin", "innkeeper", "fool", "gossip", "tinker", "gambler"])
    g.start_day(); g.end_day()
    g.resolve(step(g, "po"), [])           # nobody
    g.start_day(); g.end_day()
    g.resolve(step(g, "innkeeper"), [p(g, "Ema").pid, p(g, "Finn").pid], drunk=p(g, "Finn").pid)
    with pytest.raises(GameError):
        g.resolve(step(g, "po"), [p(g, "Ema").pid])   # must pick 3
    g.resolve(step(g, "po"), [p(g, "Ema").pid, p(g, "Finn").pid, p(g, "Gita").pid])
    assert p(g, "Ema").alive and p(g, "Finn").alive and not p(g, "Gita").alive
    g.start_day()
    assert "Gita died" in g.announcements[0]

def test_exorcist_blocks_the_demon():
    g = make(["po", "assassin", "exorcist", "fool", "gossip", "tinker", "gambler"])
    g.start_day(); g.end_day()
    g.resolve(step(g, "exorcist"), [p(g, "Asha").pid])
    assert g.step_applies(g.steps[step(g, "po")]) is False
    g.start_day()
    assert "Exorcist" in p(g, "Asha").thread[-1]["text"]

def test_shabaloth_regurgitates():
    g = make(["shabaloth", "assassin", "sailor", "fool", "gossip", "tinker", "gambler"])
    g.start_day(); g.end_day()
    g.resolve(step(g, "shabaloth"), [p(g, "Dev").pid, p(g, "Ema").pid])
    g.start_day(); g.end_day()
    g.resolve(step(g, "shabaloth"), [p(g, "Finn").pid, p(g, "Gita").pid], regurgitate=p(g, "Dev").pid)
    assert p(g, "Dev").alive
```

- [ ] **Step 2: Run to verify they fail**.
- [ ] **Step 3: Implement** per Interfaces (`resolve` keyword options: `drunk`, `regurgitate`, `guess`, `character`, `redirect`, `new_demon` all flow through `options`).
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: BMR demons, Exorcist and Lunatic"`.

---

### Task 12: The rest of Bad Moon Rising

**Files:**
- Modify: `scripts/bad_moon_rising.py`, `game.py`
- Test: `test_bmr.py`

**Interfaces:**
- `apply`: Sailor (`options["drunk"]` = actor pid or target pid, `mark(..., "drunk", "night")`); Innkeeper (`"protected"` on both with `until="dawn"`, `"drunk"` with `until="night"` on `options["drunk"]`); Gambler (`options["guess"]` cid; wrong → `_die(actor, "gambler")`); Devil's Advocate (`"survives execution"` until `"night"`); Courtier (`options["character"]`: if in play, `mark(holder, "drunk 3", None)`, `actor.used = True`); Professor (target dead Townsfolk → `revive`, `actor.used = True`; otherwise used with no effect); Assassin (`_die(target, "assassin")`, `used = True`); Godfather (`step_applies` other nights only when an Outsider is in `died_today`; `_die(target, "godfather")`); Goon (in `apply` of any step: if a target is the Goon and no one has chosen the Goon tonight, `mark(actor, "drunk", "night")`, `goon.team = team of actor` via `game.team_override[pid]`); Chambermaid (`suggest`: count of the two picks whose step applied and was not skipped tonight — `game.woke_tonight: set[str]` of pids, filled in `resolve`/`send`).
- `suggest`: Grandmother first night → "Your grandchild is <name>, the <character>." and `mark(grandchild, "grandchild", None)`; Godfather first night → the Outsiders in play; Chambermaid as above.
- `storyteller` steps resolve through `resolve(step, [], decision=...)`: Tinker (`options["dies"]: bool`), Gossip (`options["dies"]: pid | None`, allowed only when `game.gossip_true` was set by `day_ability`), Moonchild (automatic: the pick stored by `day_ability` dies if good, cause `"moonchild"`).
- `day_ability(game, p, options)`: Gossip `{"true": bool}` → `game.gossip_true`; Moonchild `{"target": pid}` allowed only when `p` is dead (sets `game.moonchild_pick`).
- `on_death`: Grandmother's grandchild killed by the Demon → `_die(grandmother, "grandmother")`; Minstrel: `on_execution` of a Minion → every other player `mark(..., "drunk", "night")`.
- `day_end`: Mastermind: when the Demon was executed today and a sober Mastermind is alive, do not end the game; set `game.mastermind_day = True` and continue; on the following `end_day`, if anyone was executed the executed player's team loses, else good wins. `_check_win` consults `mastermind_day`.
- `before_dawn`: Courtier countdown (`"drunk 3"` → `"drunk 2"` → `"drunk 1"` → removed); Tinker/Gossip/Moonchild steps left unresolved count as "no death".
- `is_good(chars, cid)` gains the `team_override` check in `Game.is_good(p)` (a new helper used by every rule that asks a player's alignment; Goon only).

- [ ] **Step 1: Write the tests** (one per rule; names fixed, assertions follow §9)

```python
def test_gambler_wrong_guess_dies(): ...        # guess "fool" for a sailor → gambler dead
def test_courtier_drunk_counts_down(): ...     # "drunk 3" → after two dawns "drunk 1" → gone; actor.used
def test_professor_revives_townsfolk_once(): ...
def test_assassin_ignores_protection_and_is_once(): ...
def test_godfather_kills_only_after_outsider_death(): ...
def test_goon_drunks_first_chooser_and_changes_team(): ...
def test_grandmother_dies_with_grandchild(): ...
def test_minstrel_drunks_everyone_when_minion_executed(): ...
def test_mastermind_gives_one_more_day(): ...
def test_gossip_true_statement_kills_at_night(): ...
def test_moonchild_pick_dies_if_good(): ...
def test_chambermaid_counts_who_woke(): ...
```

Each test builds the table with `make`, drives to the needed night with `start_day()/end_day()`, resolves the step with the `options` named above and asserts `alive`, `used`, `has(...)`, or `winner` exactly as §9 states.

- [ ] **Step 2: Run to verify they fail**.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: remaining Bad Moon Rising characters"`.

---

### Task 13: Dawn with several deaths

**Files:**
- Modify: `game.py`
- Test: `test_bmr.py`, `test_game.py`

**Interfaces:**
- `night_deaths` becomes `list[dict]` `{"pid", "cause"}` (TB code that appends pids updated); `storyteller_view()["night_deaths"]` keeps a list of pids for the old page and adds `night_deaths_full`.
- `start_day` announces `"<A>, <B> and <C> died in the night."` (Oxford-free: two names "A and B", three or more "A, B and C"), `"Nobody died in the night."` otherwise.
- `storyteller_view()["dawn"] = {"deaths": [{"pid", "cause", "linked": bool}], "pending": pending_deaths, "held": int}`.

- [ ] **Step 1: Write the tests**

```python
def test_dawn_announces_every_death():
    g = make(["po", "assassin", "sailor", "fool", "gossip", "tinker", "gambler"])
    g.start_day(); g.end_day()
    g.resolve(step(g, "po"), [])
    g.start_day(); g.end_day()
    g.resolve(step(g, "po"), [p(g, "Dev").pid, p(g, "Ema").pid, p(g, "Gita").pid])
    v = g.storyteller_view()["dawn"]
    assert [d["cause"] for d in v["deaths"]] == ["demon", "demon", "demon"]
    g.start_day()
    assert g.announcements[0] == "Dawn. Dev, Ema and Gita died in the night."
```

- [ ] **Step 2: Run to verify it fails**.
- [ ] **Step 3: Implement**; keep `test_game.py`'s existing dawn assertion ("X died in the night") passing.
- [ ] **Step 4: Run the suite** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: dawn card with every death and its cause"`.

---

## Self-review notes

- Spec coverage: §5 (Tasks 1, 9), §6.3–6.4 data (Tasks 2–3), §6.5.3 dawn/pending (10, 13), §6.6 (4), §6.7 (5), §7 (6–7), §8.4 engine side (5), §9 (10–12), §10 (8: README). Sounds/vibration (§7.3) and every screen are plans 2–3; they only need `clock.go_at` and `hand_index`, which Task 7 provides.
- Names used across tasks: `has/mark/unmark/set_reminder`, `ability_state`, `day_ability`, `confirm_death`, `raise_hand/set_hand`, `start_clock/pause_clock/resume_clock/restart_clock/stop_clock`, `read_thread`, `set_night_check/set_exempt/stop_waiting`, `pending_deaths`, `night_deaths` (dicts from Task 13).
- Proportion: the plan is shorter than the engine it changes; bodies are omitted except where the signature leaves the algorithm open.
