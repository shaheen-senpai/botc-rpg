"""Game state and generic rules: seating, setup, night steps, nominations, deaths, wins.

Everything character-specific lives in the script module (scripts/<script>.py) behind the hooks
listed in scripts/__init__.py. Every public method is either a Storyteller action (called with
pids) or a player action (called with the player's secret token). Invalid actions raise GameError
with a message for the user.
"""

from __future__ import annotations

import copy
import math
import random
import secrets
import time
from dataclasses import dataclass, field

import dealing
import scripts
from scripts import DEMON, MINION, OUTSIDER, SCRIPTS, SETUP_COUNTS, TOWNSFOLK, TYPES


class GameError(Exception):
    """Invalid action; the message is shown to whoever attempted it."""


@dataclass
class Player:
    """One seat at the table.

    pid is public (used by everyone to refer to the player); token is secret (the player's login).
    thread schema: list of {"from": "st" | "player", "text": str, "label": str, "seen": bool} - the
    conversation between this player and the Storyteller, oldest first.
    prompt schema, one of (or None):
        real choice: {"kind": "choose", "text": str, "count": int, "allow_self": bool,
                      "answer": list[str] | None, "step": int (index into Game.steps)}
        tap task:    {"kind": "tap", "text": str, "target": list[str] (3 character ids, in order),
                      "options": list[str] (6 character ids incl. the targets), "answer": list[str] | None,
                      "step": None}
    phone is False for players the Storyteller seated by hand; they never get tap tasks.
    reminders schema: list of {"text": str, "until": "night" | "dawn" | None} - chips under the token;
    "night" ones clear when the next night starts, "dawn" ones at dawn, None stays until removed.
    """
    pid: str
    token: str
    name: str
    character: str | None = None
    believed: str | None = None
    alive: bool = True
    ghost_vote: bool = True
    thread: list[dict] = field(default_factory=list)
    prompt: dict | None = None
    phone: bool = False
    # exempt from the night check: still prompted for real choices, never waited for
    exempt: bool = False
    # hand raised by day to ask to nominate
    hand: bool = False
    reminders: list[dict] = field(default_factory=list)
    # a once-per-game ability (or a first-death save) has been spent
    used: bool = False

    @property
    def messages(self) -> list[dict]:
        """The Storyteller's side of the thread as [{label, text}] (older clients and tests)."""
        return [{"label": m["label"], "text": m["text"]} for m in self.thread if m["from"] == "st"]


class Game:
    """Single game in memory. Seat order is the order of self.players."""

    def __init__(self, rng: random.Random | None = None, script: str = "tb", clock=time.time):
        """Empty lobby. rng is injectable for reproducible games; clock (-> float seconds) for timed votes."""
        self.rng = rng or random.Random()
        self.clock = clock
        self.script = self._script(script)
        # phones tap three icons at night so real choices do not stand out; off for remote games
        self.night_check = True
        self.players: list[Player] = []
        self.version = 0
        self._next_pid = 1
        self._next_msg = 1
        # storyteller undo stack: [{"label", "seen", "state", "phone_inputs"}], newest last
        self.history: list[dict] = []
        # picks and taps made on phones; undo reports how many it throws away
        self.phone_inputs = 0
        self._reset_round()

    def _reset_round(self) -> None:
        """Clear everything except the seated players."""
        self.phase = "lobby"  # lobby | setup | night | day | over
        self.night = 0
        self.day = 0
        self.red_herring: str | None = None
        self.bluffs: list[str] = []
        self.counts: dict[str, int] = {}
        self.executed_today: str | None = None
        # tonight's deaths, in order: [{"pid", "cause", "linked"}]; linked = a consequence of another death
        self.night_deaths: list[dict] = []
        self._dying = 0
        # pids that died (or registered as dead) during the current day; some characters act only when it is empty
        self.died_today: list[str] = []
        # the script's own bookkeeping (last picks, the Po's empty night...); undo restores it with the rest
        self.script_state: dict = {}
        # pids whose night step was resolved tonight (the Chambermaid counts these)
        self.woke_tonight: list[str] = []
        # deaths the script wants the Storyteller to decide: [{"pid", "cause", "why"}]
        self.pending_deaths: list[dict] = []
        self.steps: list[dict] = []
        self.nominations: list[dict] = []
        self.announcements: list[str] = []
        self.winner: str | None = None
        self.win_reason = ""
        self.log: list[str] = []
        # every phone vibrates when this rises, so a buzz never singles anyone out
        self.buzz = 0
        # pid -> private texts held until the next table-wide buzz
        self.queued: dict[str, list[str]] = {}
        self.second_round_done = False
        # the Storyteller stopped waiting for phones this night
        self.waiting_stopped = False
        # pids with a hand up, in the order they were raised
        self.hand_order: list[str] = []
        for p in self.players:
            p.character = p.believed = None
            p.alive, p.ghost_vote, p.thread, p.prompt, p.reminders, p.used, p.hand = True, True, [], None, [], False, False

    # --- abilities ---

    ABILITY_LABELS = {"each_night": "Acts each night", "passive": "Passive", "none": ""}

    def ability_state(self, p: Player, as_believed: bool = False) -> dict:
        """{"uses": str, "used": bool, "label": str} for the token and the drawer.

        as_believed reads the character the player believes they are (a Drunk's phone must not learn
        from this that their ability is passive).
        """
        cid = p.believed if as_believed else p.character
        uses = self.C[cid]["uses"] if cid else "none"
        label = self.ABILITY_LABELS.get(uses, "Used" if p.used else "Unused")
        return {"uses": uses, "used": p.used, "label": label}

    def _spent(self, character: str) -> bool:
        return any(p.character == character and p.used for p in self.players)

    # older clients and tests read these as fields
    virgin_spent = property(lambda self: self._spent("virgin"))
    slayer_spent = property(lambda self: self._spent("slayer"))

    # --- reminders ---

    def has(self, p: Player, text: str) -> bool:
        """Whether p carries the reminder chip text (exact match)."""
        return any(r["text"] == text for r in p.reminders)

    def mark(self, p: Player, text: str, until: str | None = None) -> None:
        """Put a reminder chip on p (no duplicates); until is "night", "dawn" or None (stays)."""
        if not self.has(p, text):
            p.reminders.append({"text": text, "until": until})

    def unmark(self, p: Player, text: str) -> None:
        """Remove the reminder chip text from p, if present."""
        p.reminders = [r for r in p.reminders if r["text"] != text]

    def _expire(self, until: str) -> None:
        for p in self.players:
            p.reminders = [r for r in p.reminders if r["until"] != until]

    def _with_chip(self, text: str) -> str | None:
        """pid of the first player carrying the chip, or None (compatibility views)."""
        return next((p.pid for p in self.players if self.has(p, text)), None)

    def set_reminder(self, pid: str, text: str, on: bool) -> None:
        """Storyteller adds or removes a reminder chip; such chips stay until removed."""
        p = self.get(pid)
        if not text.strip():
            raise GameError("Reminder text required")
        (self.mark if on else self.unmark)(p, text.strip())
        self._log(f"Storyteller {'adds' if on else 'removes'} {text.strip()!r} on {p.name}")

    # --- lookups ---

    @staticmethod
    def _script(script_id: str):
        if script_id not in SCRIPTS:
            raise GameError(f"Unknown script {script_id!r}")
        return SCRIPTS[script_id]

    @staticmethod
    def error(message: str) -> GameError:
        """A GameError for script modules to raise (they cannot import this module)."""
        return GameError(message)

    @property
    def C(self) -> dict:
        """The current script's character table."""
        return self.script.CHARACTERS

    def cname(self, cid: str) -> str:
        return self.C[cid]["name"]

    def is_good(self, cid: str) -> bool:
        return scripts.is_good(self.C, cid)

    def good(self, p: Player) -> bool:
        """The player's alignment: their character's team unless the script changed it (the Goon)."""
        team = self.script_state.get("team", {}).get(p.pid)
        return team == "good" if team else self.is_good(p.character)

    def get(self, pid: str | None) -> Player:
        """Player by public id."""
        for p in self.players:
            if p.pid == pid:
                return p
        raise GameError(f"No player {pid!r}")

    def by_token(self, token: str) -> Player:
        """Player by secret token."""
        for p in self.players:
            if p.token == token:
                return p
        raise GameError("Unknown player - please join again")

    def alive_count(self) -> int:
        """Number of living players."""
        return sum(p.alive for p in self.players)

    def threshold(self) -> int:
        """Votes needed to put a nominee up for execution: half the living (as the table knows it), rounded up."""
        return math.ceil(sum(self._publicly_alive(p) for p in self.players) / 2)

    def impaired(self, p: Player) -> bool:
        """True if the player's ability does not work: a Drunk-like character, or a poisoned / drunk chip."""
        return p.character in self.script.IMPAIRED_CHARACTERS or any(
            r["text"].split()[0] in ("poisoned", "drunk") for r in p.reminders)

    def _working(self, p: Player, character: str) -> bool:
        """True if p is alive, truly holds character, and is not poisoned."""
        return p.alive and p.character == character and not self.impaired(p)

    def _alive_demon(self) -> Player | None:
        """The living Demon, if any."""
        return next((p for p in self.players if p.alive and self._type_of(p) == DEMON), None)

    def _type_of(self, p: Player) -> str:
        return self.C[p.character]["type"]

    def _require(self, *phases: str) -> None:
        if self.phase not in phases:
            raise GameError(f"Not allowed during {self.phase}")

    def _log(self, text: str) -> None:
        self.log.append(f"[{self._stamp()}] {text}")

    def _stamp(self) -> str:
        return f"Night {self.night}" if self.phase == "night" else f"Day {self.day}" if self.phase == "day" else self.phase

    def _announce(self, text: str) -> None:
        self.announcements.append(text)
        self._log(text)

    # --- lobby ---

    def set_script(self, script: str) -> None:
        """Choose the script (lobby only)."""
        self._require("lobby")
        self.script = self._script(script)

    def set_night_check(self, on: bool) -> None:
        """Turn the night check on or off for this game (off for remote games)."""
        self.night_check = bool(on)
        self._log(f"Night check {'on' if on else 'off'}")

    def set_exempt(self, pid: str, on: bool) -> None:
        """Exempt one player from the night check (a remote player at an in-room game)."""
        p = self.get(pid)
        p.exempt = bool(on)
        self._log(f"{p.name} {'exempt from' if on else 'back in'} the night check")

    def stop_waiting(self) -> None:
        """Release the second buzz and dawn for every phone still pending tonight."""
        self._require("night")
        self.waiting_stopped = True
        self._log("Storyteller stopped waiting for phones")

    def add_player(self, name: str, phone: bool = False) -> Player:
        """Seat a new player at the end of the circle (lobby only). Returns the player incl. token.

        phone is True when the player joined from their own phone, so night rounds wait for them.
        """
        self._require("lobby")
        name = name.strip()
        if not name:
            raise GameError("Name required")
        if any(p.name.lower() == name.lower() for p in self.players):
            raise GameError(f"{name} is already taken")
        if len(self.players) >= max(SETUP_COUNTS):
            raise GameError("Table is full")
        p = Player(pid=f"p{self._next_pid}", token=secrets.token_urlsafe(12), name=name, phone=phone)
        self._next_pid += 1
        self.players.append(p)
        return p

    def remove_player(self, pid: str) -> None:
        """Remove a player from the lobby."""
        self._require("lobby")
        self.players.remove(self.get(pid))

    def move_player(self, pid: str, delta: int) -> None:
        """Shift a player's seat by delta (lobby/setup), to match the real seating circle."""
        self._require("lobby", "setup")
        p = self.get(pid)
        i = self.players.index(p)
        j = max(0, min(len(self.players) - 1, i + delta))
        self.players.insert(j, self.players.pop(i))

    # --- setup ---

    def deal(self) -> None:
        """Randomly deal a valid setup to the seated players (lobby or re-deal during setup)."""
        self._require("lobby", "setup")
        if len(self.players) not in SETUP_COUNTS:
            raise GameError(f"{self.script.NAME} needs 5-15 players")
        result = dealing.deal(self.script, [p.pid for p in self.players], self.rng)
        for p in self.players:
            p.character = result["characters"][p.pid]
            p.believed = result["believed"][p.pid]
        self.red_herring = result["red_herring"]
        self.bluffs = result["bluffs"]
        self.phase = "setup"

    def _fakers(self) -> list[Player]:
        """Players whose character believes it is another character (the Drunk, the Lunatic)."""
        return [p for p in self.players if p.character and self.C[p.character].get("fake")]

    def set_character(self, pid: str, character: str, believed: str | None = None) -> None:
        """Storyteller override of a player's character (any time before the game ends).

        For a character with a fake belief (the Drunk believes a Townsfolk, the Lunatic a Demon),
        believed must be of that type; it defaults to a random one not in play. For everyone else,
        believed always equals character.
        """
        self._require("setup", "night", "day")
        if character not in self.C:
            raise GameError(f"Unknown character {character!r}")
        p = self.get(pid)
        fake = self.C[character].get("fake")
        if fake:
            in_play = {q.character for q in self.players}
            believed = believed or self.rng.choice(
                [c for c in self.C if self.C[c]["type"] == fake and c not in in_play])
            if believed not in self.C or self.C[believed]["type"] != fake:
                raise GameError(f"The {self.cname(character)} must believe they are a {fake.title()}")
        else:
            believed = character
        p.character, p.believed = character, believed
        if self.phase != "setup":
            self._log(f"Storyteller set {p.name} to {self.cname(character)}")

    def set_setup(self, red_herring: str | None, bluffs: list[str]) -> None:
        """Set the Fortune Teller red herring (a pid, scripts with one) and the Demon's three bluffs."""
        self._require("setup")
        if red_herring:
            self.get(red_herring)
        problems = self.bluff_problems(bluffs)
        if problems:
            raise GameError(problems[0])
        self.red_herring, self.bluffs = red_herring, bluffs

    def bluff_problems(self, bluffs: list[str]) -> list[str]:
        """Reasons the Demon's bluffs are illegal for the current seating; empty when they are fine.

        Algorithm: require exactly three known character ids, all different, each on the good team
        (Townsfolk or Outsider), none held by a player, and none a faker believes they are (the
        Drunk openly claims that character, so the Demon would be caught out by a double claim).
        """
        if len(bluffs) != 3 or any(b not in self.C for b in bluffs):
            return ["Pick exactly three bluff characters"]
        problems = []
        if len(set(bluffs)) != 3:
            problems.append("The three Demon bluffs must be different characters")
        evil = sorted({self.cname(b) for b in bluffs if not self.is_good(b)})
        if evil:
            problems.append(f"Demon bluffs must be good characters, not {', '.join(evil)}")
        in_play = sorted({self.cname(b) for b in bluffs if any(p.character == b for p in self.players)})
        if in_play:
            problems.append(f"Demon bluffs must not be in play: {', '.join(in_play)}")
        for f in self._fakers():
            if f.believed in bluffs:
                problems.append(f"The {self.cname(f.character)} believes they are the {self.cname(f.believed)}, so it cannot be a bluff")
        return problems

    def setup_warnings(self) -> list[str]:
        """Soft problems with the current setup; the Storyteller may start anyway."""
        if self.phase != "setup":
            return []
        chars = [p.character for p in self.players]
        warnings = []
        counts = tuple(sum(self.C[c]["type"] == t for c in chars) for t in TYPES)
        want = self.script.expected_counts(len(chars), chars)
        if counts != want:
            warnings.append(f"Counts (townsfolk, outsiders, minions, demons) are {counts}; rules say {want}")
        dupes = {c for c in chars if chars.count(c) > 1}
        if dupes:
            warnings.append("Duplicate characters: " + ", ".join(self.cname(c) for c in dupes))
        for f in self._fakers():
            if f.believed in chars:
                warnings.append(f"The {self.cname(f.character)} believes they are a character that is in play")
        if self.red_herring and not self.is_good(self.get(self.red_herring).character):
            warnings.append("The red herring should be a good player")
        return warnings

    def start_game(self) -> None:
        """Lock the setup, publish type counts, and begin the first night.

        Refuses duplicate characters, counting fake beliefs: two holders of one character would share
        a single night step, so only one of them would ever be prompted. Refuses illegal Demon bluffs,
        since character changes after the deal can put a bluff in play.
        """
        self._require("setup")
        if not any(self._type_of(p) == DEMON for p in self.players):
            raise GameError("There must be a Demon")
        chars = [p.character for p in self.players]
        dupes = sorted({self.cname(c) for c in chars if chars.count(c) > 1})
        if dupes:
            raise GameError(f"Each character can only be dealt once: {', '.join(dupes)}")
        for f in self._fakers():
            if f.believed in chars:
                raise GameError(f"The {self.cname(f.character)} must believe they are a character not in play, "
                                f"and the {self.cname(f.believed)} is in play")
        problems = self.bluff_problems(self.bluffs)
        if problems:
            raise GameError(problems[0])
        self.counts = {t: sum(self._type_of(p) == t for p in self.players) for t in TYPES}
        self._log("Game started: " + ", ".join(f"{p.name}={self.cname(p.character)}" for p in self.players))
        self.start_night()

    # --- night ---

    def start_night(self) -> None:
        """Begin the next night with every phone buzzing at once.

        Algorithm: expire poison, protection and Master; build the night order; push each living
        chooser's prompt (except steps the script wakes later, e.g. the Ravenkeeper); deliver anything
        held since the day; buzz every phone.
        """
        self._require("setup", "day")
        self.phase = "night"
        self.night += 1
        self._expire("night")
        self.night_deaths = []
        self.woke_tonight = []
        self.second_round_done = False
        self.waiting_stopped = False
        for p in self.players:
            p.prompt = None
        self.steps = self._build_steps()
        for i, s in enumerate(self.steps):
            if s["choose"] and self.step_applies(s):
                self.ask(i)
        self._hand_out_tap_tasks()
        self._log("Night falls")
        self._flush()
        self.buzz += 1

    def second_round(self) -> None:
        """Buzz every phone again (nights 2+); steps that only apply after a death get their prompt now.

        Runs every night regardless, so the second buzz never reveals that a Ravenkeeper died.
        """
        self._require("night")
        if self.second_round_done:
            return
        self._require_phones_done("the second buzz")
        self.second_round_done = True
        for i, s in enumerate(self.steps):
            if s["choose"] and not s["done"] and s["answer"] is None and self.step_applies(s) and not self._asked(i):
                self.ask(i)
        self._hand_out_tap_tasks()
        self.buzz += 1
        self._log("Second round: every phone buzzes")

    def _asked(self, step: int) -> bool:
        actor = self.get(self.steps[step]["pids"][0])
        return bool(actor.prompt and actor.prompt.get("step") == step)

    def _hand_out_tap_tasks(self) -> None:
        """Give a tap task to every publicly alive phone player not busy with an unanswered real choice.

        Algorithm: draw six different character icons, and ask for three of them in a set order;
        the phone shows the three in order above a shuffled grid of all six. A random guess passes
        1 time in 120, so a player has to look. Tonight's victims count as alive so they tap like
        everyone else; players known dead since an earlier day, and players without a phone, are
        left alone.
        """
        for p in self._phone_players():
            if p.prompt and p.prompt["kind"] == "choose" and p.prompt["answer"] is None:
                continue
            options = self.rng.sample(sorted(self.C), 6)
            target = self.rng.sample(options, 3)
            p.prompt = {"kind": "tap", "text": "Tap these three, in this order.", "target": target,
                        "options": options, "answer": None, "step": None}

    def _phone_players(self) -> list[Player]:
        """Publicly alive, non-exempt players with a phone: everyone a night round waits for (nobody when the check is off)."""
        if not self.night_check:
            return []
        return [p for p in self.players if p.phone and not p.exempt and self._publicly_alive(p)]

    def phones_waiting(self) -> list[Player]:
        """Phone players who still have an unanswered prompt (tap task or real choice)."""
        return [p for p in self._phone_players() if p.prompt and p.prompt["answer"] is None]

    def phones_done(self) -> tuple[int, int]:
        """(phone players with nothing left to tap, phone players)."""
        phones = self._phone_players()
        return len(phones) - len(self.phones_waiting()), len(phones)

    def _require_phones_done(self, before: str) -> None:
        """Refuse to go on while any phone player has not finished, unless the Storyteller stopped waiting."""
        if self.waiting_stopped:
            return
        waiting = [p.name for p in self.phones_waiting()]
        if waiting:
            raise GameError(f"Waiting for {' and '.join(waiting) if len(waiting) < 3 else ', '.join(waiting)} "
                            f"to finish on their phone before {before}")

    def _notify(self, pid: str, text: str) -> None:
        """Hold a private text for the next table-wide buzz."""
        self.queued.setdefault(pid, []).append(text)

    def _entry(self, sender: str, text: str) -> dict:
        self._next_msg += 1
        return {"id": self._next_msg, "from": sender, "text": text, "label": self._stamp(), "seen": False}

    def _say(self, p: Player, text: str) -> None:
        """Deliver a Storyteller text into p's thread now."""
        p.thread.append(self._entry("st", text))

    def _flush(self, filler: str | None = None) -> None:
        """Deliver held texts; with filler, every player without one gets filler instead."""
        for p in self.players:
            texts = self.queued.pop(p.pid, []) or ([filler] if filler else [])
            for text in texts:
                self._say(p, text)

    def _build_steps(self) -> list[dict]:
        """Night order for this night, limited to characters that are in play.

        Step schema: {"key": str, "kind": str, "pids": list[str], "choose": int, "allow_self": bool,
                      "prompt": str, "choices": list[str], "answer": list[str] | None (phone pick),
                      "suggestion": str | None, "sent": str | None (text held for dawn), "done": bool}
        """
        steps = []
        for key in self.script.FIRST_NIGHT if self.night == 1 else self.script.OTHER_NIGHTS:
            if key in self.script.MEETINGS:
                if len(self.players) < self.script.EVIL_INFO_MIN_PLAYERS:
                    continue
                wanted = MINION if key == "minion_info" else DEMON
                pids = [p.pid for p in self.players if self._type_of(p) == wanted]
                night = {"kind": "meeting"}
            else:
                # living only (a dead Imp still holds the token after a star-pass), except characters that act
                # because they died (the Moonchild)
                on_death = self.C[key]["uses"] == "on_death"
                pids = [p.pid for p in self.players if p.believed == key and (p.alive or on_death)]
                night = self.C[key]["night"]
                if night and self.night == 1 and night.get("first"):
                    night = night["first"]   # e.g. the Godfather learns the Outsiders on night 1 and kills later
            if not pids or night is None:
                continue
            choose = night["count"] if night["kind"] == "choose" else 0
            steps.append({"key": key, "kind": night["kind"], "pids": pids, "choose": choose,
                          "variable": bool(night.get("variable")), "question": night.get("question", ""),
                          "allow_self": night.get("allow_self", True), "prompt": night.get("prompt", ""),
                          "choices": [], "answer": None, "suggestion": None, "sent": None, "done": False,
                          "resolved": False})   # resolved: applied or sent at least once (a done step without it was skipped)
        return steps

    def _step(self, index: int) -> dict:
        self._require("night")
        if not 0 <= index < len(self.steps):
            raise GameError("No such step")
        return self.steps[index]

    def step_applies(self, step: dict) -> bool:
        """Whether a step's players should be woken now: a spent once-per-game ability sleeps, the script
        decides the rest, else everyone in it is alive."""
        key = step["key"]
        if key in self.C and self.C[key]["uses"] == "once_per_game" and self.get(step["pids"][0]).used:
            return False
        verdict = self.script.step_applies(self, step)
        if verdict is not None:
            return verdict
        return all(self.get(pid).alive for pid in step["pids"])

    def ask(self, step: int) -> None:
        """Push a step's choice prompt to the woken player's phone."""
        s = self._step(step)
        if not s["choose"]:
            raise GameError("This step has no choice to make")
        self.get(s["pids"][0]).prompt = {"kind": "choose", "text": s["prompt"], "count": s["choose"],
                                         "variable": s["variable"], "allow_self": s["allow_self"], "answer": None, "step": step}
        s["answer"] = None

    def resolve(self, step: int, choices: list[str], **options) -> None:
        """Apply a step's effect (via the script) and compute the truthful info suggestion.

        Args:
            step (int): index into self.steps.
            choices (list[str]): chosen pids, in order.
            **options: script-specific extras, e.g. the Imp's redirect / new_demon.
        """
        s = self._step(step)
        if len(choices) != s["choose"] and not (s["variable"] and len(choices) <= s["choose"]):
            raise GameError(f"Choose exactly {s['choose']} player(s)")
        targets = [self.get(c) for c in choices]
        actor = self.get(s["pids"][0])
        if not s["allow_self"] and actor in targets:
            raise GameError("This character cannot choose themselves")
        if not self.step_applies(s):
            raise GameError("This step does not happen tonight")
        # the Demon's kill (nights 2+) triggers the second buzz, so check before anything is applied
        demon_step = len(s["pids"]) == 1 and self._type_of(actor) == DEMON and self.night > 1
        if demon_step and not self.second_round_done:
            self._require_phones_done("the second buzz")
        self.script.apply(self, s, actor, targets, options)
        if len(s["pids"]) == 1 and s["kind"] != "storyteller" and actor.pid not in self.woke_tonight:
            self.woke_tonight.append(actor.pid)
        if demon_step and self.phase == "night":
            self.second_round()
        s["choices"] = choices
        s["resolved"] = True
        s["suggestion"] = self.script.suggest(self, s["key"], actor if len(s["pids"]) == 1 else None, targets)
        if s["suggestion"] is None:
            s["done"] = True
            self._close_prompt(actor, step)

    def _close_prompt(self, p: Player, step: int) -> None:
        """Clear p's prompt only if it belongs to this step (a Minion may hold their own prompt)."""
        if p.prompt and p.prompt.get("step") == step:
            p.prompt = None

    def send(self, step: int, text: str) -> None:
        """Hold info text for every player in a step until dawn, and mark the step done."""
        s = self._step(step)
        if not text.strip():
            raise GameError("Message is empty")
        for pid in s["pids"]:
            self._notify(pid, text.strip())
            self._close_prompt(self.get(pid), step)
        s["sent"] = text.strip()
        s["done"] = s["resolved"] = True
        self._log(f"For {', '.join(self.get(pid).name for pid in s['pids'])} at dawn: {text.strip()}")

    def finish_step(self, step: int, done: bool = True) -> None:
        """Mark a step done (e.g. skipped) or reopen it."""
        self._step(step)["done"] = done

    # --- messages and player actions ---

    def message(self, pid: str, text: str, now: bool = False) -> None:
        """Private message to one player: held until dawn at night unless now, delivered at once by day.

        Delivery never vibrates the phone (only table-wide buzzes do), so now is safe for rules answers.
        """
        p = self.get(pid)
        if not text.strip():
            raise GameError("Message is empty")
        if self.phase == "night" and not now:
            self._notify(pid, text.strip())
            self._log(f"For {p.name} at dawn: {text.strip()}")
        else:
            self._say(p, text.strip())
            self._log(f"To {p.name}: {text.strip()}")

    def choose(self, token: str, choices: list[str]) -> None:
        """Player answers their current prompt with a list of pids."""
        p = self.by_token(token)
        if not p.prompt or p.prompt["kind"] != "choose":
            raise GameError("Nothing to choose right now")
        n = p.prompt["count"]
        fits = len(choices) == n or (p.prompt.get("variable") and len(choices) <= n)
        if not fits or len(set(choices)) != len(choices):
            raise GameError(f"Choose {'up to' if p.prompt.get('variable') else 'exactly'} {n} different player(s)")
        for c in choices:
            self.get(c)
        if not p.prompt["allow_self"] and p.pid in choices:
            raise GameError("You cannot choose yourself")
        p.prompt["answer"] = choices
        if p.prompt["step"] is not None:
            self.steps[p.prompt["step"]]["answer"] = choices
        self.phone_inputs += 1

    def tap(self, token: str, sequence: list[str]) -> None:
        """Player completes their tap task by tapping the three shown icons in order."""
        p = self.by_token(token)
        if not p.prompt or p.prompt["kind"] != "tap":
            raise GameError("Nothing to tap right now")
        if sequence != p.prompt["target"]:
            raise GameError("Not quite. Start again from the first one.")
        p.prompt["answer"] = sequence
        self.phone_inputs += 1

    def note_to_storyteller(self, token: str, text: str) -> None:
        """Player sends a private note to the Storyteller (any phase, alive or dead)."""
        p = self.by_token(token)
        text = text.strip()
        if not text:
            raise GameError("Write something first")
        if len(text) > 500:
            raise GameError("Keep it under 500 characters")
        p.thread.append(self._entry("player", text))
        self._log(f"Note from {p.name}: {text}")

    def read_thread(self, pid: str) -> None:
        """Storyteller has read one player's messages: they show as seen on that phone."""
        for m in self.get(pid).thread:
            if m["from"] == "player":
                m["seen"] = True

    def read_inbox(self) -> None:
        """Storyteller marks every player's messages as seen (older clients)."""
        for p in self.players:
            self.read_thread(p.pid)

    def _unread(self) -> int:
        return sum(m["from"] == "player" and not m["seen"] for p in self.players for m in p.thread)

    @property
    def inbox(self) -> list[dict]:
        """Every player's own messages as [{pid, text, label, read}] (older clients and tests)."""
        return [{"pid": p.pid, "text": m["text"], "label": m["label"], "read": m["seen"]}
                for p in self.players for m in p.thread if m["from"] == "player"]

    # --- hands ---

    def raise_hand(self, token: str, up: bool) -> None:
        """Player raises or lowers their hand (day only): a vote while the clock runs, else to ask to nominate."""
        p = self.by_token(token)
        self._require("day")
        if self._vote_hand(p, up):
            return
        if not p.alive:
            raise GameError("Dead players cannot nominate")
        self.set_hand(p.pid, up)

    def set_hand(self, pid: str, up: bool) -> None:
        """Storyteller raises or lowers a player's hand on their behalf (vote or nomination queue)."""
        self._require("day")
        p = self.get(pid)
        if self._vote_hand(p, up):
            return
        p.hand = bool(up)
        if p.pid in self.hand_order:
            self.hand_order.remove(p.pid)
        if up:
            self.hand_order.append(p.pid)

    def _lower_hands(self, pids: list[str] | None = None) -> None:
        for p in self.players:
            if pids is None or p.pid in pids:
                p.hand = False
        self.hand_order = [pid for pid in self.hand_order if self.get(pid).hand]

    # --- the vote clock ---
    # Nomination "clock" schema: None | {"state": "countdown" | "running" | "paused" | "done", "go_at": float,
    # "seat_seconds": int, "paused_at": float | None, "paused_total": float,
    # "hands": {pid: bool}, "locked": {pid: bool | None}}. Seats lock from the server's clock, never a timer.

    COUNTDOWN_SECONDS = 3

    def _nomination(self, index: int) -> dict:
        if not 0 <= index < len(self.nominations):
            raise GameError("No such nomination")
        return self.nominations[index]

    def _live_clock(self) -> tuple[int, dict] | None:
        """(nomination index, clock) of the clock that is not finished, if any."""
        for i, n in enumerate(self.nominations):
            if n.get("clock") and n["clock"]["state"] != "done":
                return i, n["clock"]
        return None

    def _latest_clock(self) -> tuple[int, dict] | None:
        """The live clock, else the most recent finished one."""
        live = self._live_clock()
        if live:
            return live
        for i in range(len(self.nominations) - 1, -1, -1):
            if self.nominations[i].get("clock"):
                return i, self.nominations[i]["clock"]
        return None

    def start_clock(self, nomination: int, seat_seconds: int = 3) -> None:
        """Start the vote: a 3 second countdown, then the hand sweeps one seat per seat_seconds from the nominee.

        Hands raised before the clock carry over as votes-in-waiting.
        """
        self._require("day")
        if self._live_clock():
            raise GameError("A clock is already running")
        n = self._nomination(nomination)
        if n["votes"] is not None:
            raise GameError("This nomination already has votes")
        if not 1 <= int(seat_seconds) <= 10:
            raise GameError("Seconds a seat must be between 1 and 10")
        n["clock"] = {"state": "countdown", "go_at": self.clock() + self.COUNTDOWN_SECONDS, "seat_seconds": int(seat_seconds),
                      "paused_at": None, "paused_total": 0.0,
                      "hands": {p.pid: p.hand for p in self.players}, "locked": {p.pid: None for p in self.players}}
        self._lower_hands()
        self._log(f"Clock started on {self.get(n['nominator']).name}'s nomination of {self.get(n['nominee']).name}")

    def _require_live_clock(self) -> tuple[int, dict]:
        self._require("day")
        self._sync_clock()
        live = self._live_clock()
        if not live:
            raise GameError("No clock is running")
        return live

    def pause_clock(self) -> None:
        """Freeze the hand where it is."""
        i, c = self._require_live_clock()
        if c["state"] == "paused":
            return
        c["state"], c["paused_at"] = "paused", self.clock()
        self._log("Clock paused")

    def resume_clock(self) -> None:
        """Let the hand move again from where it stopped."""
        i, c = self._require_live_clock()
        if c["state"] != "paused":
            return
        c["paused_total"] += self.clock() - c["paused_at"]
        c["paused_at"], c["state"] = None, "running"
        self._sync_clock()
        self._log("Clock resumed")

    def restart_clock(self) -> None:
        """Back to the countdown with every seat unlocked; raised hands stay raised."""
        i, c = self._require_live_clock()
        c.update({"state": "countdown", "go_at": self.clock() + self.COUNTDOWN_SECONDS, "paused_at": None, "paused_total": 0.0,
                  "locked": {p.pid: None for p in self.players}})
        self._log("Clock restarted")

    def stop_clock(self) -> None:
        """Abandon the vote; the nomination stays, unvoted."""
        i, c = self._require_live_clock()
        self.nominations[i]["clock"] = None
        self._log("Clock stopped")

    def clock_elapsed(self, c: dict) -> float:
        """Seconds since "go", not counting pauses; negative during the countdown."""
        now = c["paused_at"] if c["paused_at"] is not None else self.clock()
        return now - c["go_at"] - c["paused_total"]

    def hand_index(self, c: dict) -> int:
        """How many seats past the nominee the hand has swept (0 = on the nominee, negative = counting down)."""
        return math.floor(self.clock_elapsed(c) / c["seat_seconds"])

    def seat_offset(self, nominee_pid: str, pid: str) -> int:
        """Seats clockwise from the nominee, 1..N; the nominee is N (they vote last)."""
        seats = [p.pid for p in self.players]
        k = (seats.index(pid) - seats.index(nominee_pid)) % len(seats)
        return k or len(seats)

    def _counts_as_yes(self, p: Player, c: dict) -> bool:
        """A raised hand counts unless the player has no vote, or is a working Butler whose Master's hand is down."""
        if not c["hands"].get(p.pid):
            return False
        if not self._publicly_alive(p) and not p.ghost_vote:
            return False
        if self._working(p, "butler"):
            master = self._with_chip("master")
            return bool(master and c["hands"].get(master))
        return True

    def _sync_clock(self) -> None:
        """Lock every seat the hand has passed; record the votes when it has passed them all.

        The only place locks are written. Called before every view and every hand action, so screens
        agree to within one poll without any server-side timer.
        """
        live = self._live_clock()
        if not live:
            return
        i, c = live
        n = self.nominations[i]
        idx = self.hand_index(c)
        before = (c["state"], dict(c["locked"]))
        if c["state"] != "paused":
            c["state"] = "countdown" if idx < 0 else "running"
        for p in self.players:
            if c["locked"][p.pid] is None and self.seat_offset(n["nominee"], p.pid) <= idx:
                c["locked"][p.pid] = self._counts_as_yes(p, c)
        if all(v is not None for v in c["locked"].values()):
            c["state"] = "done"
            self.record_votes(i, [pid for pid, v in c["locked"].items() if v])
        if (c["state"], c["locked"]) != before:
            self.version += 1   # time moved the clock on: polling pages must redraw even without a POST

    def _vote_hand(self, p: Player, up: bool) -> bool:
        """Toggle p's hand on the live clock, if there is one. Returns False when no clock is live."""
        self._sync_clock()
        live = self._live_clock()
        if not live:
            return False
        _, c = live
        if c["locked"][p.pid] is not None:
            raise GameError("The clock has passed you")
        if not self._publicly_alive(p) and not p.ghost_vote:
            raise GameError("No vote left")
        c["hands"][p.pid] = bool(up)
        return True

    def _clock_view(self) -> dict | None:
        found = self._latest_clock()
        if not found:
            return None
        i, c = found
        n = self.nominations[i]
        return {"nomination": i, "nominator": n["nominator"], "nominee": n["nominee"], "state": c["state"],
                "go_at": c["go_at"], "seat_seconds": c["seat_seconds"], "paused_at": c["paused_at"],
                "paused_total": c["paused_total"], "hands": [pid for pid, up in c["hands"].items() if up],
                "locked": {pid: v for pid, v in c["locked"].items() if v is not None}}

    # --- day ---

    def start_day(self) -> None:
        """Dawn: every player gets their held info (or a blank slip), every phone buzzes, nominations open.

        The script first does whatever it sends automatically (e.g. an Undertaker step left open).
        """
        self._require("night")
        if self.pending_deaths:
            raise GameError("Decide the pending deaths first")
        self._require_phones_done("dawn")
        self.script.before_dawn(self)
        self._flush(filler="Nothing to report tonight.")
        self.buzz += 1
        self._expire("dawn")
        self.phase = "day"
        self.day += 1
        self.nominations = []
        self.announcements = []
        self.executed_today = None
        self.died_today = []
        for p in self.players:
            p.prompt = None
        dead = [self.get(pid).name for pid in self._night_dead()]
        self._announce(f"Dawn. {self._names(dead) + ' died' if dead else 'Nobody died'} in the night.")

    @staticmethod
    def _names(names: list[str]) -> str:
        """"A", "A and B", "A, B and C"."""
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    def nominate(self, nominator: str, nominee: str, **options) -> None:
        """Record a nomination; the script may react (the Virgin).

        Args:
            nominator (str): pid, must be alive and not have nominated today.
            nominee (str): pid, must be alive and not have been nominated today.
            **options: script-specific extras, e.g. spy_as_townsfolk.
        """
        self._require("day")
        if self.executed_today:
            raise GameError("There has already been an execution today")
        a, b = self.get(nominator), self.get(nominee)
        if not self._publicly_alive(a) or not self._publicly_alive(b):
            raise GameError("Only living players nominate and can be nominated")
        if any(n["nominator"] == a.pid for n in self.nominations):
            raise GameError(f"{a.name} has already nominated today")
        if any(n["nominee"] == b.pid for n in self.nominations):
            raise GameError(f"{b.name} has already been nominated today")
        self.nominations.append({"nominator": a.pid, "nominee": b.pid, "voters": [], "votes": None})
        self._lower_hands([a.pid])
        self._announce(f"{a.name} nominates {b.name}.")
        self.script.on_nomination(self, a, b, options)

    def record_votes(self, nomination: int, voters: list[str]) -> None:
        """Set who voted on a nomination; dead voters spend their one ghost vote (refunded on re-record)."""
        self._require("day")
        if not 0 <= nomination < len(self.nominations):
            raise GameError("No such nomination")
        n = self.nominations[nomination]
        previous = set(n["voters"])
        for pid in voters:
            p = self.get(pid)
            if not self._publicly_alive(p) and not p.ghost_vote and pid not in previous:
                raise GameError(f"{p.name} is dead and has used their vote")
        for pid in previous:
            if not self._publicly_alive(self.get(pid)):
                self.get(pid).ghost_vote = True
        for pid in voters:
            if not self._publicly_alive(self.get(pid)):
                self.get(pid).ghost_vote = False
        n["voters"], n["votes"] = list(voters), len(voters)
        self._announce(f"{len(voters)} vote(s) to execute {self.get(n['nominee']).name} "
                       f"(needs {self.threshold()}).")

    def day_ability(self, pid: str, options: dict) -> None:
        """A player's daytime ability, resolved by the script (the Slayer's shot, the Gossip's statement)."""
        self._require("day")
        self.script.day_ability(self, self.get(pid), options)

    def slayer_shot(self, shooter: str, target: str, recluse_as_demon: bool = False) -> None:
        """Public Slayer claim (older clients); see day_ability."""
        self.day_ability(shooter, {"target": target, "recluse_as_demon": recluse_as_demon})

    def end_day(self) -> None:
        """Dusk: execute the unique top nominee at or above threshold, let the script react, then start the night."""
        self._require("day")
        self._sync_clock()
        if self._live_clock():
            raise GameError("Finish or stop the clock first")
        if not self.executed_today:
            t = self.threshold()
            eligible = [n for n in self.nominations if n["votes"] is not None and n["votes"] >= t]
            if eligible:
                top = max(n["votes"] for n in eligible)
                leaders = [n for n in eligible if n["votes"] == top]
                if len(leaders) == 1:
                    self._execute(self.get(leaders[0]["nominee"]))
                else:
                    self._announce("Tied vote: nobody is executed.")
            else:
                self._announce("Nobody is executed.")
        if self.pending_deaths:
            names = " and ".join(self.get(d["pid"]).name for d in self.pending_deaths)
            self._announce(f"Decide whether {names} dies, then end the day.")
            return
        self._lower_hands()
        if not self.winner:
            self.script.day_end(self)
        if not self.winner:
            self.start_night()

    def _execute(self, p: Player) -> None:
        """Execute a player; the script may react (a working Saint loses the game for good)."""
        self.executed_today = p.pid
        self._announce(f"{p.name} is executed.")
        self._die(p, "executed")
        if not p.alive:
            self.script.on_execution(self, p)

    # --- deaths and wins ---

    def _die(self, p: Player, cause: str, force: bool = False) -> None:
        """Kill a player unless the script saves them or asks the Storyteller; then check for a win.

        cause is one of the script's cause words ("demon", "executed", "slayer", "storyteller", ...).
        force skips the script's may_die (a death the Storyteller has already confirmed).
        """
        if not p.alive:
            return
        verdict = True if force else self.script.may_die(self, p, cause)
        if verdict is False:
            return
        if isinstance(verdict, str):
            why = verdict.partition(":")[2].strip()
            self.pending_deaths.append({"pid": p.pid, "cause": cause, "why": why})
            self._log(f"{p.name} would die ({cause}): {why}")
            return
        p.alive = False
        if self.phase == "night":
            self.night_deaths.append({"pid": p.pid, "cause": cause, "linked": self._dying > 0})
        else:
            self.died_today.append(p.pid)
        self._log(f"{p.name} ({self.cname(p.character)}) dies: {cause}")
        self._dying += 1
        try:
            self.script.on_death(self, p, cause)
        finally:
            self._dying -= 1
        self._check_win()

    def _night_dead(self) -> list[str]:
        return [d["pid"] for d in self.night_deaths]

    def confirm_death(self, index: int, dies: bool) -> None:
        """Storyteller decides a death the script left to them (see pending_deaths)."""
        if not 0 <= index < len(self.pending_deaths):
            raise GameError("No such pending death")
        d = self.pending_deaths.pop(index)
        p = self.get(d["pid"])
        if dies:
            self._die(p, d["cause"], force=True)
            if d["cause"] == "executed" and not p.alive:
                self.script.on_execution(self, p)
        else:
            self._log(f"{p.name} survives ({d['cause']}): Storyteller's call")

    def _check_win(self) -> None:
        if self.winner:
            return
        if not self._alive_demon():
            if self.script_state.get("extra_day") is not None:
                return   # the script (Mastermind) keeps the game going one more day
            self._win("good", "The Demon is dead.")
        elif self.alive_count() <= 2:
            self._win("evil", "Only two players remain and the Demon is one of them.")

    def _win(self, team: str, reason: str) -> None:
        self.winner, self.win_reason, self.phase = team, reason, "over"
        self._log(f"{team.upper()} WINS: {reason}")

    # --- storyteller overrides ---

    def kill(self, pid: str, force: bool = False) -> None:
        """Storyteller kills a player; the script's saves (Fool, Sailor...) apply unless force."""
        self._require("night", "day")
        self._die(self.get(pid), "storyteller", force=force)

    def revive(self, pid: str) -> None:
        """Storyteller undoes a death."""
        self._require("night", "day")
        p = self.get(pid)
        p.alive = True
        self.night_deaths = [d for d in self.night_deaths if d["pid"] != pid]
        self._log(f"Storyteller revives {p.name}")

    def set_poisoned(self, pid: str | None) -> None:
        """Storyteller sets or clears the poisoned player (older clients; see set_reminder)."""
        self._require("night", "day")
        for p in self.players:
            self.unmark(p, "poisoned")
        if pid:
            self.mark(self.get(pid), "poisoned")
        self._log(f"Storyteller sets poisoned: {self.get(pid).name if pid else 'nobody'}")

    def set_ghost_vote(self, pid: str, value: bool) -> None:
        """Storyteller sets whether a dead player still has their vote."""
        self.get(pid).ghost_vote = value

    def declare_winner(self, team: str) -> None:
        """Storyteller ends the game."""
        if team not in ("good", "evil"):
            raise GameError("Team must be good or evil")
        self._win(team, "Declared by the Storyteller.")

    def reset(self) -> None:
        """Back to the lobby with the same seated players."""
        self._reset_round()

    # --- undo ---

    UNDO_DEPTH = 30
    # survive an undo: counters phones compare, the record of what happened (players' own messages: see undo)
    _KEPT_ON_UNDO = ("version", "buzz", "log", "history", "_next_pid", "_next_msg", "phone_inputs", "clock", "script")

    def snapshot(self) -> dict:
        """Deep copy of everything an undo restores (all state except _KEPT_ON_UNDO)."""
        return copy.deepcopy({k: v for k, v in self.__dict__.items() if k not in self._KEPT_ON_UNDO})

    def push_undo(self, label: str, state: dict, seen: bool) -> None:
        """Record the state from before a Storyteller action so undo() can return to it.

        Args:
            label (str): what the action did, e.g. "Kill Asta".
            state (dict): snapshot() taken just before the action ran.
            seen (bool): the action already reached phones (buzz, dawn slips, a sent message).
        """
        self.history.append({"label": label, "seen": seen, "state": state, "phone_inputs": self.phone_inputs})
        del self.history[:-self.UNDO_DEPTH]

    def undo_info(self) -> dict | None:
        """The action undo() would reverse.

        Schema: {"label": str, "seen": bool, "phone_picks": int (picks and taps made since), "depth": int}
        or None when there is nothing to undo.
        """
        if not self.history:
            return None
        top = self.history[-1]
        return {"label": top["label"], "seen": top["seen"],
                "phone_picks": self.phone_inputs - top["phone_inputs"], "depth": len(self.history)}

    def undo(self) -> None:
        """Reverse the most recent Storyteller action.

        Algorithm: pop the newest history entry and restore its snapshot over the current state.
        Fields in _KEPT_ON_UNDO are left alone, so phones do not buzz again, player notes stay and
        pids are never reused. Players who joined the lobby since the snapshot are re-seated at the
        end rather than dropped. Picks and taps made on phones since then are lost; undo_info()
        reports how many beforehand.
        """
        if not self.history:
            raise GameError("Nothing to undo")
        entry = self.history.pop()
        restored = {p.pid for p in entry["state"]["players"]}
        joined = [p for p in self.players if p.pid not in restored]
        # what players wrote since the snapshot is theirs to keep, and whether the Storyteller has read it
        written = {p.pid: {m["id"]: m for m in p.thread if m["from"] == "player"} for p in self.players}
        self.__dict__.update(entry["state"])
        if self.phase == "lobby":
            self.players += joined
        for p in self.players:
            live = written.get(p.pid, {})
            for m in p.thread:
                if m["from"] == "player" and m["id"] in live:
                    m["seen"] = live[m["id"]]["seen"]
            have = {m["id"] for m in p.thread}
            p.thread += [m for mid, m in sorted(live.items()) if mid not in have]
        self._log(f"Storyteller undid: {entry['label']}")

    # --- views ---

    def public_view(self) -> dict:
        """What every player may see. Characters are revealed only once the game is over.

        Schema: {version, script: {id, name}, phase, night, day, counts: {type: int}, threshold, buzz,
                 seats: [{pid, name, alive, ghost_vote, character|None}],
                 announcements: [str], nominations: [{nominator, nominee, votes}],
                 winner: str|None, win_reason: str}
        Tonight's deaths stay hidden (seat still alive) until dawn is announced.
        """
        over = self.phase == "over"
        self._sync_clock()
        return {
            "version": self.version, "server_time": self.clock(),
            "script": {"id": self.script.ID, "name": self.script.NAME},
            "phase": self.phase, "night": self.night, "day": self.day,
            "counts": self.counts, "buzz": self.buzz,
            # from the public alive count, so a night kill does not show early
            "threshold": math.ceil(sum(self._publicly_alive(p) for p in self.players) / 2),
            "seats": [{"pid": p.pid, "name": p.name, "alive": self._publicly_alive(p), "ghost_vote": p.ghost_vote,
                       "character": p.character if over else None} for p in self.players],
            "announcements": self.announcements,
            "nominations": [{"nominator": self.get(n["nominator"]).name, "nominee": self.get(n["nominee"]).name,
                             "votes": n["votes"]} for n in self.nominations],
            "hands": [p.pid for p in self.players if p.hand], "clock": self._clock_view(),
            # the day number the game goes on to after the Demon's execution (the Mastermind), else None
            "extra_day": self.script_state.get("extra_day"),
            "winner": self.winner, "win_reason": self.win_reason,
        }

    def _publicly_alive(self, p: Player) -> bool:
        """Alive as the table knows it: a player killed tonight still looks alive until dawn; a player
        who "registers dead" (the Zombuul's first death) looks dead while alive."""
        if self.phase == "night" and p.pid in self._night_dead():
            return True
        if self.has(p, "registers dead"):
            return False
        return p.alive

    def player_view(self, token: str) -> dict:
        """Public view plus the player's own role (as they believe it), messages and prompt."""
        p = self.by_token(token)
        started = self.phase in ("night", "day", "over")
        return {**self.public_view(), "me": {
            "pid": p.pid, "name": p.name, "alive": self._publicly_alive(p),
            "role": {"id": p.believed, **self.C[p.believed]} if started and p.believed else None,
            "ability": self.ability_state(p, as_believed=True) if started and p.believed else None,
            "thread": p.thread, "prompt": p.prompt,
            # older clients: the Storyteller's side and the player's side as separate lists
            "messages": p.messages,
            "notes": [{"text": m["text"], "label": m["label"]} for m in p.thread if m["from"] == "player"],
        }}

    def storyteller_view(self) -> dict:
        """Everything: grimoire, hidden setup choices, night steps with live answers, warnings, log.

        Extra keys over public_view: players [{pid, name, character, believed, alive, ghost_vote,
        impaired, answer}], red_herring, bluffs, poisoned, protected, master, virgin_spent,
        slayer_spent, executed_today, night_deaths, pending_deaths, steps (with applies / impaired /
        asked / hint added), nominations_full, queued {pid: [text]}, second_round_done,
        inbox [{pid, text, label, read}], phones_done [done, total], phones [{pid, name, done}]
        (phone players a round waits for), warnings, log, bluff_problems [str], undo (see undo_info).
        """
        steps = []
        for i, s in enumerate(self.steps):
            actor = self.get(s["pids"][0])
            hint = self.script.MEETINGS[s["key"]]["hint"] if s["key"] in self.script.MEETINGS else self.C[s["key"]]["hint"]
            steps.append({**s, "applies": self.step_applies(s), "impaired": self.impaired(actor),
                          "asked": self._asked(i), "hint": hint})
        return {
            **self.public_view(),
            "hands": list(self.hand_order),
            "night_check": self.night_check, "waiting_stopped": self.waiting_stopped,
            "players": [{"pid": p.pid, "name": p.name, "character": p.character, "believed": p.believed,
                         "alive": p.alive, "ghost_vote": p.ghost_vote, "reminders": [r["text"] for r in p.reminders],
                         "ability": self.ability_state(p), "exempt": p.exempt, "phone": p.phone,
                         "impaired": bool(p.character) and self.impaired(p)} for p in self.players],
            "red_herring": self.red_herring, "bluffs": self.bluffs, "poisoned": self._with_chip("poisoned"),
            "protected": self._with_chip("protected"), "master": self._with_chip("master"),
            "virgin_spent": self._spent("virgin"), "slayer_spent": self._spent("slayer"), "executed_today": self.executed_today,
            "night_deaths": self._night_dead(), "night_deaths_full": self.night_deaths,
            "pending_deaths": self.pending_deaths, "steps": steps,
            "dawn": {"deaths": self.night_deaths, "pending": self.pending_deaths,
                     "held": sum(len(t) for t in self.queued.values())},
            "nominations_full": self.nominations,
            "queued": {pid: texts for pid, texts in self.queued.items()}, "second_round_done": self.second_round_done,
            "threads": {p.pid: p.thread for p in self.players}, "unread": self._unread(),
            "inbox": self.inbox, "phones_done": list(self.phones_done()),
            "phones": [{"pid": p.pid, "name": p.name, "done": p not in self.phones_waiting()} for p in self._phone_players()],
            "warnings": self.setup_warnings(), "log": self.log, "undo": self.undo_info(),
            "bluff_problems": self.bluff_problems(self.bluffs) if self.phase == "setup" else [],
        }


if __name__ == "__main__":
    g = Game(random.Random(3))
    for name in ["Asha", "Ben", "Chen", "Dev", "Ema", "Finn", "Gita", "Hari", "Ines"]:
        g.add_player(name)
    g.deal()
    print("warnings:", g.setup_warnings())
    g.start_game()
    for i, s in enumerate(g.steps):
        picks = [p.pid for p in g.players if s["allow_self"] or p.pid != s["pids"][0]][:s["choose"]]
        g.resolve(i, picks)
        print(f"{s['key']:15} -> {s['suggestion']}")
    g.start_day()
    g.nominate(g.players[0].pid, g.players[1].pid)
    g.record_votes(0, [p.pid for p in g.players[:6]])
    g.end_day()
    print("\n".join(g.log))
