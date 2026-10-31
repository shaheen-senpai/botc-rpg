// Vote-clock maths shared by both pages. Run: node --test "static/*.test.js"
import test from "node:test";
import assert from "node:assert/strict";
import { seatAngle, offset, elapsed, handIndex, handAngle, secondsUntil, serverNow } from "./clockmath.js";

const seats = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"];
const clock = (over = {}) => ({state: "running", go_at: 1000, seat_seconds: 3, paused_at: null, paused_total: 0, hands: [], locked: {}, nominee: "p2", ...over});

test("offset puts the nominee last", () => {
  assert.equal(offset(seats, "p2", "p3"), 1);
  assert.equal(offset(seats, "p2", "p1"), 7);
  assert.equal(offset(seats, "p2", "p2"), 8);
});

test("handIndex is negative during the countdown and counts seats after go", () => {
  assert.equal(handIndex(clock(), 998), -1);
  assert.equal(handIndex(clock(), 1000), 0);
  assert.equal(handIndex(clock(), 1006.5), 2);
  assert.equal(elapsed(clock({paused_at: 1004, paused_total: 2}), 1100), 2);
});

test("handAngle sweeps from the nominee and never exceeds the last locked seat", () => {
  assert.equal(seatAngle(8, 0), -90);
  assert.equal(handAngle(seats, clock(), 998), seatAngle(8, 1));          // countdown: on the nominee
  assert.equal(handAngle(seats, clock(), 1003), seatAngle(8, 1) + 45);     // one seat on
  assert.equal(handAngle(seats, clock({locked: {p3: true, p4: false, p5: true}}), 1001), seatAngle(8, 1) + 135);  // never behind seat p5
  assert.equal(handAngle(seats, clock(), 2000), seatAngle(8, 1) + 360);    // stops after a full turn
});

test("secondsUntil counts down to a seat and is null once locked", () => {
  assert.equal(secondsUntil(seats, clock(), 1000, "p4"), 6);
  assert.equal(secondsUntil(seats, clock(), 1004, "p4"), 2);
  assert.equal(secondsUntil(seats, clock(), 1010, "p4"), 0);
  assert.equal(secondsUntil(seats, clock({locked: {p4: true}}), 1010, "p4"), null);
});

test("serverNow adds the local delta since the poll", () => {
  assert.equal(serverNow({server_time: 5000}, 10_000, 12_500), 5002.5);
});
