// Node built-in test runner (`npm test`).
// Wizard retry boundary: a retry reuses the draft an earlier attempt created,
// and "already submitted" is confirmed from the server, never assumed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createAndSubmit, draftSignature } from "./registrationSubmit.js";

function fakeApi({ submitFails = [], status = "draft" } = {}) {
  const calls = { create: 0, submit: 0, get: 0 };
  let n = 0;
  return {
    calls,
    async create() { calls.create += 1; n += 1; return { registration: { registration_id: `REG-${n}` }, resume_token: `tok-${n}` }; },
    async submit() {
      calls.submit += 1;
      const f = submitFails.shift();
      if (f) throw Object.assign(new Error(`HTTP ${f}`), { status: f });
      status = "submitted";
    },
    async get() { calls.get += 1; return { status }; },
  };
}

test("a retry after a failed submit reuses the created draft (no duplicate registration)", async () => {
  const api = fakeApi({ submitFails: [503] });
  const prior = { current: null };
  const saved = [];
  await assert.rejects(createAndSubmit(api, { a: 1 }, prior, (ids) => saved.push(ids)));
  const r = await createAndSubmit(api, { a: 1 }, prior, (ids) => saved.push(ids));
  assert.equal(api.calls.create, 1);
  assert.equal(api.calls.submit, 2);
  assert.equal(r.registration_id, "REG-1");
  assert.equal(r.reusedDraft, true);
  assert.deepEqual(saved, [{ registration_id: "REG-1", resume_token: "tok-1" }]);   // resume link kept
});

test("409 is treated as submitted only when the server confirms it", async () => {
  const confirmed = fakeApi({ submitFails: [409], status: "submitted" });
  const r = await createAndSubmit(confirmed, { a: 1 }, { current: null });
  assert.equal(r.registration_id, "REG-1");
  assert.equal(confirmed.calls.get, 1);

  const stillDraft = fakeApi({ submitFails: [409], status: "draft" });
  await assert.rejects(createAndSubmit(stillDraft, { a: 1 }, { current: null }), /HTTP 409/);
});

test("non-409 submit failures are never reported as success", async () => {
  for (const code of [500, 503, 429, 403]) {
    const api = fakeApi({ submitFails: [code] });
    await assert.rejects(createAndSubmit(api, { a: 1 }, { current: null }), new RegExp(`HTTP ${code}`));
  }
});

test("changed answers after a failure start a fresh registration; attribution alone does not", async () => {
  const api = fakeApi({ submitFails: [503, 503] });
  const prior = { current: null };
  await assert.rejects(createAndSubmit(api, { a: 1, attribution: { utm_source: "x" } }, prior));
  await assert.rejects(createAndSubmit(api, { a: 1, attribution: { utm_source: "y" } }, prior));
  assert.equal(api.calls.create, 1);
  await createAndSubmit(api, { a: 2 }, prior);
  assert.equal(api.calls.create, 2);
  assert.equal(draftSignature({ a: 1, attribution: 1 }), draftSignature({ a: 1 }));
});

test("a malformed create response fails without submitting", async () => {
  const api = { async create() { return {}; }, async submit() { throw new Error("must not run"); }, async get() {} };
  await assert.rejects(createAndSubmit(api, {}, { current: null }), /Unexpected response/);
});
