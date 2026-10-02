// Node built-in test runner (`npm test`).
// D-031: the public client may show "received" ONLY for a durable server receipt.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  EVENTS, SERVER_CONFIRMED, captureAttribution, isReceipt, newIdempotencyKey, rememberCta,
  setSink, submitAcquisition, track, getAttribution,
} from "./acquisition.js";

const fail = (err) => async () => { throw err; };
const httpErr = (status) => Object.assign(new Error(`HTTP ${status}`), { status });

for (const [name, poster] of [
  ["404 (endpoint missing)", fail(httpErr(404))],
  ["500 (server error)", fail(httpErr(500))],
  ["503 (persistence unavailable)", fail(httpErr(503))],
  ["422 (validation)", fail(httpErr(422))],
  ["429 (rate limited)", fail(httpErr(429))],
  ["network error", fail(Object.assign(new Error("Network error — unable to reach"), { networkError: true }))],
  ["timeout / abort", fail(Object.assign(new Error("aborted"), { name: "AbortError" }))],
  ["empty body", async () => ({})],
  ["null body", async () => null],
  ["received without a record", async () => ({ received: true })],
  ["record without received", async () => ({ record_ref: "ACQ-1" })],
  ["truthy-but-not-true received", async () => ({ received: "yes", record_ref: "ACQ-1" })],
]) {
  test(`no success on ${name}`, async () => {
    await assert.rejects(submitAcquisition(poster, "/public/quote-request", {}));
  });
}

test("success only with a durable receipt, and lead_created is emitted from it", async () => {
  const seen = [];
  setSink((n, p) => seen.push([n, p]));
  const r = await submitAcquisition(async () => ({ received: true, record_ref: "ACQ-ABC", status: "inquiry" }), "/x", {});
  assert.equal(r.record_ref, "ACQ-ABC");
  assert.deepEqual(seen, [["lead_created", { record_ref: "ACQ-ABC" }]]);
  setSink(null);
});

test("a failed submission never emits lead_created", async () => {
  const seen = [];
  setSink((n) => seen.push(n));
  await assert.rejects(submitAcquisition(fail(httpErr(500)), "/x", {}));
  assert.deepEqual(seen, []);
  setSink(null);
});

test("error messages are safe and specific to the failure class", async () => {
  await assert.rejects(submitAcquisition(fail(httpErr(429)), "/x", {}), /Too many attempts/);
  await assert.rejects(submitAcquisition(fail(httpErr(422)), "/x", {}), /check the highlighted/);
  await assert.rejects(submitAcquisition(fail(httpErr(500)), "/x", {}), /couldn't confirm/);
});

test("isReceipt is strict", () => {
  assert.equal(isReceipt({ received: true, record_ref: "ACQ-1" }), true);
  assert.equal(isReceipt({ received: true, record_ref: "" }), false);
  assert.equal(isReceipt(undefined), false);
});

test("event vocabulary is fixed; unknown events are dropped; a throwing sink never breaks the UI", () => {
  assert.deepEqual([...EVENTS], ["page_view", "cta_click", "assessment_started", "assessment_step",
    "assessment_submitted", "lead_created", "lead_qualified", "customer_created", "subscriber_activated"]);
  for (const e of SERVER_CONFIRMED) assert.ok(EVENTS.includes(e));
  assert.equal(track("purchase"), false);
  setSink(() => { throw new Error("vendor down"); });
  assert.equal(track("page_view"), true);
  setSink(null);
});

test("idempotency keys satisfy the server pattern and differ per attempt", () => {
  const a = newIdempotencyKey(), b = newIdempotencyKey();
  assert.match(a, /^[A-Za-z0-9-]{16,64}$/);
  assert.notEqual(a, b);
});

function memStore() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

test("attribution is first-touch, path-only, and records the first CTA", () => {
  const st = memStore();
  const a = captureAttribution({ pathname: "/quote", search: "?utm_source=li&utm_campaign=q3&x=1" },
    "https://ref.example/p?secret=1", st);
  assert.deepEqual(a, { landing_path: "/quote", utm_source: "li", utm_campaign: "q3", referrer: "https://ref.example/p" });
  const again = captureAttribution({ pathname: "/other", search: "?utm_source=new" }, "", st);
  assert.equal(again.utm_source, "li");                       // first touch wins
  rememberCta("hero_assessment", st);
  rememberCta("final_quote", st);
  assert.equal(getAttribution(st).initial_cta, "hero_assessment");
});
