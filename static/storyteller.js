// The grimoire: polls /api/st, renders the top bar, the circle and the right column, posts actions.
// Pure render data comes from stmodel.js / clockmath.js; this file owns the DOM and the Storyteller's UI state.

import { phaseTitle, tokenMarks, seatPositions, nextStepPid, lobbyModel, drawerModel, nightCards } from "./stmodel.js";
import { sound } from "./sound.js";

const KEY = new URLSearchParams(location.search).get("key") || "";
let S = null, C = {}, SCRIPTS = [], lastVersion = -1, toastTimer = null;
let selected = null;          // pid whose drawer is open
let openStep = null;          // night ledger card the Storyteller opened by hand
let mode = "none";            // "none" | "nominator" | "nominee": clicking tokens picks a nomination
let view = "ledger";          // "ledger" | "drawer" | "messages"
let pendingNominator = null;
let logOpen = false, toolsOpen = false;
const dirty = {};             // element id -> value typed but not yet submitted
const voteDraft = {};         // nomination index -> Set of pids

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const cname = id => C[id]?.name ?? "";
const glyph = id => id && C[id]?.icon ? `<span class="glyph" style="--icon:url(/static/icons/${id}.svg)"></span>` : "";
const team = id => ["minion", "demon"].includes(C[id]?.type) ? "evil" : "good";
const tone = id => C[id]?.type === "outsider" ? "outsider" : team(id);
const pname = pid => S.players.find(p => p.pid === pid)?.name ?? "";
const el = id => document.getElementById(id);
const val = id => el(id)?.type === "checkbox" ? el(id).checked : el(id)?.value;
const q = s => `'${s}'`;
const KIND = {townsfolk: "Townsfolk", outsider: "Outsider", minion: "Minion", demon: "Demon"};

function toast(msg) {
  el("toast").innerHTML = `<div class="toast">${esc(msg)}</div>`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el("toast").innerHTML = "", 5000);
}

async function api(path, body) {
  const res = await fetch(path, body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || data.detail?.[0]?.msg || res.statusText);
  return data;
}

async function act(action, body = {}, clearPrefix = null) {
  try {
    const before = S?.script?.id;
    S = await api(`/api/st/${action}?key=${encodeURIComponent(KEY)}`, body);
    if (clearPrefix) Object.keys(dirty).filter(k => k.startsWith(clearPrefix)).forEach(k => delete dirty[k]);
    lastVersion = S.version;
    if (S.script.id !== before) C = await api("/api/characters");
    render();
    return true;
  } catch (e) { toast(e.message); return false; }
}

async function poll() {
  try {
    const s = await api(`/api/st?key=${encodeURIComponent(KEY)}`);
    if (s.version !== lastVersion) { S = s; lastVersion = s.version; render(); }
  } catch (e) { toast(e.message); }
}

// --- rendering ---

function fitNames(root) {
  root.querySelectorAll(".token .char").forEach(c => {
    c.style.fontSize = "";
    const maxH = c.parentElement.clientHeight * 0.7;
    let fs = parseFloat(getComputedStyle(c).fontSize);
    while ((c.scrollWidth > c.clientWidth || c.offsetHeight > maxH) && fs > 6) c.style.fontSize = `${fs -= 0.5}px`;
  });
}

function render() {
  if (!S || drag?.moved) return;
  document.body.classList.toggle("day", S.phase !== "night");
  const focusId = document.activeElement?.id;
  if (selected && !S.players.some(p => p.pid === selected)) { selected = null; view = "ledger"; }
  el("topbar").innerHTML = topbar();
  el("square").innerHTML = square();
  el("square").classList.toggle("seating", ["lobby", "setup"].includes(S.phase));
  fitNames(el("square"));
  el("column").innerHTML = column();
  for (const [id, v] of Object.entries(dirty)) {
    const e = el(id);
    if (!e) continue;
    if (e.type === "checkbox") e.checked = v; else e.value = v;
  }
  if (focusId && el(focusId)) el(focusId).focus();
}

function alive() { return S.players.filter(p => p.alive).length; }

function topbar() {
  const u = S.undo;
  const cost = u ? [u.seen ? "phones already showed this" : "", u.phone_picks ? `clears ${u.phone_picks} ${u.phone_picks === 1 ? "pick" : "picks"} made on phones since` : ""].filter(Boolean).join("; ") : "";
  const phones = S.phase === "night" && S.night_check && S.phones.length ? `<span class="phones-strip">
      <span><b>${S.phones_done[0]} of ${S.phones_done[1]}</b> phones done</span>
      ${S.phones_done[0] < S.phones_done[1] && !S.waiting_stopped ? `<span class="dim">waiting: ${esc(S.phones.filter(x => !x.done).map(x => x.name).join(", "))}</span>
        <button class="btn quiet small accent" onclick="act('stop_waiting')">Stop waiting</button>` : ""}</span>` : "";
  const unread = S.unread ? `<button class="btn quiet small accent" onclick="showMessages()">${S.unread} new ${S.unread === 1 ? "message" : "messages"}</button>` : "";
  return `<h1>${esc(S.script.name)}</h1><span class="phase">${esc(phaseTitle(S))}</span>
    <span class="dim">${S.players.length ? `${alive()} of ${S.players.length} alive` : ""}${S.phase === "day" ? ` · ${S.threshold} votes to execute` : ""}</span>
    ${phones}
    <span class="spacer"></span>${unread}
    ${u ? `<span class="undo"><button class="btn quiet small" onclick="act('undo')" title="Ctrl or Cmd + Z">Undo: ${esc(u.label)}</button>${cost ? `<span class="cost">${esc(cost[0].toUpperCase() + cost.slice(1))}.</span>` : ""}</span>` : ""}
    ${gear()}`;
}

function gear() {
  const started = ["night", "day"].includes(S.phase);
  return `<details class="gear"><summary aria-label="Game settings">${GEAR}</summary><div class="menu">
    <label><input type="checkbox" ${S.night_check ? "checked" : ""} onchange="act('set_night_check', {on: this.checked})"> Night check (phones tap three icons at night; off for remote games)</label>
    <label>Seconds a seat <select onchange="localStorage.setItem('tb_seat_seconds', this.value)">${[2, 3, 4, 5].map(n => `<option ${n === seatSeconds() ? "selected" : ""}>${n}</option>`).join("")}</select></label>
    <label><input type="checkbox" ${sound.muted() ? "checked" : ""} onchange="sound.mute(this.checked)"> Mute the clock</label>
    ${S.phase === "lobby" && !S.players.length ? `<button class="btn quiet small" onclick="changeScript()">Change script</button>` : ""}
    ${started ? `<div class="line"><span class="dim">End the game early</span><button class="btn quiet small" onclick="act('declare_winner', {team:'good'})">Good wins</button><button class="btn quiet small" onclick="act('declare_winner', {team:'evil'})">Evil wins</button></div>` : ""}
  </div></details>`;
}

const GEAR = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"></path></svg>`;

function seatSeconds() { return Number(localStorage.getItem("tb_seat_seconds") || 3); }

function square() {
  const n = S.players.length;
  const pos = seatPositions(n);
  const size = n ? `min(6.4rem, ${Math.round(200 / Math.max(n, 5))}cqmin)` : "6rem";
  const spots = S.players.map((p, i) => {
    const m = tokenMarks(p, S, C);
    const face = p.character
      ? `<span class="char">${glyph(p.character)}${esc(cname(p.character))}${p.believed !== p.character ? `<small>thinks ${esc(cname(p.believed))}</small>` : ""}</span>`
      : `<span class="char"></span>`;
    const cls = [p.character ? tone(p.character) : "blank", p.alive ? "" : "dead", m.lit ? "lit" : "", m.vote === "up" ? "hand" : "",
      selected === p.pid && view === "drawer" ? "selected" : "", mode !== "none" ? "pickme" : ""].join(" ");
    const badge = m.vote === "yes" ? `<span class="vote yes">✓</span>` : m.vote === "no" ? `<span class="vote no">–</span>` : m.vote === "up" ? `<span class="vote up">✋</span>` : "";
    const extra = [];
    if (S.clock && S.clock.state !== "done" && S.clock.nominee === p.pid) extra.push("nominated");
    if (S.hands?.includes(p.pid) && !(S.clock && S.clock.state !== "done")) extra.push("✋");
    return `<div class="spot" style="left:${pos[i].left};top:${pos[i].top}">
      <span class="seatno">${i + 1}</span>
      <button class="token ${cls}" style="--size:${size}" data-pid="${p.pid}" data-seat="${i}" onclick="pick('${p.pid}')" aria-label="${esc(p.name)}${p.character ? ", " + esc(cname(p.character)) : ""}">${face}
        ${!p.alive ? `<span class="shroud" aria-hidden="true"></span>` : ""}
        ${m.pip ? `<span class="pip ${m.pip}" title="${esc(m.pipTitle)}"></span>` : ""}${badge}</button>
      <span class="nameplate ${extra.length ? "nom" : ""}">${esc(p.name)}${extra.length ? " · " + extra.join(" ") : ""}</span>
      ${m.chips.length ? `<div class="reminders">${m.chips.map(c => `<span class="rem ${c.cls}">${esc(c.text)}</span>`).join("")}</div>` : ""}</div>`;
  }).join("");
  return spots + `<div class="center" id="center">${centre()}</div>`;
}

function centre() {
  if (S.phase === "lobby") {
    return `<img class="qr" src="/qr.svg" alt="QR code to join"><div class="url">${esc(S.join_url)}</div>
      <p>${S.players.length ? `${S.players.length} seated. Drag a token onto another seat to move it there.` : "Scan to take a seat, or send the link."}</p>`;
  }
  if (S.phase === "setup") return `<h2>Setup</h2><p>Tap a token to change its character. Drag it to move its seat.</p>`;
  if (S.phase === "night") return `<h2>Night ${S.night}</h2><p>${alive()} alive. ${nextStepPid(S) ? "The glowing token is next." : "Nothing left to resolve."}</p>`;
  if (S.phase === "day") {
    if (mode !== "none") return `<h2>Nominate</h2><p>${mode === "nominator" ? "Click the player who nominates." : `Click the player ${esc(pname(pendingNominator))} nominates.`}</p>`;
    return `<h2>Day ${S.day}</h2><p>${alive()} alive, ${S.threshold} votes to execute.</p>`;
  }
  return `<h2 class="${S.winner}-text">${S.winner === "good" ? "Good" : "Evil"} wins</h2><p>${esc(S.win_reason)}</p>`;
}

function pick(pid) {
  if (justDragged) { justDragged = false; return; }
  if (mode === "nominator") { pendingNominator = pid; mode = "nominee"; render(); return; }
  if (mode === "nominee") {
    const a = pendingNominator;
    mode = "none"; pendingNominator = null;
    act("nominate", {nominator: a, nominee: pid, spy_as_townsfolk: !!val("nom-spy")});
    return;
  }
  if (S.clock && !["done"].includes(S.clock.state)) {
    act("set_hand", {pid, up: !S.clock.hands.includes(pid)});
    return;
  }
  if (selected === pid && view === "drawer") { selected = null; view = "ledger"; }
  else { selected = pid; view = "drawer"; abilityTarget = null; reminderPicker = false; }
  // the Storyteller has now read what this player wrote
  if (view === "drawer" && (S.threads?.[pid] ?? []).some(m => m.from === "player" && !m.seen)) { act("read_thread", {pid}); return; }
  render();
}

function closeDrawer() { selected = null; view = "ledger"; render(); }
function showMessages() { view = view === "messages" ? "ledger" : "messages"; selected = null; render(); }
function changeScript() { sessionStorage.removeItem("tb_script_chosen"); render(); }

// --- drag a token onto another seat (lobby and setup) ---
let drag = null, justDragged = false;

function seatAt(x, y, rect) {
  const n = S.players.length;
  const angle = Math.atan2(y - (rect.top + rect.height / 2), x - (rect.left + rect.width / 2));
  const turn = ((angle + Math.PI / 2) / (2 * Math.PI) + 1) % 1;
  return Math.round(turn * n) % n;
}

function markTarget(seat) {
  document.querySelectorAll(".spot.target").forEach(e => e.classList.remove("target"));
  if (seat !== null && seat !== drag.from) document.querySelector(`.token[data-seat="${seat}"]`)?.closest(".spot").classList.add("target");
}

function installDrag() {
  const sq = el("square");
  sq.addEventListener("pointerdown", e => {
    const tok = e.target.closest(".token[data-pid]");
    if (!tok || !["lobby", "setup"].includes(S?.phase)) return;
    drag = {pid: tok.dataset.pid, from: Number(tok.dataset.seat), to: null, x0: e.clientX, y0: e.clientY, moved: false, spot: tok.closest(".spot")};
    tok.setPointerCapture(e.pointerId);
  });
  sq.addEventListener("pointermove", e => {
    if (!drag) return;
    if (!drag.moved && Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 6) return;
    drag.moved = true;
    const r = sq.getBoundingClientRect();
    drag.spot.classList.add("dragging");
    drag.spot.style.left = `${((e.clientX - r.left) / r.width) * 100}%`;
    drag.spot.style.top = `${((e.clientY - r.top) / r.height) * 100}%`;
    drag.to = seatAt(e.clientX, e.clientY, r);
    markTarget(drag.to);
  });
  const endDrag = () => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.moved) return;
    justDragged = true;
    setTimeout(() => { justDragged = false; }, 0);
    if (d.to !== null && d.to !== d.from) act("move_player", {pid: d.pid, delta: d.to - d.from});
    else render();
  };
  sq.addEventListener("pointerup", endDrag);
  sq.addEventListener("pointercancel", endDrag);
}

// --- the right column ---

function column() {
  if (view === "drawer" && selected) return drawer();
  if (view === "messages") return messages();
  if (S.phase === "lobby" && !S.players.length && !sessionStorage.getItem("tb_script_chosen")) return picker();
  return ({lobby, setup, night, day, over})[S.phase]() + tools() + logBlock();
}

const BLURB = {
  tb: ["Beginner", "Clear information, one death a night, a Demon that dies when executed. The script every table starts on."],
  bmr: ["Intermediate", "Deaths pile up at night, Minions kill too, and the Demon may not die when you think. For tables that know the game and do not fear dying."],
};

function picker() {
  const cards = SCRIPTS.map(s => `<article class="script-card">
      <h3 class="${s.id === "tb" ? "good-text" : "evil-text"}">${esc(s.name)}</h3>
      <p class="note">${esc(BLURB[s.id]?.[0] ?? "")}</p>
      <p>${esc(BLURB[s.id]?.[1] ?? "")}</p>
      <p class="note">${s.counts.townsfolk} Townsfolk · ${s.counts.outsider} Outsiders · ${s.counts.minion} Minions · ${s.counts.demon} ${s.counts.demon === 1 ? "Demon" : "Demons"}</p>
      <button class="btn" onclick="chooseScript('${esc(s.id)}')">Run ${esc(s.name)}</button></article>`).join("");
  return `<h2>Which script tonight?</h2><p class="lede">Players join after this. You can change your mind until the first person takes a seat.</p>${cards}`;
}

async function chooseScript(id) {
  if (await act("set_script", {script: id})) { sessionStorage.setItem("tb_script_chosen", "1"); render(); }
}

async function copyLink() {
  try { await navigator.clipboard.writeText(S.join_url); toast("Link copied"); } catch { toast("Could not copy; select the link instead"); }
}

function opts(list, chosen, blank) {
  return (blank !== undefined ? `<option value="">${esc(blank)}</option>` : "") +
    list.map(([v, label]) => `<option value="${esc(v)}" ${v === chosen ? "selected" : ""}>${esc(label)}</option>`).join("");
}
const playerOpts = (filter = () => true, chosen, blank) =>
  opts(S.players.filter(filter).map(p => [p.pid, p.name + (p.alive ? "" : " (dead)")]), chosen, blank);
const charOpts = (chosen, type) =>
  opts(Object.entries(C).filter(([, c]) => !type || c.type === type).map(([id, c]) => [id, c.name]), chosen);

function bluffOpts(chosen) {
  const held = new Set(S.players.flatMap(p => [p.character, p.believed]));
  return opts(Object.entries(C).filter(([id, c]) => id === chosen || (["townsfolk", "outsider"].includes(c.type) && !held.has(id)))
    .map(([id, c]) => [id, c.name]), chosen);
}

function roleDetails(p) {
  const c = C[p.character];
  if (!c) return "";
  let h = `<div class="details"><div class="role ${tone(p.character)}-text">${glyph(p.character)}${esc(c.name)}</div>
    <div class="kind">${KIND[c.type]}, ${team(p.character)} team</div><p>${esc(c.ability)}</p>`;
  if (p.believed && p.believed !== p.character) {
    const b = C[p.believed];
    h += `<div class="believed"><div class="kind">Thinks they are the ${esc(b.name)}. Their ability does not work.</div><p>${esc(b.ability)}</p></div>`;
  }
  if (p.reminders.length) h += `<div class="kind">Right now: ${esc(p.reminders.join(", "))}.</div>`;
  return h + `</div>`;
}

// --- the token drawer ---
let shootTarget = null, abilityTarget = null, reminderPicker = false;

function drawer() {
  const p = S.players.find(x => x.pid === selected);
  const d = drawerModel(p, S, C);
  const id = p.pid;
  const head = `<div class="drawer-head"><button class="btn quiet small dim" onclick="closeDrawer()">← Back</button><button class="btn quiet small dim" onclick="closeDrawer()" aria-label="Close">✕</button></div>
    <h2>${esc(d.name)} <span class="seat">seat ${d.seat}</span></h2>`;
  if (S.phase === "lobby" || S.phase === "setup") return head + lobbyDrawer(p);
  if (S.phase === "over") return head + roleDetails(p);
  const role = d.role ? `<div class="role-line ${d.role.team}-text">${glyph(d.role.id)}${esc(d.role.name)} <span class="note">${esc(d.role.kind)}, ${d.role.team} team${d.thinks ? ` · thinks they are the ${esc(d.thinks)}` : ""}</span></div>
    <p class="note" style="color:var(--ink)">${esc(d.role.ability)}</p>` : "";
  const status = `<div class="toggles">${d.status.map(s => `<button class="tog" aria-pressed="${s.on}" onclick="act('${s.action.name}', ${JSON.stringify(s.action.body).replace(/"/g, "&quot;")})">${esc(s.label)}</button>`).join("")}</div>`;
  const rems = `<h3>Reminders</h3><div class="chips">${d.reminders.map(r => `<span class="rem ${r.cls} big">${esc(r.text)} <button class="x" aria-label="Remove ${esc(r.text)}" onclick="act('set_reminder', {pid:${q(id)}, text:${q(r.text)}, on:false})">✕</button></span>`).join("")}
      <button class="btn quiet small" onclick="ui.picker(${!reminderPicker})">+ Reminder</button></div>
    ${reminderPicker ? `<div class="chips picker">${d.options.map(t => `<button class="tog" onclick="ui.picker(false); act('set_reminder', {pid:${q(id)}, text:${q(t)}, on:true})">${esc(t)}</button>`).join("")}</div>` : ""}`;
  const exempt = d.showExempt ? `<h3>Night check</h3><label class="line note"><input type="checkbox" ${d.exempt ? "checked" : ""} onchange="act('set_exempt', {pid:${q(id)}, on:this.checked})"> Exempt from the night check (a remote player)</label>` : "";
  const night = S.phase === "night";
  const thread = `<h3>Thread with ${esc(d.name)}</h3>
    <div class="thread">${d.thread.slice(-6).map(m => `<div class="bub ${m.from === "player" ? "them" : "me"}">${esc(m.text)}</div>`).join("") || `<p class="note">Nothing yet.</p>`}</div>
    <div class="line"><input id="msg-${id}" placeholder="Message ${esc(d.name)}" style="flex:1" autocomplete="off">
      <button class="btn small" onclick="act('message', {pid:${q(id)}, text: val('msg-${id}')}, 'msg-${id}')">${night ? "Hold until dawn" : "Send"}</button>
      ${night ? `<button class="btn quiet small" onclick="act('message', {pid:${q(id)}, text: val('msg-${id}'), now: true}, 'msg-${id}')">Send now</button>` : ""}</div>`;
  const change = `<details class="tools"><summary>Change character</summary><div class="line"><select id="ch-${id}">${charOpts(p.character)}</select>
      <button class="btn quiet small" onclick="act('set_character', {pid:${q(id)}, character: val('ch-${id}')}, 'ch-${id}')">Change</button></div></details>`;
  return head + role + status + abilityBlock(p, d) + rems + exempt + thread + change;
}

function lobbyDrawer(p) {
  const id = p.pid;
  let body = `<div class="acts"><button class="btn quiet small" onclick="act('move_player', {pid:${q(id)}, delta:-1})">Move anticlockwise</button>
      <button class="btn quiet small" onclick="act('move_player', {pid:${q(id)}, delta:1})">Move clockwise</button></div>`;
  if (S.phase === "lobby") body += `<div class="acts"><button class="btn quiet small" onclick="act('remove_player', {pid:${q(id)}})">Remove from the game</button></div>`;
  if (S.phase === "setup") {
    body += `<label class="field"><span>Character</span><select onchange="act('set_character', {pid:${q(id)}, character:this.value})">${charOpts(p.character)}</select></label>`;
    if (C[p.character]?.fake) body += `<label class="field"><span>Believes they are</span><select onchange="act('set_character', {pid:${q(id)}, character:${q(p.character)}, believed:this.value})">${charOpts(p.believed, C[p.character].fake)}</select></label>`;
    body += roleDetails(p);
  }
  return body;
}

function abilityBlock(p, d) {
  const a = d.ability;
  if (!a.title) return "";
  const id = p.pid;
  let action = "";
  const targets = (filter) => S.players.filter(x => x.pid !== id && filter(x)).map(x =>
    `<button class="pick" aria-pressed="${abilityTarget === x.pid}" onclick="ui.target(${q(x.pid)})">${glyph(x.character)}${esc(x.name)}</button>`).join("");
  if (a.kind === "shoot") {
    action = `<p class="note">${esc(p.name)} shoots at</p><div class="picks">${targets(x => x.alive)}</div>
      <label class="line note"><input type="checkbox" id="recluse-${id}"> The Recluse registers as the Demon</label>
      <div class="acts"><button class="btn small" ${abilityTarget ? "" : "disabled"} onclick="ui.target(null); act('day_ability', {pid:${q(id)}, options:{target:${q(abilityTarget)}, recluse_as_demon: val('recluse-${id}')}})">Resolve the shot</button></div>`;
  } else if (a.kind === "gossip") {
    action = `<p class="note">Was today's statement true? If so, you pick who dies tonight.</p>
      <div class="acts"><button class="btn small" onclick="act('day_ability', {pid:${q(id)}, options:{true:true}})">True</button><button class="btn quiet small" onclick="act('day_ability', {pid:${q(id)}, options:{true:false}})">False</button></div>`;
  } else if (a.kind === "moonchild") {
    action = `<p class="note">${esc(p.name)} chooses, out loud</p><div class="picks">${targets(x => x.alive)}</div>
      <div class="acts"><button class="btn small" ${abilityTarget ? "" : "disabled"} onclick="ui.target(null); act('day_ability', {pid:${q(id)}, options:{target:${q(abilityTarget)}}})">Record the choice</button></div>`;
  }
  return `<div class="card-soft"><div class="line" style="justify-content:space-between;margin:0"><span class="disp">${esc(a.title)}</span><span class="state">${esc(a.state)}</span></div>
    ${a.note ? `<p class="note">${esc(a.note)}</p>` : ""}${action}</div>`;
}

function messages() {
  return `<div class="drawer-head"><button class="btn quiet small dim" onclick="showMessages()">← Back</button></div><h2>Messages</h2><p class="note">Coming in a later task.</p>`;
}

function lobby() {
  const m = lobbyModel(S);
  const seated = m.seated.map(s => `<div class="row-line"><b>${s.seat}</b> ${esc(s.name)}${s.phone ? "" : ` <span class="tag">no phone</span>`}
      <button class="btn quiet small dim" style="margin-left:auto" onclick="act('remove_player', {pid:${q(s.pid)}})">Remove</button></div>`).join("");
  return `<h2>Gather the players</h2>
    <p class="lede">Scan the code at the table, or send the link. Then drag the tokens so the circle matches the real table, clockwise.</p>
    <div class="linkbox"><span>${esc(S.join_url)}</span><button class="btn quiet small" onclick="copyLink()">Copy link</button></div>
    <h3>Seated, clockwise</h3>
    ${seated || `<p class="note">Nobody yet.</p>`}
    <div class="line"><input id="add-name" placeholder="Someone without a phone" style="flex:1"><button class="btn quiet small" onclick="act('add_player', {name: val('add-name')}, 'add-')">Seat them</button></div>
    <p class="note">You read their character and night info to them yourself.</p>
    <div class="card-accent"><h3>Deal</h3>
      <p class="note">${esc(m.why)} Night check is ${S.night_check ? "on; turn it off in settings for remote games" : "off: phones are not waited for"}.</p>
      <button class="btn" ${m.canDeal ? "" : "disabled"} onclick="act('deal')">Deal characters</button></div>`;
}

function setup() {
  const types = ["townsfolk", "outsider", "minion", "demon"];
  const plural = {townsfolk: "Townsfolk", outsider: "Outsiders", minion: "Minions", demon: "Demon"};
  const counts = types.map(t => `${S.players.filter(p => C[p.character]?.type === t).length} ${plural[t]}`).join(", ");
  const rh = S.script.id === "tb" ? `<label class="field"><span>Fortune Teller's red herring</span><select id="rh">${playerOpts(p => team(p.character) === "good", S.red_herring)}</select></label>` : "";
  return `<h2>Check the deal</h2>
    <p class="lede">${counts}. Tap any token to swap its character. Nobody sees anything until you start.</p>
    ${S.warnings.map(w => `<div class="warn">${esc(w)}</div>`).join("")}
    ${rh}
    <div class="field"><span>Demon bluffs: good characters nobody holds</span><div class="line">${[0, 1, 2].map(i => `<select id="bluff-${i}" aria-label="Bluff ${i + 1}">${bluffOpts(S.bluffs[i])}</select>`).join("")}</div>
      ${S.bluff_problems.map(w => `<div class="warn">${esc(w)}</div>`).join("")}</div>
    <button class="btn quiet small" onclick="act('set_setup', {red_herring: val('rh') || null, bluffs: [0,1,2].map(i => val('bluff-'+i))}, 'bluff-')">Save ${S.script.id === "tb" ? "red herring and " : ""}bluffs</button>
    <h3>Begin</h3>
    <div class="line"><button class="btn" ${S.bluff_problems.length ? "disabled" : ""} onclick="act('start_game')">Start the first night</button>
      <button class="btn quiet" onclick="act('deal', {}, 'bluff-')">Deal again</button></div>`;
}

// --- the night ledger ---

function extraInput(i, x, s) {
  const id = `x-${i}-${x.id}`;
  if (x.kind === "player") return `<label class="field"><span>${esc(x.label)}</span><select id="${id}">${playerOpts(() => true, "", x.blank)}</select></label>`;
  if (x.kind === "character") return `<label class="field"><span>${esc(x.label)}</span><select id="${id}">${charOpts("")}</select></label>`;
  return "";   // yesno renders as two primary buttons
}

function extrasArgs(i, c) {
  return c.extras.filter(x => x.kind !== "yesno").map(x => `, ${x.id}: val('x-${i}-${x.id}') || null`).join("");
}

function stepCard(c) {
  const i = c.i;
  const head = `<button class="head" onclick="ui.open(${c.state === "open" ? -1 : i})" aria-expanded="${c.state === "open"}">
      <span><span class="stitle">${esc(c.title)}</span> <span class="note inline">· ${esc(c.who)}</span></span><span class="pill ${c.pill.cls}">${esc(c.pill.text)}</span></button>`;
  const num = `<span class="num ${c.state}">${c.state === "done" ? "✓" : i + 1}</span>`;
  if (c.state !== "open") {
    const reopen = c.state === "done" || c.state === "skipped" ? `<button class="btn quiet small dim" onclick="act('finish_step', {step:${i}, done:false})">Reopen</button>` : "";
    return `<li class="step ${c.state}">${num}${head}${c.result ? `<div class="result">${esc(c.result)} ${reopen}</div>` : ""}</li>`;
  }
  const k = c.controls;
  let body = `<p class="note">${esc(c.hint)}</p>`;
  if (k.impaired) body += `<p><span class="flag">Drunk or poisoned</span> <span class="note inline">Their information may be false.</span></p>`;
  let primary = "";
  if (k.kind === "choose") {
    const selects = [...Array(k.selects).keys()].map(n => `<select id="c-${i}-${n}" aria-label="Pick ${n + 1}">${playerOpts(() => true, k.values[n] ?? "", k.variable ? "Nobody" : "Pick a player")}</select>`).join("");
    body += `<div class="line">${selects}${k.askAgain ? `<button class="btn quiet small" onclick="act('ask', {step:${i}})">Ask again</button>` : ""}</div>
      ${k.variable ? `<p class="note">Nobody, one player, or three after a night of nobody.</p>` : ""}
      ${k.extras.map(x => extraInput(i, x)).join("")}`;
    const picks = `[${[...Array(k.selects).keys()].map(n => `val('c-${i}-${n}')`).join(",")}].filter(Boolean)`;
    const apply = `act('resolve', {step:${i}, choices:${picks}${extrasArgs(i, k)}}, 'c-${i}')`;
    if (k.text === null) primary = `<button class="btn small primary" onclick="${apply}">Apply</button>`;
    else {
      // the pick is applied and produced information: hold the (editable) text for dawn
      body += `<label class="field"><span>What they learn (edit if someone is drunk, poisoned, or misregisters)</span><textarea id="t-${i}">${esc(k.text)}</textarea></label>`;
      primary = `<button class="btn small primary" onclick="ui.open(null, false); act('send', {step:${i}, text: val('t-${i}')}, 't-${i}')">Hold for dawn</button>
        <button class="btn quiet small" onclick="${apply}">Apply again</button>`;
    }
  } else if (k.kind === "storyteller") {
    body += `<p class="question">${esc(k.question)}</p>${k.extras.filter(x => x.kind !== "yesno").map(x => extraInput(i, x)).join("")}`;
    const yesno = k.extras.find(x => x.kind === "yesno");
    primary = yesno
      ? `<button class="btn small primary" onclick="ui.open(null, false); act('resolve', {step:${i}, choices:[], ${yesno.id}:true})">Yes</button>
         <button class="btn quiet small" onclick="ui.open(null, false); act('resolve', {step:${i}, choices:[], ${yesno.id}:false})">No</button>`
      : `<button class="btn small primary" onclick="ui.open(null, false); act('resolve', {step:${i}, choices:[]${extrasArgs(i, k)}})">${esc(k.primary)}</button>`;
  } else {
    // info and meetings: work it out, then hold the (editable) text for dawn
    if (k.text !== null) body += `<label class="field"><span>What they learn (edit if someone is drunk, poisoned, or misregisters)</span><textarea id="t-${i}">${esc(k.text)}</textarea></label>`;
    primary = k.text === null
      ? `<button class="btn small primary" onclick="act('resolve', {step:${i}, choices:[]})">${esc(k.primary)}</button>`
      : `<button class="btn small primary" onclick="ui.open(null, false); act('send', {step:${i}, text: val('t-${i}')}, 't-${i}')">${esc(k.primary)}</button>`;
  }
  body += `<div class="line">${primary}<button class="btn quiet small" style="margin-left:auto" onclick="ui.open(null, false); act('finish_step', {step:${i}, done:true})">Skip</button></div>`;
  return `<li class="step open">${num}${head}${body}</li>`;
}

function night() {
  const n = nightCards(S, C, openStep);
  const strip = n.phones.show ? `<div class="phones">${S.phones.map(x => `<span class="phone ${x.done || n.phones.stopped ? "" : "wait"}">${esc(x.name)}</span>`).join("")}</div>` : "";
  const waitNote = n.dawn.waiting.length ? `<p class="note red">Waiting for ${esc(n.dawn.waiting.join(", "))}, or stop waiting in the top bar.</p>` : "";
  const round2 = n.secondRound.show ? `<h3>Second round</h3>${n.secondRound.done ? `<p class="note">Every phone has buzzed a second time.</p>`
      : `<p class="note">The Demon's kill buzzes every phone again; a step that only wakes after a death gets its prompt then.</p><button class="btn quiet small" ${n.secondRound.blocked ? "disabled" : ""} onclick="act('second_round')">Buzz every phone now</button>`}` : "";
  const deaths = n.dawn.deaths.length ? n.dawn.deaths.map(d => `<p class="death ${d.linked ? "linked" : ""}"><b>${esc(d.name)}</b> <span class="note inline">${esc(d.cause)}</span></p>`).join("") : `<p class="note">Nobody has died yet tonight.</p>`;
  const pending = n.dawn.pending.map(d => `<div class="line"><span><b>${esc(d.name)}</b> <span class="note inline">${esc(d.why)}</span></span>
      <button class="btn small" onclick="act('confirm_death', {index:${d.index}, dies:true})">Dies</button><button class="btn quiet small" onclick="act('confirm_death', {index:${d.index}, dies:false})">Survives</button></div>`).join("");
  return `${strip}<h2>Tonight, in order</h2>
    <p class="lede">Only the open step needs you. Enter applies it, ↑ ↓ move, S skips.</p>
    ${n.cards.length ? `<ol class="order">${n.cards.map(stepCard).join("")}</ol>` : `<p class="note">Nobody has anything to do tonight.</p>`}
    ${n.notTonight.length ? `<p class="note">Not tonight: ${n.notTonight.map(x => `${esc(x.title)} (${esc(x.who)}, ${esc(x.why)})`).join(" · ")}</p>` : ""}
    ${round2}
    <div class="card-accent"><h3>Dawn</h3>${deaths}${pending}
      <p class="note">${n.dawn.held ? `${n.dawn.held} ${n.dawn.held === 1 ? "message is" : "messages are"} held for dawn; everyone else gets "Nothing to report".` : `Everyone without news gets "Nothing to report".`}</p>
      ${waitNote}<button class="btn" ${n.dawn.blocked || n.dawn.pending.length ? "disabled" : ""} onclick="ui.open(null, false); act('start_day')">Deliver everything and start day ${S.day + 1}</button></div>`;
}

function nightKey(e) {
  if (S?.phase !== "night" || view !== "ledger") return false;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return false;
  const n = nightCards(S, C, openStep);
  const idx = n.cards.findIndex(c => c.state === "open");
  if (e.key === "Enter") { document.querySelector(".step.open .primary")?.click(); return true; }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    const next = n.cards[idx + (e.key === "ArrowDown" ? 1 : -1)];
    if (next) ui.open(next.i);
    return true;
  }
  if (e.key.toLowerCase() === "s" && idx >= 0) { act("finish_step", {step: n.cards[idx].i, done: true}); return true; }
  return false;
}

function toggleVote(i, pid) {
  const set = voteDraft[i];
  set.has(pid) ? set.delete(pid) : set.add(pid);
  render();
}

// Task 5 replaces this with the day ledger; until then: nominations and votes by chips
function day() {
  const noms = S.nominations_full.map((n, i) => {
    voteDraft[i] ??= new Set(n.voters);
    const eligible = S.players.filter(p => p.alive || p.ghost_vote || n.voters.includes(p.pid));
    const enough = n.votes !== null && n.votes >= S.threshold;
    return `<div class="nom"><div class="line"><span class="tally ${enough ? "enough" : ""}">${esc(pname(n.nominator))} nominates ${esc(pname(n.nominee))}</span>
        ${n.votes !== null ? `<span class="note">${n.votes} ${n.votes === 1 ? "vote" : "votes"}${enough ? ", enough to execute" : ""}</span>` : ""}</div>
      <div class="chips">${eligible.map(p => `<button class="chip ${p.alive ? "" : "ghost"}" aria-pressed="${voteDraft[i].has(p.pid)}" onclick="toggleVote(${i}, '${p.pid}')">${esc(p.name)}</button>`).join("")}</div>
      <button class="btn quiet small" onclick="act('record_votes', {nomination:${i}, voters:[...voteDraft[${i}]]}).then(() => delete voteDraft[${i}])">Record ${voteDraft[i].size} ${voteDraft[i].size === 1 ? "vote" : "votes"}</button></div>`;
  }).join("");
  return `<h2>Day ${S.day}</h2>
    <p class="lede">${S.threshold} votes execute.</p>
    <ul class="crier">${S.announcements.map(a => `<li>${esc(a)}</li>`).join("")}</ul>
    <h3>Nominations</h3>
    <div class="line"><select id="nom-a" aria-label="Nominator">${playerOpts(p => p.alive, "", "Who nominates")}</select>
      <select id="nom-b" aria-label="Nominee">${playerOpts(p => p.alive, "", "Who is nominated")}</select></div>
    <label class="line note"><input type="checkbox" id="nom-spy"> A Spy nominating the Virgin registers as Townsfolk</label>
    <button class="btn small" onclick="act('nominate', {nominator: val('nom-a'), nominee: val('nom-b'), spy_as_townsfolk: val('nom-spy')}, 'nom-')">Nominate</button>
    ${noms}
    <h3>Dusk</h3>
    <button class="btn" onclick="Object.keys(voteDraft).forEach(k => delete voteDraft[k]); act('end_day')">End the day</button>`;
}

function over() {
  return `<h2 class="verdict ${S.winner}-text">${S.winner === "good" ? "Good" : "Evil"} wins</h2>
    <p class="lede">${esc(S.win_reason)} Every character is now revealed on players' phones.</p>
    <div class="line"><button class="btn" onclick="ui.deselect(); act('reset')">New game, same players</button>
      <button class="btn quiet" onclick="act('reset').then(ok => ok && changeScript())">Change script</button></div>`;
}

function tools() {
  if (S.phase !== "night" && S.phase !== "day") return "";
  return `<details class="tools" ${toolsOpen ? "open" : ""} ontoggle="ui.tools(this.open)"><summary>Setup secrets</summary>
    <p class="note">Bluffs: ${S.bluffs.map(cname).join(", ")}.${S.red_herring ? ` Red herring: ${esc(pname(S.red_herring))}.` : ""}</p></details>`;
}

function logBlock() {
  if (!S.log.length) return "";
  return `<details class="log" ${logOpen ? "open" : ""} ontoggle="ui.log(this.open)"><summary>Everything that has happened</summary>
    <ol reversed>${S.log.slice().reverse().map(l => `<li>${esc(l)}</li>`).join("")}</ol></details>`;
}

// --- wiring ---

// inline handlers in the templates reach module state through these
const ui = {
  open(i, rerender = true) { openStep = i; if (rerender) render(); },
  target(pid) { abilityTarget = pid; render(); },
  picker(on) { reminderPicker = on; render(); },
  tools(v) { toolsOpen = v; },
  log(v) { logOpen = v; },
  deselect() { selected = null; view = "ledger"; },
};
Object.assign(window, {act, pick, closeDrawer, showMessages, changeScript, chooseScript, copyLink, toggleVote, val, voteDraft, sound, render, ui});

document.addEventListener("input", e => { if (e.target.id) dirty[e.target.id] = e.target.type === "checkbox" ? e.target.checked : e.target.value; });
document.addEventListener("pointerdown", () => sound.unlock(), {once: true});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && view !== "ledger") { closeDrawer(); return; }
  if (nightKey(e)) { e.preventDefault(); return; }
  if (e.key.toLowerCase() !== "z" || !(e.metaKey || e.ctrlKey) || e.shiftKey) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || !S?.undo) return;
  e.preventDefault();
  act("undo");
});
addEventListener("resize", () => el("square") && fitNames(el("square")));

installDrag();
api("/api/scripts").then(s => { SCRIPTS = s; });
api("/api/characters").then(c => { C = c; lastVersion = -1; poll(); });
setInterval(poll, 1200);
