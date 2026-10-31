// Pure model tests for the grimoire page. Run: node --test static/
import test from "node:test";
import assert from "node:assert/strict";
import { phaseTitle, tokenMarks, seatPositions } from "./stmodel.js";

const C = {imp: {uses: "each_night"}, slayer: {uses: "day"}, assassin: {uses: "once_per_game"}, soldier: {uses: "passive"}};

test("phaseTitle", () => {
  assert.equal(phaseTitle({phase: "lobby"}), "Lobby");
  assert.equal(phaseTitle({phase: "setup"}), "Setup");
  assert.equal(phaseTitle({phase: "night", night: 2}), "Night 2");
  assert.equal(phaseTitle({phase: "day", day: 3}), "Day 3");
  assert.equal(phaseTitle({phase: "over", winner: "good"}), "Good wins");
});

test("tokenMarks pips and chips", () => {
  const v = {phase: "day", clock: null, steps: [], hands: []};
  const m = tokenMarks({pid: "p1", character: "slayer", ability: {uses: "day", used: false}, reminders: ["poisoned", "vote left"]}, v, C);
  assert.equal(m.pip, "unused");
  assert.deepEqual(m.chips, [{text: "poisoned", cls: "poison"}, {text: "vote left", cls: "vote"}]);
  const used = tokenMarks({pid: "p1", character: "slayer", ability: {uses: "day", used: true}, reminders: []}, v, C);
  assert.equal(used.pip, "used");
  assert.equal(tokenMarks({pid: "p2", character: "soldier", ability: {uses: "passive", used: false}, reminders: []}, v, C).pip, null);
  assert.deepEqual(tokenMarks({pid: "p3", character: "imp", ability: {uses: "each_night"}, reminders: ["drunk 2", "protected", "grandchild", "died today", "whatever"]}, v, C).chips.map(c => c.cls),
    ["poison", "safe", "info", "death", ""]);
});

test("tokenMarks vote marks and lit step", () => {
  const v = {phase: "day", clock: {state: "running", hands: ["p1", "p2"], locked: {p2: true, p3: false}}, steps: [], hands: []};
  const mk = pid => tokenMarks({pid, character: "imp", ability: {uses: "each_night"}, reminders: []}, v, C).vote;
  assert.deepEqual([mk("p1"), mk("p2"), mk("p3"), mk("p4")], ["up", "yes", "no", null]);
  const n = {phase: "night", clock: null, hands: [], steps: [{pids: ["p8"], done: true, applies: true}, {pids: ["p9"], done: false, applies: true}]};
  assert.equal(tokenMarks({pid: "p9", character: "imp", ability: {uses: "each_night"}, reminders: []}, n, C).lit, true);
  assert.equal(tokenMarks({pid: "p8", character: "imp", ability: {uses: "each_night"}, reminders: []}, n, C).lit, false);
});

test("seatPositions puts seat 1 at the top", () => {
  const s = seatPositions(8);
  assert.equal(s.length, 8);
  assert.equal(s[0].left, "50.0%");
  assert.equal(s[0].top, "9.0%");
  assert.equal(s[2].left, "91.0%");
});
