// Node built-in test runner (`npm test`) — no extra dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  visibleActions, canVerifyE911, e911FormProblems, e911Tone, contactProblems,
  contactPayload, changedFields, containsInternalTerm, errorText, actionCenterHeadline,
  PURPOSES, actionCenterSections, TWIN_LABELS, healthFactorLabel, healthFactorWeight,
  readinessProgress, contributionControl, connectionServiceLabel, servicesConnectionsSummary,
  protectionBanner,
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
  assert.equal(actionCenterHeadline({ e911_confirmation_required: 0, missing_contact_information: 0, needs_attention: 0 }), "You're all caught up.");
  assert.equal(actionCenterHeadline({ e911_confirmation_required: 3, missing_contact_information: 1, needs_attention: 0 }),
    "3 E911 confirmations needed · 1 location missing contacts");
});

// ── RH go-live semantics pass ────────────────────────────────────────
const RH_COUNTS = { e911_confirmation_required: 35, e911_not_ready: 10, e911_attention: 45,
  e911_verification_required: 45, missing_contact_information: 45, needs_attention: 0 };

test("35 confirmations + 10 not-ready never renders as '45 confirmations'", () => {
  const h = actionCenterHeadline(RH_COUNTS);
  assert.ok(h.includes("35 E911 confirmations needed"), h);
  assert.ok(h.includes("10 E911 records being prepared"), h);
  assert.ok(!/45 E911 confirmation/.test(h), h);
  // the combined attention count is still 45 — it is just not called confirmations
  assert.equal(RH_COUNTS.e911_confirmation_required + RH_COUNTS.e911_not_ready, RH_COUNTS.e911_attention);
});

test("confirmation rows carry Verify E911; not-ready rows carry no action and no 'confirm' wording", () => {
  const data = {
    e911_confirmation_required: [{ location_ref: "bldg_a", location: "Chicago Gallery #147", state: "customer_confirmation_required", action: "verify_e911" }],
    e911_not_ready: [{ location_ref: "bldg_b", location: "Nashville Gallery", state: "not_verified", action: null }],
  };
  const byKey = Object.fromEntries(actionCenterSections(data).map((x) => [x.key, x]));
  assert.deepEqual(byKey.e911_confirmation_required.action, { intent: "verify_e911", label: "Verify E911" });
  assert.equal(byKey.e911_not_ready.action, undefined);
  assert.equal(byKey.e911_not_ready.informational, true);
  assert.ok(!/confirmation/i.test(byKey.e911_not_ready.title));
  assert.ok(!/needs your confirmation|confirm it/i.test(byKey.e911_not_ready.subtitle));
});

test("Verify E911 is never offered on a record with no dispatch address", () => {
  assert.equal(canVerifyE911(ADMIN, { state: "not_verified" }), false);
  assert.notEqual(e911Tone("not_verified"), "action");
});

test("Data Completeness and Operational Readiness are distinct, non-contradictory labels", () => {
  assert.equal(healthFactorLabel({ key: "digital_twin_completeness", label: "Digital Twin Completeness" }), "Data Completeness");
  assert.equal(healthFactorWeight(25), "weight 25%");       // a weight, never a second score
  assert.notEqual(TWIN_LABELS.dataCompleteness, TWIN_LABELS.readinessTitle);
  const progress = readinessProgress(0, 7);
  assert.equal(progress, "0 of 7 readiness items in place");
  for (const t of [TWIN_LABELS.readinessTitle, progress]) assert.ok(!/complet/i.test(t), t);
});

test("coming-soon controls are disabled; self-service replaces the older contact/request paths", () => {
  assert.equal(contributionControl("photo"), "coming_soon");
  assert.equal(contributionControl("document"), "coming_soon");
  for (const t of ["procedure", "inspection", "note"]) assert.equal(contributionControl(t), "available");
  assert.equal(contributionControl("contact", { selfService: true }), "replaced");
  assert.equal(contributionControl("service_request", { selfService: true }), "replaced");
  assert.equal(contributionControl("contact", { selfService: false }), "available");
  assert.equal(contributionControl("billing"), "hidden");
});

test("service -> connection wording is semantically accurate", () => {
  assert.equal(connectionServiceLabel({ service: "Elevator" }), "Elevator");
  assert.equal(connectionServiceLabel({ service: null }), "Not yet linked to a life-safety service");
  assert.equal(servicesConnectionsSummary({ service_count: 1, connection_count: 2, unlinked_connection_count: 1 }),
    "2 connections across 1 service · 1 not yet linked to a service");
});

test("29/45 is never a green all-protected banner", () => {
  assert.deepEqual(protectionBanner({ locations_total: 45, locations_protected: 29 }),
    { allProtected: false, text: "29 of 45 locations protected." });
  assert.equal(protectionBanner({ locations_total: 45, locations_protected: 45 }).allProtected, true);
  assert.equal(protectionBanner({ locations_total: 0, locations_protected: 0 }).allProtected, false);
  // missing attention/critical keys do not matter any more
  assert.equal(protectionBanner({ locations_total: 45, locations_protected: 29, critical_sites: undefined }).allProtected, false);
});
