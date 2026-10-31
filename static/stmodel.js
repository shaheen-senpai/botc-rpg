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

const MEETING_TITLES = {minion_info: "Minions meet the Demon", demon_info: "Demon meets the Minions"};

// extra inputs a step's card needs beyond its player picks; kind: player | character | yesno
const EXTRAS = {
  imp: [{id: "redirect", label: "If the Mayor is attacked, kill instead", kind: "player", blank: "Nobody, the Mayor dies"},
        {id: "new_demon", label: "If the Imp picks themselves, the new Imp is", kind: "player", blank: "Scarlet Woman first, else random"}],
  innkeeper: [{id: "drunk", label: "Who is drunk until dusk", kind: "player", blank: "Their first pick"}],
  sailor: [{id: "drunk", label: "Who is drunk until dusk", kind: "player", blank: "Their pick"}],
  gambler: [{id: "guess", label: "Their guess", kind: "character"}],
  shabaloth: [{id: "regurgitate", label: "Regurgitate (one of last night's victims)", kind: "player", blank: "Nobody"}],
  gossip: [{id: "dies", label: "Who dies", kind: "player", blank: "Nobody"}],
  courtier: [{id: "character", label: "Named character", kind: "character"}],
  tinker: [{id: "dies", label: "Does the Tinker die tonight?", kind: "yesno"}],
};

export function stepTitle(s, C) {
  return C[s.key]?.name ?? MEETING_TITLES[s.key] ?? s.key;
}

// the night ledger: one open card, done cards collapsed, sleeping steps listed apart, dawn summary
export function nightCards(v, C, openStep) {
  const name = pid => v.players.find(p => p.pid === pid)?.name ?? "";
  const player = pid => v.players.find(p => p.pid === pid);
  const steps = v.steps || [];
  const openable = s => !s.done && s.applies;
  const openIdx = openStep !== null && openStep !== undefined && steps[openStep] && openable(steps[openStep])
    ? openStep : steps.findIndex(openable);
  const cards = [], notTonight = [];
  steps.forEach((s, i) => {
    const who = s.pids.map(name).join(", ");
    const title = stepTitle(s, C);
    if (!s.applies && !s.done) {
      const actor = player(s.pids[0]);
      const why = actor && !actor.alive ? "dead" : (C[s.key]?.uses === "once_per_game" && actor?.ability?.used) ? "ability used" : "sleeps tonight";
      notTonight.push({title, who, why});
      return;
    }
    const resolved = !!(s.resolved || s.sent || s.choices.length);
    const state = s.done ? (resolved ? "done" : "skipped") : i === openIdx ? "open" : "upcoming";
    let pill, result = "";
    if (s.done) {
      pill = {text: resolved ? "Done" : "Skipped", cls: "calm"};
      result = s.sent ? `Held for dawn: "${s.sent}"` : s.choices.length ? `Chose ${s.choices.map(name).join(" and ")}.` : resolved ? "Done." : "Skipped.";
    } else if (s.kind === "choose") {
      pill = s.answer ? {text: "Picked on their phone", cls: ""} : s.asked ? {text: "Waiting for their phone", cls: "wait"} : {text: "No phone: pick for them", cls: "calm"};
    } else if (s.kind === "info") pill = {text: "Answer to work out", cls: ""};
    else if (s.kind === "storyteller") pill = {text: "Your call", cls: ""};
    else pill = {text: "Everyone awake", cls: ""};
    const controls = {kind: s.kind, selects: s.choose, variable: !!s.variable, values: s.answer ?? s.choices,
      askAgain: s.kind === "choose" && !!(s.asked || s.answer), allowSelf: s.allow_self, extras: EXTRAS[s.key] ?? [],
      text: s.suggestion, impaired: !!s.impaired, question: s.question || "",
      primary: s.kind === "storyteller" || (s.kind === "choose" && s.suggestion === null) ? "Apply"
        : s.suggestion === null ? "Work out their info" : "Hold for dawn"};
    cards.push({i, key: s.key, title, who, state, pill, hint: s.hint || "", result, controls});
  });
  const waiting = v.night_check && !v.waiting_stopped ? (v.phones || []).filter(x => !x.done).map(x => x.name) : [];
  const phones = {show: !!v.night_check && (v.phones || []).length > 0, done: v.phones_done?.[0] ?? 0, total: v.phones_done?.[1] ?? 0, waiting, stopped: !!v.waiting_stopped};
  const secondRound = {show: v.night > 1, done: !!v.second_round_done, blocked: waiting.length > 0};
  const dawn = {
    deaths: (v.dawn?.deaths ?? []).map(d => ({name: name(d.pid), cause: d.cause, linked: !!d.linked})),
    pending: (v.dawn?.pending ?? []).map((d, index) => ({index, name: name(d.pid), why: d.why})),
    held: v.dawn?.held ?? 0, waiting, blocked: waiting.length > 0,
  };
  return {cards, notTonight, phones, secondRound, dawn, openIdx};
}

// the day ledger: hands, nominations with their clock, abilities usable today, dusk
export function dayModel(v, C) {
  const byPid = Object.fromEntries(v.players.map(p => [p.pid, p]));
  const name = pid => byPid[pid]?.name ?? "";
  const seats = v.players.map(p => p.pid);
  const live = v.clock && v.clock.state !== "done" ? v.clock : null;
  const nominations = (v.nominations_full || []).map((n, i) => {
    const c = n.clock;
    const recorded = n.votes !== null;
    const state = recorded ? "recorded" : c ? c.state : "idle";
    const start = seats.indexOf(n.nominee);
    const order = seats.map((_, k) => seats[(start + 1 + k) % seats.length]);   // clockwise from the nominee, nominee last
    const locked = c ? order.filter(pid => c.locked[pid] !== null && c.locked[pid] !== undefined).map(pid => ({name: name(pid), yes: !!c.locked[pid]})) : [];
    const pending = c ? order.filter(pid => c.locked[pid] === null || c.locked[pid] === undefined).map(pid => ({name: name(pid), up: !!c.hands[pid], ghost: !byPid[pid].alive})) : [];
    let butlerWarn = null;
    if (c && c.state !== "done") {
      for (const p of v.players) {
        if (p.character === "butler" && p.alive && c.hands[p.pid] && (c.locked[p.pid] === null || c.locked[p.pid] === undefined)) {
          const master = v.players.find(x => x.reminders.includes("master"));
          if (master && !c.hands[master.pid]) butlerWarn = `${p.name} is the Butler and ${master.name}'s hand is down: ${p.name}'s hand will not count unless ${master.name} raises hers first.`;
        }
      }
    }
    const tally = recorded ? n.votes : locked.filter(x => x.yes).length;
    return {i, text: `${name(n.nominator)} nominates ${name(n.nominee)}`, state, tally, threshold: v.threshold, locked, pending, butlerWarn, votes: n.votes};
  });
  const abilities = v.players.filter(p => p.ability?.uses === "day" && !p.ability.used && p.alive).map(p => ({
    pid: p.pid, name: p.name,
    label: p.character === "slayer" ? "Slayer, shot unused" : `${C[p.character]?.name ?? p.character}, today`,
    kind: p.character === "slayer" ? "shoot" : p.character === "gossip" ? "gossip" : "none",
  }));
  const picked = (v.announcements || []).some(a => a.includes("the Moonchild, chooses"));
  for (const p of v.players) if (p.character === "moonchild" && !p.alive && !picked) abilities.push({pid: p.pid, name: p.name, label: "Moonchild, chooses a player", kind: "moonchild"});
  const recorded = nominations.filter(n => n.state === "recorded" && n.votes >= v.threshold);
  const top = recorded.length ? Math.max(...recorded.map(n => n.votes)) : 0;
  const leaders = recorded.filter(n => n.votes === top);
  let text = `Nobody has reached ${v.threshold} votes yet. Ending the day with no execution starts the night.`;
  if (leaders.length === 1) text = `${name((v.nominations_full[leaders[0].i]).nominee)} is set to be executed with ${top} votes.`;
  else if (leaders.length > 1) text = `Tied at ${top} votes: nobody is executed.`;
  const pending = (v.pending_deaths || []).map((d, index) => ({index, name: name(d.pid), why: d.why}));
  return {
    announcements: v.announcements || [],
    hands: (v.hands || []).map(pid => ({pid, name: name(pid)})),
    nominations, abilities,
    dusk: {text, pending, mastermind: (v.announcements || []).some(a => a.includes("one more day")), canEnd: !live && !pending.length},
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
