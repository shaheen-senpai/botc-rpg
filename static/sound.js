// Tones and vibration for the vote clock: a chime at "go", a tick per seat, a buzz for table-wide moments.
// WebAudio needs a user gesture first: call sound.unlock() from any click/tap handler.

let ctx = null;

function tone(freq, ms, at = 0, gain = 0.15) {
  if (!ctx || sound.muted()) return;
  const osc = ctx.createOscillator();
  const vol = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  vol.gain.value = gain;
  osc.connect(vol).connect(ctx.destination);
  const t = ctx.currentTime + at / 1000;
  osc.start(t);
  vol.gain.setValueAtTime(gain, t);
  vol.gain.exponentialRampToValueAtTime(0.001, t + ms / 1000);
  osc.stop(t + ms / 1000 + 0.02);
}

export const sound = {
  unlock() {
    if (ctx) { if (ctx.state === "suspended") ctx.resume(); return; }
    const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (AC) ctx = new AC();
  },
  muted() {
    try { return localStorage.getItem("tb_mute") === "1"; } catch { return false; }
  },
  mute(on) {
    try { localStorage.setItem("tb_mute", on ? "1" : "0"); } catch { /* storage blocked */ }
  },
  chime() { tone(880, 120); tone(1320, 160, 130); },
  tick() { tone(1760, 30, 0, 0.1); },
  buzz() { if (!sound.muted()) globalThis.navigator?.vibrate?.(200); },
};
