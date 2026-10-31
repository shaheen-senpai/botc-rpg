// Pure model tests for the player page. Run: node --test "static/*.test.js"
import test from "node:test";
import assert from "node:assert/strict";
import { nudge, tabs, layout, abilityLine, thread, square, handButton } from "./pmodel.js";

const CHARS = {slayer: {name: "Slayer", uses: "day"}, empath: {name: "Empath", uses: "each_night"}, butler: {name: "Butler", uses: "each_night"}};

test("abilityLine names a once-per-game ability's state", () => {
  assert.equal(abilityLine({role: {id: "slayer"}, ability: {uses: "day", used: false}}, CHARS), "Your shot is unused.");
  assert.equal(abilityLine({role: {id: "slayer"}, ability: {uses: "day", used: true}}, CHARS), "Your shot is used.");
  assert.equal(abilityLine({role: {id: "empath"}, ability: {uses: "each_night", used: false}}, CHARS), null);
});

const seatsV = {phase: "day", day: 2, threshold: 3, announcements: ["Dawn. Finn died in the night."], hands: ["p8"], clock: null,
  seats: [["p1", "Asha", true], ["p2", "Ben", true], ["p3", "Chen", true], ["p6", "Finn", false], ["p8", "Hari", true]].map(([pid, name, alive]) => ({pid, name, alive, ghost_vote: true})),
  nominations: [{nominator: "Asha", nominee: "Dev", votes: 3}]};

test("thread groups by label and keeps the open prompt last", () => {
  const me = {pid: "p3", thread: [
    {id: 1, from: "st", text: "You are the Empath.", label: "Night 1", seen: false},
    {id: 2, from: "st", text: "1 evil neighbour.", label: "Night 1", seen: false},
    {id: 3, from: "player", text: "Does dead count?", label: "Day 1", seen: true},
    {id: 4, from: "st", text: "No.", label: "Day 1", seen: false},
  ], prompt: {kind: "choose", text: "Pick two", count: 2, allow_self: true, answer: null, step: 3}};
  const t = thread(me, seatsV);
  assert.deepEqual(t.map(x => x.kind), ["header", "st", "st", "header", "me", "st", "card"]);
  assert.equal(t[0].text, "Night 1");
  assert.equal(t[3].text, "Day 1");
  assert.deepEqual(t[6].card, {type: "choose", text: "Pick two", count: 2, variable: false, allowSelf: true,
    options: [{pid: "p1", name: "Asha", dead: false}, {pid: "p2", name: "Ben", dead: false}, {pid: "p3", name: "Chen", dead: false}, {pid: "p6", name: "Finn", dead: true}, {pid: "p8", name: "Hari", dead: false}]});
});

test("thread turns an answered choose prompt into an outgoing bubble and a done tap into a card", () => {
  const me = {pid: "p3", thread: [], prompt: {kind: "choose", text: "Pick", count: 1, allow_self: false, answer: ["p2"], step: 0}};
  assert.deepEqual(thread(me, seatsV).map(x => [x.kind, x.text]), [["me", "You chose Ben."]]);
  const tap = {pid: "p3", thread: [], prompt: {kind: "tap", text: "Tap these", target: ["imp", "chef", "monk"], options: ["imp", "chef", "monk", "spy", "mayor", "saint"], answer: ["imp", "chef", "monk"], step: null}};
  assert.deepEqual(thread(tap, seatsV)[0], {kind: "card", card: {type: "done", text: "Done. Keep your phone close until dawn."}});
});

test("thread marks seen on the last outgoing only", () => {
  const me = {pid: "p3", thread: [
    {id: 1, from: "player", text: "a", label: "Day 1", seen: true},
    {id: 2, from: "player", text: "b", label: "Day 1", seen: false},
  ], prompt: null};
  const t = thread(me, seatsV);
  assert.deepEqual(t.map(x => [x.kind, x.state ?? null]), [["header", null], ["me", null], ["me", "Sent"]]);
  me.thread[1].seen = true;
  assert.equal(thread(me, seatsV)[2].state, "Seen");
});

test("square lists seats with hands and marks, and today's news", () => {
  const sq = square(seatsV, {pid: "p3"});
  assert.deepEqual(sq.seats[4], {pid: "p8", name: "Hari", no: 5, alive: true, me: false, hand: true, mark: null, ghost: false});
  assert.equal(sq.seats[2].me, true);
  assert.deepEqual(sq.centre, {big: "3", small: "votes to execute"});
  assert.deepEqual(sq.nominations, [{text: "Asha nominates Dev", note: "3 votes, enough"}]);
  const vote = {...seatsV, clock: {nomination: 0, nominator: "p1", nominee: "p2", state: "running", hands: ["p3"], locked: {p8: true, p6: false}}};
  assert.deepEqual(square(vote, {pid: "p3"}).seats.map(s => s.mark), [null, "nominee", "up", "no", "yes"]);
});

test("handButton states outside a vote", () => {
  assert.deepEqual(handButton(seatsV, {pid: "p3", alive: true}, 0), {label: "Raise hand to nominate", pressed: false, disabled: false, hint: "The Storyteller sees your hand and calls on you."});
  assert.equal(handButton(seatsV, {pid: "p8", alive: true}, 0).label, "✋ Hand up");
  assert.deepEqual(handButton(seatsV, {pid: "p6", alive: false}, 0), {label: "Raise hand to nominate", pressed: false, disabled: true, hint: "Dead players cannot nominate."});
});

test("handButton during a clock", () => {
  // the server lists every raised hand, locked or not, so a locked-yes seat is also in hands
  const clock = {nomination: 0, nominator: "p1", nominee: "p2", state: "running", go_at: 100, seat_seconds: 3, paused_at: null, paused_total: 0, hands: ["p3", "p8"], locked: {p8: true}};
  const v = {...seatsV, clock};
  // Chen (p3): seat 3, nominee Ben is seat 2 → offset 1 → locks at 3 s; now is 1 s after go
  assert.deepEqual(handButton(v, {pid: "p3", alive: true, ghost_vote: true}, 101), {label: "✋ Hand up", pressed: true, disabled: false, hint: "The hand reaches you in 2 s."});
  assert.deepEqual(handButton(v, {pid: "p8", alive: true, ghost_vote: true}, 101), {label: "✋ Hand up", pressed: true, disabled: true, hint: "Hand up, counted."});
  assert.equal(handButton(v, {pid: "p6", alive: false, ghost_vote: true}, 101).label, "Use my last vote");
  assert.deepEqual(handButton(v, {pid: "p6", alive: false, ghost_vote: false}, 101), {label: "Raise hand", pressed: false, disabled: true, hint: "No vote left."});
  const butler = handButton(v, {pid: "p3", alive: true, ghost_vote: true, role: {id: "butler"}}, 101, "p1");
  assert.match(butler.hint, /Asha's hand is down/);
  assert.equal(handButton({...v, clock: {...clock, go_at: 105}}, {pid: "p3", alive: true, ghost_vote: true}, 101).hint, "The clock is about to start.");
});

const night = {phase: "night", night: 2, buzz: 3, clock: null, hands: []};
const me = (extra = {}) => ({pid: "p1", name: "Asha", alive: true, thread: [], prompt: null, ...extra});

test("nudge is the same with or without a prompt", () => {
  const plain = nudge(night, me(), false);
  const withPrompt = nudge(night, me({prompt: {kind: "choose", text: "Pick", count: 1, allow_self: true, answer: null, step: 0}}), false);
  assert.deepEqual(plain, withPrompt);
  assert.deepEqual(plain, {show: true, title: "Night 2", text: "Everyone does this: shield your screen and open your token."});
  assert.equal(nudge(night, me(), true).show, false);          // revealed: no banner
  assert.equal(nudge(night, me({alive: false}), false).show, false);   // the dead sleep
});

test("nudge by day shows for unread Storyteller words or an unanswered prompt", () => {
  const day = {phase: "day", day: 2, buzz: 4, clock: null, hands: []};
  assert.equal(nudge(day, me(), false).show, false);
  const unread = nudge(day, me({thread: [{id: 1, from: "st", text: "x", label: "Day 2", seen: false}]}), false, 0);
  assert.deepEqual(unread, {show: true, title: "Dawn", text: "Everyone does this: shield your screen and open your token."});
  assert.equal(nudge(day, me({thread: [{id: 1, from: "st", text: "x", label: "Day 2", seen: false}]}), false, 1).show, false);
});

test("tabs marks messages and square fresh", () => {
  const v = {phase: "day", clock: {state: "running"}, hands: []};
  const m = me({thread: [{id: 1, from: "st", text: "x", label: "Day 2", seen: false}, {id: 2, from: "player", text: "y", label: "Day 2", seen: true}]});
  const t = tabs(v, m, "character", 0);
  assert.deepEqual(t.map(x => [x.id, x.current, x.fresh]), [["character", true, false], ["messages", false, true], ["square", false, true], ["almanac", false, false]]);
  assert.equal(tabs(v, m, "messages", 1)[1].fresh, false);
  assert.equal(tabs({phase: "day", clock: null, hands: []}, m, "square", 1)[2].fresh, false);
});

test("layout switches at 900px", () => {
  assert.equal(layout(899), "phone");
  assert.equal(layout(900), "laptop");
});
