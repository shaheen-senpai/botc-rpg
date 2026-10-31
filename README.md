# Trouble Brewing on the local Wi-Fi

A digital grimoire for Blood on the Clocktower: Trouble Brewing. The Storyteller runs a small server on
their laptop; every player joins from their phone on the same Wi-Fi.

## Run

```
uv run server.py            # optional: --port 8000
```

The terminal prints a QR code and two URLs:

- **Players join** at `http://<laptop-ip>:8000/` (the QR code is also shown on the Storyteller screen).
- **Storyteller** opens `http://localhost:8000/st?key=...` on the laptop. Keep that key private: it shows
  every character.

If phones cannot connect, allow incoming connections for Python in the laptop's firewall.

**Remote play.** Players (and the Storyteller) can be anywhere: put the server behind a public URL (a tunnel
or a small VPS) and share that link instead of the LAN one. Turn the night check off in the game settings
(`set_night_check`) so nobody waits on tap challenges, or exempt the one remote player at an in-room game.
Votes run on the server's clock, so every screen sees the same hand.

## Flow

1. **Script**: the Storyteller picks Trouble Brewing or Bad Moon Rising before anyone joins.
2. **Lobby**: players scan the code (or open the link) and enter their name. Drag each token onto the right
   seat until the circle matches the real table clockwise. Players without a phone can be seated by the
   Storyteller. The gear holds the game settings: night check on/off, seconds a seat for votes, mute.
3. **Deal**: a random rules-valid setup for 5-15 players, with the script's hidden choices (the Drunk's fake
   character, the Lunatic's fake Demon, the red herring, three Demon bluffs). Tap any token to change it, then start.
4. **Night**: every phone buzzes at once. Players with a night choice get it on their phone automatically;
   with the night check on, everyone else gets a tap challenge so real choices do not stand out. The ledger
   lists tonight's steps in order with one card open at a time: *Apply* a pick (or pick for a player who has
   no phone), *Work out their info* (the truthful answer is filled in; edit it if they are drunk or poisoned),
   *Hold for dawn*, *Skip*. Enter applies the open card, the arrow keys move, S skips. Steps that do not happen
   tonight are listed apart. The phones strip shows who is still tapping; *Stop waiting* releases the second
   buzz and dawn. The dawn card lists every death with its cause, asks about the ones the rules leave to you
   (the Pacifist), then *Deliver everything* buzzes every phone with its slip.
5. **Day**: players raise a hand to ask to nominate; nominate from the hands list or by clicking tokens.
   *Start the clock*: a 3-2-1 on every screen, then a hand sweeps clockwise from the nominee one seat at a
   time; players raise or lower their hand until the hand passes them, and the tally fills in. Pause, restart
   or stop; click a token to raise a hand for someone without a phone. Space starts or pauses. Day abilities
   (the Slayer's shot, the Gossip's statement) are one button each. *End the day* executes and starts the night.
6. Win conditions are checked after every death. Players see all characters when the game ends.

Click any token to open its drawer: status toggles (alive, poisoned, drunk, protected, ghost vote), the ability
block, reminder chips, the night-check exemption, the message thread with that player, and a character change.

**Undo** (top of the Storyteller screen, or Ctrl/Cmd+Z) reverses the last Storyteller action, up to 30 back. It
warns when phones already showed the result or when picks made on phones since would be cleared.

## Files

- `scripts/` one module per script: character data (night order, reminders, hints) and the rule hooks
  `game.py` calls (`trouble_brewing.py`; `bad_moon_rising.py`)
- `dealing.py` random setup for any script
- `game.py` generic game state: seats, phases, night steps, reminders, threads, hands, the vote clock, undo
- `server.py` FastAPI server
- `static/` phone page, Storyteller page, theme and bundled fonts
- `test_game.py` Trouble Brewing rules, `test_table.py` table features (reminders, night check, threads, hands,
  the clock), `test_bmr.py` Bad Moon Rising rules, `test_scripts.py` script data, `test_server.py` HTTP routes.
  Run them all with `uv run pytest -q`
- `trouble-brewing-almanac.pdf`, `bad-moon-rising-almanac.pdf` player sheets for the scripts, by Rithwik aka BlazeReceptor
- `static/fonts/OFL-*.txt` licences for the bundled Grenze Gotisch and Alegreya Sans fonts

Game state is in memory: restarting the server ends the game.
