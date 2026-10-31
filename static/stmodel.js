// Pure render-model functions for the grimoire page: the /api/st view in, plain data out. No DOM here.

const ONCE = new Set(["day", "on_nomination", "once_per_game"]);

const CHIP_CLASS = [
  [/^(poisoned|drunk)/, "poison"],
  [/^(protected|survives execution)$/, "safe"],
  [/^(vote left|no vote)$/, "vote"],
  [/^(grandchild|master|chosen|red herring|exorcised)$/, "info"],
  [/^(dead|died today|registers dead)$/, "death"],
];

export function chipClass(text) {
  const hit = CHIP_CLASS.find(([re]) => re.test(text));
  return hit ? hit[1] : "";
}

export function phaseTitle(v) {
  if (v.phase === "night") return `Night ${v.night}`;
  if (v.phase === "day") return `Day ${v.day}`;
  if (v.phase === "over") return `${v.winner === "good" ? "Good" : "Evil"} wins`;
  return v.phase === "lobby" ? "Lobby" : "Setup";
}

// which seat is next to resolve: the first step that is not done and applies
export function nextStepPid(v) {
  if (v.phase !== "night") return null;
  const s = (v.steps || []).find(x => !x.done && x.applies);
  return s ? s.pids[0] : null;
}

export function tokenMarks(p, v, C) {
  const uses = p.ability?.uses ?? C[p.character]?.uses ?? "none";
  const once = ONCE.has(uses);
  const name = C[p.character]?.name ?? p.character;
  const chips = (p.reminders || []).map(text => ({text, cls: chipClass(text)}));
  let vote = null;
  const c = v.clock;
  if (c && c.state !== "done") {
    if (p.pid in c.locked) vote = c.locked[p.pid] ? "yes" : "no";
    else if (c.hands.includes(p.pid)) vote = "up";
  } else if (c && c.state === "done" && p.pid in c.locked) {
    vote = c.locked[p.pid] ? "yes" : "no";
  }
  return {
    pip: once ? (p.ability?.used ? "used" : "unused") : null,
    pipTitle: once ? `${name}: ability ${p.ability?.used ? "used" : "unused"}` : "",
    chips, vote,
    lit: nextStepPid(v) === p.pid,
  };
}

const GLOBAL_REMINDERS = ["poisoned", "drunk", "protected", "dead vote"];
const KIND = {townsfolk: "Townsfolk", outsider: "Outsider", minion: "Minion", demon: "Demon"};

// what the token drawer shows for one player
export function drawerModel(p, v, C) {
  const c = C[p.character];
  const seat = v.players.findIndex(x => x.pid === p.pid) + 1;
  const team = c && ["minion", "demon"].includes(c.type) ? "evil" : "good";
  const inGame = v.phase === "night" || v.phase === "day";
  const status = [];
  if (inGame) {
    status.push({key: "alive", label: "Alive", on: p.alive, action: p.alive ? {name: "kill", body: {pid: p.pid}} : {name: "revive", body: {pid: p.pid}}});
    for (const text of ["poisoned", "drunk", "protected"]) {
      const on = p.reminders.includes(text);
      status.push({key: text, label: text[0].toUpperCase() + text.slice(1), on, action: {name: "set_reminder", body: {pid: p.pid, text, on: !on}}});
    }
    if (!p.alive) status.push({key: "ghost", label: "Ghost vote", on: p.ghost_vote, action: {name: "set_ghost_vote", body: {pid: p.pid, value: !p.ghost_vote}}});
  }
  const uses = p.ability?.uses ?? c?.uses ?? "none";
  const used = !!p.ability?.used;
  let kind = "none", title = c ? `${c.name}'s ability` : "", state = "", note = "";
  if (uses === "each_night") { state = "Acts each night"; note = "See the night ledger."; }
  else if (uses === "passive") { state = "Passive"; note = "The rules apply it; nothing to press."; }
  else if (uses === "none") { title = ""; }
  else { state = used ? "Used" : "Unused"; }
  if (p.character === "slayer") { title = "Slayer's shot"; if (!used && p.alive && v.phase === "day") kind = "shoot"; }
  if (p.character === "virgin") { title = "Virgin's nomination"; note = "Fires on their first nomination."; }
  if (p.character === "gossip" && v.phase === "day" && p.alive) { title = "Gossip's statement"; kind = "gossip"; state = "Today"; }
  if (p.character === "moonchild") {
    title = "Moonchild's choice";
    const picked = (v.announcements || []).some(a => a.includes("the Moonchild, chooses"));
    if (!p.alive && !picked && v.phase === "day") kind = "moonchild";
    state = picked ? "Chosen" : p.alive ? "Alive" : "Waiting for their pick";
  }
  const own = (c?.reminders ?? []).filter(t => !p.reminders.includes(t));
  const options = [...own, ...GLOBAL_REMINDERS.filter(t => !own.includes(t) && !p.reminders.includes(t))];
  const thread = v.threads?.[p.pid] ?? [];
  return {
    name: p.name, seat,
    role: c ? {id: p.character, name: c.name, kind: KIND[c.type], team, ability: c.ability} : null,
    thinks: p.believed && p.believed !== p.character ? C[p.believed]?.name ?? p.believed : null,
    status, ability: {title, state, kind, note},
    reminders: p.reminders.map(text => ({text, cls: chipClass(text)})), options,
    exempt: !!p.exempt, showExempt: !!v.night_check && !!p.phone,
    thread, unread: thread.filter(m => m.from === "player" && !m.seen).length,
    changeCharacter: Object.entries(C).map(([id, x]) => ({id, name: x.name})),
  };
}

export function lobbyModel(v) {
  const n = v.players.length;
  const canDeal = n >= 5 && n <= 15;
  return {
    canDeal,
    why: canDeal ? `${n} seated.` : `${v.script.name} needs 5 to 15 players; ${n} seated.`,
    seated: v.players.map((p, i) => ({pid: p.pid, name: p.name, phone: !!p.phone, seat: i + 1})),
  };
}

// seat centres around a ring, as CSS percentages; seat 1 at the top, clockwise
export function seatPositions(n) {
  return Array.from({length: n}, (_, i) => {
    const a = (i / n) * 2 * Math.PI - Math.PI / 2;
    return {left: `${(50 + 41 * Math.cos(a)).toFixed(1)}%`, top: `${(50 + 41 * Math.sin(a)).toFixed(1)}%`};
  });
}
