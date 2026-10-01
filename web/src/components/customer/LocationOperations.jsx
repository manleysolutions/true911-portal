import { useState, useEffect, useCallback } from "react";
import { X } from "lucide-react";
import { apiFetch } from "@/api/client";
import {
  CHANGE_REQUEST_TYPES, PURPOSES, CONTACT_ROLES, e911FormProblems, contactProblems,
  contactPayload, changedFields, errorText, CUSTOMER_NOUNS, customerLocationName,
} from "@/components/customer/selfService";

// ════════════════════════════════════════════════════════════════════
// Location self-service building blocks — the data hook and the action
// modals used by the location page (LocationCommandCenter).
//
// Data: GET /customer/locations/{ref}/workspace (self-service, flag-gated; a
// 404 means the console is off for this user and the page stays read-only).
// Customer-owned details save directly; anything touching provisioning,
// identity or E911 is submitted as a request operations review.
// ════════════════════════════════════════════════════════════════════

const TONE = {
  ok: "bg-emerald-50 border-emerald-200 text-emerald-800",
  action: "bg-amber-50 border-amber-200 text-amber-800",
  pending: "bg-blue-50 border-blue-200 text-blue-800",
  bad: "bg-red-50 border-red-200 text-red-800",
  muted: "bg-slate-50 border-slate-200 text-slate-600",
  // trust-rule tones (selfService.statusWord / operationalView)
  good: "bg-emerald-50 border-emerald-200 text-emerald-800",
  problem: "bg-amber-50 border-amber-200 text-amber-800",
  urgent: "bg-red-50 border-red-200 text-red-800",
  neutral: "bg-white border-slate-300 text-slate-600",
};

export const Pill = ({ tone = "muted", children }) => (
  <span className={`inline-flex items-center text-[10.5px] font-medium px-2 py-0.5 rounded-full border ${TONE[tone]}`}>{children}</span>
);

const inputCls = "w-full px-2.5 py-1.5 text-[12.5px] border border-slate-200 rounded-lg bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300";

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium text-slate-600">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="text-[10.5px] text-slate-400">{hint}</span>}
    </label>
  );
}

function Modal({ title, onClose, children, footer }) {
  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-slate-900/40" />
      <div className="relative w-full max-w-md bg-white rounded-xl shadow-xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between sticky top-0 bg-white">
          <h3 className="text-[14px] font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 text-slate-500" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-3">{children}</div>
        {footer && <div className="px-5 py-3 border-t border-slate-100 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

export const Btn = ({ primary, disabled, onClick, children }) => (
  <button type="button" disabled={disabled} onClick={onClick}
    className={`text-[12px] font-medium px-3 py-1.5 rounded-lg border disabled:opacity-50 ${primary ? "bg-slate-800 border-slate-800 text-white hover:bg-slate-700" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}>
    {children}
  </button>
);

function Problems({ items }) {
  if (!items?.length) return null;
  return <ul className="text-[11.5px] text-red-700 list-disc pl-4 space-y-0.5">{items.map((p) => <li key={p}>{p}</li>)}</ul>;
}

// ── E911 verification wizard ────────────────────────────────────────
function E911Wizard({ ws, onClose, onDone, post }) {
  const e = ws.e911;
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k) => (ev) => setF((p) => ({ ...p, [k]: ev.target.type === "checkbox" ? ev.target.checked : ev.target.value }));
  const problems = e911FormProblems(f);
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await post("/e911/verification", {
        number_confirmed: !!f.number_confirmed, address_confirmed: !!f.address_confirmed,
        building_confirmed: !!f.building_confirmed, corrected_address: f.corrected_address || null,
        suite: f.suite || null, floor: f.floor || null, additional_location: f.additional_location || null,
        callback_number: f.callback_number || null, note: f.note || null, attest: !!f.attest,
      });
      onDone("Thank you — your E911 confirmation was submitted. The verification team will complete verification.");
    } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  const Check = ({ k, children }) => (
    <label className="flex items-start gap-2 text-[12.5px] text-slate-700"><input type="checkbox" className="mt-0.5" checked={!!f[k]} onChange={set(k)} />{children}</label>
  );
  return (
    <Modal title="Verify E911" onClose={onClose}
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn primary disabled={busy || problems.length > 0} onClick={submit}>{busy ? "Submitting…" : "Submit verification"}</Btn></>}>
      <p className="text-[12px] text-slate-500">Review what 911 dispatchers would see for <strong>{ws.location.display_name}</strong>. Your confirmation is recorded and the verification team completes the official verification.</p>
      <div className="rounded-lg border border-slate-200 p-3 space-y-2">
        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">1 · Service numbers</p>
        <p className="text-[12.5px] text-slate-800">{(e.service_numbers || []).join(" · ") || "No number on file yet"}</p>
        <Check k="number_confirmed">These are the numbers used by this location's life-safety services.</Check>
      </div>
      <div className="rounded-lg border border-slate-200 p-3 space-y-2">
        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">2 · Dispatch address</p>
        <p className="text-[12.5px] text-slate-800">{e.dispatch_address || "No address on file"}</p>
        <Check k="address_confirmed">This is the correct address for emergency dispatch.</Check>
        <Field label="Not right? Enter the correct address"><input className={inputCls} value={f.corrected_address || ""} onChange={set("corrected_address")} /></Field>
      </div>
      <div className="rounded-lg border border-slate-200 p-3 space-y-2">
        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">3 · Building & where in it</p>
        <Check k="building_confirmed">This is the right building ({ws.location.display_name}).</Check>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Suite"><input className={inputCls} value={f.suite || ""} onChange={set("suite")} /></Field>
          <Field label="Floor"><input className={inputCls} value={f.floor || ""} onChange={set("floor")} /></Field>
        </div>
        <Field label="Additional location detail"><input className={inputCls} value={f.additional_location || ""} onChange={set("additional_location")} placeholder="e.g. Elevator 2, rear stairwell" /></Field>
      </div>
      <div className="rounded-lg border border-slate-200 p-3 space-y-2">
        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">4 · Callback</p>
        <Field label="Callback number (only if it should change)" hint="A new callback number is reviewed before it is used."><input className={inputCls} value={f.callback_number || ""} onChange={set("callback_number")} /></Field>
        <Field label="Note (optional)"><textarea rows={2} className={inputCls} value={f.note || ""} onChange={set("note")} /></Field>
      </div>
      <Check k="attest">I confirm this information is correct to the best of my knowledge.</Check>
      <Problems items={problems} />
      {err && <p className="text-[12px] text-red-700">{err}</p>}
    </Modal>
  );
}

// ── Governed request form ───────────────────────────────────────────
function RequestForm({ ws, initialType, onClose, onDone, post }) {
  const isChange = initialType === "move_service";
  const [type, setType] = useState(initialType);
  const [notes, setNotes] = useState("");
  const [conn, setConn] = useState("");
  const [priority, setPriority] = useState("normal");
  const [purpose, setPurpose] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const title = type === "add_service" ? "Add Service" : type === "support_request" ? "Report a Problem" : "Request Service Change";
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await post("/requests", {
        request_type: type, notes, priority, connection_ref: conn || null,
        requested_changes: purpose ? { service_purpose: purpose } : {},
      });
      onDone(`${title} submitted — you can follow its status under Requests.`);
    } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  return (
    <Modal title={title} onClose={onClose}
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn primary disabled={busy || !notes.trim()} onClick={submit}>{busy ? "Submitting…" : "Submit request"}</Btn></>}>
      <p className="text-[12px] text-slate-500">Changes that affect service, numbers or equipment are reviewed and scheduled by the operations team. Nothing changes until then.</p>
      {isChange && (
        <Field label="What would you like to change?">
          <select className={inputCls} value={type} onChange={(e) => setType(e.target.value)}>
            {CHANGE_REQUEST_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </Field>
      )}
      {type === "add_service" && (
        <Field label="Service purpose">
          <select className={inputCls} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="">Select…</option>{PURPOSES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </Field>
      )}
      {type !== "add_service" && ws.connections.length > 0 && (
        <Field label="Which telephone line? (optional)">
          <select className={inputCls} value={conn} onChange={(e) => setConn(e.target.value)}>
            <option value="">The whole location</option>
            {ws.connections.map((c) => <option key={c.connection_ref} value={c.connection_ref}>{c.name}{c.phone_number ? ` · ${c.phone_number}` : ""}</option>)}
          </select>
        </Field>
      )}
      <Field label={type === "support_request" ? "What's happening?" : "Details"}>
        <textarea rows={4} className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      {type === "support_request" && (
        <Field label="Urgency">
          <select className={inputCls} value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent — life-safety service down</option>
          </select>
        </Field>
      )}
      {err && <p className="text-[12px] text-red-700">{err}</p>}
    </Modal>
  );
}

// ── Manage Location (customer-owned details + governed corrections) ──
function LocationForm({ ws, onClose, onDone, patch }) {
  const keys = ["display_name", "location_notes", "access_notes", "customer_reference"];
  const [f, setF] = useState({ ...ws.profile, display_name: ws.profile.display_name || "" });
  const [corr, setCorr] = useState({ address: "", store_number: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const changes = changedFields(ws.profile, f, keys);
      if (corr.address.trim()) changes.address = corr.address.trim();
      if (corr.store_number.trim()) changes.store_number = corr.store_number.trim();
      if (!Object.keys(changes).length) { onClose(); return; }
      const r = await patch("/profile", { changes });
      onDone(r.request ? `Saved. Your address / ${CUSTOMER_NOUNS.locationId} correction was sent to True911 for review.` : "Location details saved.");
    } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  return (
    <Modal title="Manage Location" onClose={onClose}
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn primary disabled={busy} onClick={submit}>{busy ? "Saving…" : "Save"}</Btn></>}>
      <Field label="Location name (how your team refers to it)" hint={`${CUSTOMER_NOUNS.trueRecord}: ${customerLocationName(ws.location.canonical_name)}`}><input className={inputCls} value={f.display_name || ""} onChange={set("display_name")} /></Field>
      <Field label="Your reference / cost-center #"><input className={inputCls} value={f.customer_reference || ""} onChange={set("customer_reference")} /></Field>
      <Field label="Location notes"><textarea rows={3} className={inputCls} value={f.location_notes || ""} onChange={set("location_notes")} /></Field>
      <Field label="Access notes" hint="Gate codes and keys are best shared by phone, not stored here."><textarea rows={2} className={inputCls} value={f.access_notes || ""} onChange={set("access_notes")} /></Field>
      <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-2">
        <p className="text-[11.5px] text-slate-600">Wrong address or {CUSTOMER_NOUNS.locationId}? These are part of True911's record for this location, so True911 reviews a correction before applying it.</p>
        <Field label="Correct address"><input className={inputCls} value={corr.address} onChange={(e) => setCorr((p) => ({ ...p, address: e.target.value }))} placeholder={ws.location.address || ""} /></Field>
        <Field label={`Correct ${CUSTOMER_NOUNS.locationId}`} hint={CUSTOMER_NOUNS.locationIdHint}><input className={inputCls} value={corr.store_number} onChange={(e) => setCorr((p) => ({ ...p, store_number: e.target.value }))} placeholder={ws.location.store_number || ""} /></Field>
      </div>
      {err && <p className="text-[12px] text-red-700">{err}</p>}
    </Modal>
  );
}

// ── Update Contacts ─────────────────────────────────────────────────
function ContactsForm({ ws, onClose, onDone, put }) {
  const [c, setC] = useState(() => Object.fromEntries(CONTACT_ROLES.map((r) => [r.value, { ...(ws.contacts.contacts[r.value] || {}) }])));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const problems = CONTACT_ROLES.flatMap((r) => contactProblems(c[r.value]).map((p) => `${r.label}: ${p}`));
  const set = (role, k) => (e) => setC((p) => ({ ...p, [role]: { ...p[role], [k]: e.target.value } }));
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const contacts = {};
      for (const r of CONTACT_ROLES) {
        const before = contactPayload(ws.contacts.contacts[r.value]);
        const after = contactPayload(c[r.value]);
        if (JSON.stringify(before) !== JSON.stringify(after)) contacts[r.value] = after;
      }
      if (!Object.keys(contacts).length) { onClose(); return; }
      await put("/contacts", { contacts });
      onDone("Contacts saved.");
    } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  return (
    <Modal title="Update Contacts" onClose={onClose}
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn primary disabled={busy || problems.length > 0} onClick={submit}>{busy ? "Saving…" : "Save contacts"}</Btn></>}>
      {CONTACT_ROLES.map((r) => (
        <div key={r.value} className="rounded-lg border border-slate-200 p-3 space-y-2">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{r.label}</p>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Name"><input className={inputCls} value={c[r.value].name || ""} onChange={set(r.value, "name")} /></Field>
            <Field label="Title"><input className={inputCls} value={c[r.value].title || ""} onChange={set(r.value, "title")} /></Field>
            <Field label="Phone"><input className={inputCls} value={c[r.value].phone || ""} onChange={set(r.value, "phone")} /></Field>
            <Field label="Email"><input className={inputCls} value={c[r.value].email || ""} onChange={set(r.value, "email")} /></Field>
          </div>
        </div>
      ))}
      <Problems items={problems} />
      {err && <p className="text-[12px] text-red-700">{err}</p>}
    </Modal>
  );
}

// ── Edit one connection ─────────────────────────────────────────────
function ConnectionForm({ conn, onClose, onDone, patchConn }) {
  const [f, setF] = useState({
    friendly_name: conn.name === conn.default_name ? "" : conn.name, purpose: conn.purpose,
    customer_notes: conn.customer_notes || "", contact: { ...(conn.customer_contact || {}) }, new_number: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const contactErr = contactProblems(f.contact);
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const original = { friendly_name: conn.name === conn.default_name ? "" : conn.name, purpose: conn.purpose, customer_notes: conn.customer_notes || "" };
      const changes = changedFields(original, f, ["friendly_name", "purpose", "customer_notes"]);
      const before = contactPayload(conn.customer_contact); const after = contactPayload(f.contact);
      if (JSON.stringify(before) !== JSON.stringify(after)) changes.customer_contact = after;
      if (f.new_number.trim()) changes.phone_number = f.new_number.trim();
      if (!Object.keys(changes).length) { onClose(); return; }
      const r = await patchConn(conn.connection_ref, { changes });
      onDone(r.requests?.length ? "Saved. Your number change was sent for review." : "Telephone line saved.");
    } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  const setC = (k) => (e) => setF((p) => ({ ...p, contact: { ...p.contact, [k]: e.target.value } }));
  return (
    <Modal title={`Manage ${conn.name}`} onClose={onClose}
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn primary disabled={busy || contactErr.length > 0} onClick={submit}>{busy ? "Saving…" : "Save"}</Btn></>}>
      <Field label="Name" hint={`Default: ${conn.default_name}`}><input className={inputCls} value={f.friendly_name} onChange={(e) => setF((p) => ({ ...p, friendly_name: e.target.value }))} placeholder="e.g. Fire Alarm Line 1" /></Field>
      <Field label="Purpose">
        <select className={inputCls} value={f.purpose} onChange={(e) => setF((p) => ({ ...p, purpose: e.target.value }))}>
          {PURPOSES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </Field>
      <Field label="Notes"><textarea rows={2} className={inputCls} value={f.customer_notes} onChange={(e) => setF((p) => ({ ...p, customer_notes: e.target.value }))} /></Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Point of contact"><input className={inputCls} value={f.contact.name || ""} onChange={setC("name")} /></Field>
        <Field label="Contact phone"><input className={inputCls} value={f.contact.phone || ""} onChange={setC("phone")} /></Field>
      </div>
      <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
        <Field label="Change the telephone number" hint="Number changes affect carrier service and E911, so they are reviewed before anything changes.">
          <input className={inputCls} value={f.new_number} onChange={(e) => setF((p) => ({ ...p, new_number: e.target.value }))} placeholder={conn.phone_number || ""} />
        </Field>
      </div>
      <Problems items={contactErr} />
      {err && <p className="text-[12px] text-red-700">{err}</p>}
    </Modal>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Data hook: the self-service workspace + the mutation helpers the modals use.
// ══════════════════════════════════════════════════════════════════════
export function useLocationWorkspace(locationRef) {
  const [ws, setWs] = useState(null);
  const [off, setOff] = useState(false);
  const enc = encodeURIComponent(locationRef);

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch(`/customer/locations/${enc}/workspace`);
      setWs(r.data); setOff(false);
    } catch (e) {
      if (e.status === 404) { setOff(true); setWs(null); }
    }
  }, [enc]);
  useEffect(() => { reload(); }, [reload]);

  const call = (method) => (path, body) => apiFetch(`/customer/locations/${enc}${path}`, { method, body: JSON.stringify(body) }).then((r) => r.data);
  const api = {
    post: call("POST"), patch: call("PATCH"), put: call("PUT"),
    patchConn: (ref, body) => apiFetch(`/customer/locations/${enc}/connections/${encodeURIComponent(ref)}`, { method: "PATCH", body: JSON.stringify(body) }).then((r) => r.data),
    requestAction: (ref, verb, notes) => apiFetch(`/customer/requests/${encodeURIComponent(ref)}/${verb}`, { method: "POST", body: JSON.stringify({ notes }) }),
  };
  return { ws, off, reload, api };
}

// The one place every self-service modal is mounted.  `modal` = { type, ... }.
export function LocationModals({ modal, ws, api, onClose, onDone }) {
  if (!modal || !ws) return null;
  switch (modal.type) {
    case "verify_e911": return <E911Wizard ws={ws} post={api.post} onClose={onClose} onDone={onDone} />;
    case "request": return <RequestForm ws={ws} initialType={modal.requestType} post={api.post} onClose={onClose} onDone={onDone} />;
    case "manage_location": return <LocationForm ws={ws} patch={api.patch} onClose={onClose} onDone={onDone} />;
    case "update_contacts": return <ContactsForm ws={ws} put={api.put} onClose={onClose} onDone={onDone} />;
    case "connection": return <ConnectionForm conn={modal.conn} patchConn={api.patchConn} onClose={onClose} onDone={onDone} />;
    default: return null;
  }
}
