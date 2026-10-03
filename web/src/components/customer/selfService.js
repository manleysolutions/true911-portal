// ════════════════════════════════════════════════════════════════════
// Customer Self-Service — pure helpers for the Customer Operations Console.
//
// Dependency-free on purpose (no React, no "@/" alias) so the logic that decides
// what a customer may do and how it is worded can be unit-tested with the Node
// built-in test runner (`npm test`).  The SERVER re-checks every permission on
// every mutation; these helpers only decide what to show.
// ════════════════════════════════════════════════════════════════════

// Primary contextual actions, in display order.  `cap` names the capability flag
// from GET /customer/self-service/capabilities that unlocks it.
import { portfolioInventoryView } from "./serviceInventory.js";

export const PRIMARY_ACTIONS = [
  { key: "manage_location", label: "Manage Location", cap: "can_manage_location" },
  { key: "manage_connections", label: "Manage Telephone Lines", cap: "can_manage_location" },
  { key: "verify_e911", label: "Verify E911", cap: "can_attest_e911" },
  { key: "add_service", label: "Add Service", cap: "can_submit_requests", requestType: "add_service" },
  { key: "service_change", label: "Request Service Change", cap: "can_submit_requests", requestType: "move_service" },
  { key: "report_problem", label: "Report a Problem", cap: "can_submit_requests", requestType: "support_request" },
  { key: "update_contacts", label: "Update Contacts", cap: "can_manage_contacts" },
];

export function visibleActions(caps) {
  if (!caps || !caps.enabled) return [];
  return PRIMARY_ACTIONS.filter((a) => Boolean(caps[a.cap]));
}

// Request types a customer can pick in "Request Service Change".
export const CHANGE_REQUEST_TYPES = [
  { value: "move_service", label: "Move service" },
  { value: "remove_service", label: "Remove service" },
  { value: "change_number", label: "Change telephone number" },
  { value: "change_service_type", label: "Change service type" },
  { value: "replace_device", label: "Replace equipment" },
  { value: "location_correction", label: "Correct location details" },
];

export const PURPOSES = [
  { value: "elevator", label: "Elevator" },
  { value: "fire_alarm", label: "Fire Alarm" },
  { value: "emergency_phone", label: "Emergency Phone" },
  { value: "security", label: "Security" },
  { value: "fax", label: "Fax" },
  { value: "gate", label: "Gate" },
  { value: "other", label: "Other" },
];

export const CONTACT_ROLES = [
  { value: "facility", label: "Facility contact" },
  { value: "emergency", label: "Emergency contact" },
  { value: "property_manager", label: "Property / facility manager" },
];

// Terms that must never reach a customer screen (Constitution §7; the registry,
// source systems and True911's reconciliation / certification work are internal —
// D-028).  Used by tests and as a render-time guard.  Entries are regex fragments.
export const INTERNAL_TERMS = [
  "PortfolioReviewItem", "source confidence", "Napco", "Genesis", "Zoho",
  "ICCID", "IMEI", "MSISDN", "SIM",
  "reconcil\\w*", "canonical", "registry", "research required", "pending review",
  "store number",
];

export function containsInternalTerm(text) {
  const t = String(text || "");
  return INTERNAL_TERMS.some((term) => new RegExp(`\\b${term}\\b`, "i").test(t));
}

// ── Universal customer nouns (D-028) ────────────────────────────────
// Generic UI says LOCATION (and FACILITY where a physical place reads better) —
// never Store / School / Gallery / Installation.  Those belong to the customer's
// own data (a building called "Edmonton Gallery #505" keeps its name) or to a
// future per-tenant vocabulary layer, which would override these defaults.
export const CUSTOMER_NOUNS = {
  location: "Location",
  locations: "Locations",
  facility: "Facility",
  // the customer's own identifier for a location on True911's record (stored as
  // `store_number` for historical reasons — the field name is not UI language)
  locationId: "Location ID",
  locationIdHint: "The number or code your organization uses for this location, such as a site, building, school, store or facility number.",
  // the True911-governed record of the location (not a legal / government record)
  trueRecord: "True911 record",
};

// Internal review / research flags that sometimes sit inside a record's NAME
// (e.g. "RESEARCH REQUIRED Gallery #653").  Mirrors serialize._INTERNAL_NAME_MARKERS;
// the API strips them first, this is the render-time backstop.  Only the flag is
// removed — a replacement name is never invented.
const INTERNAL_NAME_MARKERS = /[[(]?\s*\b(?:research\s+(?:required|needed)|needs?\s+research|requires\s+research|(?:pending|needs?)\s+review|review\s+required)\b\s*[\])]?\s*[:\-–—]?/gi;

export function customerLocationName(name, fallback = CUSTOMER_NOUNS.location) {
  if (name == null) return name;
  const cleaned = String(name).replace(INTERNAL_NAME_MARKERS, " ").replace(/\s+/g, " ")
    .replace(/^[\s\-–—:,]+|[\s\-–—:,]+$/g, "");
  return cleaned || fallback;
}

// E911 states in which the CUSTOMER can act (Verify E911).  "not_verified" means
// no dispatch address is on file yet: there is nothing to confirm, so it is never
// offered as a confirmation — the verification team prepares the record first.
export const E911_ACTIONABLE_STATES = ["customer_confirmation_required", "failed"];

// E911 state -> visual tone.  Only "verified" is ever green; nothing a customer
// submits can produce it (the server derives it from the official record).
export function e911Tone(state) {
  if (state === "verified") return "ok";
  if (state === "failed") return "bad";
  if (state === "customer_confirmation_required") return "action";
  return "pending";
}

export function canVerifyE911(caps, e911) {
  if (!caps?.can_attest_e911 || !e911) return false;
  return E911_ACTIONABLE_STATES.includes(e911.state);
}

// Validate the E911 wizard before submit.  Returns a list of problems (empty = ok).
export function e911FormProblems(form) {
  const p = [];
  if (!form.building_confirmed) p.push("Confirm this is the right building.");
  if (!form.address_confirmed && !String(form.corrected_address || "").trim()) {
    p.push("Confirm the dispatch address or enter the correct one.");
  }
  if (!form.attest) p.push("Confirm that the information is correct.");
  return p;
}

// A contact card is savable when it can be reached by phone or email.
export function contactProblems(c) {
  if (!c) return [];
  const has = (v) => String(v || "").trim().length > 0;
  if (!has(c.name) && !has(c.phone) && !has(c.email) && !has(c.title)) return [];
  const p = [];
  if (!has(c.phone) && !has(c.email)) p.push("Add a phone number or an email address.");
  if (has(c.email) && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email.trim())) p.push("Enter a valid email address.");
  if (has(c.phone) && String(c.phone).replace(/\D/g, "").length < 7) p.push("Enter a valid phone number.");
  return p;
}

// Contact payload for PUT /contacts — blank cards clear the contact (null).
export function contactPayload(c) {
  if (!c) return null;
  const out = {};
  for (const k of ["name", "title", "phone", "email"]) {
    const v = String(c[k] || "").trim();
    if (v) out[k] = v;
  }
  return Object.keys(out).length ? out : null;
}

// Only send fields that actually changed (keeps the audit trail meaningful).
export function changedFields(original, edited, keys) {
  const out = {};
  for (const k of keys) {
    const a = original?.[k] ?? null;
    const b = edited?.[k] ?? null;
    const norm = (v) => (typeof v === "string" ? v.trim() || null : v);
    if (JSON.stringify(norm(a)) !== JSON.stringify(norm(b))) out[k] = norm(b);
  }
  return out;
}

export function requestTone(status) {
  if (status === "waiting_customer") return "action";
  if (status === "completed") return "ok";
  if (status === "rejected" || status === "cancelled") return "muted";
  return "pending";
}

export function errorText(e, fallback = "Something went wrong — please try again.") {
  const d = e?.body?.detail;
  if (d && typeof d === "object" && d.message) return d.message;
  if (typeof d === "string") return d;
  return e?.message || fallback;
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// Headline for the Action Center: "What do I need to do?"  Actionable E911
// confirmations and records still being prepared are counted SEPARATELY — a
// record with no dispatch address is never called a confirmation.
export function actionCenterHeadline(counts) {
  if (!counts) return null;
  const confirm = counts.e911_confirmation_required || 0;
  const notReady = counts.e911_not_ready || 0;
  const contacts = counts.missing_contact_information || 0;
  const attention = counts.needs_attention || 0;
  const waiting = counts.awaiting_your_response || 0;
  if (!confirm && !contacts && !attention && !waiting) {
    return notReady
      ? `You're all caught up. ${plural(notReady, "E911 record is", "E911 records are")} being prepared by the verification team.`
      : "You're all caught up.";
  }
  const parts = [];
  if (waiting) parts.push(`${plural(waiting, "request", "requests")} waiting on you`);
  if (confirm) parts.push(`${plural(confirm, "E911 confirmation", "E911 confirmations")} needed`);
  if (contacts) parts.push(`${plural(contacts, "location", "locations")} missing contacts`);
  if (attention) parts.push(`${attention} needing attention`);
  if (notReady) parts.push(`${plural(notReady, "E911 record", "E911 records")} being prepared`);
  return parts.join(" · ");
}

// Action Center buckets, in order.  `action` is what a row's button does; only
// actionable buckets carry one.  `informational` buckets never prompt the
// customer to do something they cannot do.
export function actionCenterSections(data) {
  if (!data) return [];
  const name = (it) => customerLocationName(it.location);
  const req = (it) => `${name(it)} — ${it.request_label}`;
  // a request waiting on the customer is THEIR action ("Waiting on you"), never
  // also listed as True911's in-progress work
  const true911Owned = (list) => (list || []).filter((it) => it.status !== "waiting_customer");
  return [
    { key: "awaiting_your_response", title: "Waiting on you", tone: "amber",
      items: data.awaiting_your_response || [], row: req, action: { intent: null, label: "Respond" } },
    { key: "needs_attention", title: "Service issues", tone: "red", items: data.needs_attention || [],
      row: (it) => `${name(it)} — ${it.label || statusWord(it.status).label}`, action: { intent: null, label: "Review" } },
    { key: "e911_confirmation_required", title: "E911 confirmations needed", tone: "amber",
      items: data.e911_confirmation_required || [], row: name,
      action: { intent: "verify_e911", label: "Verify E911" } },
    { key: "missing_contact_information", title: "Add site contacts", tone: "slate",
      subtitle: "Who we should call about each location. Add them when convenient.",
      items: data.missing_contact_information || [], row: name,
      action: { intent: "update_contacts", label: "Add contacts" } },
    { key: "being_reconciled", title: "Monitoring records being confirmed", tone: "slate",
      subtitle: "True911 is confirming these locations' monitoring information. No action is needed from you.",
      items: data.being_reconciled || [], row: name, informational: true },
    { key: "service_change_requests", title: "Service change requests", tone: "blue",
      subtitle: "Submitted by your team. True911 is processing these.",
      items: true911Owned(data.service_change_requests), row: (it) => `${req(it)}: ${it.status_label}`, informational: true },
    { key: "open_problems", title: "Reported problems", tone: "blue",
      subtitle: "True911 is working on these.",
      items: true911Owned(data.open_problems), row: (it) => `${name(it)} — ${it.status_label}`, informational: true },
    { key: "e911_not_ready", title: "E911 records being prepared", tone: "slate",
      subtitle: "No dispatch address on file yet — the verification team is preparing these. Nothing for you to confirm yet.",
      items: data.e911_not_ready || [], row: name, informational: true },
    { key: "recently_updated", title: "Recent activity", tone: "slate", items: data.recently_updated || [],
      subtitle: "Already done, for your records. Open requests and their current status are under In progress.",
      row: (it) => `${it.by} · ${activityText(it)}`, informational: true, noOpen: true },
  ];
}

// ── Activity = history, never a status (D-028) ──────────────────────
// Activity rows are append-only records of something that ALREADY happened.  The
// stored summaries of request events read like statuses ("Change service type
// requested", "Change service type: under review"), so they are rendered in the
// past tense.  A request's CURRENT status lives on the request itself (Requests /
// In progress), never here.  Stored events are not rewritten.
export function activityText(ev) {
  const summary = String(ev?.summary || "").trim();
  if (ev?.event_type === "request_submitted") {
    const m = summary.match(/^(.*?)\s+requested$/i);
    return m ? `Submitted a request: ${m[1]}` : summary;
  }
  if (ev?.event_type === "request_status_changed") {
    const m = summary.match(/^(.*?):\s*(.+)$/);
    return m ? `Request "${m[1]}" was marked ${m[2]}` : summary;
  }
  return summary;
}

// ── Data Completeness vs Operational Readiness ──────────────────────
// Two different questions, two different names:
//   * Data Completeness — how completely True911 knows the building's technical
//     record (a Building-health factor; its WEIGHT in overall health is shown as
//     a weight, never as a second score).
//   * Operational Readiness — how many of the seven readiness items the customer
//     has in place (the Bronze / Silver / Gold / Platinum tier).
export const TWIN_LABELS = {
  dataCompleteness: "Data Completeness",
  readinessTitle: "Operational Readiness",
  readinessHint: "Documents, contacts, procedures, testing, compliance, photos and E911 that you have in place.",
};
const FACTOR_LABELS = {
  operational_health: "Operational Health",
  digital_twin_completeness: TWIN_LABELS.dataCompleteness,
  compliance: "Compliance",
  documentation: "Documentation",
};
export function healthFactorLabel(f) {
  return FACTOR_LABELS[f?.key] || f?.label || "";
}
export function healthFactorWeight(weight) {
  return weight != null ? `weight ${weight}%` : "";
}
export function readinessProgress(met, total) {
  return `${met} of ${total} readiness items in place`;
}

// ── Building Workspace contribution controls ────────────────────────
// "coming_soon": the capability is not built (no file storage yet) — render a
// disabled control, never one that looks active and dead-ends.
// "replaced": self-service provides the real workflow (contacts overlay,
// governed requests) — hide the older append-only control to avoid two paths.
export const CONTRIBUTION_AVAILABILITY = {
  photo: "coming_soon",
  document: "coming_soon",
  procedure: "available",
  inspection: "available",
  note: "available",
  contact: "available",
  service_request: "available",
};
export function contributionControl(type, { selfService = false } = {}) {
  const base = CONTRIBUTION_AVAILABILITY[type];
  if (!base) return "hidden";
  if (selfService && (type === "contact" || type === "service_request")) return "replaced";
  return base;
}

// ── Service → telephone line wording ────────────────────────────────
// A telephone number is a LINE, not a life-safety connection: connections are
// the required communications paths of a confirmed service (D-023) and are not
// shown to customers until the canonical inventory is reconciled (PR #186b).
export function connectionServiceLabel(c) {
  return c?.service || "Not yet linked to a life-safety service";
}
export function servicesConnectionsSummary(loc) {
  if (!loc) return "";
  const s = loc.service_count ?? 0;
  const n = loc.connection_count ?? 0;
  const base = `${plural(n, "telephone line", "telephone lines")} across ${plural(s, "service", "services")}`;
  return loc.unlinked_connection_count
    ? `${base} · ${loc.unlinked_connection_count} not yet linked to a service` : base;
}

// ── Portfolio banner (no green unless every location is Protected) ──
export function protectionBanner(m) {
  const total = m?.locations_total || 0;
  const protectedN = m?.locations_protected || 0;
  const allProtected = total > 0 && protectedN === total;
  return {
    allProtected,
    text: allProtected ? "All listed locations are currently protected." : `${protectedN} of ${total} locations protected.`,
  };
}

// ════════════════════════════════════════════════════════════════════
// Customer trust rule (DECISIONS D-022):
//   KNOWN GOOD · KNOWN PROBLEM · UNKNOWN — and UNKNOWN ≠ FAILED, UNKNOWN ≠ PROTECTED.
// Missing evidence renders NEUTRAL (never red, never green).  Only an
// evidence-backed problem is red/amber; only evidence-backed good is green.
// ════════════════════════════════════════════════════════════════════
export const TONES = { good: "good", problem: "problem", urgent: "urgent", neutral: "neutral" };

// Location operational state (from the API's `operational_state.state`).
const OPERATIONAL = {
  monitored: { label: "Monitored", tone: "good" },
  attention_required: { label: "Needs attention", tone: "problem" },
  // UNKNOWN states: True911's work, said plainly — never green, never red (D-022)
  being_reconciled: { label: "Monitoring record being confirmed", tone: "neutral", owner: "true911",
    summary: "True911 is confirming this location's monitoring information. No action is needed from you." },
  not_yet_confirmed: { label: "Status being confirmed", tone: "neutral", owner: "true911",
    summary: "True911 is confirming this location's status. No action is needed from you." },
};
// A list item's operational state — the API's `operational_state` when present,
// else derived from the assurance label (older payloads) with the SAME rule.
export function locationOperational(item) {
  if (item?.operational_state) return operationalView(item.operational_state);
  const st = item?.protection?.status;
  const state = st === "Critical" || st === "Attention Needed" ? "attention_required"
    : item?.monitoring_linked === false ? "being_reconciled"
    : st === "Protected" ? "monitored" : "not_yet_confirmed";
  return operationalView({ state, urgent: st === "Critical" });
}

export function operationalView(op) {
  const state = OPERATIONAL[op?.state] ? op.state : "not_yet_confirmed";
  const base = OPERATIONAL[state];
  // UNKNOWN states always use their owner-explicit copy; known states use the
  // API's evidence-backed summary.
  return { ...base, state, tone: op?.urgent ? "urgent" : base.tone,
    summary: base.summary || op?.summary || OPERATIONAL.not_yet_confirmed.summary };
}

// What True911 is doing at ONE location — the location page's counterpart of the
// dashboard's "In progress".  Never contains anything the customer must do.
export function locationTrue911Work(ws, op) {
  const out = [];
  if (op?.owner === "true911") {
    out.push(op.state === "being_reconciled" ? "confirming monitoring information" : "confirming this location's status");
  }
  if (ws?.e911?.state === "not_verified") out.push("preparing the E911 record");
  const processing = (ws?.requests || []).filter((r) => r.open && r.status !== "waiting_customer").length;
  if (processing) out.push(`processing ${plural(processing, "request", "requests")}`);
  return out;
}

// Service / connection assurance label -> customer word + tone.  "Protected"
// reads "Monitored" (what the evidence supports); "Unknown" is neutral.
const STATUS_WORDS = {
  Protected: { label: "Monitored", tone: "good" },
  "Attention Needed": { label: "Needs attention", tone: "problem" },
  Critical: { label: "Needs attention now", tone: "urgent" },
  "Pending Install": { label: "Being installed", tone: "neutral" },
  Inactive: { label: "Inactive", tone: "neutral" },
  Unknown: { label: "Status being confirmed", tone: "neutral" },
};
export function statusWord(status) {
  return STATUS_WORDS[status] || STATUS_WORDS.Unknown;
}

// ── Portfolio hero: facts, four separate dimensions, and who owns what ──
// Deliberately NO blended health score: documentation / data completeness is
// "Portfolio setup", never presented as service health.
// The "Service inventory" fact: the canonical readiness when the backend sends
// it (#186b), else the original placeholder exactly.  Never a service total.
function inventoryFact(m) {
  const inv = portfolioInventoryView(m);
  if (!inv) return { key: "inventory", label: "Service inventory", value: "Being finalized by True911", pending: true };
  return { key: "inventory", label: "Service inventory", value: inv.value, detail: inv.detail, pending: inv.pending };
}

export function portfolioHero(summary, ac) {
  const m = summary || {};
  const ops = m.operational_states || {};
  const c = ac?.counts || {};
  const total = m.locations_total || 0;
  const attention = ops.attention_required || 0;
  const monitored = ops.monitored || 0;
  const reconciling = ops.being_reconciled || 0;
  const confirming = ops.not_yet_confirmed || 0;
  const withContacts = ac ? Math.max(total - (c.missing_contact_information || 0), 0) : null;

  const dimensions = [
    { key: "service_status", title: "Service status",
      value: attention ? plural(attention, "location needs attention", "locations need attention") : "No known service issues",
      detail: attention ? "Being worked on — see Urgent below." : "Based on current monitoring evidence.",
      tone: attention ? "problem" : "good" },
    { key: "monitoring", title: "Monitoring coverage",
      value: `${monitored} of ${total} locations monitored`,
      detail: [reconciling && `${plural(reconciling, "monitoring record", "monitoring records")} being confirmed by True911`,
        confirming && `${plural(confirming, "status", "statuses")} being confirmed by True911`]
        .filter(Boolean).join(" · ") || "All locations linked to monitoring.",
      tone: "neutral" },
    { key: "e911", title: "E911 readiness",
      value: `${m.e911_verified_locations ?? 0} verified`,
      detail: ac
        ? [c.e911_confirmation_required && `${c.e911_confirmation_required} ready for your confirmation`,
          c.e911_not_ready && `${c.e911_not_ready} being prepared by True911`].filter(Boolean).join(" · ") || "Nothing waiting."
        : "Verification is completed by the verification team.",
      tone: "neutral" },
    { key: "setup", title: "Portfolio setup",
      value: withContacts == null ? "—" : `Contacts on file for ${withContacts} of ${total}`,
      detail: "Contacts, procedures and records you add over time.",
      tone: "neutral" },
  ];
  const customerActions = ac ? [
    c.e911_confirmation_required && { key: "e911", text: `${plural(c.e911_confirmation_required, "E911 confirmation", "E911 confirmations")} ready` },
    (ac.awaiting_your_response || []).length && { key: "respond", text: `${plural(ac.awaiting_your_response.length, "request", "requests")} waiting on you` },
    c.missing_contact_information && { key: "contacts", text: `${plural(c.missing_contact_information, "location needs", "locations need")} contacts` },
  ].filter(Boolean) : [];
  const operationsActions = ac ? [
    c.e911_not_ready && { key: "e911_prep", text: `${plural(c.e911_not_ready, "E911 record", "E911 records")} being prepared` },
    reconciling && { key: "reconcile", text: `Confirming monitoring information for ${plural(reconciling, "location", "locations")}` },
  ].filter(Boolean) : [];
  return {
    facts: [
      { key: "locations", label: "Locations", value: total },
      { key: "devices", label: "Physical devices", value: m.devices ?? m.total_devices ?? 0 },
      // The legacy distinct-telephone-number count is NOT a count of life-safety
      // connections (D-023); no service/connection total is shown until the
      // canonical inventory is approved for customer use.
      inventoryFact(m),
    ],
    dimensions, customerActions, operationsActions,
  };
}

// ── Action Center tiers ─────────────────────────────────────────────
export const TIER_META = {
  urgent: { title: "Urgent", subtitle: "Known service problems", open: true },
  action_needed: { title: "Action needed", subtitle: "Things you can do now", open: true },
  in_progress: { title: "In progress", subtitle: "True911 is handling these — nothing for you to do", open: false },
  informational: { title: "Portfolio setup", subtitle: "Optional — complete over time; nothing is wrong", open: false },
  activity: { title: "Recent activity", subtitle: "History — already done; nothing is waiting", open: false },
};
// Ownership (D-028): customer action · True911 action · optional setup · history.
const DEFAULT_TIERS = [
  { tier: "urgent", owner: "true911", lists: ["needs_attention"] },
  { tier: "action_needed", owner: "customer", lists: ["awaiting_your_response", "e911_confirmation_required"] },
  { tier: "in_progress", owner: "true911", lists: ["e911_not_ready", "being_reconciled", "service_change_requests", "open_problems"] },
  { tier: "informational", owner: "customer", lists: ["missing_contact_information"] },
  { tier: "activity", owner: "none", lists: ["recently_updated"] },
];
// History always gets its own tier, even if an older API lists it under setup.
function normalizeTiers(tiers) {
  const out = tiers.map((t) => (t.tier === "activity" ? t
    : { ...t, lists: t.lists.filter((k) => k !== "recently_updated") }));
  return out.some((t) => t.tier === "activity") ? out
    : [...out, { tier: "activity", owner: "none", lists: ["recently_updated"] }];
}
export function actionCenterTiers(data) {
  if (!data) return [];
  const sections = Object.fromEntries(actionCenterSections(data).map((s) => [s.key, s]));
  return normalizeTiers(data.tiers || DEFAULT_TIERS).map((t) => {
    const list = t.lists.map((k) => sections[k]).filter((s) => s && s.items.length);
    return { ...t, ...TIER_META[t.tier], sections: list, count: list.reduce((n, s) => n + (s.key === "recently_updated" ? 0 : s.items.length), 0) };
  }).filter((t) => t.sections.length);
}

// ── Location page: one place per thing ──────────────────────────────
// Overview · Services & Lines · Compliance · Records.  Each subject lives in exactly
// one section; the header carries at most two primary actions.
export const LOCATION_TABS = [
  { key: "overview", label: "Overview", sections: ["status", "your_actions", "requests"] },
  { key: "connections", label: "Services & Lines", sections: ["services_connections_devices"] },
  { key: "compliance", label: "Compliance", sections: ["e911", "inspections", "procedures"] },
  { key: "records", label: "Records", sections: ["contacts", "notes", "activity", "documents_photos"] },
];

export function locationActions(ws, caps) {
  if (!caps?.enabled) return { primary: [], more: [] };
  const primary = [];
  if (canVerifyE911(caps, ws?.e911)) primary.push({ key: "verify_e911", label: "Confirm E911", tab: "compliance" });
  if (caps.can_manage_location) primary.push({ key: "manage_location", label: "Manage Location" });
  const more = [
    caps.can_submit_requests && { key: "add_service", label: "Add Service", requestType: "add_service" },
    caps.can_submit_requests && { key: "service_change", label: "Request Service Change", requestType: "move_service" },
    caps.can_submit_requests && { key: "report_problem", label: "Report a Problem", requestType: "support_request" },
    caps.can_manage_contacts && { key: "update_contacts", label: "Update Contacts", tab: "records" },
  ].filter(Boolean);
  if (!primary.length && more.length) primary.push(more.shift());
  return { primary: primary.slice(0, 2), more };
}

// Group connections under their service; connections not yet linked to a
// service get their own group (never presented as a service).
export function groupConnectionsByService(services, connections) {
  const groups = (services || []).map((s) => ({
    key: s.service_ref, service: s.service, status: s.status, equipment: s.equipment || [],
    connections: (connections || []).filter((c) => c.service_ref && c.service_ref === s.service_ref),
  }));
  const unlinked = (connections || []).filter((c) => !c.service_ref || !groups.some((g) => g.key === c.service_ref));
  if (unlinked.length) {
    groups.push({ key: "unlinked", service: null, status: null, equipment: [], connections: unlinked });
  }
  return groups;
}
