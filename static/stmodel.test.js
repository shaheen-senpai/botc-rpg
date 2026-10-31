// Pure model tests for the grimoire page. Run: node --test static/
import test from "node:test";
import assert from "node:assert/strict";
import { phaseTitle, tokenMarks, seatPositions, lobbyModel, drawerModel, nightCards, dayModel, messagesModel } from "./stmodel.js";

test("messagesModel sorts unread first and shows the last line", () => {
  const v = {players: [{pid: "p1", name: "Asha"}, {pid: "p2", name: "Ben"}, {pid: "p3", name: "Chen"}], threads: {
    p1: [{id: 1, from: "st", text: "hi", label: "Day 1", seen: false}],
    p2: [{id: 2, from: "player", text: "help?", label: "Day 1", seen: false}, {id: 3, from: "player", text: "please", label: "Day 1", seen: false}],
    p3: [],
  }};
  assert.deepEqual(messagesModel(v), [
    {pid: "p2", name: "Ben", last: "please", unread: 2},
    {pid: "p1", name: "Asha", last: "hi", unread: 0},
    {pid: "p3", name: "Chen", last: "", unread: 0},
  ]);
});

const DC = {slayer: {name: "Slayer", uses: "day"}, butler: {name: "Butler", uses: "each_night"}, imp: {name: "Imp", uses: "each_night"},
  empath: {name: "Empath", uses: "each_night"}, gossip: {name: "Gossip", uses: "day"}};
const dv = (extra = {}) => ({
  phase: "day", day: 2, threshold: 3, announcements: ["Dawn. Nobody died in the night."], hands: ["p4"],
  players: [{pid: "p1", name: "Asha", character: "slayer", alive: true, ghost_vote: true, reminders: [], ability: {uses: "day", used: false}},
            {pid: "p2", name: "Ben", character: "imp", alive: true, ghost_vote: true, reminders: [], ability: {uses: "each_night", used: false}},
            {pid: "p3", name: "Chen", character: "butler", alive: true, ghost_vote: true, reminders: [], ability: {uses: "each_night", used: false}},
            {pid: "p4", name: "Dev", character: "empath", alive: false, ghost_vote: true, reminders: ["vote left"], ability: {uses: "each_night", used: false}}],
  nominations_full: [{nominator: "p1", nominee: "p2", voters: [], votes: null, clock: {state: "running", go_at: 0, seat_seconds: 3, paused_at: null, paused_total: 0, hands: {p3: true}, locked: {p3: null, p1: null, p2: null, p4: true}}}],
  clock: {nomination: 0, nominator: "p1", nominee: "p2", state: "running", go_at: 0, seat_seconds: 3, paused_at: null, paused_total: 0, hands: ["p3", "p4"], locked: {p4: true}},
  pending_deaths: [], ...extra});

test("dayModel builds the butler warning when the master's hand is down", () => {
  const v = dv();
  v.players[0].reminders = ["master"];   // Asha is Chen's Master, and her hand is down
  const m = dayModel(v, DC);
  assert.equal(m.nominations[0].state, "running");
  assert.equal(m.nominations[0].tally, 1);
  assert.match(m.nominations[0].butlerWarn, /Chen is the Butler and Asha's hand is down/);
  assert.deepEqual(m.nominations[0].locked, [{name: "Dev", yes: true}]);
  assert.deepEqual(m.nominations[0].pending.map(x => [x.name, x.up]), [["Chen", true], ["Asha", false], ["Ben", false]]);
});

test("dayModel marks a nomination recorded after votes and lists hands to nominate", () => {
  const v = dv({clock: null, nominations_full: [{nominator: "p1", nominee: "p2", voters: ["p3", "p4"], votes: 2, clock: {state: "done", hands: {}, locked: {p3: true, p4: true, p1: false, p2: false}}}]});
  const m = dayModel(v, DC);
  assert.equal(m.nominations[0].state, "recorded");
  assert.equal(m.nominations[0].votes, 2);
  assert.deepEqual(m.hands, [{pid: "p4", name: "Dev"}]);
  assert.equal(m.dusk.text, "Nobody has reached 3 votes yet. Ending the day with no execution starts the night.");
});

test("dayModel lists the Slayer once and not after use", () => {
  const v = dv({clock: null, nominations_full: []});
  assert.deepEqual(dayModel(v, DC).abilities, [{pid: "p1", name: "Asha", label: "Slayer, shot unused", kind: "shoot"}]);
  v.players[0].ability.used = true;
  assert.deepEqual(dayModel(v, DC).abilities, []);
});

test("dayModel offers the dead Moonchild's choice until it is used, and flags the Mastermind's extra day", () => {
  const v = dv({clock: null, nominations_full: [], extra_day: null});
  v.players.push({pid: "p5", name: "Ema", character: "moonchild", alive: false, ghost_vote: true, reminders: [], ability: {uses: "on_death", used: false}});
  assert.ok(dayModel(v, DC).abilities.some(a => a.kind === "moonchild"));
  v.players[4].ability.used = true;
  assert.ok(!dayModel(v, DC).abilities.some(a => a.kind === "moonchild"));
  assert.equal(dayModel(v, DC).dusk.mastermind, false);
  assert.equal(dayModel({...v, extra_day: 2}, DC).dusk.mastermind, true);
  assert.equal(dayModel({...v, extra_day: 3}, DC).dusk.mastermind, false);
});

const NC = {
  sailor: {name: "Sailor", uses: "each_night", hint: "h1"}, gossip: {name: "Gossip", uses: "day", hint: "h2"},
  po: {name: "Po", uses: "each_night", hint: "h3"}, courtier: {name: "Courtier", uses: "once_per_game", hint: "h4"},
  tinker: {name: "Tinker", uses: "passive", hint: "h5"},
};
const stepOf = (key, pid, extra = {}) => ({key, kind: "choose", pids: [pid], choose: 1, variable: false, question: "", allow_self: false,
  prompt: "", choices: [], answer: null, suggestion: null, sent: null, done: false, applies: true, impaired: false, asked: true, hint: NC[key].hint, ...extra});
const nightView = (steps, extra = {}) => ({
  phase: "night", night: 2, day: 1, night_check: true, waiting_stopped: false, second_round_done: false,
  players: [{pid: "p1", name: "Asha", character: "sailor", alive: true, ability: {uses: "each_night", used: false}},
            {pid: "p2", name: "Ben", character: "gossip", alive: false, ability: {uses: "day", used: false}},
            {pid: "p3", name: "Chen", character: "po", alive: true, ability: {uses: "each_night", used: false}},
            {pid: "p4", name: "Dev", character: "courtier", alive: true, ability: {uses: "once_per_game", used: true}}],
  phones: [{pid: "p1", name: "Asha", done: true}, {pid: "p3", name: "Chen", done: false}], phones_done: [1, 2],
  steps, dawn: {deaths: [], pending: [], held: 0}, queued: {}, ...extra});

test("nightCards opens the first undone applying step and collapses done ones", () => {
  const v = nightView([stepOf("sailor", "p1", {done: true, choices: ["p3"]}), stepOf("gossip", "p2", {applies: false}), stepOf("po", "p3", {asked: true})]);
  const n = nightCards(v, NC, null);
  assert.deepEqual(n.cards.map(c => [c.i, c.state]), [[0, "done"], [2, "open"]]);
  assert.equal(n.cards[0].result, "Chose Chen.");
  assert.deepEqual(n.notTonight, [{title: "Gossip", who: "Ben", why: "dead"}]);
  assert.equal(n.cards[1].pill.text, "Waiting for their phone");
});

test("nightCards keeps the open card's draft", () => {
  const v = nightView([stepOf("sailor", "p1"), stepOf("po", "p3")]);
  assert.deepEqual(nightCards(v, NC, 1).cards.map(c => c.state), ["upcoming", "open"]);
  assert.deepEqual(nightCards(v, NC, null).cards.map(c => c.state), ["open", "upcoming"]);
});

test("nightCards explains why a step sleeps", () => {
  const v = nightView([stepOf("courtier", "p4", {applies: false}), stepOf("tinker", "p1", {kind: "storyteller", choose: 0, applies: false})]);
  assert.deepEqual(nightCards(v, NC, null).notTonight.map(x => x.why), ["ability used", "sleeps tonight"]);
});

test("nightCards dawn is blocked while phones wait, released by stop waiting or the check being off", () => {
  const v = nightView([stepOf("po", "p3")]);
  assert.equal(nightCards(v, NC, null).dawn.blocked, true);
  assert.deepEqual(nightCards(v, NC, null).dawn.waiting, ["Chen"]);
  assert.equal(nightCards({...v, waiting_stopped: true}, NC, null).dawn.blocked, false);
  assert.equal(nightCards({...v, night_check: false, phones: [], phones_done: [0, 0]}, NC, null).phones.show, false);
});

test("nightCards gives the Po three selects and a nobody option", () => {
  const v = nightView([stepOf("po", "p3", {choose: 3, variable: true})]);
  const c = nightCards(v, NC, null).cards[0].controls;
  assert.equal(c.selects, 3);
  assert.equal(c.variable, true);
});

const CH = {
  slayer: {name: "Slayer", type: "townsfolk", ability: "Shoot once.", uses: "day", reminders: ["no ability"]},
  butler: {name: "Butler", type: "outsider", ability: "Pick a master.", uses: "each_night", reminders: ["master"]},
  gossip: {name: "Gossip", type: "townsfolk", ability: "Say a thing.", uses: "day", reminders: ["dead"]},
  moonchild: {name: "Moonchild", type: "outsider", ability: "Pick when dead.", uses: "on_death", reminders: ["dead"]},
  imp: {name: "Imp", type: "demon", ability: "Kill.", uses: "each_night", reminders: ["dead"]},
};
const dayView = (players, extra = {}) => ({phase: "day", night_check: true, players, threads: {}, announcements: [], ...extra});
const pl = (pid, character, extra = {}) => ({pid, name: pid.toUpperCase(), character, believed: character, alive: true, ghost_vote: true,
  reminders: [], ability: {uses: CH[character].uses, used: false}, exempt: false, phone: true, ...extra});

test("drawerModel: an unused Slayer by day offers the shot", () => {
  const v = dayView([pl("p1", "slayer"), pl("p2", "imp")]);
  const d = drawerModel(v.players[0], v, CH);
  assert.equal(d.seat, 1);
  assert.equal(d.role.name, "Slayer");
  assert.deepEqual(d.ability, {title: "Slayer's shot", state: "Unused", kind: "shoot", note: ""});
  assert.equal(d.status.find(s => s.key === "alive").on, true);
  const used = drawerModel({...v.players[0], ability: {uses: "day", used: true}}, v, CH);
  assert.equal(used.ability.kind, "none");
  assert.equal(used.ability.state, "Used");
});

test("drawerModel: a dead Butler gets the ghost vote toggle, a living one does not", () => {
  const v = dayView([pl("p1", "butler", {alive: false, ghost_vote: true}), pl("p2", "imp")]);
  const d = drawerModel(v.players[0], v, CH);
  assert.ok(d.status.some(s => s.key === "ghost" && s.on === true));
  assert.ok(!drawerModel(v.players[1], v, CH).status.some(s => s.key === "ghost"));
});

test("drawerModel: reminder options are the character's then the globals, minus chips already on", () => {
  const v = dayView([pl("p1", "butler", {reminders: ["master", "poisoned"]}), pl("p2", "imp")]);
  const d = drawerModel(v.players[0], v, CH);
  assert.deepEqual(d.reminders, [{text: "master", cls: "info"}, {text: "poisoned", cls: "poison"}]);
  assert.deepEqual(d.options, ["drunk", "protected", "dead vote"]);
});

test("drawerModel: gossip and dead moonchild expose their day actions; thread is passed through oldest first", () => {
  const thread = [{id: 1, from: "st", text: "a", label: "Night 1", seen: false}, {id: 2, from: "player", text: "b", label: "Day 1", seen: false}];
  const v = dayView([pl("p1", "gossip"), pl("p2", "moonchild", {alive: false}), pl("p3", "imp")], {threads: {p1: thread}});
  assert.equal(drawerModel(v.players[0], v, CH).ability.kind, "gossip");
  assert.equal(drawerModel(v.players[1], v, CH).ability.kind, "moonchild");
  const picked = {...v, players: [v.players[0], {...v.players[1], ability: {uses: "on_death", used: true}}, v.players[2]]};
  assert.equal(drawerModel(picked.players[1], picked, CH).ability.kind, "none");
  assert.deepEqual(drawerModel(v.players[0], v, CH).thread.map(m => m.text), ["a", "b"]);
  assert.equal(drawerModel(v.players[0], v, CH).unread, 1);
});

test("lobbyModel says when the table can be dealt", () => {
  const four = {players: [1, 2, 3, 4].map(i => ({pid: `p${i}`, name: `P${i}`, phone: i < 4})), script: {name: "Trouble Brewing"}};
  assert.deepEqual(lobbyModel(four), {canDeal: false, why: "Trouble Brewing needs 5 to 15 players; 4 seated.", seated: [
    {pid: "p1", name: "P1", phone: true, seat: 1}, {pid: "p2", name: "P2", phone: true, seat: 2},
    {pid: "p3", name: "P3", phone: true, seat: 3}, {pid: "p4", name: "P4", phone: false, seat: 4}]});
  const six = {players: [1, 2, 3, 4, 5, 6].map(i => ({pid: `p${i}`, name: `P${i}`, phone: true})), script: {name: "Bad Moon Rising"}};
  assert.equal(lobbyModel(six).canDeal, true);
  assert.equal(lobbyModel(six).why, "6 seated.");
});

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

test("tokenMarks adds a note chip while a player's message is unseen", () => {
  const v = {phase: "day", clock: null, steps: [], hands: [], threads: {p1: [{id: 1, from: "player", text: "hi", label: "Day 1", seen: false}]}};
  assert.deepEqual(tokenMarks({pid: "p1", character: "imp", ability: {uses: "each_night"}, reminders: ["poisoned"]}, v, C).chips,
    [{text: "poisoned", cls: "poison"}, {text: "note", cls: "note"}]);
  v.threads.p1[0].seen = true;
  assert.deepEqual(tokenMarks({pid: "p1", character: "imp", ability: {uses: "each_night"}, reminders: []}, v, C).chips, []);
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

test("dayModel dusk names today's execution (a Virgin's nominator) instead of counting votes", () => {
  const v = dv({clock: null, nominations_full: [{nominator: "p3", nominee: "p1", voters: [], votes: null, clock: null}], executed_today: "p3"});
  const m = dayModel(v, DC);
  assert.equal(m.dusk.text, "Chen was executed today. Ending the day starts the night.");
});

test("nightCards lets the Courtier name nobody", () => {
  const v = nightView([stepOf("courtier", "p4", {kind: "storyteller", choose: 0, question: "Which character?"})]);
  v.players[3].ability.used = false;
  const c = nightCards(v, NC, null).cards[0].controls;
  assert.equal(c.extras[0].blank, "Nobody: they shake their head");
});
