import { useState, useEffect, useCallback } from "react";
import {
  Settings2, PhoneCall, ShieldCheck, PlusCircle, Repeat, AlertOctagon, Users, X,
  CheckCircle2, AlertTriangle, Clock, Edit3, History, ClipboardList, MapPin, LifeBuoy,
} from "lucide-react";
import { apiFetch } from "@/api/client";
import {
  visibleActions, CHANGE_REQUEST_TYPES, PURPOSES, CONTACT_ROLES, canVerifyE911,
  e911FormProblems, e911Tone, contactProblems, contactPayload, changedFields, requestTone,
  errorText,
} from "@/components/customer/selfService";

// ════════════════════════════════════════════════════════════════════
// LocationOperations — the customer's operations console for ONE location.
//
// Sourced from GET /customer/locations/{ref}/workspace (self-service, flag-gated:
// a 404 means the feature is off for this user and the component renders
// nothing, leaving the existing read-only workspace exactly as it was).
//
// Customer-owned details (names, purpose, notes, contacts) save directly.
// Anything that touches provisioning, identity or E911 is submitted as a
// request that the operations team reviews — the UI says so plainly.  Support
// stays available as a secondary escalation, never the primary path.
// ════════════════════════════════════════════════════════════════════

const TONE = {
  ok: "bg-emerald-50 border-emerald-200 text-emerald-800",
  action: "bg-amber-50 border-amber-200 text-amber-800",
  pending: "bg-blue-50 border-blue-200 text-blue-800",
  bad: "bg-red-50 border-red-200 text-red-800",
  muted: "bg-slate-50 border-slate-200 text-slate-600",
};
const STATUS_TONE = { Protected: "ok", "Attention Needed": "action", Critical: "bad" };
const ICONS = {
  manage_location: Settings2, manage_connections: PhoneCall, verify_e911: ShieldCheck,
  add_service: PlusCircle, service_change: Repeat, report_problem: AlertOctagon,
  update_contacts: Users,
};

const Pill = ({ tone = "muted", children }) => (
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

const Btn = ({ primary, disabled, onClick, children }) => (
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
        <Field label="Which connection? (optional)">
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
      onDone(r.request ? "Saved. Your address / store-number correction was sent for review." : "Location details saved.");
    } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  return (
    <Modal title="Manage Location" onClose={onClose}
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn primary disabled={busy} onClick={submit}>{busy ? "Saving…" : "Save"}</Btn></>}>
      <Field label="Location name (how your team refers to it)" hint={`Official record: ${ws.location.canonical_name}`}><input className={inputCls} value={f.display_name || ""} onChange={set("display_name")} /></Field>
      <Field label="Your reference / cost-center #"><input className={inputCls} value={f.customer_reference || ""} onChange={set("customer_reference")} /></Field>
      <Field label="Location notes"><textarea rows={3} className={inputCls} value={f.location_notes || ""} onChange={set("location_notes")} /></Field>
      <Field label="Access notes" hint="Gate codes and keys are best shared by phone, not stored here."><textarea rows={2} className={inputCls} value={f.access_notes || ""} onChange={set("access_notes")} /></Field>
      <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-2">
        <p className="text-[11.5px] text-slate-600">Wrong address or store number? These are part of the official record, so a correction is reviewed before it's applied.</p>
        <Field label="Correct address"><input className={inputCls} value={corr.address} onChange={(e) => setCorr((p) => ({ ...p, address: e.target.value }))} placeholder={ws.location.address || ""} /></Field>
        <Field label="Correct store number"><input className={inputCls} value={corr.store_number} onChange={(e) => setCorr((p) => ({ ...p, store_number: e.target.value }))} placeholder={ws.location.store_number || ""} /></Field>
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
      onDone(r.requests?.length ? "Saved. Your number change was sent for review." : "Connection saved.");
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
export default function LocationOperations({ locationRef }) {
  const [ws, setWs] = useState(null);
  const [off, setOff] = useState(false);
  const [modal, setModal] = useState(null);
  const [flash, setFlash] = useState(null);
  const [busyRef, setBusyRef] = useState(null);
  const enc = encodeURIComponent(locationRef);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch(`/customer/locations/${enc}/workspace`);
      setWs(r.data); setOff(false);
    } catch (e) {
      if (e.status === 404) setOff(true);
    }
  }, [enc]);
  useEffect(() => { load(); }, [load]);

  const call = (method) => (path, body) => apiFetch(`/customer/locations/${enc}${path}`, { method, body: JSON.stringify(body) }).then((r) => r.data);
  const post = call("POST"); const patch = call("PATCH"); const put = call("PUT");
  const patchConn = (ref, body) => apiFetch(`/customer/locations/${enc}/connections/${encodeURIComponent(ref)}`, { method: "PATCH", body: JSON.stringify(body) }).then((r) => r.data);
  const done = async (text) => { setModal(null); setFlash({ ok: true, text }); await load(); };

  const requestAction = async (ref, verb) => {
    setBusyRef(ref);
    try {
      const notes = verb === "respond" ? window.prompt("Your response to the operations team:") : null;
      if (verb === "respond" && !notes) return;
      await apiFetch(`/customer/requests/${encodeURIComponent(ref)}/${verb}`, { method: "POST", body: JSON.stringify({ notes }) });
      await done(verb === "cancel" ? "Request cancelled." : "Response sent.");
    } catch (x) { setFlash({ ok: false, text: errorText(x) }); } finally { setBusyRef(null); }
  };

  if (off || !ws) return null;
  const caps = ws.capabilities || {};
  const actions = visibleActions(caps);
  const e = ws.e911;
  const open = (key) => {
    const a = actions.find((x) => x.key === key);
    if (key === "manage_connections") { document.getElementById("ops-connections")?.scrollIntoView({ behavior: "smooth" }); return; }
    setModal(a?.requestType ? { type: "request", requestType: a.requestType } : { type: key });
  };

  return (
    <div className="space-y-4">
      {/* Outstanding actions + primary actions */}
      <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-3">
        <div className="flex items-center gap-2"><ClipboardList className="w-4 h-4 text-slate-600" /><h3 className="text-[13px] font-semibold text-slate-900">Manage this location</h3></div>
        {ws.location.outstanding_actions.length > 0 ? (
          <ul className="space-y-1.5">
            {ws.location.outstanding_actions.map((a, i) => (
              <li key={i} className="flex items-center gap-2 text-[12.5px] text-slate-700">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                <span className="flex-1">{a.label}<span className="text-slate-400"> — {a.reason}</span></span>
                {a.action === "verify_e911" && canVerifyE911(caps, e) && <button className="text-[11.5px] font-medium text-slate-800 underline" onClick={() => setModal({ type: "verify_e911" })}>Start</button>}
                {a.action === "update_contacts" && caps.can_manage_contacts && <button className="text-[11.5px] font-medium text-slate-800 underline" onClick={() => setModal({ type: "update_contacts" })}>Add</button>}
                {a.action === "respond_request" && caps.can_submit_requests && <button className="text-[11.5px] font-medium text-slate-800 underline" onClick={() => requestAction(a.request_ref, "respond")}>Respond</button>}
              </li>
            ))}
          </ul>
        ) : <p className="text-[12px] text-emerald-700 flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5" />Nothing needs your attention here.</p>}
        {actions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {actions.map((a) => {
              const Icon = ICONS[a.key];
              const disabled = a.key === "verify_e911" && !canVerifyE911(caps, e);
              return (
                <button key={a.key} type="button" disabled={disabled} onClick={() => open(a.key)}
                  className="inline-flex items-center gap-1.5 text-[11.5px] font-medium px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-100 disabled:opacity-40">
                  {Icon && <Icon className="w-3.5 h-3.5" />}{a.label}
                </button>
              );
            })}
          </div>
        )}
        {flash && <p className={`text-[12px] ${flash.ok ? "text-emerald-700" : "text-red-700"}`}>{flash.text}</p>}
      </div>

      {/* E911 */}
      <div className="rounded-xl border border-slate-200 p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-slate-600" /><h3 className="text-[13px] font-semibold text-slate-900">E911</h3></div>
          <Pill tone={e911Tone(e.state)}>{e.label}</Pill>
        </div>
        <p className="text-[12px] text-slate-600 mt-2 flex items-start gap-1.5"><MapPin className="w-3.5 h-3.5 mt-0.5 text-slate-400" />{e.dispatch_address || "No dispatch address on file"}</p>
        {e.provenance?.verification_method === "customer_attestation" && (
          <p className="text-[11px] text-slate-400 mt-1">Confirmed by {e.provenance.attested_by} · awaiting official verification</p>
        )}
        {canVerifyE911(caps, e) && <div className="mt-3"><Btn primary onClick={() => setModal({ type: "verify_e911" })}>Verify E911</Btn></div>}
      </div>

      {/* Connections */}
      <div id="ops-connections" className="rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2"><PhoneCall className="w-4 h-4 text-slate-600" /><h3 className="text-[13px] font-semibold text-slate-900">Life-Safety Connections</h3><span className="text-[11px] text-slate-400">{ws.connections.length}</span></div>
        {ws.connections.length === 0 && <p className="px-4 py-4 text-[12px] text-slate-400">No connections on file yet.</p>}
        <div className="divide-y divide-slate-100">
          {ws.connections.map((c) => (
            <div key={c.connection_ref} className="px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-slate-900">{c.name}</p>
                  <p className="text-[12px] text-slate-600 tabular-nums">{c.phone_number || "No number on file"}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">{c.purpose_label}{c.device_association ? ` · ${c.device_association}` : ""}{c.e911_state ? ` · E911: ${c.e911_state}` : ""}</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Pill tone={STATUS_TONE[c.status?.status] || "muted"}>{c.status?.status === "Protected" ? "Protected" : c.status?.status === "Unknown" ? "Status being confirmed" : c.status?.status}</Pill>
                  {caps.can_manage_location && <button className="text-[11px] text-slate-600 hover:text-slate-900 inline-flex items-center gap-1" onClick={() => setModal({ type: "connection", conn: c })}><Edit3 className="w-3 h-3" />Manage</button>}
                </div>
              </div>
              {c.open_requests.length > 0 && <p className="text-[11px] text-blue-700 mt-1 flex items-center gap-1"><Clock className="w-3 h-3" />{c.open_requests.map((r) => `${r.request_label}: ${r.status_label}`).join(" · ")}</p>}
              {c.customer_notes && <p className="text-[11.5px] text-slate-500 mt-1">{c.customer_notes}</p>}
            </div>
          ))}
        </div>
      </div>

      {/* Contacts + notes */}
      <div className="rounded-xl border border-slate-200 p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2"><Users className="w-4 h-4 text-slate-600" /><h3 className="text-[13px] font-semibold text-slate-900">Contacts</h3></div>
          {caps.can_manage_contacts && <button className="text-[11.5px] text-slate-600 hover:text-slate-900" onClick={() => setModal({ type: "update_contacts" })}>Edit</button>}
        </div>
        {CONTACT_ROLES.map((r) => {
          const c = ws.contacts.contacts[r.value];
          return (
            <div key={r.value} className="text-[12px]">
              <span className="text-slate-500">{r.label}: </span>
              {c ? <span className="text-slate-800">{[c.name, c.title, c.phone, c.email].filter(Boolean).join(" · ")}</span> : <span className="text-amber-700">Not provided</span>}
            </div>
          );
        })}
        {(ws.profile.location_notes || ws.profile.access_notes) && (
          <div className="pt-2 border-t border-slate-100 space-y-1">
            {ws.profile.location_notes && <p className="text-[12px] text-slate-700"><span className="text-slate-500">Notes: </span>{ws.profile.location_notes}</p>}
            {ws.profile.access_notes && <p className="text-[12px] text-slate-700"><span className="text-slate-500">Access: </span>{ws.profile.access_notes}</p>}
          </div>
        )}
      </div>

      {/* Requests */}
      {caps.can_view_requests && (
        <div className="rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2"><Repeat className="w-4 h-4 text-slate-600" /><h3 className="text-[13px] font-semibold text-slate-900">Requests</h3></div>
          {ws.requests.length === 0 ? <p className="px-4 py-4 text-[12px] text-slate-400">No requests yet.</p> : (
            <div className="divide-y divide-slate-100">
              {ws.requests.map((r) => (
                <div key={r.request_ref} className="px-4 py-2.5 flex items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-[12.5px] text-slate-800">{r.request_label}</p>
                    <p className="text-[11px] text-slate-400">{new Date(r.requested_at).toLocaleDateString()} · {r.requested_by}{r.resolution_notes ? ` · ${r.resolution_notes}` : ""}</p>
                  </div>
                  <Pill tone={requestTone(r.status)}>{r.status_label}</Pill>
                  {caps.can_submit_requests && r.status === "waiting_customer" && <button disabled={busyRef === r.request_ref} className="text-[11px] underline text-slate-700" onClick={() => requestAction(r.request_ref, "respond")}>Respond</button>}
                  {caps.can_submit_requests && ["submitted", "under_review", "waiting_customer"].includes(r.status) && <button disabled={busyRef === r.request_ref} className="text-[11px] text-slate-500 hover:text-slate-800" onClick={() => requestAction(r.request_ref, "cancel")}>Cancel</button>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Activity */}
      <div className="rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2"><History className="w-4 h-4 text-slate-600" /><h3 className="text-[13px] font-semibold text-slate-900">Activity</h3></div>
        {ws.activity.length === 0 ? <p className="px-4 py-4 text-[12px] text-slate-400">No activity yet.</p> : (
          <div className="divide-y divide-slate-100">
            {ws.activity.map((a, i) => (
              <div key={i} className="px-4 py-2 flex items-center gap-2 text-[12px]">
                <span className="text-slate-800 flex-1">{a.by} · {a.summary}</span>
                <span className="text-[11px] text-slate-400 tabular-nums">{a.when ? new Date(a.when).toLocaleString() : ""}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Support — a secondary escalation, not the primary path */}
      <p className="text-[11px] text-slate-400 flex items-center gap-1.5"><LifeBuoy className="w-3 h-3" />Urgent or unsure? <a className="underline hover:text-slate-600" href="mailto:support@manleysolutions.com">Contact support</a></p>

      {modal?.type === "verify_e911" && <E911Wizard ws={ws} post={post} onClose={() => setModal(null)} onDone={done} />}
      {modal?.type === "request" && <RequestForm ws={ws} initialType={modal.requestType} post={post} onClose={() => setModal(null)} onDone={done} />}
      {modal?.type === "manage_location" && <LocationForm ws={ws} patch={patch} onClose={() => setModal(null)} onDone={done} />}
      {modal?.type === "update_contacts" && <ContactsForm ws={ws} put={put} onClose={() => setModal(null)} onDone={done} />}
      {modal?.type === "connection" && <ConnectionForm conn={modal.conn} patchConn={patchConn} onClose={() => setModal(null)} onDone={done} />}
    </div>
  );
}
