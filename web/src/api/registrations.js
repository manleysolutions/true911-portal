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
