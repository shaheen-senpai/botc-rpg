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

1. **Lobby**: players scan and enter their name. Drag each token onto the right seat until the circle
   matches the real table clockwise. Players without a phone can be seated by the Storyteller.
2. **Deal**: a random rules-valid setup for 5-15 players, with the Drunk's fake character, the Fortune
   Teller's red herring and three Demon bluffs. Tap any token to change it, then start.
3. **Night** (eyes open): every phone buzzes at once. Players with a night choice get it on their phone
   automatically; everyone else gets a tap challenge (tap three character icons in the order shown), so
   every player taps and real choices do not stand out. The ledger shows which phones are still going;
   the second buzz and dawn are refused until every living player with a phone has finished (players
   seated without a phone are not waited for). Work down the ledger in
   order: *Apply their pick* / *Work out their info* (the truthful answer is filled in), edit if they
   are drunk or poisoned, then *Hold until dawn*. Applying the Imp's kill buzzes every phone a second
   time; a Ravenkeeper killed tonight picks then. Kills, Monk, Soldier, Mayor, star-pass and Scarlet
   Woman are handled automatically.
   At dawn every phone buzzes and every player gets a slip: their info, or "Nothing to report tonight".
4. **Day**: record nominations and tap who voted. Virgin, Slayer, Saint, ghost votes, ties and the
   Mayor are resolved; *End the day* executes and starts the next night.
5. Win conditions are checked after every death. Players see all characters when the game ends.

Tap any token during play to kill, revive, poison, send a private message or change a character.

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
