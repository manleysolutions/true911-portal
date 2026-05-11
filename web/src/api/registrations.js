/**
 * Public registration API wrapper.
 *
 * All four endpoints live under /api/public and are anonymous — they
 * don't require a JWT.  The resume token issued at create time is the
 * sole authorization for every subsequent call against that record.
 *
 * The backend contract (Phase R1):
 *   POST   /public/registrations
 *     body: { submitter_email, ..., locations: [{ ..., service_units: [...] }] }
 *     201 -> { registration: {...}, resume_token: "<plaintext, one-time>" }
 *
 *   GET    /public/registrations/{registration_id}?token=<token>
 *     200 -> RegistrationOut (with locations and service_units)
 *
 *   PATCH  /public/registrations/{registration_id}?token=<token>
 *     body: top-level fields only (locations/units are not editable post-create)
 *     200 -> RegistrationOut
 *
 *   POST   /public/registrations/{registration_id}/submit?token=<token>
 *     200 -> RegistrationOut (status = "submitted")
 *
 * Error contract: 403 token mismatch, 410 token expired, 404 not found,
 * 409 illegal transition / not editable, 422 payload validation.
 */

import { apiFetch } from "./client";

function withToken(path, token) {
  return `${path}?token=${encodeURIComponent(token || "")}`;
}

export const RegistrationAPI = {
  /** Create a new draft.  Returns { registration, resume_token }. */
  create(body) {
    return apiFetch("/public/registrations", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Load a saved registration via its resume token. */
  get(registrationId, token) {
    return apiFetch(withToken(`/public/registrations/${registrationId}`, token));
  },

  /** Partial update — only the customer-facing top-level fields are
   * accepted by the backend.  Locations / service units are not
   * editable on this surface today; they live in the original POST. */
  update(registrationId, token, body) {
    return apiFetch(
      withToken(`/public/registrations/${registrationId}`, token),
      { method: "PATCH", body: JSON.stringify(body) },
    );
  },

  /** Finalize a draft (status: draft -> submitted).  After this call
   * the public surface is read-only for this registration. */
  submit(registrationId, token) {
    return apiFetch(
      withToken(`/public/registrations/${registrationId}/submit`, token),
      { method: "POST" },
    );
  },
};


/**
 * Internal review API (Phase R3) — authenticated, gated by
 * VIEW_REGISTRATIONS / MANAGE_REGISTRATIONS server-side.
 *
 * Lives under /api/registrations (not /api/public).  The JWT in the
 * Authorization header is the sole credential here — no resume tokens.
 */
function buildQuery(params = {}) {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") usp.set(k, v);
  });
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export const RegistrationAdminAPI = {
  /** List/filter registrations.
   *  Accepts: { status, search, sort, limit }
   *  status is sent as ?status=, NOT ?status_filter= (the backend
   *  aliases the param). */
  list(params = {}) {
    return apiFetch(`/registrations${buildQuery(params)}`);
  },

  /** { total, by_status: { draft: N, submitted: N, ... } } */
  count() {
    return apiFetch("/registrations/count");
  },

  /** Full detail incl. locations, service units, and status timeline. */
  get(registrationId) {
    return apiFetch(`/registrations/${registrationId}`);
  },

  /** Admin-side partial update (reviewer notes, plan, target tenant, etc.).
   *  Status is not editable here — use transition().  Unknown fields
   *  are silently dropped server-side. */
  update(registrationId, body) {
    return apiFetch(`/registrations/${registrationId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  /** Move a registration to a new status.
   *  body: { to_status, note? }
   *  409 on illegal transitions. */
  transition(registrationId, toStatus, note) {
    return apiFetch(`/registrations/${registrationId}/transition`, {
      method: "POST",
      body: JSON.stringify({ to_status: toStatus, note: note || null }),
    });
  },

  /** Move to pending_customer_info with a recorded question.
   *  R3 stores the message in the status event note only — no email is sent. */
  requestInfo(registrationId, message) {
    return apiFetch(`/registrations/${registrationId}/request-info`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  },

  /** Cancel from any non-terminal state.  The reason is stamped on
   *  both the registration row and the status event. */
  cancel(registrationId, reason) {
    return apiFetch(`/registrations/${registrationId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },

  /** Materialize a registration into production rows.
   *
   *  Body fields (see RegistrationConvertRequest on the backend):
   *    tenant_choice            "attach_existing" | "create_new"
   *    existing_tenant_id       required if attach
   *    new_tenant_id, _name     required if create
   *    customer_choice          "attach_existing" | "create_new"
   *    existing_customer_id     required if attach
   *    create_subscription      bool
   *    dry_run                  bool
   *    confirm                  must be true on real runs
   *
   *  On per-stage failure the backend returns 422 with a structured
   *  body { detail: { stage, message, next_steps, details } } —
   *  apiFetch surfaces it on err.body so callers can render the
   *  stage + next_steps to the reviewer.
   *
   *  Permission: CONVERT_REGISTRATIONS (server-enforced). */
  convert(registrationId, body) {
    return apiFetch(`/registrations/${registrationId}/convert`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Read-only status of the registration's customer portal invite.
   *
   *  Response shape (RegistrationInviteStatusOut):
   *    {
   *      has_invite: bool,
   *      user_id: str | null,
   *      email: str | null,
   *      is_active: bool,          // customer already signed in
   *      has_pending_invite: bool, // unaccepted invite with valid expiry
   *      invite_expires_at: datetime | null,
   *    }
   *
   *  The plaintext invite_token is deliberately NOT returned here —
   *  the operator's only chance to see it is on the transition
   *  response that just created or rotated it.
   *
   *  Permission: VIEW_REGISTRATIONS (server-enforced). */
  getInviteStatus(registrationId) {
    return apiFetch(`/registrations/${registrationId}/invite-status`);
  },
};
