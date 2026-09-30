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
export const PRIMARY_ACTIONS = [
  { key: "manage_location", label: "Manage Location", cap: "can_manage_location" },
  { key: "manage_connections", label: "Manage Connections", cap: "can_manage_location" },
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

// Terms that must never reach a customer screen (Constitution §7; the registry
// and source systems are internal).  Used by tests and as a render-time guard.
export const INTERNAL_TERMS = [
  "PortfolioReviewItem", "source confidence", "Napco", "Genesis", "Zoho",
  "ICCID", "IMEI", "MSISDN", "SIM",
];

export function containsInternalTerm(text) {
  const t = String(text || "");
  return INTERNAL_TERMS.some((term) => new RegExp(`\\b${term}\\b`, "i").test(t));
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
  const req = (it) => `${it.location} — ${it.request_label}`;
  return [
    { key: "awaiting_your_response", title: "Waiting on you", tone: "amber",
      items: data.awaiting_your_response || [], row: req, action: { intent: null, label: "Respond" } },
    { key: "needs_attention", title: "Needs attention", tone: "red", items: data.needs_attention || [],
      row: (it) => `${it.location} — ${it.status}`, action: { intent: null, label: "Review" } },
    { key: "e911_confirmation_required", title: "E911 confirmations needed", tone: "amber",
      items: data.e911_confirmation_required || [], row: (it) => it.location,
      action: { intent: "verify_e911", label: "Verify E911" } },
    { key: "missing_contact_information", title: "Missing contact information", tone: "amber",
      items: data.missing_contact_information || [], row: (it) => it.location,
      action: { intent: "update_contacts", label: "Add contacts" } },
    { key: "service_change_requests", title: "Service change requests", tone: "blue",
      items: data.service_change_requests || [], row: (it) => `${req(it)}: ${it.status_label}`, informational: true },
    { key: "open_problems", title: "Open problems", tone: "blue", items: data.open_problems || [],
      row: (it) => `${it.location} — ${it.status_label}`, informational: true },
    { key: "e911_not_ready", title: "E911 records being prepared", tone: "slate",
      subtitle: "No dispatch address on file yet — the verification team is preparing these. Nothing for you to confirm yet.",
      items: data.e911_not_ready || [], row: (it) => it.location, informational: true },
    { key: "recently_updated", title: "Recently updated", tone: "slate", items: data.recently_updated || [],
      row: (it) => `${it.by} · ${it.summary}`, informational: true, noOpen: true },
  ];
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

// ── Service → connection wording ────────────────────────────────────
export function connectionServiceLabel(c) {
  return c?.service || "Not yet linked to a life-safety service";
}
export function servicesConnectionsSummary(loc) {
  if (!loc) return "";
  const s = loc.service_count ?? 0;
  const n = loc.connection_count ?? 0;
  const base = `${plural(n, "connection", "connections")} across ${plural(s, "service", "services")}`;
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
