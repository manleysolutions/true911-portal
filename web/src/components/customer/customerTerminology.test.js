// Node built-in test runner (`npm test`) — no extra dependencies.
// Customer-facing terminology & ownership (DECISIONS D-028).  Presentation only:
// what the customer READS — never what is monitored, verified or permitted.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CUSTOMER_NOUNS, customerLocationName, containsInternalTerm, operationalView, locationOperational,
  actionCenterSections, actionCenterTiers, activityText, locationTrue911Work, portfolioHero, TIER_META,
  visibleActions, locationActions,
} from "./selfService.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CUSTOMER_JSX = ["CustomerAssuranceView.jsx", "ActionCenter.jsx", "LocationCommandCenter.jsx", "LocationOperations.jsx",
  "command/CommandMap.jsx", "command/CommandParts.jsx", "command/CustomerShell.jsx"];
// Customer-visible source text: comments removed (identifiers such as
// `being_reconciled` / `store_number` are API keys, not UI language).
const visible = (f) => readFileSync(join(HERE, f), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");

const ADMIN = { enabled: true, can_manage_location: true, can_manage_contacts: true,
  can_submit_requests: true, can_attest_e911: true, can_view_requests: true };
const MANAGER = { ...ADMIN, can_manage_location: false, can_attest_e911: false };
const VIEWER = { enabled: true, can_view_requests: true };

const AC = {
  counts: {},
  being_reconciled: [{ location_ref: "bldg:168", location: "Dallas Gallery #168", label: "x", reason: "y" }],
  e911_not_ready: [{ location_ref: "bldg:1", location: "RESEARCH REQUIRED Gallery #653" }],
  service_change_requests: [
    { location_ref: "bldg:2", location: "Edmonton Gallery #505", request_label: "Change service type", status: "submitted", status_label: "Submitted", request_ref: "CSR-1" },
    { location_ref: "bldg:2", location: "Edmonton Gallery #505", request_label: "Move service", status: "waiting_customer", status_label: "Waiting on you", request_ref: "CSR-2" },
  ],
  awaiting_your_response: [
    { location_ref: "bldg:2", location: "Edmonton Gallery #505", request_label: "Move service", status: "waiting_customer", status_label: "Waiting on you", request_ref: "CSR-2" },
  ],
  open_problems: [],
  missing_contact_information: [{ location_ref: "bldg:2", location: "Edmonton Gallery #505" }],
  recently_updated: [
    { by: "RH Test", summary: "Change service type requested", event_type: "request_submitted", request_ref: "CSR-1" },
    { by: "RH Test", summary: "Updated connection name", event_type: "field_updated" },
    { by: "RH Test", summary: "Updated facility contact", event_type: "field_updated" },
    { by: "Operations team", summary: "Move service: waiting on you", event_type: "request_status_changed" },
  ],
};

// ── 1. Universal nouns: no "store" in generic UI ─────────────────────
test("generic customer UI does not use store number as the universal label", () => {
  for (const f of CUSTOMER_JSX) {
    const src = visible(f);
    assert.doesNotMatch(src, /store number|store-number|Store #|Correct store/i, f);
    assert.doesNotMatch(src, /Official record/i, f);
  }
  const ops = visible("LocationOperations.jsx");
  assert.match(ops, /Correct \$\{CUSTOMER_NOUNS\.locationId\}/);
  assert.match(ops, /hint=\{CUSTOMER_NOUNS\.locationIdHint\}/);
  assert.match(ops, /CUSTOMER_NOUNS\.trueRecord/);
  assert.match(visible("LocationCommandCenter.jsx"), /\{CUSTOMER_NOUNS\.locationId\}<\/dt>/);
  assert.equal(CUSTOMER_NOUNS.location, "Location");
  assert.equal(CUSTOMER_NOUNS.locationId, "Location ID");
  assert.equal(CUSTOMER_NOUNS.trueRecord, "True911 record");
  for (const v of [CUSTOMER_NOUNS.location, CUSTOMER_NOUNS.locationId, CUSTOMER_NOUNS.facility]) {
    assert.doesNotMatch(v, /store|gallery|school|campus|installation/i);
  }
  // the hint explains the concept for any industry, without "official"
  assert.match(CUSTOMER_NOUNS.locationIdHint, /site/i);
  assert.match(CUSTOMER_NOUNS.locationIdHint, /school/i);
  assert.match(CUSTOMER_NOUNS.locationIdHint, /building/i);
});

test("actual customer building names containing Gallery are unchanged", () => {
  for (const n of ["Edmonton Gallery #505", "Dallas Gallery #168", "Linden House Gallery", "Review Hall Gallery"]) {
    assert.equal(customerLocationName(n), n);
  }
});

// ── 6. Internal flags never become a customer name ───────────────────
test("internal RESEARCH REQUIRED is not rendered to the customer, and nothing is invented", () => {
  assert.equal(customerLocationName("RESEARCH REQUIRED Gallery #653"), "Gallery #653");
  assert.equal(customerLocationName("research required - Gallery #653"), "Gallery #653");
  assert.equal(customerLocationName("[Needs review] Boston Gallery"), "Boston Gallery");
  assert.equal(customerLocationName("RESEARCH REQUIRED"), "Location");          // generic, not invented
  assert.equal(customerLocationName(null), null);
  const rows = actionCenterSections(AC).flatMap((s) => s.items.map(s.row));
  assert.ok(rows.includes("Gallery #653"), rows);
  assert.ok(!rows.some((r) => /research/i.test(r)), rows);
  // every customer-name render path goes through the guard
  assert.match(visible("CustomerAssuranceView.jsx"), /location: customerLocationName\(/);
  assert.match(visible("LocationCommandCenter.jsx"), /const title = customerLocationName\(/);
  assert.match(visible("LocationOperations.jsx"), /customerLocationName\(ws\.location\.canonical_name\)/);
});

// ── 2/3. Monitoring confirmation: True911's work, no claimed status ──
test("monitoring-confirmation state claims neither monitored nor failed", () => {
  const op = locationOperational({ protection: { status: "Protected" }, monitoring_linked: false });
  assert.equal(op.state, "being_reconciled");
  assert.equal(op.label, "Monitoring record being confirmed");
  assert.equal(op.tone, "neutral");
  assert.doesNotMatch(op.label, /^monitored$|working|fail|offline|down|protected/i);
  assert.doesNotMatch(op.summary, /fail|offline|down|unprotected|is monitored|working normally/i);
  // the API's older wording can never bring "reconciled" back to the screen
  const apiOld = operationalView({ state: "being_reconciled", summary: "True911 is connecting this location's monitoring record." });
  assert.doesNotMatch(`${apiOld.label} ${apiOld.summary}`, /reconcil|connecting/i);
});

test("monitoring-confirmation copy clearly assigns the work to True911", () => {
  for (const st of ["being_reconciled", "not_yet_confirmed"]) {
    const op = operationalView({ state: st });
    assert.equal(op.owner, "true911", st);
    assert.match(op.summary, /^True911 is confirming/, st);
    assert.match(op.summary, /No action is needed from you\./, st);
  }
  const s = actionCenterSections(AC).find((x) => x.key === "being_reconciled");
  assert.equal(s.title, "Monitoring records being confirmed");
  assert.match(s.subtitle, /True911 is confirming/);
  assert.match(s.subtitle, /No action is needed from you/);
});

test("no customer action is implied for True911-owned work", () => {
  const tiers = actionCenterTiers(AC);
  const inProgress = tiers.find((t) => t.tier === "in_progress");
  assert.equal(inProgress.owner, "true911");
  assert.match(TIER_META.in_progress.subtitle, /True911 is handling these — nothing for you to do/);
  for (const s of inProgress.sections) {
    assert.ok(s.informational && !s.action, s.key);                 // no button, no CTA
  }
  // a request waiting on the customer is theirs — listed once, not as True911 work
  const scr = inProgress.sections.find((s) => s.key === "service_change_requests");
  assert.deepEqual(scr.items.map((i) => i.request_ref), ["CSR-1"]);
  const action = tiers.find((t) => t.tier === "action_needed");
  assert.deepEqual(action.sections.find((s) => s.key === "awaiting_your_response").items.map((i) => i.request_ref), ["CSR-2"]);
  // location page counterpart: True911's list never contains a customer task
  const ws = { e911: { state: "not_verified" }, requests: [
    { open: true, status: "submitted" }, { open: true, status: "waiting_customer" }, { open: false, status: "completed" }] };
  const work = locationTrue911Work(ws, operationalView({ state: "being_reconciled" }));
  assert.deepEqual(work, ["confirming monitoring information", "preparing the E911 record", "processing 1 request"]);
  assert.deepEqual(locationTrue911Work({}, operationalView({ state: "monitored" })), []);
  assert.match(visible("LocationCommandCenter.jsx"), /True911 is working on: \{true911Work\.join\(" · "\)\}\. No action is needed from you\./);
  // the dashboard hero's True911 list carries no customer task words
  const hero = portfolioHero({ locations_total: 45, operational_states: { being_reconciled: 16 } }, { counts: { e911_not_ready: 10 } });
  const ours = hero.operationsActions.map((a) => a.text).join(" | ");
  assert.match(ours, /Confirming monitoring information for 16 locations/);
  assert.doesNotMatch(ours, /your|confirmation|contacts|reconcil/i);
});

// ── 4. Recently updated = history, not a waiting queue ───────────────
test("Recent activity is history in its own tier, not portfolio setup", () => {
  const tiers = actionCenterTiers(AC);
  const activity = tiers.find((t) => t.tier === "activity");
  assert.equal(activity.owner, "none");
  assert.equal(activity.count, 0);                                   // never a to-do count
  assert.deepEqual(activity.sections.map((s) => s.key), ["recently_updated"]);
  assert.match(TIER_META.activity.subtitle, /already done; nothing is waiting/i);
  const setup = tiers.find((t) => t.tier === "informational");
  assert.ok(!setup.sections.some((s) => s.key === "recently_updated"));
  assert.match(TIER_META.informational.subtitle, /Optional/);
  const sec = activity.sections[0];
  assert.equal(sec.title, "Recent activity");
  assert.ok(sec.noOpen && sec.informational && !sec.action);
  assert.match(sec.subtitle, /Open requests and their current status are under In progress/);
  // an older API that still lists history under setup is normalized the same way
  const legacy = actionCenterTiers({ ...AC, tiers: [
    { tier: "in_progress", owner: "true911", lists: ["being_reconciled"] },
    { tier: "informational", owner: "customer", lists: ["missing_contact_information", "recently_updated"] }] });
  assert.deepEqual(legacy.map((t) => t.tier), ["in_progress", "informational", "activity"]);
  assert.ok(!legacy[1].sections.some((s) => s.key === "recently_updated"));
});

test("activity wording is past tense; current request status stays on the request", () => {
  assert.equal(activityText({ event_type: "request_submitted", summary: "Change service type requested" }),
    "Submitted a request: Change service type");
  assert.equal(activityText({ event_type: "request_status_changed", summary: "Move service: waiting on you" }),
    'Request "Move service" was marked waiting on you');
  assert.equal(activityText({ event_type: "field_updated", summary: "Updated connection name" }), "Updated connection name");
  assert.equal(activityText({ event_type: "field_updated", summary: "Updated facility contact" }), "Updated facility contact");
  const rows = actionCenterSections(AC).find((s) => s.key === "recently_updated").items
    .map(actionCenterSections(AC).find((s) => s.key === "recently_updated").row);
  assert.deepEqual(rows.slice(0, 3), ["RH Test · Submitted a request: Change service type",
    "RH Test · Updated connection name", "RH Test · Updated facility contact"]);
  assert.ok(!rows.some((r) => /requested$/.test(r)), rows);
  // the submitted request keeps its real status where requests live
  const scr = actionCenterSections(AC).find((s) => s.key === "service_change_requests");
  assert.equal(scr.row(scr.items[0]), "Edmonton Gallery #505 — Change service type: Submitted");
  const lcc = visible("LocationCommandCenter.jsx");
  assert.match(lcc, /<Pill tone=\{requestTone\(r\.status\)\}>\{r\.status_label\}<\/Pill>/);
  assert.match(lcc, /text: `\$\{a\.by\} · \$\{activityText\(a\)\}`/);
});

// ── 6. Internal-language regression ──────────────────────────────────
test("no internal reconciliation / certification terms in customer copy", () => {
  for (const t of ["Being reconciled", "monitoring relationships being reconciled", "RESEARCH REQUIRED",
    "canonical record", "registry", "pending review", "store number"]) {
    assert.ok(containsInternalTerm(t), t);
  }
  assert.ok(!containsInternalTerm("Edmonton Gallery #505"));
  const copy = [
    ...actionCenterSections(AC).flatMap((s) => [s.title, s.subtitle, ...s.items.map(s.row)]),
    ...Object.values(TIER_META).flatMap((m) => [m.title, m.subtitle]),
    ...["being_reconciled", "not_yet_confirmed", "monitored", "attention_required"]
      .flatMap((st) => { const o = operationalView({ state: st }); return [o.label, o.summary]; }),
    ...(() => { // displayed hero text only (object keys are not UI)
      const h = portfolioHero({ locations_total: 45, operational_states: { being_reconciled: 16, not_yet_confirmed: 2 } }, { counts: {} });
      return [...h.facts.flatMap((f) => [f.label, String(f.value)]), ...h.dimensions.flatMap((d) => [d.title, d.value, d.detail]),
        ...h.customerActions.map((a) => a.text), ...h.operationsActions.map((a) => a.text)];
    })(),
    ...Object.values(CUSTOMER_NOUNS),
  ].filter(Boolean);
  for (const c of copy) assert.ok(!containsInternalTerm(c), c);
  for (const f of CUSTOMER_JSX) assert.doesNotMatch(visible(f), /reconcil|research required/i, f);
  // the map legend keeps its meaning (neutral) with plain wording
  assert.match(visible("command/CommandMap.jsx"), /MAP_LEGEND_ITEMS/);
});

// ── RBAC: wording changes never widen what a role can do ─────────────
test("CUSTOMER_ADMIN keeps every action; MANAGER / VIEWER are not broadened", () => {
  assert.deepEqual(visibleActions(ADMIN).map((a) => a.key), ["manage_location", "manage_connections", "verify_e911",
    "add_service", "service_change", "report_problem", "update_contacts"]);
  const mgr = visibleActions(MANAGER).map((a) => a.key);
  assert.ok(!mgr.includes("manage_location") && !mgr.includes("verify_e911") && !mgr.includes("manage_connections"));
  assert.deepEqual(visibleActions(VIEWER), []);
  const ws = { e911: { state: "customer_confirmation_required" } };
  assert.ok(locationActions(ws, ADMIN).primary.some((a) => a.key === "manage_location"));
  const m = locationActions(ws, MANAGER);
  assert.ok(![...m.primary, ...m.more].some((a) => a.key === "manage_location" || a.key === "verify_e911"));
  const v = locationActions(ws, VIEWER);
  assert.deepEqual([...v.primary, ...v.more], []);
  // the True911 work line is informational: it adds no action for anyone
  assert.deepEqual(locationActions({ ...ws, requests: [{ open: true, status: "submitted" }] }, VIEWER), { primary: [], more: [] });
});
