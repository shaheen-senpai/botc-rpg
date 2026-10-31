# Grimoire page — implementation plan (2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Storyteller page with the grimoire designed in the spec: script picker, circle with reminder chips and ability pips, a token drawer, a night ledger of step cards, a day ledger with hands and the vote clock, a messages view, and sound.

**Architecture:** One page (`static/storyteller.html`) whose markup and CSS stay in the file, with the logic split into three ES modules: `static/clockmath.js` and `static/stmodel.js` are pure functions (view JSON in, render data out) tested with `node --test`; `static/storyteller.js` polls `/api/st`, renders string templates into the three zones (top bar, circle, right column) and posts actions, exactly as today's page does. `static/sound.js` (WebAudio tones + `navigator.vibrate`) is shared with the player page in plan 3. The server does not change except to serve the new files.

**Tech Stack:** Vanilla HTML/CSS/JS (ES modules), FastAPI static files, Node 24 `node --test` for the pure modules, the Playwright MCP browser for the walkthrough checks.

**Spec:** `docs/superpowers/specs/2026-10-31-ui-revamp-design.md` §6 (all), §7.2, §7.3 (sound), §10; mockups at the canvas linked in the spec (artboards 1–5 and "Play · Night ledger" / "Play · A vote"). Engine API: plan 1 (`docs/superpowers/plans/2026-10-31-engine-scripts-votes.md`), already merged on `sn/revamp/engine`.

## Global Constraints

- No build step, no framework, no new Python dependency. Scripts load with `<script type="module">`; fonts stay the bundled Grenze Gotisch + Alegreya Sans; palette stays `static/theme.css`.
- The page targets ≥1024 px; under 1024 the right column drops below the circle (tablet fallback). No phone layout.
- Every action the page posts exists in `server.py` `ST_ACTIONS`; the page never computes a lock, a tally or a death: it renders what `/api/st` says and sends what the Storyteller did.
- Clock rendering uses `server_time` from the poll to estimate the server's clock; never `Date.now()` alone.
- Audio starts only after a user gesture (`sound.unlock()` on the first click); the gear has a mute that persists in `localStorage["tb_mute"]`.
- Escape HTML everywhere user text is rendered (`esc()` as today).
- Work on branch `sn/revamp/grimoire` off `sn/revamp/engine`; one commit per task.

## Review Focus

1. A poll that arrives while the Storyteller is typing into a step's text field or the composer must not wipe what they typed (the `dirty` map pattern from today's page) — Task 1 keeps the pattern; Task 4 test `nightCards keeps the open card's draft` covers the model side.
2. Clicking a token while the clock runs toggles that player's hand (`set_hand`), never opens the drawer; after the clock finishes it opens the drawer again — Task 5 walkthrough step 4.
3. The hand on screen must never run ahead of the server: when `server_time` jumps backwards on a poll (clock drift), the hand must not animate backwards past a locked seat — Task 6 test `handAngle never exceeds the last locked seat`.
4. The night ledger's open card must follow the first step that is not done and applies; skipping or applying must move it without the Storyteller clicking — Task 4 test `nightCards opens the first undone applying step`.
5. Undo's cost line ("phones already showed this", "clears N picks") must still appear for the new actions — Task 7 walkthrough step 2.

---

### Task 1: Page shell, modules, theme tokens

**Files:**
- Rewrite: `static/storyteller.html` (markup + CSS only; `<script type="module" src="/static/storyteller.js">`)
- Create: `static/storyteller.js`, `static/stmodel.js`, `static/clockmath.js`, `static/sound.js`, `static/stmodel.test.js`
- Modify: `static/theme.css` (add `.pip`, `.pip.used`, `.rem.info`, `.rem.death`, `.vote`, `.vote.yes/.no/.up`, `.token.hand`, `.token.selected`, `.pill`, `.pill.wait/.calm/.held`, `.step`, `.step.open`, `.num`, `.num.now/.done`, `.phone`, `.phone.wait`, `.tog[aria-pressed]`, `.bub.them/.me`, copied from the mockup CSS)
- Keep today's `static/storyteller.html` behaviour for lobby and setup inside the new shell (drag to reseat, seat someone without a phone, deal, set character, red herring / bluffs, warnings, start).

**Interfaces:**
- `storyteller.js` exports nothing; it defines `S` (last `/api/st` view), `C` (characters), `poll()`, `act(action, body, clearPrefix)`, `render()` with the three zones `#topbar`, `#square`, `#column`, and keeps `dirty`, `selected`, `openStep`, `mode` (`"none" | "nominator" | "nominee"`), `view` (`"ledger" | "drawer" | "messages"`).
- `stmodel.js` exports (all pure, all take the `/api/st` JSON as `v` and the characters table as `C`):
  - `phaseTitle(v) -> string` ("Lobby", "Setup", "Night 2", "Day 2", "Good wins")
  - `tokenMarks(p, v, C) -> {pip: null | "unused" | "used", pipTitle: string, chips: [{text, cls}], vote: null | "yes" | "no" | "up", lit: bool}` — `cls` by chip text: `poisoned`/`drunk*` → `poison`, `protected`/`survives execution` → `safe`, `vote left`/`no vote` → `vote`, `grandchild`/`master`/`chosen` → `info`, `dead`/`died today`/`registers dead` → `death`, else `""`
  - `seatPositions(n) -> [{left, top}]` (percent strings, radius 41, seat 1 at top)
- `clockmath.js`, `sound.js`: stubs here, filled in Task 6 (`sound.unlock()`, `sound.mute(bool)`, `sound.muted()`, `sound.chime()`, `sound.tick()`, `sound.buzz()` exist as no-ops so the page runs).

- [ ] **Step 1: Write the failing model tests**

```js
// static/stmodel.test.js  (node --test static/)
import test from "node:test"; import assert from "node:assert/strict";
import { phaseTitle, tokenMarks, seatPositions } from "./stmodel.js";
const C = {imp:{uses:"each_night"}, slayer:{uses:"day"}, assassin:{uses:"once_per_game"}, soldier:{uses:"passive"}};
test("phaseTitle", () => {
  assert.equal(phaseTitle({phase:"night", night:2}), "Night 2");
  assert.equal(phaseTitle({phase:"over", winner:"good"}), "Good wins");
});
test("tokenMarks pips and chips", () => {
  const v = {phase:"day", clock:null, steps:[], hands:[]};
  const m = tokenMarks({pid:"p1", character:"slayer", ability:{uses:"day", used:false}, reminders:["poisoned", "vote left"]}, v, C);
  assert.equal(m.pip, "unused");
  assert.deepEqual(m.chips, [{text:"poisoned", cls:"poison"}, {text:"vote left", cls:"vote"}]);
  assert.equal(tokenMarks({pid:"p2", character:"soldier", ability:{uses:"passive", used:false}, reminders:[]}, v, C).pip, null);
});
test("tokenMarks vote marks and lit step", () => {
  const v = {phase:"day", clock:{state:"running", hands:["p1"], locked:{p2:true, p3:false}}, steps:[], hands:[]};
  const mk = pid => tokenMarks({pid, character:"imp", ability:{uses:"each_night"}, reminders:[]}, v, C).vote;
  assert.deepEqual([mk("p1"), mk("p2"), mk("p3"), mk("p4")], ["up", "yes", "no", null]);
  const n = {phase:"night", clock:null, hands:[], steps:[{pids:["p9"], done:false, applies:true}]};
  assert.equal(tokenMarks({pid:"p9", character:"imp", ability:{uses:"each_night"}, reminders:[]}, n, C).lit, true);
});
test("seatPositions puts seat 1 at the top", () => {
  const s = seatPositions(8);
  assert.equal(s.length, 8); assert.equal(s[0].left, "50.0%"); assert.equal(s[0].top, "9.0%");
});
```

- [ ] **Step 2: Run it to verify it fails** — `node --test static/` → FAIL, `Cannot find module './stmodel.js'`.
- [ ] **Step 3: Write `stmodel.js` (the three functions), `clockmath.js` and `sound.js` stubs.**
- [ ] **Step 4: Run** `node --test static/` → PASS.
- [ ] **Step 5: Write the shell** — `storyteller.html` with the three zones and the CSS from the mockups (`project/Main.dc.html` on the canvas is the reference for the night look; day colours from `ST-Day`); `storyteller.js` with poll/act/render, the top bar (script name, phase, alive count, unread button, undo + cost, gear), the circle (tokens with `tokenMarks`, nameplates, chips, seat numbers, drag-to-reseat in lobby/setup as today), and the right column rendering today's lobby and setup content. Centre of the circle: QR + link in the lobby (`/qr.svg`, `S.join_url`), phase card otherwise.
- [ ] **Step 6: Walkthrough** (Playwright MCP against `uv run server.py --port 8010`): open `/st?key=…`, seat three players via `/api/join` with curl, confirm tokens render with seat numbers, drag one token, deal, change a character from the drawer placeholder (a plain select for now), start the game. Expected: no console errors; the night view shows tokens with the glowing next step.
- [ ] **Step 7: Commit** — `git checkout -b sn/revamp/grimoire && git add static/ && git commit -m "feat(grimoire): page shell, pure model modules, theme tokens"`.

---

### Task 2: Script picker, lobby card, settings

**Files:** `static/storyteller.js`, `static/storyteller.html`, `static/stmodel.js`, `static/stmodel.test.js`

**Interfaces:**
- When `S.phase === "lobby"` and `S.players.length === 0` and no script was chosen this session (`sessionStorage["tb_script_chosen"]` unset), the page shows the script picker (two cards from `GET /api/scripts`: name, counts, the one-line blurb from the mockup `ST-Script`, `Run <name>`) which posts `set_script {script}` and sets the flag. The gear also offers `Change script` while the lobby is empty.
- Lobby card: join link text + `Copy link` (`navigator.clipboard.writeText`), seated list in seat order with `Remove` (lobby) and a `no phone` tag, `Seat someone without a phone`, night-check line ("Night check on/off…"), `Deal characters` (5–15).
- Gear menu (a `<details>` in the top bar): night check toggle → `set_night_check {on}`; seconds a seat select (2–5, stored in `localStorage["tb_seat_seconds"]`, passed to `start_clock`); mute toggle; `End the game early` (good/evil) during night/day; `Change script` when allowed.
- `stmodel.lobbyModel(v) -> {canDeal: bool, why: string, seated: [{pid, name, phone, seat}]}`.

- [ ] **Step 1: Test** `lobbyModel`: 4 players → `canDeal false, why "needs 5 to 15 players; 4 seated"`; 6 → `canDeal true`.
- [ ] **Step 2: Run** → FAIL (`lobbyModel is not a function`).
- [ ] **Step 3: Implement** the model function, the picker, the lobby card, the gear.
- [ ] **Step 4: Run** `node --test static/` → PASS; `uv run pytest -q` → still 113 passed.
- [ ] **Step 5: Walkthrough:** fresh page → picker → pick Bad Moon Rising → lobby shows "Bad Moon Rising" in the top bar; toggle night check off in the gear → `/api/st` shows `night_check false`.
- [ ] **Step 6: Commit** — `feat(grimoire): script picker, lobby card, settings`.

---

### Task 3: Token drawer

**Files:** `static/storyteller.js`, `static/storyteller.html`, `static/stmodel.js`, `static/stmodel.test.js`

**Interfaces:**
- Clicking a token (outside a running clock and outside pick modes) sets `selected = pid`, `view = "drawer"`; the right column renders the drawer over the ledger with `← Back` and `✕` (Esc closes).
- `stmodel.drawerModel(p, v, C) -> {name, seat, role: {id, name, kind, team, ability}, thinks: string | null, status: [{key, label, on, action: {name, body}}], ability: {title, state, kind: "shoot" | "gossip" | "moonchild" | "none", note}, reminders: [{text, cls}], options: [string], exempt: bool, showExempt: bool, thread: [...], changeCharacter: [{id, name}]}`:
  - status toggles: `Alive` → `kill {pid}` / `revive {pid}`; `Poisoned`, `Drunk`, `Protected` → `set_reminder {pid, text, on}`; `Ghost vote` (dead only) → `set_ghost_vote`.
  - `ability.kind`: `"shoot"` when `character === "slayer"` and `!used` and phase day; `"gossip"` when gossip and phase day; `"moonchild"` when moonchild, dead and no pick yet (`v.script_state` is not exposed: use `v.announcements` containing "the Moonchild, chooses" as the "picked" signal); else `"none"`.
  - `options` = the script's reminders for this character (`C[character].reminders`) then the global set `["poisoned", "drunk", "protected", "dead vote"]`, minus chips already on.
- Drawer actions: shoot → a row of target buttons (alive players except self) + `Resolve the shot` → `day_ability {pid, options: {target, recluse_as_demon}}` (checkbox "The Recluse registers as the Demon"); gossip → `True` / `False` → `day_ability {pid, options: {true}}`; moonchild → target row → `day_ability {pid, options: {target}}`.
- Reminders: `+ Reminder` opens the option chips; `✕` on a chip → `set_reminder off`.
- Night check: `Exempt from the night check` checkbox → `set_exempt` (only when `v.night_check`).
- Thread: the last 6 entries of `v.threads[pid]` as bubbles (`them` = player, `me` = Storyteller) + composer; at night the primary button is `Hold until dawn` (`message {pid, text}`), secondary `Send now` (`message {..., now: true}`); by day `Send`. Opening the drawer posts `read_thread {pid}` once per open when any player entry is unseen.
- Change character: a collapsed `<details>` with a select of `C` and `Change` → `set_character`.

- [ ] **Step 1: Tests** for `drawerModel`: Slayer unused by day → `ability.kind === "shoot"`; dead Butler → status includes `Ghost vote`; reminders options exclude chips already on; thread order oldest first.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `node --test static/` → PASS.
- [ ] **Step 5: Walkthrough:** open a token → toggle Poisoned → chip appears under the token; shoot with the Slayer at the Imp → "Good wins"; send a message and see it in `/api/state?token=…` thread.
- [ ] **Step 6: Commit** — `feat(grimoire): token drawer with abilities, reminders and thread`.

---

### Task 4: Night ledger

**Files:** `static/storyteller.js`, `static/storyteller.html`, `static/stmodel.js`, `static/stmodel.test.js`

**Interfaces:**
- `stmodel.nightCards(v, C, openStep) -> {cards: [...], notTonight: [{title, why}], phones: {done, total, waiting: [names], show: bool}, secondRound: {show, done, blocked}, dawn: {deaths: [{name, cause, linked}], pending: [{index, name, why}], held, blocked, waiting}}`. A card: `{i, title, who, state: "done" | "skipped" | "open" | "upcoming", pill: {text, cls}, hint, result, controls}` where `state === "open"` for exactly one card: `openStep` if it is not done and applies, else the first not-done applying step. `controls` by `kind`:
  - `choose`: `{selects: n (or 0..n when variable), values: s.answer ?? s.choices, status: "waiting" | "picked" | "none", askAgain: bool, options: [...]}` with `options` the extra inputs per key: `imp` → redirect + heir selects; `innkeeper` → "Who is drunk" select of the two picks; `sailor` → "Who is drunk" (Sailor or the pick); `gambler` → character select; `shabaloth` → "Regurgitate" select of last night's victims (the names in the previous Shabaloth card's result, else none); `po` → a `nobody` checkbox and 1 or 3 selects.
  - `info`: `{text: s.suggestion, impaired: s.impaired, primary: "Work out their info" | "Hold for dawn"}` — first click posts `resolve` with no choices, second `send {step, text}`.
  - `storyteller`: `{question, inputs}`: tinker → `Yes` / `No` (`resolve {step, choices: [], dies}`); gossip → target select → `resolve {..., dies: pid}`; courtier → character select → `resolve {..., character}`; moonchild → `Apply`.
  - `meeting`: `{text: s.suggestion, primary: "Done"}` (resolve then send as today).
  - Every card: `Skip` → `finish_step {step, done: true}`; a done card's line has `Reopen`.
- Not tonight: steps with `applies === false` (why: "dead", "sleeps tonight", "ability used", "nobody died today", "no statement", "the Exorcist") — derive from `C[key].uses`, `v.players[].alive`, `v.died_today`? (not exposed: use "sleeps tonight" when nothing more specific is known).
- Keyboard: `Enter` triggers the open card's primary button, `↓`/`↑` move `openStep`, `S` skips — only when focus is not in an input.
- Phones strip and `Stop waiting` (`stop_waiting`); second round button (`second_round`) with `blocked` when waiting; dawn card: deaths list (linked ones indented), pending deaths with `Dies` / `Survives` → `confirm_death {index, dies}`, held count, `Deliver everything and start day N` → `start_day` (disabled while `blocked`).

- [ ] **Step 1: Tests:** `nightCards opens the first undone applying step` (steps [done, applies-false, undone] → card 3 open); `nightCards keeps the open card's draft` (openStep=1 not done → stays open even if a later step is also open-able); `nightCards lists not tonight`; `dawn blocked while phones wait and night check on`; `po controls need three selects after a nobody night` (previous Po card result "nobody" → `selects 3`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** model + rendering + keyboard.
- [ ] **Step 4: Run** `node --test static/` → PASS.
- [ ] **Step 5: Walkthrough (BMR, 7 phones via curl):** night 1: resolve Sailor, Courtier (character), Godfather info; stop waiting; dawn. Night 2: Exorcist picks the Demon → Demon card collapses; Po "nobody"; Assassin kill → appears in the dawn list; deliver.
- [ ] **Step 6: Commit** — `feat(grimoire): night ledger`.

---

### Task 5: Day ledger: hands, nominations, abilities, dusk

**Files:** `static/storyteller.js`, `static/storyteller.html`, `static/stmodel.js`, `static/stmodel.test.js`

**Interfaces:**
- `stmodel.dayModel(v, C) -> {announcements, hands: [{pid, name}], nominations: [{i, text, state: "idle" | "countdown" | "running" | "paused" | "done" | "recorded", tally, threshold, locked: [{name, yes}], pending: [{name, up, ghost}], butlerWarn: string | null, votes}], abilities: [{pid, name, label, kind}], dusk: {text, pending: [...], mastermind: bool, canEnd: bool}}`.
- Hands list: `Nominate…` sets `mode = "nominee"` with that nominator; `Lower` → `set_hand {pid, up: false}`. With no hand: "Click who nominates, then who they nominate" — clicking tokens in `mode` picks nominator then nominee → `nominate {nominator, nominee, spy_as_townsfolk}` (the Spy checkbox stays in the card).
- Nomination card controls by state: idle → `Start the clock` (`start_clock {nomination, seat_seconds}`); countdown/running → `Pause`, `Restart`, `Stop`; paused → `Resume`, `Restart`, `Stop`; done → voters, `Re-record` (the chips toggle into `record_votes` as today); the Slayer form from today's page is gone (drawer).
- While a clock is live (`v.clock.state` not `done`/null), clicking a token posts `set_hand {pid, up: !hands.includes(pid)}` instead of opening the drawer.
- Abilities today: from `v.players` where `ability.uses` is `day` and `!used` (Slayer → opens the drawer at the ability block), gossip (`True`/`False` inline), a dead Moonchild without a pick.
- Dusk card: top nominee and whether they reach `threshold`, pending executions (`confirm_death`), "The game goes on for one more day" banner when the announcements say so, `End the day` → `end_day`.

- [ ] **Step 1: Tests:** `dayModel builds the butler warning when the master's hand is down`; `dayModel marks the nomination recorded after votes`; `dayModel lists the Slayer once and not after use`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `node --test static/` → PASS.
- [ ] **Step 5: Walkthrough (TB, 7 phones):** raise two hands via `/api/hand`; nominate from the list; start the clock at 2 s; click a token during the clock → its hand toggles, the drawer does not open; after it finishes the tally matches `/api/st`; click a token → the drawer opens; end the day.
- [ ] **Step 6: Commit** — `feat(grimoire): day ledger with hands and the clock controls`.

---

### Task 6: The clock at the centre, and sound

**Files:** `static/clockmath.js`, `static/clockmath.test.js`, `static/sound.js`, `static/storyteller.js`, `static/storyteller.html`

**Interfaces:**
- `clockmath.js` exports: `seatAngle(n, i) -> deg` (−90 + i·360/n); `offset(seatPids, nomineePid, pid) -> 1..n`; `elapsed(clock, now) -> s`; `handIndex(clock, now) -> int`; `handAngle(seatPids, clock, now) -> deg` = seatAngle(nominee) + min(max(elapsed, 0) / seat_seconds, n) · 360/n, and never less than the angle of the last locked seat (`max` over `clock.locked` keys); `secondsUntil(seatPids, clock, now, pid) -> number | null` (null when locked); `serverNow(view, receivedAtMs, nowMs) -> s` = `view.server_time + (nowMs − receivedAtMs)/1000`.
- `sound.js` exports `sound` with `unlock()` (creates the AudioContext on the first gesture), `chime()` (two short tones, 880 → 1320 Hz, 120 ms each), `tick()` (one 30 ms 1760 Hz blip), `buzz()` (`navigator.vibrate?.(200)`), `mute(bool)`, `muted()` (from `localStorage["tb_mute"]`). All no-ops when muted or before `unlock()`.
- The page renders the dial at the circle centre during a live or just-finished clock (mockup `ST-Day` / `Play · A vote`): hand rotated by `handAngle`, redrawn by a 100 ms timer between polls, the 3-2-1 countdown while `handIndex < 0`, "N so far · T to execute". When `handIndex` changes from −1 to 0 the page calls `sound.chime()`; on every later increment `sound.tick()`; nothing when muted.

- [ ] **Step 1: Tests** (`static/clockmath.test.js`): `offset puts the nominee last`; `handIndex is negative during the countdown`; `handAngle never exceeds the last locked seat` (locked seat 3 but `now` earlier → angle of seat 3); `secondsUntil is null once locked`; `serverNow adds the local delta`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** maths, sound, dial rendering, the timer, the tick/chime trigger.
- [ ] **Step 4: Run** `node --test static/` → PASS.
- [ ] **Step 5: Walkthrough:** start a clock; the hand sweeps; pause → stops; resume → continues; the console shows one chime at go and one tick per seat (log calls while verifying, then remove the log); mute → silent.
- [ ] **Step 6: Commit** — `feat(grimoire): vote clock dial and sound`.

---

### Task 7: Messages view, keyboard, undo cost, over screen

**Files:** `static/storyteller.js`, `static/storyteller.html`, `static/stmodel.js`, `static/stmodel.test.js`, `README.md`

**Interfaces:**
- Top bar unread button → `view = "messages"`: a list of players with their last entry and an unread count, sorted unread first; clicking one opens the drawer at the thread. The `note` chip on tokens stays.
- Keyboard: `Ctrl/Cmd+Z` undo (as today), `Esc` closes drawer/messages, `Space` starts/pauses the clock when a nomination card is open and focus is not in a field.
- Undo button + cost text as today (`u.seen`, `u.phone_picks`).
- Over: verdict, reason, `New game, same players` (`reset`), `Change script` (reset then clear the picker flag).
- `stmodel.messagesModel(v) -> [{pid, name, last, unread}]`.
- README: replace the "Flow" section's Storyteller paragraphs with the new flow (script, lobby, night ledger, day with the clock, drawer) in the same voice and length.

- [ ] **Step 1: Test** `messagesModel sorts unread first`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `node --test static/` and `uv run pytest -q` → PASS.
- [ ] **Step 5: Walkthrough:** send a note from a phone → unread badge → messages view → drawer → seen on the phone's `/api/state`; undo after `start_clock` shows the cost line; declare a winner → over screen → new game.
- [ ] **Step 6: Commit** — `feat(grimoire): messages view, keyboard, over screen; README`.

---

## Self-review notes

- Spec coverage: §6.1 (T1), §6.2 (T1, T2, T7), §6.3 (T1, T5), §6.4 (T3), §6.5.1–2 (T1, T2), §6.5.3 (T4), §6.5.4 (T5), §6.5.5 (T7), §6.6 (T2, T3, T4), §6.7 (T7), §6.8 (T4, T7), §7.2 rendering + §7.3 grimoire sound (T6), §10 lobby link (T2).
- Names shared across tasks: `tokenMarks`, `drawerModel`, `nightCards`, `dayModel`, `messagesModel`, `clockmath.*`, `sound.*`, `mode`, `view`, `selected`, `openStep`.
- Proportion: shorter than the page it describes; bodies omitted.
