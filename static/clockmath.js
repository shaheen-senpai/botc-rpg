// Vote-clock maths, shared by the grimoire and the player page. Pure functions over the server's
// clock view: {state, go_at, seat_seconds, paused_at, paused_total, hands: [pid], locked: {pid: bool}, nominee}.
// All times are server seconds (see serverNow); angles are CSS degrees, 0 = pointing right, clockwise.

export function seatAngle(n, i) {
  return -90 + (i * 360) / n;
}

// seats clockwise from the nominee, 1..n; the nominee is n (votes last)
export function offset(seatPids, nomineePid, pid) {
  const n = seatPids.length;
  const k = (seatPids.indexOf(pid) - seatPids.indexOf(nomineePid) + n) % n;
  return k || n;
}

// seconds since "go", not counting pauses; negative during the countdown
export function elapsed(clock, now) {
  const at = clock.paused_at ?? now;
  return at - clock.go_at - clock.paused_total;
}

export function handIndex(clock, now) {
  return Math.floor(elapsed(clock, now) / clock.seat_seconds);
}

// where the hand points: from the nominee, one seat per seat_seconds, never behind a seat that has locked
export function handAngle(seatPids, clock, now) {
  const n = seatPids.length;
  const nominee = seatPids.indexOf(clock.nominee);
  const swept = Math.min(Math.max(elapsed(clock, now), 0) / clock.seat_seconds, n);
  const locked = Object.keys(clock.locked || {}).map(pid => offset(seatPids, clock.nominee, pid));
  const floor = locked.length ? Math.max(...locked) : 0;
  return seatAngle(n, nominee) + (Math.max(swept, floor) * 360) / n;
}

// seconds until the hand reaches pid's seat; null once that seat has locked
export function secondsUntil(seatPids, clock, now, pid) {
  if (clock.locked && pid in clock.locked) return null;
  const k = offset(seatPids, clock.nominee, pid);
  return Math.max(0, Math.ceil(k * clock.seat_seconds - elapsed(clock, now)));
}

// the server's clock now, from the server_time a poll carried and how long ago it arrived
export function serverNow(view, receivedAtMs, nowMs = Date.now()) {
  return view.server_time + (nowMs - receivedAtMs) / 1000;
}
