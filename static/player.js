// The player's page: polls /api/state, renders the character, the thread with the Storyteller, the square
// and the vote; posts joins, picks, taps, messages and hands. Pure render data comes from pmodel.js / clockmath.js.

import { nudge, tabs, layout, abilityLine, thread as threadModel, square as squareModel, handButton } from "./pmodel.js";
import { handAngle, handIndex, serverNow } from "./clockmath.js";
import { sound } from "./sound.js";

const $app = document.getElementById("app");
let token = localStorage.getItem("tb_token");
let state = null, chars = {}, lastVersion = -1, receivedAt = 0;
let revealed = false, hideTimer = null, hideAt = 0;
let picks = [], tapSeq = [], tapKey = "", tapError = "";
let draft = "", error = "", sentNote = false, handError = "";
let seen = Number(localStorage.getItem("tb_seen") || 0);
let lastBuzz = localStorage.getItem("tb_buzz");
let view = "character";
let width = innerWidth;
let lastHandIdx = null, lastClockKey = null;

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const team = type => (type === "minion" || type === "demon") ? "evil" : "good";
const tone = type => type === "outsider" ? "outsider" : team(type);
const glyph = id => chars[id]?.icon ? `<span class="glyph" style="--icon:url(/static/icons/${id}.svg)"></span>` : "";
const TYPE_LABEL = {townsfolk: "Townsfolk", outsider: "Outsider", minion: "Minion", demon: "Demon"};
const seatName = pid => state?.seats.find(x => x.pid === pid)?.name ?? "";
const isLaptop = () => layout(width) === "laptop";

// five-leaf clover: the grimoire cover a hidden character sits behind
const LEAF = "M50 50 C40 42 30 33 36 22 C41 13 50 16 50 25 C50 16 59 13 64 22 C70 33 60 42 50 50 Z";
const EMBLEM = `<svg viewBox="0 0 100 100" aria-hidden="true">
  <circle cx="50" cy="50" r="46" fill="none" stroke="#E0962F" stroke-width="1.2"/>
  <circle cx="50" cy="50" r="42" fill="none" stroke="#E0962F" stroke-width="0.6" stroke-dasharray="1.5 2.5"/>
  ${[...Array(5).keys()].map(i => `<path d="${LEAF}" fill="#22332A" stroke="#F5BC55" stroke-width="1.4" transform="rotate(${i * 72} 50 50)"/>
    <path d="M50 44 L50 27" stroke="#B23A33" stroke-width="0.9" transform="rotate(${i * 72} 50 50)"/>`).join("")}
  <circle cx="50" cy="50" r="3.2" fill="#F5BC55"/></svg>`;
const SEAL = `<span class="seal" aria-hidden="true">S</span>`;

async function api(path, body) {
  const res = await fetch(path, body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || data.detail?.[0]?.msg || res.statusText);
  return data;
}

async function poll() {
  try {
    const s = await api(token ? `/api/state?token=${encodeURIComponent(token)}` : "/api/state");
    receivedAt = Date.now();
    error = "";
    if (state && s.version === lastVersion) { state.server_time = s.server_time; return; }
    state = s;
  } catch (e) {
    if (token && /join again/.test(e.message)) { token = null; localStorage.removeItem("tb_token"); state = null; }
    error = e.message;
  }
  // re-rendering while typing would wipe the field
  if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  if (!state || state.version !== lastVersion || error) { lastVersion = state?.version; render(); }
}

async function join(ev) {
  ev.preventDefault();
  try {
    const r = await api("/api/join", {name: document.getElementById("name").value});
    token = r.token;
    localStorage.setItem("tb_token", token);
    localStorage.setItem("tb_seen", "0");
    seen = 0; lastVersion = -1;
    document.activeElement.blur();
    poll();
  } catch (e) { error = e.message; render(); }
}

// --- privacy: the token and the thread hide again on their own ---

function markSeen() {
  if (!state?.me) return;
  seen = state.me.thread.filter(m => m.from === "st").length;
  localStorage.setItem("tb_seen", String(seen));
}

function flip() {
  revealed = !revealed;
  clearTimeout(hideTimer);
  if (revealed) { markSeen(); armHide(); }
  render();
}

function armHide() {
  clearTimeout(hideTimer);
  hideAt = Date.now() + 45000;
  hideTimer = setTimeout(() => { revealed = false; render(); }, 45000);
}

function tickHide() {
  const e = document.getElementById("hide-in");
  if (e) e.textContent = Math.max(0, Math.ceil((hideAt - Date.now()) / 1000));
}

function show(v) {
  view = v;
  if (v === "messages" && revealed) markSeen();
  scrollTo(0, 0);
  render();
}

// --- player actions ---

async function sendMessage() {
  try {
    await api("/api/message", {token, text: draft});
    draft = ""; sentNote = true;
    document.activeElement?.blur();
    lastVersion = -1;
    poll();
  } catch (e) { error = e.message; render(); }
}

function togglePick(pid, count) {
  if (picks.includes(pid)) picks = picks.filter(p => p !== pid);
  else if (picks.length < count) picks = [...picks, pid];
  armHide();
  render();
}

async function confirmPick() {
  try {
    if (state.me.role?.id === "butler" && picks.length === 1) localStorage.setItem("tb_master", picks[0]);
    await api("/api/choose", {token, choices: picks});
    picks = []; lastVersion = -1;
    poll();
  } catch (e) { error = e.message; render(); }
}

async function tapIcon(id) {
  const target = state.me.prompt.target;
  if (id !== target[tapSeq.length]) { tapSeq = []; tapError = "Not quite. Start again from the first one."; render(); return; }
  tapSeq = [...tapSeq, id];
  tapError = "";
  armHide();
  if (tapSeq.length < target.length) { render(); return; }
  try { await api("/api/tap", {token, sequence: tapSeq}); lastVersion = -1; poll(); }
  catch (e) { tapSeq = []; tapError = e.message; render(); }
}

async function toggleHand() {
  const b = handButton(state, state.me, serverNow(state, receivedAt), localStorage.getItem("tb_master"));
  if (b.disabled) return;
  try { await api("/api/hand", {token, up: !b.pressed}); handError = ""; lastVersion = -1; poll(); }
  catch (e) { handError = e.message; render(); }
}

// --- pieces ---

function when(s) {
  return {lobby: "Waiting for everyone to sit down", setup: "The Storyteller is dealing",
          night: `Night ${s.night}`, day: `Day ${s.day}`, over: "The game is over"}[s.phase];
}

function joinScreen() {
  const open = !state || state.phase === "lobby";
  return `<div class="top"><h1>${esc(state?.script?.name ?? "Blood on the Clocktower")}</h1></div>
    <div class="join paper">${open ? `
      <h2>Take a seat</h2>
      <p>Use the name everyone at the table calls you.</p>
      <form onsubmit="join(event)"><input id="name" placeholder="Your name" autocomplete="off" maxlength="20" required>
      <button class="btn">Join the game</button></form>` : `
      <h2>This game has started</h2>
      <p>Ask the Storyteller to add you to the next one.</p>`}
      ${error ? `<p class="err">${esc(error)}</p>` : ""}</div>`;
}

function character(me) {
  if (!me.role) {
    return `<div class="hero"><div class="token blank" style="--size:15rem"><span class="char">Your character is dealt when the game starts</span></div></div>`;
  }
  const r = me.role, t = team(r.type), c = tone(r.type);
  const line = abilityLine(me, chars);
  return `<div class="hero">
    <button class="flip ${revealed ? "open" : ""}" onclick="flip()" aria-label="${revealed ? "Hide" : "Show"} my character">
      <div class="inner">
        <div class="face back"><div class="token">${EMBLEM}</div></div>
        <div class="face front"><div class="token ${c}"><span class="char">${revealed ? glyph(r.id) + esc(r.name) : ""}</span></div></div>
      </div>
    </button>
    <div class="hint">${revealed ? `Hides by itself in <span id="hide-in">${Math.max(0, Math.ceil((hideAt - Date.now()) / 1000))}</span>s. Tap the token to hide it now.` : "Shield your screen, then tap to see your character"}</div>
    ${revealed ? `<div class="ability"><div class="team ${c}-text">${TYPE_LABEL[r.type]}, ${t === "good" ? "on the good team" : "on the evil team"}</div><p>${esc(r.ability)}</p>${line ? `<p class="line-state">${esc(line)}</p>` : ""}</div>` : ""}
  </div>`;
}

function chooseCard(card) {
  return `<div class="card prompt"><span class="when">The Storyteller asks</span><p>${esc(card.text)}</p>
    <div class="picks">${card.options.map(o => `<button class="pick ${o.dead ? "dead" : ""}" aria-pressed="${picks.includes(o.pid)}" onclick="togglePick('${o.pid}', ${card.count})">${esc(o.name)}</button>`).join("")}</div>
    ${card.variable ? `<p class="empty">Pick nobody, one, or three.</p>` : ""}
    <button class="btn" ${picks.length === card.count || (card.variable && picks.length <= card.count) ? "" : "disabled"} onclick="confirmPick()">Confirm choice</button></div>`;
}

function tapCard(card) {
  const key = card.target.join();
  if (tapKey !== key) { tapKey = key; tapSeq = []; }
  const name = id => esc(chars[id]?.name ?? id);
  return `<div class="card prompt"><span class="when">The Storyteller asks</span><p>${esc(card.text)}</p>
    <ol class="seq">${card.target.map((id, i) => `<li class="${i < tapSeq.length ? "got" : ""}" aria-label="${i + 1}: ${name(id)}">${glyph(id)}</li>`).join("")}</ol>
    <div class="grid6">${card.options.map(id => {
      const at = tapSeq.indexOf(id);
      return `<button class="cell" ${at >= 0 ? "disabled" : ""} onclick="tapIcon('${id}')" aria-label="${name(id)}">${glyph(id)}<span>${at >= 0 ? at + 1 : name(id)}</span></button>`;
    }).join("")}</div>
    ${tapError ? `<p class="miss">${esc(tapError)}</p>` : ""}</div>`;
}

function thread(me) {
  const items = threadModel(me, state).map(x => {
    if (x.kind === "header") return `<p class="when">${esc(x.text)}</p>`;
    if (x.kind === "st") return `<div class="bub st">${SEAL}${esc(x.text)}</div>`;
    if (x.kind === "me") return `<div class="bub me">${esc(x.text)}</div>${x.state ? `<p class="state">${x.state}</p>` : ""}`;
    if (x.card.type === "choose") return chooseCard(x.card);
    if (x.card.type === "tap") return tapCard(x.card);
    return `<div class="card done"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"></path></svg><span>${esc(x.card.text)}</span></div>`;
  }).join("");
  const body = items || `<p class="empty">Nothing from the Storyteller yet. What you learn at night arrives here.</p>`;
  return `<section class="messages">
    <div class="thread-head">${SEAL}<div><div class="who">Storyteller</div><div class="empty">Only you and the Storyteller see this.${revealed ? ` Hides in <span id="hide-in">${Math.max(0, Math.ceil((hideAt - Date.now()) / 1000))}</span> s.` : ""}</div></div></div>
    ${revealed ? `<div class="thread">${body}</div>` : `<button class="masked" onclick="flip()"><div class="thread blur" aria-hidden="true">${body}</div><span class="tap">Tap to read</span></button>`}
    <form class="composer" onsubmit="sendMessage(); return false">
      <input id="msg" placeholder="Message the Storyteller" maxlength="500" autocomplete="off" value="${esc(draft)}" oninput="setDraft(this.value)">
      <button type="submit" class="send" aria-label="Send" ${draft.trim() ? "" : "disabled"}>↑</button></form>
    ${sentNote ? `<p class="empty">Sent.</p>` : ""}</section>`;
}

function dialClock(s) {
  const c = s.clock;
  return c && (c.state !== "done" || (s.phase === "day" && s.nominations.length)) ? c : null;
}

function square(s, me) {
  const sq = squareModel(s, me);
  const c = s.clock && s.clock.state !== "done" ? s.clock : null;
  const n = sq.seats.length;
  const seats = sq.seats.map((x, i) => {
    const a = (i / n) * 2 * Math.PI - Math.PI / 2;
    const left = 50 + 38 * Math.cos(a), top = 50 + 40 * Math.sin(a);
    const cls = [x.me ? "me" : "", x.alive ? "" : "dead", x.hand || x.mark === "up" ? "hand" : "", x.mark === "yes" ? "yes" : "", x.mark === "no" ? "no" : "", x.mark === "nominee" ? "nom" : ""].join(" ");
    const text = x.mark === "yes" ? "✓" : x.mark === "no" ? "–" : (x.hand || x.mark === "up") ? "✋" : x.no;
    const sub = !x.alive ? `<small>${x.ghost ? "has a vote" : "no vote left"}</small>` : "";
    return `<div class="seat ${x.alive ? "" : "dead"} ${x.me ? "me" : ""}" style="left:${left}%;top:${top}%"><div class="dot ${cls}">${text}</div><div class="who">${esc(x.name)}${sub}</div></div>`;
  }).join("");
  let centre, head = "";
  if (c) {
    const now = serverNow(s, receivedAt);
    const idx = handIndex(c, now);
    const yes = Object.values(c.locked).filter(Boolean).length;
    head = `<h2 class="vote-title">${esc(seatName(c.nominator))} nominates ${esc(seatName(c.nominee))}</h2><p class="empty centred">${yes} so far · ${s.threshold} to execute</p>`;
    centre = `<div class="dial" aria-hidden="true"><div class="hand" id="phand" style="transform: rotate(${handAngle(s.seats.map(x => x.pid), c, now)}deg)"></div><div class="boss"></div><div class="count" id="pcount">${idx < 0 ? Math.min(3, Math.ceil(c.go_at - now)) : ""}</div></div>`;
  } else {
    centre = `<div class="center"><b>${esc(sq.centre.big)}</b><span>${esc(sq.centre.small)}</span></div>`;
  }
  const b = handButton(s, me, serverNow(s, receivedAt), localStorage.getItem("tb_master"));
  const button = s.phase === "day" ? `<div class="handbox">
      <button class="big ${b.pressed ? "up" : ""}" aria-pressed="${b.pressed}" ${b.disabled ? "disabled" : ""} onclick="toggleHand()">${esc(b.label)}</button>
      <p class="empty centred" id="handhint">${esc(handError || b.hint)}${c ? "" : " On a laptop, Space does the same."}</p></div>` : "";
  const today = sq.today.length ? `<section><h2>${s.phase === "day" ? "Today" : "Last heard"}</h2><ul class="crier">${sq.today.map(a => `<li>${esc(a)}</li>`).join("")}</ul></section>` : "";
  const noms = sq.nominations.length ? `<ul class="crier">${sq.nominations.map(x => `<li>${esc(x.text)} <span class="empty">${esc(x.note)}</span></li>`).join("")}</ul>` : "";
  return `<section class="square">${head || `<h2>Town square</h2>`}<div class="ring">${seats}${centre}</div>${button}${noms}</section>${today}`;
}

function almanac() {
  const groups = ["townsfolk", "outsider", "minion", "demon"].map(t => `<h3>${TYPE_LABEL[t]}</h3><dl>${
    Object.entries(chars).filter(([, c]) => c.type === t).map(([id, c]) => `<dt class="${tone(c.type)}-text">${glyph(id)}${esc(c.name)}</dt><dd>${esc(c.summary)}</dd>`).join("")}</dl>`).join("");
  return `<section class="almanac"><h2>Every character in this script</h2>${groups}</section>`;
}

function setDaylight(phase) {
  const night = phase === "night";
  document.body.classList.toggle("day", !night);
  document.querySelector('meta[name="theme-color"]').content = night ? "#221A2A" : "#1B2B27";
}

function fitNames(root) {
  root.querySelectorAll(".token .char").forEach(c => {
    c.style.fontSize = "";
    const maxH = c.parentElement.clientHeight * 0.7;
    let fs = parseFloat(getComputedStyle(c).fontSize);
    while ((c.scrollWidth > c.clientWidth || c.offsetHeight > maxH) && fs > 6) c.style.fontSize = `${fs -= 0.5}px`;
  });
}

function render() {
  setDaylight(state?.phase);
  document.body.dataset.layout = layout(width);
  if (!token || !state || !state.me) { $app.innerHTML = joinScreen(); return; }
  const s = state, me = s.me;
  // only table-wide buzzes vibrate, so a phone never singles out its owner
  if (lastBuzz !== null && Number(lastBuzz) !== s.buzz && s.buzz > 0) sound.buzz();
  lastBuzz = String(s.buzz);
  localStorage.setItem("tb_buzz", lastBuzz);
  // a vote just started: the phone switches to the square by itself, once per clock
  const live = s.clock && s.clock.state !== "done" ? s.clock : null;
  const clockKey = live ? `${live.nomination}:${live.go_at}` : null;
  if (live && clockKey !== lastClockKey && !isLaptop()) view = "square";
  lastClockKey = clockKey;

  const nd = nudge(s, me, revealed, seen);
  let html = `<div class="top"><h1>${esc(s.script.name)}</h1><div class="when">${esc(me.name)}${me.alive ? "" : ", dead"}<br>${when(s)}</div></div>`;
  if (s.winner) html += `<div class="verdict paper"><h2 class="${s.winner}-text">${s.winner === "good" ? "Good" : "Evil"} wins</h2><p>${esc(s.win_reason)}</p></div>`;
  if (nd.show) html += `<button class="call" onclick="flip()"><b>${esc(nd.title)}</b>${esc(nd.text)}</button>`;
  if (error) html += `<p class="err">${esc(error)}</p>`;

  if (isLaptop()) {
    html += `<div class="cols"><div class="col"><section class="card">${character(me)}</section>${square(s, me)}</div><div class="col right">${thread(me)}</div></div>`;
    if (view === "almanac") html += `<div class="panel"><button class="btn quiet small" onclick="show('character')">Close</button>${almanac()}</div>`;
    else html += `<p class="empty centred"><a href="#" onclick="show('almanac'); return false">Almanac</a></p>`;
  } else {
    if (view === "character") html += character(me);
    else if (view === "messages") html += thread(me);
    else if (view === "square") html += square(s, me);
    else html += almanac();
    html += `<nav class="tabs">${tabs(s, me, view, seen).map(t => `<button onclick="show('${t.id}')" ${t.current ? 'aria-current="page"' : ""}>${t.label}${t.fresh ? `<span class="fresh" aria-label="new"></span>` : ""}</button>`).join("")}</nav>`;
  }
  $app.innerHTML = html;
  fitNames($app);
}

// between polls: move the hand and the countdown on the server's clock; buzz and chime at go, a tick per seat
function tickDial() {
  const c = state?.clock && state.clock.state !== "done" ? state.clock : null;
  const hand = document.getElementById("phand");
  if (!c || !hand) { lastHandIdx = null; return; }
  const now = serverNow(state, receivedAt);
  hand.style.transform = `rotate(${handAngle(state.seats.map(x => x.pid), c, now)}deg)`;
  const idx = c.state === "paused" ? lastHandIdx : handIndex(c, now);
  const count = document.getElementById("pcount");
  if (count) count.textContent = idx < 0 ? String(Math.min(3, Math.ceil(c.go_at - now))) : "";
  const hint = document.getElementById("handhint");
  if (hint && !handError) hint.textContent = handButton(state, state.me, now, localStorage.getItem("tb_master")).hint;
  if (lastHandIdx !== null && idx !== null && idx > lastHandIdx) {
    if (lastHandIdx < 0 && idx >= 0) { sound.buzz(); sound.chime(); }
    else if (idx <= state.seats.length) sound.tick();
  }
  lastHandIdx = idx;
}

function setDraft(v) {
  draft = v; sentNote = false;
  const send = document.querySelector(".composer .send");
  if (send) send.disabled = !v.trim();
  armHide();
}

Object.assign(window, {join, flip, show, sendMessage, togglePick, confirmPick, tapIcon, toggleHand, setDraft, sound});
document.addEventListener("pointerdown", () => sound.unlock(), {once: true});
document.addEventListener("keydown", e => {
  if (e.key !== " " || ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(document.activeElement?.tagName)) return;
  const live = state?.clock && state.clock.state !== "done";
  if (live && (isLaptop() || view === "square")) { e.preventDefault(); sound.unlock(); toggleHand(); }
});
addEventListener("resize", () => { const w = innerWidth; if (layout(w) !== layout(width)) { width = w; render(); } else width = w; });

api("/api/characters").then(c => { chars = c; render(); });
poll();
setInterval(poll, 1500);
setInterval(tickHide, 1000);
setInterval(tickDial, 100);
