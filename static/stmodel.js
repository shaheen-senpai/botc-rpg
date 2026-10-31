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
