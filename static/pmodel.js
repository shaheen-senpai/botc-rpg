// Pure render-model functions for the player page: the /api/state view and `me` in, plain data out. No DOM here.

const NUDGE_TEXT = "Everyone does this: shield your screen and open your token.";

export function unreadFromStoryteller(me, seenCount = 0) {
  return me.thread.filter(m => m.from === "st").length - seenCount;
}

// the banner every phone shows at the same moment: identical whether or not this player has anything to do
export function nudge(v, me, revealed, seenCount = 0) {
  if (revealed) return {show: false, title: "", text: ""};
  const night = v.phase === "night" && me.alive;
  const unread = unreadFromStoryteller(me, seenCount) > 0;
  const prompt = !!(me.prompt && me.prompt.answer === null);
  const show = night || unread || prompt;
  return {show, title: show ? (v.phase === "night" ? `Night ${v.night}` : "Dawn") : "", text: show ? NUDGE_TEXT : ""};
}

export function tabs(v, me, view, seenCount = 0) {
  const clockLive = !!(v.clock && v.clock.state !== "done");
  return [
    {id: "character", label: "Character", current: view === "character", fresh: false},
    {id: "messages", label: "Messages", current: view === "messages", fresh: view !== "messages" && unreadFromStoryteller(me, seenCount) > 0},
    {id: "square", label: "Square", current: view === "square", fresh: view !== "square" && (clockLive || (v.hands || []).length > 0)},
    {id: "almanac", label: "Almanac", current: view === "almanac", fresh: false},
  ];
}

export function layout(width) {
  return width >= 900 ? "laptop" : "phone";
}

const ABILITY_NOUN = {slayer: "shot", virgin: "nomination", assassin: "kill", professor: "resurrection", courtier: "choice"};

// "Your shot is unused." for once-per-game abilities; nothing for the rest
export function abilityLine(me, chars) {
  const uses = me.ability?.uses;
  if (!["day", "on_nomination", "once_per_game"].includes(uses)) return null;
  const noun = ABILITY_NOUN[me.role?.id] ?? "ability";
  return `Your ${noun} is ${me.ability.used ? "used" : "unused"}.`;
}

// the conversation, oldest first: headers per phase, bubbles, the open prompt as a card at the end
export function thread(me, v) {
  const out = [];
  let label = null;
  for (const m of me.thread) {
    if (m.label !== label) { label = m.label; out.push({kind: "header", text: label}); }
    out.push({kind: m.from === "player" ? "me" : "st", id: m.id, text: m.text, seen: m.seen});
  }
  const lastMine = [...out].reverse().find(x => x.kind === "me");
  if (lastMine) lastMine.state = lastMine.seen ? "Seen" : "Sent";
  const p = me.prompt;
  if (p && p.kind === "choose") {
    if (p.answer) out.push({kind: "me", text: `You chose ${p.answer.length ? p.answer.map(pid => v.seats.find(s => s.pid === pid)?.name ?? pid).join(" and ") : "nobody"}.`});
    else out.push({kind: "card", card: {type: "choose", text: p.text, count: p.count, variable: !!p.variable, allowSelf: !!p.allow_self,
      options: v.seats.filter(s => p.allow_self || s.pid !== me.pid).map(s => ({pid: s.pid, name: s.name, dead: !s.alive}))}});
  } else if (p && p.kind === "tap") {
    if (p.answer) out.push({kind: "card", card: {type: "done", text: "Done. Keep your phone close until dawn."}});
    else out.push({kind: "card", card: {type: "tap", text: p.text, target: p.target, options: p.options}});
  }
  return out;
}

export function square(v, me) {
  // only a running vote marks the ring; once it is done the ring goes back to nominate hands
  const c = v.clock && v.clock.state !== "done" ? v.clock : null;
  const seats = v.seats.map((s, i) => {
    let mark = null;
    if (c) {
      if (s.pid in c.locked) mark = c.locked[s.pid] ? "yes" : "no";
      else if (c.hands.includes(s.pid)) mark = "up";
      else if (s.pid === c.nominee) mark = "nominee";
    }
    return {pid: s.pid, name: s.name, no: i + 1, alive: s.alive, me: s.pid === me.pid, hand: !c && (v.hands || []).includes(s.pid), mark,
      ghost: !s.alive && s.ghost_vote, character: s.character ?? null};
  });
  const alive = v.seats.filter(s => s.alive).length;
  const centre = v.phase === "day" ? {big: String(v.threshold), small: "votes to execute"} : {big: String(alive), small: `of ${v.seats.length} alive`};
  const nominations = (v.nominations || []).map(n => ({text: `${n.nominator} nominates ${n.nominee}`,
    note: n.votes === null ? "no vote yet" : `${n.votes} ${n.votes === 1 ? "vote" : "votes"}${n.votes >= v.threshold ? ", enough" : ""}`}));
  return {seats, centre, today: v.announcements || [], nominations};
}

function offsetOf(seatPids, nominee, pid) {
  const n = seatPids.length;
  const k = (seatPids.indexOf(pid) - seatPids.indexOf(nominee) + n) % n;
  return k || n;
}

// the big button: to nominate by day, to vote while the clock runs. now = the server's clock (seconds)
export function handButton(v, me, now, masterPid = null) {
  const c = v.clock && v.clock.state !== "done" ? v.clock : null;
  if (!c) {
    const up = (v.hands || []).includes(me.pid);
    if (!me.alive) return {label: "Raise hand to nominate", pressed: false, disabled: true, hint: "Dead players cannot nominate."};
    return {label: up ? "✋ Hand up" : "Raise hand to nominate", pressed: up, disabled: false, hint: "The Storyteller sees your hand and calls on you."};
  }
  const up = c.hands.includes(me.pid);
  const locked = me.pid in c.locked;
  // player_view puts the ghost vote on the seat, not on `me`
  const ghost = !!v.seats.find(s => s.pid === me.pid)?.ghost_vote;
  const label = up ? "✋ Hand up" : (!me.alive && ghost ? "Use my last vote" : "Raise hand");
  if (!me.alive && !ghost) return {label: "Raise hand", pressed: false, disabled: true, hint: "No vote left."};
  if (locked) return {label, pressed: up, disabled: true, hint: c.locked[me.pid] ? "Hand up, counted." : (up ? "Hand up but not counted." : "Hand down, not counted.")};
  const elapsed = (c.paused_at ?? now) - c.go_at - c.paused_total;
  if (elapsed < 0) return {label, pressed: up, disabled: false, hint: "The clock is about to start."};
  const seatPids = v.seats.map(s => s.pid);
  const secs = Math.max(0, Math.ceil(offsetOf(seatPids, c.nominee, me.pid) * c.seat_seconds - elapsed));
  let hint = `The hand reaches you in ${secs} s.`;
  if (me.role?.id === "butler" && masterPid && !c.hands.includes(masterPid)) {
    const master = v.seats.find(s => s.pid === masterPid)?.name ?? "Your Master";
    hint = `${master}'s hand is down: yours won't count. ` + hint;
  }
  return {label, pressed: up, disabled: false, hint};
}
