// Node built-in test runner (`npm test`) — no extra dependencies.
// Life-Safety Command Center: TRUTH-SAFETY regression suite.  The redesign may
// change how things look, never what they claim (D-022, D-023, D-025, D-028).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  STATUS_TOKENS, OP_TOKEN, tokenFor, e911Display, E911_PROVIDER_VERIFICATION_AVAILABLE,
  statusStatement, opTiles, markerView, MAP_LEGEND_ITEMS, ownership, heroChips,
} from "./commandCenter.js";
import { locationOperational, actionCenterSections, actionCenterTiers } from "./selfService.js";
import { mapMarkers } from "./portfolioMap.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (...p) => readFileSync(join(HERE, ...p), "utf8");
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
const VIEW = strip(read("CustomerAssuranceView.jsx"));
const MAP = strip(read("command", "CommandMap.jsx"));
const PARTS = strip(read("command", "CommandParts.jsx"));
const SHELL = strip(read("command", "CustomerShell.jsx"));
const AC = strip(read("ActionCenter.jsx"));
const LCC = strip(read("LocationCommandCenter.jsx"));
const LAYOUT = read("..", "..", "Layout.jsx");
const CSS = read("..", "..", "index.css");

// RH-like portfolio: 45 locations, 29 monitored, 16 without a monitoring link,
// legacy counts present in the payload that must NEVER be surfaced.
const SUMMARY = {
  portfolio_name: "Restoration Hardware", locations_total: 45, devices: 73,
  operational_states: { monitored: 29, attention_required: 0, being_reconciled: 16, not_yet_confirmed: 0 },
  e911_verified_locations: 45,               // legacy validated/confirmed -> "Verified"
  life_safety_services: 120, total_phone_numbers: 28, monthly_health_score: 91, service_availability_pct: 99.9,
};
const AC_DATA = {
  counts: { e911_confirmation_required: 35, e911_not_ready: 10, missing_contact_information: 44 },
  e911_confirmation_required: [{ location_ref: "bldg:2", location: "Edmonton Gallery #505" }],
  e911_not_ready: [{ location_ref: "bldg:3", location: "Gallery #653" }],
  being_reconciled: [{ location_ref: "bldg:168", location: "Dallas Gallery #168" }],
  service_change_requests: [
    { location_ref: "bldg:2", location: "Edmonton Gallery #505", request_label: "Change service type", status: "submitted", status_label: "Submitted" },
    { location_ref: "bldg:2", location: "Edmonton Gallery #505", request_label: "Move service", status: "waiting_customer", status_label: "Waiting on you" }],
  awaiting_your_response: [{ location_ref: "bldg:2", location: "Edmonton Gallery #505", request_label: "Move service", status: "waiting_customer", status_label: "Waiting on you" }],
  open_problems: [], missing_contact_information: [], needs_attention: [], recently_updated: [],
};
const loc = (ref, protection, extra = {}) => ({ location_ref: ref, location: ref, op: locationOperational({ protection: { status: protection }, ...extra }), ...extra });

// ── UNKNOWN is never GOOD and never FAILED ───────────────────────────
test("UNKNOWN is not rendered as GOOD", () => {
  const st = statusStatement(SUMMARY, AC_DATA, []);
  assert.equal(st.title, "No known issues requiring attention");
  assert.match(st.detail, /^True911 is confirming monitoring information at 16 locations/);
  assert.equal(st.tone, "unknown", "16 unconfirmed locations: the statement is not green");
  assert.notEqual(statusStatement({ ...SUMMARY, operational_states: { ...SUMMARY.operational_states, being_reconciled: 0, not_yet_confirmed: 16 } }, AC_DATA).tone, "good");
  const unk = loc("bldg:168", "Protected", { monitoring_linked: false });       // evidence lacks a link
  assert.equal(OP_TOKEN[unk.op.tone], "unknown");
  assert.equal(markerView(unk).token, "unknown");
  assert.equal(markerView(unk).shape, "ring");
  assert.notEqual(tokenFor(unk.op.tone), STATUS_TOKENS.good);
  for (const t of opTiles(SUMMARY, AC_DATA)) assert.notEqual(t.token, "good", t.key);
  // green ONLY when every location is evidence-backed monitored
  const all = { ...SUMMARY, operational_states: { monitored: 45, attention_required: 0, being_reconciled: 0, not_yet_confirmed: 0 } };
  assert.equal(statusStatement(all, AC_DATA).tone, "good");
});

test("UNKNOWN is not rendered as FAILED", () => {
  const unk = loc("bldg:168", "Unknown", { monitoring_linked: false });
  const v = markerView(unk);
  assert.ok(!["attention", "critical"].includes(v.token));
  assert.notEqual(v.shape, "diamond");
  assert.doesNotMatch(`${unk.op.label} ${unk.op.summary}`, /fail|offline|down|unprotected|broken/i);
  const st = statusStatement(SUMMARY, AC_DATA);
  assert.ok(!["attention", "critical"].includes(st.tone));
  assert.doesNotMatch(st.title + st.detail, /fail|offline|down|unprotected/i);
  // nothing UNKNOWN is animated: no looping / pulsing / spinning anywhere in the command UI
  for (const src of [VIEW, MAP, PARTS, SHELL, AC]) {
    assert.doesNotMatch(src, /animate-pulse|animate-spin|animate-ping|repeat:\s*Infinity|repeatType/);
  }
});

test("a known problem stays prominent; urgent is critical", () => {
  const items = [loc("a", "Critical"), loc("b", "Attention Needed")];
  const st = statusStatement({ ...SUMMARY, operational_states: { ...SUMMARY.operational_states, attention_required: 2 } }, AC_DATA, items);
  assert.equal(st.tone, "critical");
  assert.equal(st.title, "1 location needs attention now");
  assert.equal(markerView(items[0]).token, "critical");
  assert.equal(markerView(items[1]).shape, "diamond");
  const tile = opTiles({ ...SUMMARY, operational_states: { ...SUMMARY.operational_states, attention_required: 2 } }, AC_DATA, items).find((t) => t.key === "attention");
  assert.equal(tile.token, "critical"); assert.equal(tile.value, 2);
});

// ── E911: legacy validated / confirmed never becomes authoritative green ──
test("legacy E911 validated does not become authoritative green Verified", () => {
  assert.equal(E911_PROVIDER_VERIFICATION_AVAILABLE, false);
  // the API maps legacy validated -> list "Verified" and workspace "verified"
  for (const s of ["Verified", "verified"]) {
    const d = e911Display(s);
    assert.notEqual(d.token, "good", s);
    assert.notEqual(d.label, "Verified", s);
    assert.equal(d.label, "Record on file");
  }
  for (const s of Object.keys({ customer_confirmation_required: 1, customer_submitted: 1, verification_pending: 1,
    not_verified: 1, failed: 1, "Verification Pending": 1, "Not yet verified": 1, "Setup needed": 1, anything: 1 })) {
    assert.notEqual(e911Display(s).token, "good", s);
  }
});

test("legacy E911 confirmed does not become authoritative green Verified", () => {
  // `confirmed` reaches the customer as the same "Verified" words; the summary's
  // e911_verified_locations (45, legacy-derived) is never shown or coloured.
  const tiles = opTiles(SUMMARY, AC_DATA);
  const e = tiles.find((t) => t.key === "e911");
  assert.notEqual(e.token, "good");
  assert.notEqual(e.value, 45);
  assert.doesNotMatch(JSON.stringify(e), /\bverified\b(?! status appears only after official)/i);
  assert.equal(e.value, 35); assert.match(e.caption, /need your confirmation/);
  assert.match(e.detail, /10 being prepared by True911/);
  assert.equal(opTiles(SUMMARY, { counts: {} }).find((t) => t.key === "e911").value, "Nothing waiting on you");
  // no surface reads the legacy count or colours E911 green
  for (const src of [VIEW, MAP, PARTS, AC, LCC]) assert.doesNotMatch(src, /e911_verified_locations/);
  assert.doesNotMatch(VIEW, /text-emerald/);
  assert.match(LCC, /e911Display\(e911Raw\)/);
  assert.match(LCC, /e911State\.rawLabel !== "Verified"/, "legacy correction gate keeps the API's word");
});

// ── No synthetic service / connection totals ─────────────────────────
test("Life-Safety Services never derives a numeric total from legacy data", () => {
  const items = [loc("a", "Protected", { life_safety_services_count: 3, phone_number_count: 2, device_count: 4 })];
  const s = opTiles(SUMMARY, AC_DATA, items).find((t) => t.key === "services");
  assert.equal(s.numeric, false);
  assert.equal(s.value, "Being finalized by True911");
  assert.doesNotMatch(`${s.value} ${s.detail}`.replace(/True911/g, ""), /\d/, "no number of any kind");
  for (const src of [VIEW, MAP, PARTS]) {
    assert.doesNotMatch(src, /life_safety_services|total_phone_numbers|monthly_health_score|service_availability_pct/);
  }
});

test("connections are not derived from telephone numbers or devices", () => {
  const tiles = opTiles(SUMMARY, AC_DATA);
  assert.deepEqual(tiles.map((t) => t.key), ["locations", "attention", "e911", "services"]);
  const all = JSON.stringify(tiles);
  assert.doesNotMatch(all, /connection(s)?\b[^"]*\d|\b28\b|\b73\b|\b120\b/i);
  assert.doesNotMatch(VIEW + PARTS, /connection_count|phone_number_count|device_count/);
});

// ── Ownership ────────────────────────────────────────────────────────
test("True911-owned work never appears as customer-required action", () => {
  for (const k of ["being_reconciled", "e911_not_ready", "needs_attention", "service_change_requests", "open_problems"]) {
    const o = ownership(k, { status_label: "Submitted" });
    assert.equal(o.owner, "true911", k);
    assert.notEqual(o.token, "attention", k);
  }
  assert.match(ownership("service_change_requests", { status_label: "Under review" }).text, /^Submitted by you · Under review · True911 owns the next step$/);
  const inProgress = actionCenterTiers(AC_DATA).find((t) => t.tier === "in_progress");
  assert.equal(inProgress.title, "In progress");
  for (const s of inProgress.sections) assert.ok(!s.action, s.key);
  // the waiting request is listed once, as the customer's — never as True911 work
  assert.ok(!inProgress.sections.flatMap((s) => s.items).some((i) => i.status === "waiting_customer"));
  const st = statusStatement(SUMMARY, AC_DATA);
  assert.ok(!st.customerActions.some((a) => /prepared|confirming monitoring/i.test(a.text)));
  assert.ok(st.true911Work.every((a) => !/your|confirmation/i.test(a.text)));
});

test("customer-required work remains clearly actionable", () => {
  const sec = actionCenterSections(AC_DATA).find((s) => s.key === "e911_confirmation_required");
  assert.equal(sec.action.label, "Verify E911");
  const o = ownership("e911_confirmation_required");
  assert.equal(o.owner, "customer"); assert.equal(o.token, "attention"); assert.equal(o.text, "Your confirmation needed");
  assert.equal(ownership("awaiting_your_response").text, "Your response needed");
  const action = actionCenterTiers(AC_DATA).find((t) => t.tier === "action_needed");
  assert.ok(action.open && action.count > 0);
  const mv = markerView({ location_ref: "bldg:2", location: "Edmonton Gallery #505", op: { tone: "neutral", label: "Status being confirmed" } }, new Set(["bldg:2"]));
  assert.equal(mv.action, true);
  assert.match(mv.ariaLabel, /Your action needed$/);
  assert.equal(opTiles(SUMMARY, AC_DATA).find((t) => t.key === "e911").token, "attention");
  // button styling only on customer-owned rows; True911-owned rows get a quiet link
  assert.match(AC, /action && \(own\.owner === "customer"\s*\? <span className="[^"]*ring-1 ring-inset ring-slate-300">\{action\.label\}<\/span>\s*: <span className="text-\[11\.5px\] text-slate-500 flex-shrink-0">/);
  // ownership is visibly different on every row: icon + word + colour
  assert.match(AC, /customer: \{ icon: UserCheck, word: "Your action"/);
  assert.match(AC, /true911: \{ icon: Wrench, word: "True911"/);
});

test("hero shows at most 3 summaries, never optional setup, never repeats the qualifying line", () => {
  const st = statusStatement(SUMMARY, AC_DATA);
  const chips = heroChips(st);
  assert.ok(chips.length <= 3);
  assert.ok(!chips.some((c) => /contact/i.test(c.text)), "contacts are optional setup -> Action Center only");
  assert.ok(!chips.some((c) => c.key === "t-reconcile"), "the qualifying line already says it");
  assert.deepEqual(chips.map((c) => c.owner), ["customer", "customer", "true911"], "customer actions first, then one True911 item");
  assert.ok(chips.every((c) => (c.owner === "customer") === (c.token === "attention")));
  assert.match(PARTS, /heroChips\(statement\)\.map/);
  // nothing is lost: the Action Center still lists contacts and True911's work
  const keys = actionCenterSections({ ...AC_DATA, missing_contact_information: [{ location_ref: "x", location: "x" }] })
    .filter((s) => s.items.length).map((s) => s.key);
  assert.ok(keys.includes("missing_contact_information") && keys.includes("being_reconciled") && keys.includes("e911_not_ready"));
});

// ── Map truth ────────────────────────────────────────────────────────
test("missing coordinates remain disclosed and no map point is fabricated", () => {
  const { markers, hidden } = mapMarkers([
    { location_ref: "a", map_point: { lat: 40.7, lng: -74 } }, { location_ref: "b", map_point: null },
    { location_ref: "c", map_point: { lat: 0, lng: 0 } }, { location_ref: "d", city: "Tampa", state: "FL" }]);
  assert.equal(markers.length, 1); assert.equal(hidden, 3);
  assert.match(MAP, /const \{ markers, hidden \} = useMemo\(\(\) => mapMarkers\(locations\), \[locations\]\)/);
  assert.match(MAP, /position=\{point\}/);
  assert.doesNotMatch(MAP, /geocod|nominatim|lat:\s*[-\d]|fallback/i);
  assert.match(MAP, /not shown on the map \(no coordinates on file\)/);
  assert.match(MAP, /TILE_CONFIG\.url/); assert.match(MAP, /TILE_CONFIG\.attribution/);
});

test("markers never rely on colour alone", () => {
  const shapes = new Set(["good", "attention", "unknown"].map((k) =>
    markerView({ location_ref: "x", op: { tone: { good: "good", attention: "problem", unknown: "neutral" }[k], label: k } }).shape));
  assert.equal(shapes.size, 3, "circle / diamond / ring");
  assert.ok(MAP_LEGEND_ITEMS.every((i) => i.label && i.shape));
  for (const k of ["good", "attention", "critical", "working", "unknown"]) assert.ok(STATUS_TOKENS[k].word && STATUS_TOKENS[k].icon, k);
  assert.match(MAP, /title=\{v\.ariaLabel\} alt=\{v\.ariaLabel\}/);
  assert.match(MAP, /keyboard/);
});

// ── Motion, accessibility, navigation, shell isolation ───────────────
test("reduced motion is honoured and motion never encodes state", () => {
  assert.match(CSS, /@media \(prefers-reduced-motion: reduce\) \{\s*\.t911-customer \*/);
  for (const src of [PARTS, MAP, AC, LCC]) assert.match(src, /useReducedMotion\(\)/);
  assert.match(LCC, /e\.key === "Escape" && !modal/);
  assert.match(LCC, /dialogRef\.current\?\.focus/);
});

test("navigation shows only real destinations; internal roles keep their shell", () => {
  assert.doesNotMatch(SHELL, /Reports|Coming soon|Soon\b|Billing|Documents/);
  assert.match(VIEW, /useCustomerNav\(\[/);
  assert.match(VIEW, /\.\.\.\(actionCenter \? \[\{ id: "cc-actions"/, "Action Center appears only when it exists");
  for (const id of ["cc-overview", "cc-actions", "cc-locations"]) assert.match(VIEW, new RegExp(`id="${id}"`));
  // customer roles branch BEFORE the sidebar; the sidebar path is untouched
  assert.match(LAYOUT, /if \(isCustomerApiRole\(user\.role\)\) \{\s*return \(\s*<>\s*<CustomerShell/);
  assert.match(LAYOUT, /<div className="hidden lg:flex flex-col fixed inset-y-0 left-0 w-\[252px\] z-30">/);
  assert.match(LAYOUT, /const NOC_NAV = \[/);
});
