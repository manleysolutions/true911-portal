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

// E911 state -> visual tone.  Only "verified" is ever green; nothing a customer
// submits can produce it (the server derives it from the official record).
export function e911Tone(state) {
  if (state === "verified") return "ok";
  if (state === "failed") return "bad";
  if (state === "customer_confirmation_required" || state === "not_verified") return "action";
  return "pending";
}

export function canVerifyE911(caps, e911) {
  if (!caps?.can_attest_e911 || !e911) return false;
  return !["verified", "customer_submitted", "verification_pending", "requires_review"].includes(e911.state);
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

// Headline for the Action Center: "What do I need to do?"
export function actionCenterHeadline(counts) {
  if (!counts) return null;
  const todo = (counts.e911_verification_required || 0) + (counts.missing_contact_information || 0);
  if (todo === 0 && !(counts.needs_attention || 0)) return "You're all caught up.";
  const parts = [];
  if (counts.e911_verification_required) parts.push(`${counts.e911_verification_required} E911 confirmation${counts.e911_verification_required === 1 ? "" : "s"}`);
  if (counts.missing_contact_information) parts.push(`${counts.missing_contact_information} location${counts.missing_contact_information === 1 ? "" : "s"} missing contacts`);
  if (counts.needs_attention) parts.push(`${counts.needs_attention} needing attention`);
  return parts.join(" · ");
}
