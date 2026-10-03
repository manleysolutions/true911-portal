// Node built-in test runner (`npm test`).
// Overview semantics: SERVICE HEALTH is separate from CUSTOMER TASKS; the E911
// tile accounts for every location without a false "Verified"; the Service
// inventory tile shows location readiness (never totals, never "certified");
// monitoring stays its own truth dimension; the map discloses missing points.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  statusStatement, opTiles, e911Reconciliation, MAP_LEGEND_ITEMS, e911Display, missingPointsText,
} from "./commandCenter.js";

const here = dirname(fileURLToPath(import.meta.url));
const src = (f) => readFileSync(join(here, f), "utf8");
const code = (f) => src(f).split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");

// the RH shape: 45 locations, no known service issue, 33 confirmations waiting
const SUMMARY = { locations_total: 45,
  operational_states: { monitored: 29, being_reconciled: 16, not_yet_confirmed: 0, attention_required: 0 } };
const STATES = { customer_confirmation_required: 33, failed: 0, not_verified: 10, customer_submitted: 1,
  verification_pending: 0, requires_review: 0, verified: 1 };
const AC = { counts: { locations: 45, e911_confirmation_required: 33, e911_not_ready: 10,
  e911_states: STATES, needs_attention: 0 } };
const tile = (key, summary = SUMMARY, ac = AC) => opTiles(summary, ac, []).find((t) => t.key === key);

test("zero service issues and outstanding customer actions coexist without contradiction", () => {
  const st = statusStatement(SUMMARY, AC, []);
  assert.equal(st.title, "No known service issues");
  const issues = tile("attention");
  assert.equal(issues.title, "Service issues");
  assert.equal(issues.value, 0);
  assert.equal(issues.detail, "No known service issues");
  // the 33 customer tasks are the E911 tile's (and the Action Center's), never service issues
  assert.equal(tile("e911").value, 33);
  assert.doesNotMatch(JSON.stringify(issues), /33|confirm/i);
});

test("a real service issue is still prominent and worded as a service issue", () => {
  const s = { ...SUMMARY, operational_states: { ...SUMMARY.operational_states, attention_required: 2 } };
  assert.equal(statusStatement(s, AC, []).title, "2 locations have service issues");
  assert.equal(tile("attention", s).value, 2);
});

test("E911 tile accounts for EVERY location from the authoritative states, never 'Verified'", () => {
  const r = e911Reconciliation(AC.counts);
  assert.equal(r.accounted, 45);
  assert.equal(r.accounted, r.total);
  const t = tile("e911");
  assert.match(t.detail, /10 being prepared by True911/);
  assert.match(t.detail, /1 submitted · awaiting verification/);
  assert.match(t.detail, /1 record on file/);
  assert.match(t.detail, /Verified status appears only after official E911 verification$/);
  // the official-record bucket is "record on file", never "verified"
  for (const p of r.others) assert.doesNotMatch(p.text, /\bverified\b/i, p.text);
  assert.notEqual(e911Display("verified").label, "Verified");
});

test("E911 reconciliation falls back to the previous wording for older payloads", () => {
  const old = { locations: 45, e911_confirmation_required: 33, e911_not_ready: 10 };
  const r = e911Reconciliation(old);
  assert.deepEqual(r.others.map((p) => p.text), ["10 being prepared by True911"]);
  assert.equal(r.accounted, 43);                    // nothing invented for the other two
});

test("Service inventory: flag-off placeholder and flag-on readiness, never totals or 'certified'", () => {
  const off = tile("services");
  assert.equal(off.title, "Service inventory");
  assert.equal(off.value, "Being finalized by True911");
  assert.equal(off.detail, "Service and connection totals appear once your inventory is confirmed.");
  const on = tile("services", { ...SUMMARY, service_inventory: { locations_total: 45, locations_ready: 1,
    locations_partially_ready: 1, locations_being_finalized: 36, locations_no_services_on_record: 7,
    ready_services_by_type: [{ service: "Elevator", count: 2 }, { service: "Fire Alarm", count: 1 }],
    records_being_finalized: true } });
  assert.equal(on.value, "2 locations have confirmed inventory");
  assert.equal(on.detail, "1 ready · 1 partially ready · 36 being finalized · 7 no services on record");
  assert.doesNotMatch(JSON.stringify([off, on]), /certif|\b\d+ (?:services|connections)\b/i);
});

test("no customer Command Center surface says 'certified'", () => {
  for (const f of ["commandCenter.js", "serviceInventory.js", "ActionCenter.jsx", "CustomerAssuranceView.jsx",
    "command/CommandMap.jsx", "LocationCommandCenter.jsx"]) {
    assert.doesNotMatch(code(f), /certif/i, f);
  }
});

test("monitoring counts are passed through from the monitoring evidence model only", () => {
  const loc = tile("locations");
  assert.equal(loc.detail, "29 monitored · 16 being confirmed by True911");
  // canonical inventory or E911 tasks never move the monitored figure
  const withInv = { ...SUMMARY, service_inventory: { locations_total: 45, locations_ready: 45 } };
  assert.equal(statusStatement(withInv, AC, []).monitored, 29);
  assert.equal(tile("locations", withInv, { counts: { ...AC.counts, e911_confirmation_required: 0 } }).detail,
    "29 monitored · 16 being confirmed by True911");
});

test("map legend: 'Service issue' for operational problems; E911 tasks are never a service issue", () => {
  assert.deepEqual(MAP_LEGEND_ITEMS.map((i) => i.label),
    ["Monitored", "Service issue", "Being confirmed by True911", "Your action needed"]);
  for (const s of ["customer_confirmation_required", "not_verified", "customer_submitted", "failed", "verified"]) {
    assert.notEqual(e911Display(s).label, "Service issue", s);
  }
});

test("missing map points are disclosed in customer words and nothing is placed", () => {
  assert.equal(missingPointsText(16), "16 locations are being prepared for map display.");
  const MAP = src("command/CommandMap.jsx");
  assert.match(MAP, /missingPointsText\(hidden\)/);
  assert.doesNotMatch(MAP, /geocod|nominatim/i);
});

test("Overview keeps the map primary, the action rail compact, and no nested scroll", () => {
  const VIEW = src("CustomerAssuranceView.jsx");
  assert.match(VIEW, /mode="summary"/);
  assert.match(VIEW, /lg:col-span-8[\s\S]*CommandMap/);           // map takes the wide column
  assert.doesNotMatch(VIEW, /max-h-\[\d+px\] overflow-y-auto/);
  const AC_SRC = src("ActionCenter.jsx");
  assert.match(AC_SRC, /useReducedMotion/);                       // reduced motion still honoured
});
