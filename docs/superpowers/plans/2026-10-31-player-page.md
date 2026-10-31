# Player page — implementation plan (3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the player page with the one in the spec: a thread with the Storyteller, a town square with raised hands and the vote clock, the character and almanac tabs, a laptop two-column layout, and vibration/sound for votes.

**Architecture:** One page (`static/player.html`, markup + CSS) and two modules: `static/pmodel.js` (pure: view JSON → render data, `node --test`) and `static/player.js` (poll `/api/state?token=`, render string templates, post actions). It shares `static/clockmath.js` and `static/sound.js` with the grimoire (plan 2). No server change.

**Tech Stack:** Vanilla HTML/CSS/JS (ES modules), Node 24 `node --test`, Playwright MCP browser at 390 px and 1280 px for walkthroughs.

**Spec:** `docs/superpowers/specs/2026-10-31-ui-revamp-design.md` §7.3, §7.4, §8 (all), §10; mockups: bottom row of the canvas (`P-Messages`, `P-Vote`, `P-Square`, `P-Desktop`) and the phone half of "Play · A vote".

## Global Constraints

- Phone first: 390 px wide works with no horizontal scroll; bottom tabs in thumb reach; the hand button ≥ 72 px tall. At ≥ 900 px the layout is two columns with no tabs.
- Every nudge is identical on every phone (the night banner, the buzz); nothing on screen reveals that this player has something to do.
- Hidden-until-revealed: the token and the thread content are masked until tapped and hide again after 45 s (`armHide()` as today). The composer and the vote button are never masked.
- Audio only after a gesture (`sound.unlock()` on the first tap anywhere); vibration via `sound.buzz()`. Chime/vibrate once at "go"; one tick per seat the hand passes, on phone and laptop alike.
- The page never computes locks or tallies; it renders `v.clock` and posts `/api/hand`.
- Keep `localStorage["tb_token"]`, `tb_seen`, `tb_buzz` as today.
- Work on branch `sn/revamp/player` off `sn/revamp/grimoire`; one commit per task.

## Review Focus

1. A player whose hand toggle is refused ("The clock has passed you" / "No vote left") must see that text under the button, and the button must reflect the server's state on the next poll, not the tapped state — Task 5 walkthrough step 3.
2. The night banner and the vibration must fire for every living player at the same `buzz`, including players with nothing to do — Task 1 test `nudge is the same with or without a prompt`.
3. Dead players must not get the nominate hand button enabled; dead players with a ghost vote must get the vote button during a clock — Task 4/5 test `handButton states`.
4. The thread must keep the prompt card visible until answered even when new messages arrive, and never show a slip before dawn — Task 3 test `thread groups by label and keeps the open prompt last`.
5. On a laptop, Space toggles the hand only when the vote screen is showing and focus is not in the composer — Task 5 walkthrough step 5.

---

### Task 1: Shell, tabs, join, nudge, privacy

**Files:**
- Rewrite: `static/player.html` (markup + CSS; `<script type="module" src="/static/player.js">`)
- Create: `static/player.js`, `static/pmodel.js`, `static/pmodel.test.js`

**Interfaces:**
- `player.js` state: `token`, `state` (last view), `chars`, `view` (`"character" | "messages" | "square" | "almanac"`), `revealed`, `hideAt`, `picks`, `tapSeq`, `draft`, `error`, `lastBuzz`, `receivedAt`.
- `pmodel.js` exports: `nudge(v, me, revealed) -> {show: bool, title: string, text: string}` — show when not revealed and (night and me.alive) or unread Storyteller entries or an unanswered prompt; title "Night N" / "Dawn"; text "Everyone does this: shield your screen and open your token."; `tabs(v, me, view, seenCount) -> [{id, label, current, fresh}]` (`fresh` on Messages when Storyteller entries > seenCount, on Square when a clock is live or hands changed); `layout(width) -> "phone" | "laptop"` (≥ 900 → laptop).
- Join screen as today (`/api/join`), with the script name as the title and "This game has started…" when not in the lobby.
- Laptop layout: left column Character + Square, right column Messages; Almanac as a panel over the right column.

- [ ] **Step 1: Tests** (`static/pmodel.test.js`): `nudge is the same with or without a prompt` (two `me` objects, one with a prompt, same `show/title/text`); `tabs marks messages fresh`; `layout(899) phone, layout(900) laptop`.
- [ ] **Step 2: Run** `node --test static/` → FAIL.
- [ ] **Step 3: Implement** the model, the shell, tabs, join, nudge banner, `armHide`/`tickHide`, the buzz → `sound.buzz()` and audio unlock on first tap.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Walkthrough (390 px and 1280 px):** join, see the lobby text; after the Storyteller starts the game the banner appears on both viewports; phone shows tabs, laptop shows two columns.
- [ ] **Step 6: Commit** — `git checkout -b sn/revamp/player && git add static/ && git commit -m "feat(player): shell, tabs, join, nudge"`.

---

### Task 2: Character tab

**Files:** `static/player.js`, `static/player.html`, `static/pmodel.js`, `static/pmodel.test.js`

**Interfaces:**
- The flip token and auto-hide as today; under the ability text a line from `me.ability` when `uses` is `day`, `on_nomination` or `once_per_game`: "Your <ability> is unused" / "used" (`pmodel.abilityLine(me, chars) -> string | null`).
- Revealing the token also unmasks the thread (one gate, §8.4).

- [ ] **Step 1: Test** `abilityLine`: Slayer unused → "Your shot is unused"; Empath → null.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Walkthrough:** reveal → ability line; wait 45 s (or set the timer to 3 s in the console) → hides.
- [ ] **Step 6: Commit** — `feat(player): character tab`.

---

### Task 3: The thread

**Files:** `static/player.js`, `static/player.html`, `static/pmodel.js`, `static/pmodel.test.js`

**Interfaces:**
- `pmodel.thread(me, v, chars) -> [{kind: "header", text} | {kind: "st" | "me", text, seen} | {kind: "card", card: {...}}]` grouped by `label` (one header per run of entries with the same label), prompt card last when `me.prompt` is unanswered: `choose` → `{type: "choose", text, count, options: [{pid, name, dead}], allow_self}`; `tap` → `{type: "tap", text, target, options}`; answered prompts collapse to a `card` `{type: "done", text: "Done, keep your phone close until dawn."}` (tap) or an outgoing bubble "You chose A and B" (choose, derived from `prompt.answer`).
- Rendering: incoming bubbles parchment left with the seal glyph; outgoing felt right with `Sent` / `Seen` under the last outgoing; the whole scroll area masked until revealed (`.masked` blurs and shows "Tap to read"); composer at the bottom posts `/api/message {token, text}`; empty state text from the spec.
- Choose card: seat chips with `aria-pressed`, `Confirm choice` → `/api/choose`; tap card: the 3-sequence + 6-grid exactly as today's `tapTask`, → `/api/tap`.
- Unread badge: Storyteller entries beyond `tb_seen`; opening the Messages tab while revealed updates `tb_seen`.

- [ ] **Step 1: Tests:** `thread groups by label and keeps the open prompt last`; `thread turns an answered choose prompt into an outgoing bubble`; `thread marks seen on the last outgoing only`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Walkthrough:** night 1 as the Poisoner: the choose card; pick, confirm → "You chose …"; the Storyteller sends a message → bubble; reply → `Sent`; the Storyteller opens the drawer → `Seen`.
- [ ] **Step 6: Commit** — `feat(player): message thread`.

---

### Task 4: The square and raised hands

**Files:** `static/player.js`, `static/player.html`, `static/pmodel.js`, `static/pmodel.test.js`

**Interfaces:**
- `pmodel.square(v, me) -> {seats: [{pid, name, no, alive, me, hand, dead, ghost}], centre: {big, small}, today: [string], nominations: [{text, note}]}` (centre: votes-to-execute by day, alive count otherwise).
- `pmodel.handButton(v, me) -> {label, pressed, disabled, hint}`: no clock → nominate button: label "Raise hand to nominate" / "✋ Hand up", disabled when dead ("Dead players cannot nominate"), hint "The Storyteller sees your hand and calls on you."; during a clock → Task 5.
- Button posts `/api/hand {token, up}`; errors show under the button; the next poll sets `pressed` from `v.hands` (not from the tap).

- [ ] **Step 1: Tests:** `handButton states` (alive no clock → enabled; dead no clock → disabled with the reason; hand in `v.hands` → pressed).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Walkthrough:** raise a hand → the grimoire's Hands list shows it; the Storyteller nominates from it → the hand lowers on the phone.
- [ ] **Step 6: Commit** — `feat(player): town square and hands`.

---

### Task 5: The vote screen

**Files:** `static/player.js`, `static/player.html`, `static/pmodel.js`, `static/pmodel.test.js`

**Interfaces:**
- When `v.clock` is live (`state` not null/`done`, or `done` within the last 10 s) the Square tab becomes the vote screen (phone: automatically switches `view` to `square` once per clock; laptop: the square panel): nominator/nominee title, tally "N so far · T to execute", the ring with the dial (`clockmath.handAngle`, 100 ms timer, countdown digits while `handIndex < 0`), seat marks (✓ / – / ✋ / nominee), own seat highlighted.
- `pmodel.handButton` during a clock → `{label: "✋ Hand up" | "Raise hand", pressed: v.clock.hands includes me, disabled: locked or (dead without ghost vote), hint}` with hints: countdown → "The clock is about to start."; running and not locked → "The hand reaches you in N s." (`clockmath.secondsUntil`), prefixed by "Your Master's hand is down: yours won't count. " when `me.role.id === "butler"` and the master's pid (the seat with chip "master" is not exposed to players — use `v.clock.hands` includes the pid the page remembers from last night's Butler choice `prompt.answer`, stored in `localStorage["tb_master"]`); locked yes → "Hand up, counted."; locked no → "Hand down, not counted."; dead with ghost vote → label "Use my last vote".
- Laptop: `keydown` Space when `view === "square"`, a clock is live and `document.activeElement` is not an input/textarea → same as tapping.
- Sound: on the poll/timer where `handIndex` goes from −1 to 0: `sound.buzz()` and `sound.chime()`; each later increment: `sound.tick()`.

- [ ] **Step 1: Tests:** `handButton during a clock` (locked → disabled with "counted"; ghost vote label; butler hint when master down).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `node --test static/` → PASS.
- [ ] **Step 5: Walkthrough (two phones in two Playwright tabs + the grimoire):** start a clock at 2 s; both phones show the countdown then the sweeping hand; raise a hand on one phone → ✋ on both and on the grimoire; after the hand passes it, the button disables with "Hand up, counted."; toggling late shows "The clock has passed you"; on the 1280 px tab Space toggles the hand only on the square view.
- [ ] **Step 6: Commit** — `feat(player): vote screen with the clock, sound and vibration`.

---

### Task 6: Almanac, laptop polish, README

**Files:** `static/player.js`, `static/player.html`, `README.md`

**Interfaces:**
- Almanac grouped by type for the current script (as today, from `/api/characters`).
- Laptop: the Almanac link in the header opens it as a panel over the right column with a close button.
- README "Flow" players' side: join, the thread, hands, the clock; note the sounds (chime at go, ticks) and that phones vibrate.

- [ ] **Step 1: Walkthrough** at 390 and 1280 px through a whole TB game (lobby → night 1 → day 1 vote → night 2 → day 2) with no console errors; `node --test static/` and `uv run pytest -q` pass.
- [ ] **Step 2: Commit** — `feat(player): almanac, laptop layout; README`.

---

## Self-review notes

- Spec coverage: §8.1 (T1, T6), §8.2 (T1), §8.3 (T2), §8.4 (T3), §8.5 (T4, T5), §8.6 (T6), §7.3 (T5), §7.4 (grimoire side, plan 2), §10 (T1 join link copy is the Storyteller's).
- Shared names: `pmodel.*`, `clockmath.*`, `sound.*`, `view`, `revealed`, `armHide`.
