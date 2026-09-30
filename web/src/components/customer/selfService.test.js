// Node built-in test runner (`npm test`) — no extra dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  visibleActions, canVerifyE911, e911FormProblems, e911Tone, contactProblems,
  contactPayload, changedFields, containsInternalTerm, errorText, actionCenterHeadline,
  PURPOSES,
} from "./selfService.js";

const ADMIN = { enabled: true, can_manage_location: true, can_manage_contacts: true,
  can_submit_requests: true, can_attest_e911: true, can_view_requests: true };
const MANAGER = { ...ADMIN, can_manage_location: false, can_attest_e911: false };
const VIEWER = { enabled: true, can_view_requests: true };

test("admin sees every primary action; support-first is gone", () => {
  const labels = visibleActions(ADMIN).map((a) => a.label);
  assert.deepEqual(labels, ["Manage Location", "Manage Connections", "Verify E911", "Add Service",
    "Request Service Change", "Report a Problem", "Update Contacts"]);
  assert.ok(!labels.some((l) => /support|live help/i.test(l)));
});

test("manager gets the operational subset; viewer and feature-off get none", () => {
  const labels = visibleActions(MANAGER).map((a) => a.label);
  assert.ok(labels.includes("Update Contacts") && labels.includes("Report a Problem"));
  assert.ok(!labels.includes("Verify E911") && !labels.includes("Manage Location"));
  assert.deepEqual(visibleActions(VIEWER), []);
  assert.deepEqual(visibleActions({ ...ADMIN, enabled: false }), []);
  assert.deepEqual(visibleActions(null), []);
});

test("Verify E911 is offered only when the customer still has something to do", () => {
  assert.equal(canVerifyE911(ADMIN, { state: "customer_confirmation_required" }), true);
  assert.equal(canVerifyE911(ADMIN, { state: "failed" }), true);
  for (const s of ["verified", "customer_submitted", "verification_pending", "requires_review"]) {
    assert.equal(canVerifyE911(ADMIN, { state: s }), false, s);
  }
  assert.equal(canVerifyE911(MANAGER, { state: "customer_confirmation_required" }), false);
});

test("only an official verified record is ever green", () => {
  assert.equal(e911Tone("verified"), "ok");
  for (const s of ["customer_submitted", "verification_pending", "requires_review"]) {
    assert.notEqual(e911Tone(s), "ok");
  }
});

test("E911 wizard requires building + address (or correction) + attestation", () => {
  assert.equal(e911FormProblems({}).length, 3);
  assert.deepEqual(e911FormProblems({ building_confirmed: true, address_confirmed: true, attest: true }), []);
  assert.deepEqual(e911FormProblems({ building_confirmed: true, corrected_address: "1 Main", attest: true }), []);
});

test("contacts must be reachable and well-formed; blank clears", () => {
  assert.deepEqual(contactProblems({ name: "Pat" }), ["Add a phone number or an email address."]);
  assert.deepEqual(contactProblems({ name: "Pat", phone: "312-555-0100" }), []);
  assert.deepEqual(contactProblems({ email: "nope" }), ["Enter a valid email address."]);
  assert.equal(contactPayload({ name: " ", phone: "" }), null);
  assert.deepEqual(contactPayload({ name: " Pat ", phone: "1" }), { name: "Pat", phone: "1" });
});

test("only changed fields are sent", () => {
  assert.deepEqual(changedFields({ display_name: "A", access_notes: null },
    { display_name: "A ", access_notes: "Dock" }, ["display_name", "access_notes"]),
  { access_notes: "Dock" });
});

test("internal / source-system terms are detectable", () => {
  for (const t of ["ICCID 8901", "Napco radio", "PortfolioReviewItem", "source confidence 80"]) {
    assert.ok(containsInternalTerm(t), t);
  }
  assert.ok(!containsInternalTerm("Fire Alarm Line 1 · (561) 555-0100"));
  assert.ok(PURPOSES.every((p) => !containsInternalTerm(p.label)));
});

test("server refusal messages are surfaced in plain language", () => {
  const e = { body: { detail: { code: "system_managed_field", message: "Managed by operations" } } };
  assert.equal(errorText(e), "Managed by operations");
  assert.equal(errorText({ message: "x" }), "x");
});

test("action center headline answers 'what do I need to do?'", () => {
  assert.equal(actionCenterHeadline({ e911_verification_required: 0, missing_contact_information: 0, needs_attention: 0 }), "You're all caught up.");
  assert.equal(actionCenterHeadline({ e911_verification_required: 3, missing_contact_information: 1, needs_attention: 0 }),
    "3 E911 confirmations · 1 location missing contacts");
});
