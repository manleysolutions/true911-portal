// Node built-in test runner (`npm test`) — no extra dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  visibleActions, canVerifyE911, e911FormProblems, e911Tone, contactProblems,
  contactPayload, changedFields, containsInternalTerm, errorText, actionCenterHeadline,
  PURPOSES, actionCenterSections, TWIN_LABELS, healthFactorLabel, healthFactorWeight,
  readinessProgress, contributionControl, connectionServiceLabel, servicesConnectionsSummary,
  protectionBanner, operationalView, locationOperational, statusWord, portfolioHero,
  actionCenterTiers, locationActions, LOCATION_TABS, groupConnectionsByService,
} from "./selfService.js";

const ADMIN = { enabled: true, can_manage_location: true, can_manage_contacts: true,
  can_submit_requests: true, can_attest_e911: true, can_view_requests: true };
const MANAGER = { ...ADMIN, can_manage_location: false, can_attest_e911: false };
const VIEWER = { enabled: true, can_view_requests: true };

test("admin sees every primary action; support-first is gone", () => {
  const labels = visibleActions(ADMIN).map((a) => a.label);
  assert.deepEqual(labels, ["Manage Location", "Manage Telephone Lines", "Verify E911", "Add Service",
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
    "2 telephone lines across 1 service · 1 not yet linked to a service");
});

test("29/45 is never a green all-protected banner", () => {
  assert.deepEqual(protectionBanner({ locations_total: 45, locations_protected: 29 }),
    { allProtected: false, text: "29 of 45 locations protected." });
  assert.equal(protectionBanner({ locations_total: 45, locations_protected: 45 }).allProtected, true);
  assert.equal(protectionBanner({ locations_total: 0, locations_protected: 0 }).allProtected, false);
  // missing attention/critical keys do not matter any more
  assert.equal(protectionBanner({ locations_total: 45, locations_protected: 29, critical_sites: undefined }).allProtected, false);
});

// ══ Customer trust rule: KNOWN GOOD · KNOWN PROBLEM · UNKNOWN (D-022) ══
// RH production shape (values change over time — these are fixtures, not constants).
const RH_SUMMARY = { locations_total: 45, locations_protected: 29, devices: 73, total_phone_numbers: 28,
  e911_verified_locations: 0, e911_verification_pct: 0, monthly_health_score: { score: 45 },
  operational_states: { monitored: 29, attention_required: 0, being_reconciled: 16, not_yet_confirmed: 0 } };
const RH_AC = {
  counts: { e911_confirmation_required: 35, e911_not_ready: 10, e911_attention: 45,
    missing_contact_information: 44, needs_attention: 0, being_reconciled: 16 },
  e911_confirmation_required: [{ location_ref: "b1", location: "Chicago Gallery #147", action: "verify_e911" }],
  e911_not_ready: [{ location_ref: "b2", location: "Nashville Gallery", action: null }],
  missing_contact_information: [{ location_ref: "b3", location: "Austin Gallery #149" }],
  being_reconciled: [{ location_ref: "b4", location: "Tulsa Gallery" }],
  needs_attention: [], awaiting_your_response: [], service_change_requests: [], open_problems: [],
  recently_updated: [{ by: "Judy", summary: "Updated emergency contact" }],
};

test("unknown monitoring is neither 'unprotected' nor green", () => {
  const reconciling = locationOperational({ protection: { status: "Unknown" }, monitoring_linked: false });
  assert.equal(reconciling.label, "Monitoring record being confirmed");
  assert.equal(reconciling.tone, "neutral");
  const unknown = locationOperational({ protection: { status: "Unknown" } });
  assert.equal(unknown.tone, "neutral");
  for (const v of [reconciling, unknown, statusWord("Unknown"), statusWord(undefined)]) {
    assert.notEqual(v.tone, "good"); assert.notEqual(v.tone, "problem"); assert.notEqual(v.tone, "urgent");
    assert.ok(!/unprotected|fail|offline|protected/i.test(v.label), v.label);
  }
});

test("known failures stay prominent, even without a monitoring link", () => {
  assert.equal(statusWord("Critical").tone, "urgent");
  assert.equal(statusWord("Attention Needed").tone, "problem");
  const crit = locationOperational({ protection: { status: "Critical" }, monitoring_linked: false });
  assert.equal(crit.label, "Service issue"); assert.equal(crit.tone, "urgent");
  assert.equal(operationalView({ state: "attention_required" }).tone, "problem");
  const hero = portfolioHero({ ...RH_SUMMARY, operational_states: { ...RH_SUMMARY.operational_states, attention_required: 2 } }, RH_AC);
  const svc = hero.dimensions.find((d) => d.key === "service_status");
  assert.equal(svc.tone, "problem"); assert.equal(svc.value, "2 locations have service issues");
});

test("RH portfolio hero states facts without implying failure", () => {
  const hero = portfolioHero(RH_SUMMARY, RH_AC);
  assert.deepEqual(hero.facts.map((f) => f.value), [45, 73, "Being finalized by True911"]);
  // the legacy distinct-number count (28) is never presented as connections (D-023)
  assert.ok(!hero.facts.some((f) => /connection/i.test(f.label)));
  assert.ok(!hero.facts.some((f) => f.value === RH_SUMMARY.total_phone_numbers));
  const dim = Object.fromEntries(hero.dimensions.map((d) => [d.key, d]));
  assert.equal(dim.service_status.value, "No known service issues");
  assert.equal(dim.monitoring.value, "29 of 45 locations monitored");
  assert.ok(dim.monitoring.detail.includes("16 monitoring records being confirmed by True911"), dim.monitoring.detail);
  assert.equal(dim.monitoring.tone, "neutral");                 // a coverage gap is not a failure
  assert.ok(dim.e911.detail.includes("35 ready for your confirmation"));
  assert.ok(dim.e911.detail.includes("10 being prepared by True911"));
  assert.equal(dim.setup.value, "Contacts on file for 1 of 45");
  const all = JSON.stringify(hero);
  assert.ok(!/unprotected|failed|critical/i.test(all), all);
  // no blended composite score is presented as service health
  assert.ok(!/\/100|health score|45%/i.test(all), all);
  assert.ok(!hero.dimensions.some((d) => /health/i.test(d.title)));
});

test("customer actions and True911 actions are separated", () => {
  const hero = portfolioHero(RH_SUMMARY, RH_AC);
  const mine = hero.customerActions.map((a) => a.text).join(" | ");
  const ours = hero.operationsActions.map((a) => a.text).join(" | ");
  assert.ok(mine.includes("35 E911 confirmations ready") && mine.includes("44 locations need contacts"), mine);
  assert.ok(ours.includes("10 E911 records being prepared") && ours.includes("Confirming monitoring information for 16 locations"), ours);
  assert.ok(!/prepared|reconcil/i.test(mine), "True911 work is never listed as the customer task");
  assert.ok(!/confirmation|contacts/i.test(ours));
});

test("action center tiers: urgent = known problems only; contacts are low-priority setup", () => {
  const tiers = actionCenterTiers(RH_AC);
  const where = {};
  for (const t of tiers) for (const s of t.sections) where[s.key] = t;
  assert.equal(where.e911_confirmation_required.tier, "action_needed");
  assert.equal(where.e911_confirmation_required.owner, "customer");
  for (const k of ["e911_not_ready", "being_reconciled"]) {
    assert.equal(where[k].tier, "in_progress", k); assert.equal(where[k].owner, "true911", k);
  }
  assert.equal(where.missing_contact_information.tier, "informational");
  assert.equal(where.missing_contact_information.open, false);        // collapsed by default
  assert.ok(!tiers.some((t) => t.tier === "urgent"));                // nothing known broken
  const withIssue = actionCenterTiers({ ...RH_AC, needs_attention: [{ location_ref: "x", location: "Dallas", status: "Critical", label: "Needs attention" }] });
  assert.equal(withIssue[0].tier, "urgent");                         // a real problem leads
  assert.equal(withIssue[0].sections[0].key, "needs_attention");
});

const ADMIN_CAPS = { enabled: true, can_manage_location: true, can_manage_contacts: true,
  can_submit_requests: true, can_attest_e911: true, can_view_requests: true };

test("location header: at most two primary actions, E911 and contacts exactly once", () => {
  const ws = { e911: { state: "customer_confirmation_required" } };
  const { primary, more } = locationActions(ws, ADMIN_CAPS);
  assert.deepEqual(primary.map((a) => a.label), ["Confirm E911", "Manage Location"]);
  const all = [...primary, ...more].map((a) => a.key);
  assert.equal(all.filter((k) => k === "verify_e911").length, 1);
  assert.equal(all.filter((k) => k === "update_contacts").length, 1);
  assert.equal(new Set(all).size, all.length);                        // no duplicates at all
  // nothing to confirm -> no E911 action anywhere
  for (const st of ["not_verified", "customer_submitted", "verification_pending", "verified"]) {
    const a = locationActions({ e911: { state: st } }, ADMIN_CAPS);
    assert.ok(![...a.primary, ...a.more].some((x) => x.key === "verify_e911"), st);
  }
  assert.deepEqual(locationActions(ws, { enabled: true, can_view_requests: true }), { primary: [], more: [] });
  assert.deepEqual(locationActions(ws, { ...ADMIN_CAPS, enabled: false }), { primary: [], more: [] });
});

test("location sections: each subject lives in exactly one place", () => {
  const sections = LOCATION_TABS.flatMap((t) => t.sections);
  assert.equal(new Set(sections).size, sections.length);
  const home = Object.fromEntries(LOCATION_TABS.flatMap((t) => t.sections.map((s) => [s, t.key])));
  assert.equal(home.e911, "compliance");
  assert.equal(home.contacts, "records");
  assert.equal(home.requests, "overview");
  assert.equal(home.activity, "records");
  assert.deepEqual(LOCATION_TABS.map((t) => t.label), ["Overview", "Services & Lines", "Compliance", "Records"]);
});

test("service -> connection -> device grouping keeps unlinked lines out of services", () => {
  const services = [{ service_ref: "svc_1", service: "Elevator", status: { status: "Protected" }, equipment: [{ equipment: "Communicator" }] }];
  const connections = [
    { connection_ref: "c1", service_ref: "svc_1", name: "Elevator", service: "Elevator" },
    { connection_ref: "c2", service_ref: null, name: "Additional line", service: null },
  ];
  const g = groupConnectionsByService(services, connections);
  assert.equal(g.length, 2);
  assert.equal(g[0].service, "Elevator"); assert.deepEqual(g[0].connections.map((c) => c.connection_ref), ["c1"]);
  assert.equal(g[0].equipment.length, 1);
  assert.equal(g[1].service, null); assert.deepEqual(g[1].connections.map((c) => c.connection_ref), ["c2"]);
});
