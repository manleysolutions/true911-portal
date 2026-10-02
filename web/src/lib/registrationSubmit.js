// Wizard create → submit with a recoverable boundary (D-031).
//
// The server makes each step atomic (a registration and its acquisition record
// commit together; submit and its acquisition status commit together).  This
// client half makes a RETRY reuse the draft that already exists instead of
// creating a duplicate:
//   - once create succeeds, its id + resume token are kept for this attempt;
//     a retry with the same answers skips create and only submits;
//   - a 409 on submit means "already submitted" — confirmed by reading the
//     registration back with its token, never assumed.
// Pure module (API injected) so node tests can exercise it.

/** Stable signature of the answers, so edits after a failure start fresh. */
export function draftSignature(payload) {
  const { attribution: _ignored, ...rest } = payload || {};
  return JSON.stringify(rest);
}

/**
 * @param {{create:Function, submit:Function, get:Function}} api
 * @param {object} payload           body for create
 * @param {{current: object|null}} prior  holder for this attempt's created draft
 * @param {(created:{registration_id:string, resume_token:string}) => void} [onCreated]
 * @returns {Promise<{registration_id:string, resume_token:string, reusedDraft:boolean}>}
 */
export async function createAndSubmit(api, payload, prior, onCreated) {
  const sig = draftSignature(payload);
  let reusedDraft = false;
  let ids = prior.current && prior.current.sig === sig ? prior.current : null;
  if (ids) {
    reusedDraft = true;
  } else {
    const created = await api.create(payload);
    const registration_id = created?.registration?.registration_id;
    const resume_token = created?.resume_token;
    if (!registration_id || !resume_token) {
      throw new Error("Unexpected response from server. Please try again.");
    }
    ids = { registration_id, resume_token, sig };
    prior.current = ids;
    if (onCreated) onCreated({ registration_id, resume_token });
  }

  try {
    await api.submit(ids.registration_id, ids.resume_token);
  } catch (err) {
    if (err?.status !== 409) throw err;
    // Possibly submitted by an earlier attempt whose response was lost: verify.
    const current = await api.get(ids.registration_id, ids.resume_token);
    if (!current?.status || current.status === "draft") throw err;
  }
  return { registration_id: ids.registration_id, resume_token: ids.resume_token, reusedDraft };
}
