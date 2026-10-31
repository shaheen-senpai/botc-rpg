# Grimoire and player UI revamp — design

Date: 2026-10-31. Status: draft for review. Mockups: https://claude.ai/artifact/384QePRwoMXyiYkVvKDDk5 (top row: script picker, lobby, night ledger, day with the vote clock, token drawer; bottom row: phone messages, phone vote, phone square, laptop player page).

## 1. Intent

The app runs Blood on the Clocktower from a laptop. Today it only knows Trouble Brewing, assumes everyone is in one room, and has grown by accretion: the Storyteller's ledger is a long scrolling column where night steps, setup fields, nominations, Slayer forms, an inbox and a log all compete; the player page shows the Storyteller's words as a pile of "slips" rather than a conversation.

This revamp restructures both screens around how a game is actually run:

- The Storyteller spends the game looking at the circle and doing one thing at a time (resolve this step, start this vote, answer this player). The grimoire shows that one thing, and nothing else, prominently.
- Players spend the game waiting, then acting fast (pick a player, raise a hand). Their page is a calm two-person conversation with the Storyteller plus one big control when it is their moment.
- Games are played in a room or fully remote (Storyteller included), on phones or laptops, with Trouble Brewing or Bad Moon Rising.

## 2. Goals, non-goals, anti-goals

Goals

1. Script choice before the lobby: Trouble Brewing or Bad Moon Rising. Night order, abilities, reminders and setup rules come from script data, not from code written per script.
2. A night ledger that shows only tonight's steps, in order, with one primary action per step, and handles multiple deaths a night.
3. Ability usage visible on the token and recorded with one obvious action (Slayer shoots, Gossip was true, Professor resurrects), never through a generic form.
4. The tap challenge ("night check") becomes a setting: on or off per game, exempt per player, and the Storyteller can always stop waiting.
5. Voting in the app: a clock hand sweeps clockwise from the nominee, players raise a hand that locks as the hand passes. Players raise a hand to ask to nominate; the Storyteller starts the clock.
6. A per-player message thread with the Storyteller that reads like SMS: incoming and outgoing bubbles, prompts inline, delivered/seen state. No toasts or notification piles.
7. The player page works at phone width and in a laptop browser.

Non-goals

- Scripts beyond Trouble Brewing and Bad Moon Rising (the data model must allow adding one as data, but no third script ships).
- Travellers and Fabled.
- Voice or video. Remote games use whatever call the group already has.
- Accounts, history, or persistence across a server restart. Game state stays in memory.
- A phone-sized Storyteller layout. The grimoire targets a laptop (≥1024 px); tablet landscape should work, phone is not supported.

Anti-goals (would make this a failure even if it works)

- Anything on a player's screen that singles them out to a neighbour: every phone gets the same nudge at the same moment, whether or not that player has something to do.
- The Storyteller scrolling past steps that do not apply tonight, or hunting for the step that is waiting on a phone.
- A vote that disagrees between screens: the hand position and which seats are locked are computed from the server's clock, never from each client's timer.
- Chat that behaves like a notification feed (toast, then gone). Everything said stays in the thread.

## 3. Constraints

- Stack stays: FastAPI server, in-memory `Game`, two static HTML pages, JSON polling (1–1.5 s). No build step, no framework. Polling is fine for the vote clock because the clock is time-based (see §7).
- Look stays: the current theme (`static/theme.css`): plum felt at night, verdigris at day, parchment paper, brass buttons, Grenze Gotisch display + Alegreya Sans body, the seal-style tokens. This is a restructure, not a rebrand.
- Remote play means the server is reachable from the internet. How (tunnel, VPS) is the Storyteller's business and out of scope; the app only needs to show a shareable join link and not assume the LAN IP.
- The existing undo (30 steps, warns when phones already saw the result) must keep working for every Storyteller action, including vote actions.
- Rule logic that exists for Trouble Brewing (Virgin, Slayer, Soldier, Mayor, star-pass, Scarlet Woman, ghost votes, win checks) keeps its behaviour.

## 4. Vocabulary

- Script: Trouble Brewing (TB) or Bad Moon Rising (BMR). One per game.
- Token: a seat on the circle: player, character, alive/dead, reminders, ability state.
- Reminder: a small chip under a token (`poisoned`, `protected`, `drunk 2`, `survives execution`, `grandchild`). Some are placed by the app when a step resolves, any can be placed or removed by the Storyteller.
- Ledger: the right-hand column of the grimoire. Shows the current phase's work only.
- Step: one entry in tonight's night order (one character, or "Minions meet the Demon").
- Thread: the message conversation between one player and the Storyteller.
- Hand: a player's raised hand. Outside a vote it means "I want to nominate"; during a vote it means "yes".
- Clock: the vote in progress: a hand that sweeps from the nominee, one seat per tick, locking seats as it passes.
- Night check: the tap challenge (tap three icons in order) that every phone gets at night so real choices do not stand out.

## 5. Scripts as data

Each script is a data module (`scripts/trouble_brewing.py`, `scripts/bad_moon_rising.py` or JSON) declaring, per character:

- `name`, `type` (townsfolk/outsider/minion/demon), `ability` (holder text), `summary` (almanac line), icon id.
- `first_night`, `other_night`: order numbers (0 = does not act). Trouble Brewing and Bad Moon Rising orders are in Appendix A.
- `night_kind`: how the step resolves. One of:
  - `info`: the app works out the truthful answer (Washerwoman, Empath, Chambermaid, Grandmother, Godfather's outsiders).
  - `choose(n, allow_self, prompt)`: the player picks on their phone; the Storyteller applies (Poisoner, Imp, Monk, Innkeeper, Pukka, Po, Shabaloth, Gambler = choose 1 + a character guess).
  - `storyteller`: no phone prompt; the Storyteller decides from the card (Tinker might die, Gossip's statement was true, Lunatic's fake attack).
  - `meeting`: Minions meet the Demon / Demon meets Minions (first night only, 7+ players).
- `uses`: `each_night`, `once_per_game`, `passive`, `day`, `on_death`, `on_nomination`. Drives the ability block (§6.4) and the ability pip on the token.
- `reminders`: chips this character can place (from the script's reminder list), e.g. Courtier: `drunk 3`, `drunk 2`, `drunk 1`, `no ability`; Devil's Advocate: `survives execution`; Zombuul: `died today`, `dead`.
- `setup`: adjustments to the bag (Baron +2 outsiders, Godfather ±1 outsider, Drunk's believed character, Lunatic's believed demon, Fortune Teller red herring).
- `hint`: one line for the Storyteller shown on the step card (today's `HINTS` table, extended for BMR from the official night sheet reminder text).

The game engine resolves steps generically from `night_kind` and `uses`; character-specific rules that cannot be expressed as data (Zombuul registers as dead, Shabaloth regurgitation, Exorcist blocks the Demon, Mastermind's extra day, Minstrel's drunk day, Tea Lady, Fool, Pacifist, Sailor cannot die, Grandmother's linked death, Moonchild's pick) live in a per-script rules module with a small, named hook surface: `on_death(player, cause)`, `may_die(player, cause) -> bool | "ask"`, `before_dawn()`, `on_execution(player)`, `extra_day_after_demon_death()`. "ask" means the Storyteller confirms on the dawn card (§6.5.3) instead of the rule deciding alone.

## 6. The grimoire (Storyteller)

### 6.1 Layout

Three zones at ≥1024 px:

```
┌──────────────────────────────────────────────────────────────────────┐
│ Top bar: script · Night 2 · 7 of 9 alive · phones 6/8 · Undo · ⚙     │
├──────────────────────────────────────────┬───────────────────────────┤
│                                          │ Ledger (phase work)       │
│          The circle                      │ or                        │
│   tokens + reminders + ability pips      │ Token drawer (slides over │
│   centre: phase card / vote clock        │ the ledger, ← back)       │
│                                          │                           │
└──────────────────────────────────────────┴───────────────────────────┘
```

- The circle keeps the space it has now (square, `min(100%, 100vh - top bar)`), tokens around a ring, seat numbers, nameplates, reminder chips.
- The ledger is a fixed 30 rem column, scrolls on its own.
- Selecting a token opens the token drawer in the same column, over the ledger, with a back arrow and Esc to close. The circle centre is never covered: it holds the phase card (night/day number, alive count, votes to execute) and, during a vote, the clock.
- Under 1024 px the ledger drops under the circle (as today); this is the tablet fallback, not a target.

### 6.2 Top bar

Left to right: script name, phase and number (Night 2 / Day 2), alive count, phones state at night ("6 of 8 phones done" with the waiting names on hover and a `Stop waiting` button when any are pending), unread messages count (opens the Messages view, §6.7), Undo (label + cost warning as today), settings (gear): night check on/off for this game, vote seconds per seat (2–5, default 3), end the game early.

### 6.3 Tokens

Each token shows, as today, the character glyph and name, "thinks X" for the Drunk/Lunatic, dead shroud, and the `lit` ring when its step is next. Added:

- Ability pip at the token's lower-right: filled brass = unused once-per-game ability, hollow = used, none for each-night and passive abilities. Hovering names it ("Slayer: shot unused").
- Reminder chips under the nameplate, from the script's reminder list plus the global set (`poisoned`, `drunk`, `protected`, `dead vote`/`no vote`). Chips are coloured by what they do: poison/drunk purple, protection brass, death-related oxblood, information lapis.
- During a vote: a raised hand shows as a brass ring, a locked yes as a filled brass dot, a locked no as nothing, "cannot vote" (no ghost vote) as a grey slash. Clicking a token during the clock toggles that player's hand (for players without a phone, or to overrule).
- During the day, when a player has raised a hand to nominate, the token shows a small hand badge, numbered by order raised.

Click selects (opens the drawer); drag reseats in lobby and setup, as today.

### 6.4 Token drawer

Replaces today's centre inspector. Sections, top to bottom, with the first two always visible and the rest collapsed by default:

1. Header: name, seat number, character glyph + name, team, "thinks they are X" if applicable, the ability text. Status chips as toggles: alive/dead, poisoned, drunk, protected, ghost vote spent/available. Toggling writes the matching reminder and game state (kill, revive, set poisoned...).
2. Ability block, driven by `uses`:
   - `once_per_game` day ability (Slayer): state line ("Unused") and one button: `Shoot…` → pick a target from a row of tokens → `Resolve`. After: "Shot Ben on day 2, nothing happened". Virgin: no button, state only ("Nomination effect unused"); it fires when nominated, as today.
   - `once_per_game` night ability (Assassin, Professor, Courtier): state only ("Unused · acts at night"). The night ledger prompts it; after use the pip hollows and the state reads "Used night 2: killed Dev".
   - `day` (Gossip): `Statement was true` / `false` buttons, available during the day; the chosen answer shows and feeds tonight's Gossip step.
   - `on_death` (Moonchild): when the player is marked dead, the drawer shows `Moonchild chooses…` with a token row; the pick is stored and shows on tonight's step card.
   - `passive` (Soldier, Fool, Tea Lady, Pacifist, Minstrel, Sailor, Mayor, Recluse, Spy, Mastermind): a state line only ("Fool: first death not yet used"). The rule hooks decide; where the rule says "might", the dawn or execution card asks.
   - `each_night`: "Acts each night · see the ledger", with the last result ("Night 2: picked Asha").
3. Reminders: current chips with × to remove, `+ Reminder` opens the script's list for this character first, then the global ones.
4. Night check: `Exempt from the night check` toggle (only when the game setting is on).
5. Thread with this player: the last few bubbles and a composer (§8.4 describes the bubbles). At night the primary send is `Hold until dawn`, secondary `Send now`; in the day it is `Send`.
6. Change character: a select and a button, collapsed; used for mistakes and for the Imp's star-pass when the app's choice should be overruled.

### 6.5 Ledger by phase

#### 6.5.1 Lobby

Join card: the join link (large, copyable) and the QR code; a note that remote players need the public link. Seated list in seat order with a drag handle (same as dragging on the circle). `Seat someone without a phone` (name field). Script badge with `Change script` (only while nobody is seated, otherwise it warns that changing it unseats nobody but re-deals). `Deal characters` enabled at 5–15 players.

Script choice is a step before the lobby: the Storyteller page opens on a script picker (two cards, Trouble Brewing / Bad Moon Rising, with their character counts and a one-line character of the script) and only then shows the lobby. The picker is also reachable from the gear when the lobby is empty.

#### 6.5.2 Setup

Counts line (Townsfolk/Outsiders/Minions/Demon) with the script's adjustments explained ("Godfather: +1 Outsider"). Warnings. Script-specific setup fields: TB: red herring, three bluffs with the legal-bluff rule. BMR: three bluffs; Lunatic's believed Demon (when a Lunatic is dealt). `Start the first night`, `Deal again`.

#### 6.5.3 Night: the night ledger

The ledger is a list of step cards in tonight's order. Rules:

- Only steps that apply tonight are listed in full. Steps that do not apply (character not in play, dead, first-night-only, once-per-game already used, Zombuul when someone died today) collapse into one line at the bottom: `Not tonight (6)` which expands to the names and the reason.
- Exactly one card is expanded: the first that is not done. Done cards collapse to one line with a ✓ and the result ("Poisoner → Asha"). Upcoming cards are one line. Clicking any line expands it; `Enter` applies the expanded card's primary action, `↓`/`↑` move.
- Card content: order number, character and player, status pill, the hint, the ability state if once-per-game, then the controls:
  - `choose`: "Waiting for their phone" / "Picked: Asha" with an `Ask again`; the pick(s) as selects the Storyteller can override; `Apply`.
  - `info`: the computed answer in an editable field with the "drunk or poisoned, may be false" flag when impaired; `Hold for dawn`.
  - `storyteller`: the question and the buttons ("Tinker dies tonight?" `Yes` / `No`; "Gossip's statement was true" shown from the day's answer with `A player dies…` target picker).
  - `meeting`: the lists to show; `Done`.
  - Every card has `Skip` (collapses as done with "skipped").
- Demon cards cover the BMR demons: Po shows "chose nobody last night: must pick 3 tonight" or "pick 1 or nobody"; Shabaloth shows two picks and `Regurgitate…` with last night's victims; Pukka shows the poison pick and "X dies tonight (poisoned last night)"; Zombuul is listed only when nobody died today and shows "registers as dead" when on its first death. The Imp keeps its Mayor-redirect and heir fields.
- Lunatic card (BMR): the Lunatic's phone gets the Demon's prompt; the card shows their picks and `Show the Demon` which puts the picks on the Demon's step card. Exorcist card: if the Exorcist picked the Demon, the Demon's card collapses to "Does not wake tonight (Exorcist)".
- Chambermaid: the answer is computed from which steps woke tonight (steps that applied and were not skipped), so it sits last and is `info`.
- Phones strip at the top of the ledger (only when the night check is on): "6 of 8 done", the waiting names, `Stop waiting`. `Stop waiting` releases the second buzz and dawn immediately for everyone still pending.
- Second round (as today, Imp/Demon kill triggers the second buzz; Ravenkeeper prompt).
- Dawn card at the bottom: tonight's deaths as a list with the cause ("Dev, Imp", "Gita, Assassin"), each with an override toggle for the rules that say "might" (Tea Lady, Fool, Pacifist are execution-time; at night: Tinker, Gossip, Moonchild, Sailor cannot die). Linked deaths show indented ("Grandmother dies: grandchild killed"). Held messages count. `Deliver everything and start day N`.

#### 6.5.4 Day

Top: announcements (as today). Then:

- Hands: the players with a hand up, in the order raised, each `Nominate` (sets them as nominator, opens the nominee picker) or `Lower`. Empty state: "Nobody has a hand up."
- Nominations list: each nomination is a card: "Asha nominates Ben", the state (not started / clock running / done) and the tally against the threshold. The open card holds the clock controls (§7.2): `Start the clock` (3-2-1 then go), `Pause`/`Resume`, `Restart`, `Stop`, seconds per seat. When the clock has finished: the voter names, `Record` is automatic; the Storyteller can still toggle any token's vote and `Re-record`.
- Day abilities: only the abilities that are available today, as one line each with their button (Slayer `Shoot…`, Gossip `True`/`False`, Moonchild's pending pick). Empty when none.
- Dusk card: who is executed (top tally, ties noted), execution-time confirmations (Pacifist "does the executed good player die?", Devil's Advocate "survives execution" shown, Virgin resolved earlier), Mastermind's extra day if applicable, `End the day`.

#### 6.5.5 Over

Winner, reason, `New game, same players` (returns to the lobby with the same script), `Change script`.

### 6.6 Night check settings

- Game setting (gear): `Night check: on / off`. Default on. Shown on the lobby card as a line ("Night check on: phones tap three icons at night. Turn off for remote games.").
- Per player: `Exempt from the night check` in the token drawer. Exempt phones still buzz and still get real prompts; they are not waited for.
- `Stop waiting` (top bar and phones strip) ends the wait for every pending phone at once. It is an undoable action.
- When the night check is off, the phones strip is hidden and the second buzz/dawn are never blocked.

### 6.7 Messages view

The unread count in the top bar opens a list of players with their last message and unread badge; selecting one opens that token's drawer at the thread. This replaces the inbox block in the ledger. A player message also raises a `note` chip on their token, as today.

### 6.8 Keyboard

`Ctrl/Cmd+Z` undo (as today). In the night ledger: `Enter` primary action, `↓`/`↑` move, `S` skip. During a vote: `Space` start/pause the clock. `Esc` closes the drawer.

## 7. Voting

### 7.1 Hands outside a vote

During the day, any living player can raise a hand; for dead players the button is disabled with "Dead players cannot nominate". It appears in the Storyteller's Hands list and on their token. The player can lower it. Hands clear when the Storyteller starts a nomination with them as nominator, or at dusk.

### 7.2 The clock

State on the server for the open nomination: `started_at` (server time), `seat_seconds`, `paused_at`, `paused_total`, `hands {pid: bool}`, `locked {pid: bool|null}`.

- `Start the clock`: a 3-2-1 countdown (3 s) on every screen, then the hand begins at the nominee and advances one seat clockwise every `seat_seconds`.
- Seats are numbered k = 1..n clockwise from the nominee; the nominee is seat n and votes last, after a full turn of the hand. Elapsed = now − started_at − paused_total (− (now − paused_at) while paused). Hand index = floor(elapsed / seat_seconds). Seat k is locked when hand index ≥ k. Every client renders from these numbers and the server time offset it measures on each poll, so screens agree to within a poll.
- Locking records the hand state at that moment. Raising or lowering a locked seat is refused ("The clock has passed you").
- Nominator and nominee are seats like any other.
- Pause freezes elapsed. Restart clears locks and hands. Stop abandons the vote (the nomination stays, unvoted).
- Finished when hand index ≥ number of seats. Tally = locked yes count; the app compares with the threshold and marks the nomination as today's top as it does now.
- Storyteller override: clicking a token during or after the clock toggles its hand/vote; after the clock, `Re-record`.

### 7.3 Players during the clock

- Phone: the Square tab becomes the vote screen automatically: the nominee and nominator named, the ring with the hand sweeping, their own seat highlighted, and one large bottom button `Raise hand` / `Lower hand` (≥72 px tall, in thumb reach) with the time until the hand reaches them ("locks in 6 s"). After lock: "Hand up, counted" or "Hand down".
- Laptop: the same screen; `Space` toggles the hand (held state is a toggle, not press-and-hold). The button shows the key hint.
- Dead with a ghost vote: the button reads `Use my last vote`; locking a yes spends it. Dead without: the button is disabled, "No vote left".
- Butler (TB): the hand only counts if the Master's hand is up when the Butler locks; the button shows "Your Master's hand is down" when it would not count.
- Sound and vibration, on every player device: when the clock starts (at "go", after the 3-2-1), a phone vibrates once and a laptop plays a short chime (laptops have no vibration); then every time the hand moves on to the next seat, every player device plays a short tick, phone or laptop. The ticks follow the server-timed hand position (§7.2), so they stay in step across devices. Browsers only allow audio after a user gesture: the page unlocks its audio context on the first tap (joining, any button) and keeps it ready. The Storyteller's grimoire ticks too, with a mute in the gear menu.

### 7.4 Without a phone

The Storyteller raises and lowers their hand by clicking the token. The clock does not wait for anyone.

## 8. The player page

### 8.1 Layout

- Phone (≤ 899 px): one column, bottom tabs in thumb reach: `Character`, `Messages` (unread badge), `Square` (badge when a vote is live or a hand queue changed), `Almanac`.
- Laptop (≥ 900 px): two columns. Left: Character on top, Square below. Right: Messages thread full height. Almanac opens as a panel over the right column. No bottom tabs; the three areas are visible at once.
- The nudge banner ("Night 2: everyone shield your screen and open your token") stays at the top of every tab, identical on every phone.

### 8.2 Join

Script name as the title, name field, `Take a seat`. If the game has started: "This game has started. Ask the Storyteller to add you to the next one."

### 8.3 Character

As today: the flip token, 45 s auto-hide, ability text, team. Added: once-per-game ability state ("Your shot is unused") when the script declares it; nothing for passives.

### 8.4 Messages: the thread

One conversation between this player and the Storyteller, newest at the bottom, composer at the bottom.

- Incoming (Storyteller) bubbles are parchment, left-aligned, with a small seal glyph. Night information, dawn slips ("Nothing to report tonight"), and replies are all incoming bubbles. A bubble carries its night/day label as a group header ("Night 2", "Day 2"), not a timestamp per bubble; several bubbles in the same phase share one header.
- Outgoing (player) bubbles are felt-deep, right-aligned, with state under the last one: `Sent` → `Seen` when the Storyteller has opened the thread (replaces today's "mark all read").
- Prompts are inline cards in the incoming column: "Choose a player" with the seat chips and `Confirm` (as today), after which the choice appears as an outgoing bubble ("You chose Ben") and the card collapses. The night check is also an inline card ("Tap these three in order"); when done it collapses to "Done, keep your phone close".
- Hidden until revealed: the thread content is masked (blurred, "Tap to read") under the same rule as the token and hides again after 45 s, so a phone on the table does not show a night slip. The composer is always usable.
- Composer: single field, 500 characters, `Send`. No subject, no labels.
- Empty state: "Nothing from the Storyteller yet. What you learn at night arrives here."

### 8.5 Square

The ring (seats, alive/dead, ghost votes, own seat marked), the alive count or votes-to-execute in the centre. Day: today's announcements, the nominations with tallies, and the `Raise hand` button (nominate). During a vote the ring shows the clock and the button becomes the vote control (§7.3). Night: alive count only.

### 8.6 Almanac

As today, for the current script.

## 9. Bad Moon Rising: what the UI must handle

| Character | UI handling |
| --- | --- |
| Grandmother | `info` first night (grandchild + character), reminder `grandchild`; linked death at dawn (shown indented). |
| Sailor | `choose 1` each night; reminder `drunk` on the Sailor or the pick; `may_die` always false (dawn/execution cards show "Sailor cannot die"). |
| Chambermaid | `info` each night, computed from steps that woke; last in order. |
| Exorcist | `choose 1` (different from last night, enforced); if the Demon: Demon card collapses, Demon told. |
| Innkeeper | `choose 2`; reminders `protected` ×2 and `drunk` on one (Storyteller picks which). |
| Gambler | `choose 1` + character guess on the phone; wrong guess → death at dawn. |
| Gossip | `day` ability: true/false buttons on the day ledger; night `storyteller` card picks who dies. |
| Courtier | `once_per_game` night: pick a character; reminders `drunk 3/2/1` counting down at each dawn. |
| Professor | `once_per_game` night: pick a dead player; Townsfolk → revived. |
| Minstrel | `passive`: when a Minion is executed, everyone drunk until next dusk (banner on the day ledger). |
| Tea Lady | `passive`: neighbours cannot die while both good; dawn/execution card shows the block. |
| Pacifist | `passive`: execution card asks "does the executed good player die?". |
| Fool | `passive`: first death skipped automatically, pip hollows. |
| Goon | `passive`: first chooser each night becomes drunk and the Goon takes their alignment; shown as a reminder and a team change on the token. |
| Lunatic | thinks they are a Demon (chosen at setup); gets Demon prompts; Lunatic card feeds the real Demon's card. |
| Tinker | `storyteller` card each night: "Tinker dies tonight?"; also killable any time from the drawer. |
| Moonchild | `on_death`: picker in the drawer when marked dead; night card kills the pick if good. |
| Godfather | `info` first night (outsiders); `storyteller` card other nights only when an Outsider died today; setup ±1 Outsider. |
| Devil's Advocate | `choose 1` (different from last night); reminder `survives execution`; execution card honours it. |
| Assassin | `once_per_game` night `choose 1`; kill ignores protection. |
| Mastermind | `passive`: Demon executed → one more day; banner "Mastermind day: an execution ends the game". |
| Pukka | `choose 1`: poison now, previous pick dies at dawn and is cured. |
| Shabaloth | `choose 2`; `Regurgitate…` one of last night's picks. |
| Po | `choose 0/1` or `choose 3` when last night was nobody. |
| Zombuul | listed only when nobody died today; first death → "registers as dead" (counts as dead for the table, token shrouded with a Zombuul mark, still acts). |

Several deaths a night are the norm, so the dawn card is a list, and announcements read "Dev, Gita and Hari died in the night."

## 10. Remote play

- The lobby shows the join link as text with a copy button; the QR stays for rooms.
- Night check default stays on; the lobby card says to turn it off for remote games. Nothing else differs: hands, clock and the thread already assume players are not in the room.
- Latency: the clock tolerates a poll of up to 1.5 s because locks are time-based. A player whose hand toggle arrives after the lock is told so in the button; the Storyteller can overrule from the token.

## 11. Left to the builder

- File layout and whether the player page stays one file. Reusing the current rendering approach (string templates + poll) is fine.
- Exact chip colours within the team palette; icon set for BMR characters: cut masks from `bad-moon-rising-almanac.pdf` (in the repo, one page, the official sheet by Rithwik) the way the TB icons were cut from `trouble-brewing-almanac.pdf`.
- How `Seen` is detected (opening the drawer at the thread is enough).
- Sound: none required.
- Whether `scripts/` is Python or JSON.
- Test strategy: the existing `test_game.py` style (rule tests on `Game`) extended per script; the clock's time maths tested with an injected clock.

## 12. Calls made after the builder check

The reviewer's only open question was where the Bad Moon Rising material comes from. Settled as:

- Ability text and icons: `bad-moon-rising-almanac.pdf` in the repo. `summary` is the sheet's official one-liner; `ability` (the holder's text) is a plain-English expansion in the style of `roles.py`.
- Night order, reminder chips and the Storyteller hints: the community Townsquare role data, `https://raw.githubusercontent.com/bra1n/townsquare/main/src/roles.json` (edition `bmr`; fields `firstNight`, `otherNight`, `reminders`, `firstNightReminder`, `otherNightReminder`). Vendor the 23 BMR entries into the script module; do not fetch at runtime. Hints are paraphrased from the reminder text, as TB's `HINTS` are.
- Appendix A is the oracle for the order; a test asserts the script module's order matches it.

## Appendix A: Bad Moon Rising night order

First night (characters that act): Lunatic (7+ players, shown fake Minions and bluffs; if their fake Demon acts, they act), Sailor, Courtier, Godfather (sees Outsiders), Devil's Advocate, Pukka, Grandmother, Chambermaid. Minion info and Demon info meetings come before Sailor as in TB (7+ players).

Other nights: Sailor, Courtier, Innkeeper, Gambler, Devil's Advocate, Lunatic, Exorcist, Zombuul, Pukka, Shabaloth, Po, Assassin, Godfather, Gossip, Professor, Tinker, Moonchild, Grandmother, Chambermaid.

Trouble Brewing keeps today's order (`roles.py`).

Source for the orders and reminder text: the official night sheet as encoded in the community Townsquare role data; the almanac PDF (`Bad Moon Rising`, by Rithwik) for ability text.
