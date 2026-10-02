import { useState, useEffect, useMemo, useRef } from "react";
import {
  X, PhoneCall, MapPin, Cpu, Wifi, WifiOff, ShieldCheck, ClipboardCheck, LifeBuoy, Link2,
  Check, ChevronRight, ChevronDown, Users, Send, Plus, Edit3, CheckCircle2, MoreHorizontal,
} from "lucide-react";
import { apiFetch } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { useLocationWorkspace, LocationModals, Pill, Btn } from "@/components/customer/LocationOperations";
import {
  LOCATION_TABS, locationActions, locationOperational, operationalView, statusWord,
  groupConnectionsByService, canVerifyE911, contributionControl, readinessProgress,
  TWIN_LABELS, CONTACT_ROLES, requestTone, errorText, connectionServiceLabel,
  activityText, customerLocationName, locationTrue911Work, CUSTOMER_NOUNS,
} from "@/components/customer/selfService";
import { motion, useReducedMotion } from "framer-motion";
import { e911Display } from "@/components/customer/commandCenter";

// ════════════════════════════════════════════════════════════════════
// LocationCommandCenter — one location, in four places:
//
//   Overview    — who/where it is, its operational status, what's needed, requests
//   Connections — Service → Connection → Device (customer-readable first)
//   Compliance  — E911, inspections, emergency procedures
//   Records     — contacts, notes, activity (documents / photos / billing: soon)
//
// Each subject lives in exactly one place; the header carries at most two
// primary actions (Confirm E911 when there is something to confirm, Manage
// Location) plus a "More" menu.  Customer trust rule (D-022): unknown or
// incomplete evidence is neutral — never red, never green.  No blended health
// score is shown; data completeness is never presented as service health.
// ════════════════════════════════════════════════════════════════════

const DOT = {
  good: "bg-emerald-500", problem: "bg-amber-500", urgent: "bg-red-500",
  neutral: "bg-white border border-slate-400",
};
const TEXT = { good: "text-emerald-800", problem: "text-amber-800", urgent: "text-red-700", neutral: "text-slate-700" };
// E911 pill tone from the Command Center display policy: nothing E911 is green
// until verification is provider-backed (commandCenter.e911Display).
const E911_PILL = { good: "good", attention: "problem", critical: "urgent", working: "neutral", unknown: "neutral", neutral: "neutral" };

function Block({ title, icon: Icon, count, action, children }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        {Icon && <Icon className="w-3.5 h-3.5 text-slate-400" />}
        <h3 className="text-[11px] font-semibold text-slate-600 uppercase tracking-[0.08em]">{title}</h3>
        {count != null && <span className="text-[10.5px] text-slate-400 tabular-nums">{count}</span>}
        <div className="ml-auto">{action}</div>
      </div>
      {children}
    </section>
  );
}

const Muted = ({ children }) => <p className="text-[12px] text-slate-400">{children}</p>;

// ── Older append-only contributions (used where no governed flow replaces them) ──
const CONTRIB = {
  contact:         { label: "Add Contact",     fields: [["name", "Name"], ["phone", "Phone"], ["email", "Email"], ["role", "Role (e.g. Facilities)"]], noteLabel: "Note (optional)" },
  inspection:      { label: "Record Inspection", fields: [["date", "Date"], ["kind", "Inspection type"]], noteLabel: "Findings / notes" },
  photo:           { label: "Upload Photo",    fields: [], noteLabel: "" },
  document:        { label: "Upload Document", fields: [], noteLabel: "" },
  procedure:       { label: "Add Procedure",   fields: [["title", "Procedure title"]], noteLabel: "Procedure steps" },
  note:            { label: "Add Note",        fields: [], noteLabel: "Note", noteOnly: true },
  service_request: { label: "Create Request",  fields: [["summary", "What do you need?"]], noteLabel: "Details" },
};

function Contribute({ type, canContribute, selfService, onSubmit }) {
  const cfg = CONTRIB[type];
  const control = contributionControl(type, { selfService });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);
  if (!canContribute || !cfg || control === "hidden" || control === "replaced") return null;
  if (control === "coming_soon") {
    // Not built yet (no file storage): visibly disabled; cannot open a form or submit.
    return (
      <span aria-disabled="true" title="Coming soon"
        className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-lg border border-slate-100 text-slate-300 cursor-not-allowed select-none">
        <Plus className="w-3 h-3" />{cfg.label}
        <span className="text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400 bg-slate-100 rounded px-1 py-px">Soon</span>
      </span>
    );
  }
  const submit = async () => {
    setBusy(true); setFlash(null);
    const payload = {};
    for (const [k] of cfg.fields) if (f[k]) payload[k] = f[k];
    try {
      const res = await onSubmit(type, payload, note);
      setFlash({ ok: true, text: res?.message || "Saved" });
      setOpen(false); setF({}); setNote("");
    } catch (e) {
      setFlash({ ok: false, text: e.message || "Could not submit — please try again." });
    } finally { setBusy(false); }
  };
  if (!open) {
    return (
      <div className="text-right">
        <button onClick={() => { setOpen(true); setFlash(null); }}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50">
          <Plus className="w-3 h-3" />{cfg.label}
        </button>
        {flash && <p className={`mt-1 text-[11px] ${flash.ok ? "text-emerald-700" : "text-red-600"}`}>{flash.text}</p>}
      </div>
    );
  }
  const inputCls = "w-full px-2.5 py-1.5 text-[12px] border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-300";
  return (
    <div className="mt-2 rounded-lg border border-slate-200 p-3 space-y-2 text-left">
      {cfg.fields.map(([k, label]) => (
        <input key={k} type="text" aria-label={label} placeholder={label} value={f[k] || ""}
          onChange={(e) => setF((prev) => ({ ...prev, [k]: e.target.value }))} className={inputCls} />
      ))}
      <textarea aria-label={cfg.noteLabel} placeholder={cfg.noteLabel} rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} />
      <div className="flex gap-2">
        <button onClick={submit} disabled={busy || (cfg.noteOnly && !note)}
          className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50">
          <Send className="w-3.5 h-3.5" />Save
        </button>
        <button onClick={() => { setOpen(false); setF({}); setNote(""); }} disabled={busy}
          className="text-[11.5px] px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50">Cancel</button>
      </div>
    </div>
  );
}

function Pending({ items, render }) {
  if (!items.length) return null;
  return (
    <div className="space-y-1">
      {items.map((c, i) => (
        <div key={c.contribution_id || i} className="text-[11.5px] rounded-lg border border-slate-200 px-2.5 py-1.5">
          <span className="text-slate-700">{render(c)}</span>
          <span className="block text-[10px] text-slate-400">{c.status === "recorded" ? "Recorded" : "Awaiting review"}{c.when ? ` · ${c.when.slice(0, 10)}` : ""}{c.by ? ` · ${c.by}` : ""}</span>
        </div>
      ))}
    </div>
  );
}

// ── Header "More" menu ───────────────────────────────────────────────
function MoreMenu({ items, onPick }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  if (!items.length) return null;
  return (
    <div className="relative" ref={ref}>
      <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-[12px] font-medium px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50">
        <MoreHorizontal className="w-3.5 h-3.5" />More<ChevronDown className="w-3 h-3" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-1 w-56 bg-white border border-slate-200 rounded-lg shadow-lg z-20 py-1">
          {items.map((a) => (
            <button key={a.key} role="menuitem" type="button" onClick={() => { setOpen(false); onPick(a); }}
              className="w-full text-left px-3 py-1.5 text-[12.5px] text-slate-700 hover:bg-slate-50">{a.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
export default function LocationCommandCenter({ locationRef, locationName, intent, onClose }) {
  const { can } = useAuth();
  const canSubmitLegacyE911 = typeof can === "function" && can("CUSTOMER_SUBMIT_E911_REVIEW");
  const canContribute = typeof can === "function" && can("CUSTOMER_CONTRIBUTE");
  const { ws, reload, api } = useLocationWorkspace(locationRef);
  const caps = useMemo(() => ws?.capabilities || {}, [ws]);
  const selfServiceOn = Boolean(caps.enabled);

  const [d, setD] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("overview");
  const [modal, setModal] = useState(null);
  const [flash, setFlash] = useState(null);
  const [copied, setCopied] = useState(false);
  const [legacyForm, setLegacyForm] = useState(null);   // legacy E911 correction (self-service off)
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef(null);
  const reduceMotion = useReducedMotion();

  // Accessibility: focus moves into the record on open and returns to whatever
  // opened it on close; Escape closes it — unless a dialog is open on top of it.
  useEffect(() => {
    const opener = document.activeElement;
    dialogRef.current?.focus({ preventScroll: true });
    return () => { if (opener && typeof opener.focus === "function") opener.focus({ preventScroll: true }); };
  }, []);
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" && !modal) onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [modal, onClose]);

  const enc = encodeURIComponent(locationRef);
  const get = (p) => apiFetch(`/customer/locations/${enc}${p}`).then((r) => r.data).catch(() => null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const detail = await apiFetch(`/customer/locations/${enc}`).then((r) => r.data);
        const [services, e911, timeline, contacts, inspections, health, review, contributions] = await Promise.all([
          get("/services"), get("/e911"), get("/timeline"), get("/contacts"),
          get("/inspections"), get("/health"), get("/e911/review-status"), get("/contributions"),
        ]);
        if (alive) setD({ detail, services, e911, timeline, contacts, inspections, health, review, contributions });
      } catch (err) {
        if (alive) setError(err.message || "Unable to load this location");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [locationRef]);

  // Opened from an Action Center row: go straight to the task, once, and only
  // when it is available (never Confirm E911 on a record with nothing to confirm).
  const intentDone = useRef(false);
  useEffect(() => {
    if (!ws || !intent || intentDone.current) return;
    intentDone.current = true;
    if (intent === "verify_e911") {
      setTab("compliance");
      if (canVerifyE911(caps, ws.e911)) setModal({ type: "verify_e911" });
    } else if (intent === "update_contacts") {
      setTab("records");
      if (caps.can_manage_contacts) setModal({ type: "update_contacts" });
    }
  }, [ws, intent, caps]);

  const submitContribution = async (type, payload, note) => {
    const res = await apiFetch(`/customer/locations/${enc}/contributions`, {
      method: "POST", body: JSON.stringify({ type, payload: payload || {}, note: note || null }),
    }).then((r) => r.data);
    const [c, h] = await Promise.all([get("/contributions"), get("/health")]);
    setD((prev) => ({ ...prev, contributions: c, health: h }));
    return res;
  };

  const done = async (text) => {
    setModal(null); setFlash({ ok: true, text });
    await reload();
    const h = await get("/health");
    setD((prev) => ({ ...prev, health: h }));
  };

  const requestAction = async (ref, verb) => {
    const notes = verb === "respond" ? window.prompt("Your response to the operations team:") : null;
    if (verb === "respond" && !notes) return;
    try { await api.requestAction(ref, verb, notes); await done(verb === "cancel" ? "Request cancelled." : "Response sent."); }
    catch (x) { setFlash({ ok: false, text: errorText(x) }); }
  };

  // Legacy E911 confirm/correction — only when self-service is OFF (otherwise
  // the single Confirm E911 flow covers confirmation AND corrections).
  const legacyConfirm = async () => {
    setBusy(true); setFlash(null);
    try {
      await apiFetch(`/customer/locations/${enc}/e911/confirm`, { method: "POST", body: JSON.stringify({}) });
      setFlash({ ok: true, text: "Thank you — your confirmation was submitted." });
      const r = await get("/e911/review-status"); setD((p) => ({ ...p, review: r }));
    } catch (e) { setFlash({ ok: false, text: e.message || "Could not submit — please try again." }); } finally { setBusy(false); }
  };
  const legacyCorrection = async () => {
    setBusy(true); setFlash(null);
    try {
      const f = legacyForm || {};
      await apiFetch(`/customer/locations/${enc}/e911/correction-request`, {
        method: "POST",
        body: JSON.stringify({ corrected_address: f.address || null, suite: f.suite || null, floor: f.floor || null,
          unit: null, callback_number: f.callback || null, service_identifier: null, note: f.note || null }),
      });
      setLegacyForm(null); setFlash({ ok: true, text: "Correction submitted — under review." });
      const r = await get("/e911/review-status"); setD((p) => ({ ...p, review: r }));
    } catch (e) { setFlash({ ok: false, text: e.message || "Could not submit — please try again." }); } finally { setBusy(false); }
  };

  const { detail, services, e911, timeline, contacts, inspections, health, review, contributions } = d;
  const contribOf = (t) => (contributions?.contributions || []).filter((c) => c.type === t);
  const svcList = useMemo(() => services?.services || [], [services]);
  const groups = useMemo(() => groupConnectionsByService(svcList, ws?.connections || []), [svcList, ws]);

  // Operational status (evidence-based; neutral when unknown).
  const op = ws?.location?.operational_state ? operationalView(ws.location.operational_state)
    : locationOperational(detail || {});
  const monitoredSvcs = ws?.location?.monitored_service_count
    ?? svcList.filter((s) => s.status?.status === "Protected").length;
  const connCount = ws?.location?.connection_count ?? null;
  // rawLabel keeps the API's word for logic; label/tone are the display policy.
  const e911Raw = ws?.e911 ? ws.e911.state : (review?.state || detail?.emergency_address_state || "Verification Pending");
  const e911View = e911Display(e911Raw);
  const e911State = {
    rawLabel: ws?.e911 ? ws.e911.label : e911Raw,
    label: e911View.label,
    tone: E911_PILL[e911View.token] || "neutral",
    reason: e911Raw === "verified" || e911Raw === "Verified"
      ? "An E911 record is on file. Verified status appears only after official E911 verification."
      : ws?.e911?.reason,
  };
  const actions = locationActions(ws, caps);
  const title = customerLocationName(ws?.location?.display_name || detail?.display_name || detail?.location || locationName);
  const true911Work = locationTrue911Work(ws, op);
  const address = ws?.location?.address || detail?.service_address;
  const openRequests = (ws?.requests || []).filter((r) => r.open);

  const pick = (a) => {
    if (a.tab) setTab(a.tab);
    if (a.requestType) setModal({ type: "request", requestType: a.requestType });
    else setModal({ type: a.key });
  };

  const shareLink = () => {
    const url = `${window.location.origin}${window.location.pathname}?location=${encodeURIComponent(locationRef)}`;
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); });
  };

  // Activity: self-service events + real E911 record activity, newest first.
  const activity = [
    ...(ws?.activity || []).map((a) => ({ when: a.when, text: `${a.by} · ${activityText(a)}` })),
    ...((timeline?.timeline || []).map((t) => ({ when: t.when, text: `${t.by} · ${t.title}` }))),
  ].sort((a, b) => String(b.when || "").localeCompare(String(a.when || "")));

  return (
    <div className="fixed inset-0 z-[1000] flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-slate-900/30" />
      <motion.div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title || "Location"}
        initial={reduceMotion ? false : { x: 32, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.2, ease: "easeOut" }}
        className="t911-customer relative w-full max-w-2xl bg-white h-full shadow-xl overflow-y-auto outline-none" onClick={(e) => e.stopPropagation()}>

        {/* ── Header: identity, evidence-based status, ≤2 primary actions, tabs ── */}
        <div className="px-6 pt-4 border-b border-slate-200 sticky top-0 bg-white z-10">
          <div className="flex items-center justify-between">
            <nav className="flex items-center gap-1 text-[11px] text-slate-400 min-w-0">
              <span>Portfolio</span><ChevronRight className="w-3 h-3" />
              <span className="text-slate-600 truncate">{title}</span>
            </nav>
            <div className="flex items-center gap-1">
              <button onClick={shareLink} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" aria-label="Copy link to this location">
                {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Link2 className="w-4 h-4" />}
              </button>
              <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" aria-label="Close"><X className="w-4 h-4" /></button>
            </div>
          </div>

          <h2 className="text-[17px] font-semibold text-slate-900 mt-1 truncate">{title}</h2>
          {detail && (
            <div className="mt-1.5 space-y-1">
              <p className="flex items-center gap-2 text-[12.5px]">
                <span className={`w-2 h-2 rounded-full ${DOT[op.tone]}`} aria-hidden="true" />
                <span className={`font-medium ${TEXT[op.tone]}`}>{op.tone === "good" ? op.summary.replace(/\.$/, "") : op.label}</span>
                {op.tone !== "good" && <span className="text-slate-500">— {op.summary}</span>}
              </p>
              <p className="text-[12px] text-slate-500">
                {monitoredSvcs > 0 ? `${monitoredSvcs} monitored life-safety service${monitoredSvcs === 1 ? "" : "s"}` : `${svcList.length} life-safety service${svcList.length === 1 ? "" : "s"}`}
                {connCount != null && ` · ${connCount} telephone line${connCount === 1 ? "" : "s"}`}
                <span className="mx-1.5">·</span>E911: <span className="font-medium text-slate-700">{e911State.label}</span>
              </p>
            </div>
          )}

          {(actions.primary.length > 0 || actions.more.length > 0) && (
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {actions.primary.map((a, i) => (
                <Btn key={a.key} primary={i === 0} onClick={() => pick(a)}>{a.label}</Btn>
              ))}
              <MoreMenu items={actions.more} onPick={pick} />
            </div>
          )}
          {flash && <p role="status" className={`mt-2 text-[12px] ${flash.ok ? "text-emerald-700" : "text-red-700"}`}>{flash.text}</p>}

          <div role="tablist" aria-label="Location sections" className="flex gap-1 mt-3 -mb-px">
            {LOCATION_TABS.map((t) => (
              <button key={t.key} role="tab" type="button" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                className={`px-3 py-2 text-[12.5px] font-medium border-b-2 ${tab === t.key ? "border-slate-800 text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="px-6 py-5 space-y-6" role="tabpanel">
          {loading && <Muted>Loading…</Muted>}
          {error && <p className="text-xs text-red-600">{error}</p>}

          {detail && tab === "overview" && (
            <>
              <Block title="Location" icon={MapPin}>
                <dl className="grid grid-cols-[120px_1fr] gap-y-1.5 text-[12.5px]">
                  <dt className="text-slate-500">Address</dt><dd className="text-slate-800">{address || "Not yet on file"}</dd>
                  {(ws?.location?.building_type || detail.building_category) && (<><dt className="text-slate-500">Type</dt><dd className="text-slate-800">{ws?.location?.building_type || detail.building_category}</dd></>)}
                  {(ws?.location?.store_number || detail.store_number) && (<><dt className="text-slate-500">{CUSTOMER_NOUNS.locationId}</dt><dd className="text-slate-800">{ws?.location?.store_number || detail.store_number}</dd></>)}
                  {ws?.location?.device_count != null && (<><dt className="text-slate-500">Devices</dt><dd className="text-slate-800">{ws.location.device_count}</dd></>)}
                </dl>
              </Block>

              <Block title="Status" icon={ShieldCheck}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="rounded-lg border border-slate-200 px-3 py-2">
                    <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.07em]">Service status</p>
                    <p className={`text-[13px] font-medium ${TEXT[op.tone]}`}>{op.label}</p>
                    <p className="text-[11px] text-slate-500">{op.summary}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 px-3 py-2">
                    <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.07em]">E911</p>
                    <p className="text-[13px] font-medium text-slate-800">{e911State.label}</p>
                    <p className="text-[11px] text-slate-500">{e911State.reason || "Verification is completed by the verification team."}</p>
                  </div>
                  {health?.maturity && (
                    <div className="rounded-lg border border-slate-200 px-3 py-2 sm:col-span-2">
                      <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.07em]">Portfolio setup · {TWIN_LABELS.readinessTitle}</p>
                      <p className="text-[13px] font-medium text-slate-800">{health.maturity.tier} · {readinessProgress(health.maturity.met, health.maturity.total)}</p>
                      {(health.maturity.next_steps || []).length > 0 && <p className="text-[11px] text-slate-500">Next: {health.maturity.next_steps.join(", ")}</p>}
                    </div>
                  )}
                </div>
              </Block>

              {selfServiceOn && (
                <Block title="Your to-do here" icon={CheckCircle2}>
                  {(ws.location.outstanding_actions || []).length === 0
                    ? <p className="text-[12px] text-slate-600">Nothing needs you here right now.</p>
                    : (
                      <ul className="space-y-1">
                        {ws.location.outstanding_actions.map((a, i) => (
                          <li key={i} className="flex items-center gap-2 text-[12.5px] text-slate-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-400" aria-hidden="true" />
                            <span className="flex-1">{a.label}<span className="text-slate-400"> — {a.reason}</span></span>
                            {a.action === "verify_e911" && <button className="text-[11.5px] underline text-slate-600" onClick={() => setTab("compliance")}>Go to Compliance</button>}
                            {a.action === "update_contacts" && <button className="text-[11.5px] underline text-slate-600" onClick={() => setTab("records")}>Go to Records</button>}
                            {a.action === "respond_request" && caps.can_submit_requests && <button className="text-[11.5px] underline text-slate-600" onClick={() => requestAction(a.request_ref, "respond")}>Respond</button>}
                          </li>
                        ))}
                      </ul>
                    )}
                  {true911Work.length > 0 && (
                    <p className="text-[11.5px] text-slate-500 mt-2">True911 is working on: {true911Work.join(" · ")}. No action is needed from you.</p>
                  )}
                </Block>
              )}

              {selfServiceOn && caps.can_view_requests ? (
                <Block title="Requests" icon={Send} count={openRequests.length || null}>
                  {(ws.requests || []).length === 0 ? <Muted>No requests yet.</Muted> : (
                    <div className="rounded-lg border border-slate-200 divide-y divide-slate-100">
                      {ws.requests.slice(0, 8).map((r) => (
                        <div key={r.request_ref} className="px-3 py-2 flex items-center gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-[12.5px] text-slate-800">{r.request_label}</p>
                            <p className="text-[11px] text-slate-400">{new Date(r.requested_at).toLocaleDateString()} · {r.requested_by}{r.resolution_notes ? ` · ${r.resolution_notes}` : ""}</p>
                          </div>
                          <Pill tone={requestTone(r.status)}>{r.status_label}</Pill>
                          {caps.can_submit_requests && r.status === "waiting_customer" && <button className="text-[11px] underline text-slate-700" onClick={() => requestAction(r.request_ref, "respond")}>Respond</button>}
                          {caps.can_submit_requests && ["submitted", "under_review", "waiting_customer"].includes(r.status) && <button className="text-[11px] text-slate-500 hover:text-slate-800" onClick={() => requestAction(r.request_ref, "cancel")}>Cancel</button>}
                        </div>
                      ))}
                    </div>
                  )}
                </Block>
              ) : (
                <Block title="Service requests" icon={Send} action={<Contribute type="service_request" canContribute={canContribute} selfService={selfServiceOn} onSubmit={submitContribution} />}>
                  {contribOf("service_request").length === 0 ? <Muted>No open service requests.</Muted>
                    : <Pending items={contribOf("service_request")} render={(c) => c.payload?.summary || c.note || "Service request"} />}
                </Block>
              )}
            </>
          )}

          {detail && tab === "connections" && (
            <Block title="Services, telephone lines and devices" icon={PhoneCall}
              count={ws?.location ? `${ws.location.service_count} service${ws.location.service_count === 1 ? "" : "s"} · ${ws.location.connection_count} telephone line${ws.location.connection_count === 1 ? "" : "s"}` : null}>
              {groups.length === 0 ? <Muted>No life-safety services on file yet.</Muted> : (
                <div className="space-y-3">
                  {groups.map((g) => {
                    const sw = g.status ? statusWord(g.status.status) : null;
                    const legacyPhones = !ws && g.service ? (svcList.find((s) => s.service_ref === g.key)?.phone_numbers || []) : [];
                    return (
                      <div key={g.key} className="rounded-lg border border-slate-200 overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-2 bg-slate-50/70">
                          <div>
                            <p className="text-[13px] font-semibold text-slate-900">{g.service || connectionServiceLabel({ service: null })}</p>
                            {!g.service && <p className="text-[11px] text-slate-500">Known numbers True911 is still linking to a service.</p>}
                          </div>
                          {sw && <Pill tone={sw.tone}>{sw.label}</Pill>}
                        </div>
                        {g.connections.length > 0 && (
                          <div className="divide-y divide-slate-100">
                            {g.connections.map((c) => {
                              const cw = statusWord(c.status?.status);
                              return (
                                <div key={c.connection_ref} className="px-3 py-2 flex items-start gap-2">
                                  <PhoneCall className="w-3.5 h-3.5 text-slate-400 mt-0.5 flex-shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <p className="text-[12.5px] text-slate-900">{c.name} <span className="text-slate-500 tabular-nums">· {c.phone_number || "No number on file"}</span></p>
                                    <p className="text-[11px] text-slate-400">Purpose: {c.purpose_label}{c.customer_notes ? ` · ${c.customer_notes}` : ""}</p>
                                    {c.open_requests.length > 0 && <p className="text-[11px] text-slate-600 mt-0.5">{c.open_requests.map((r) => `${r.request_label}: ${r.status_label}`).join(" · ")}</p>}
                                  </div>
                                  {!g.service && <Pill tone={cw.tone}>{cw.label}</Pill>}
                                  {caps.can_manage_location && (
                                    <button className="text-[11px] text-slate-600 hover:text-slate-900 inline-flex items-center gap-1" onClick={() => setModal({ type: "connection", conn: c })}>
                                      <Edit3 className="w-3 h-3" />Manage
                                    </button>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                        {legacyPhones.length > 0 && <p className="border-t border-slate-100 px-3 py-1.5 text-[11.5px] text-slate-600">{legacyPhones.join(", ")}</p>}
                        {g.equipment.length > 0 && (
                          <div className="border-t border-slate-100 px-3 py-1.5 space-y-1">
                            {g.equipment.map((eq, i) => (
                              <div key={i} className="flex items-center justify-between text-[11.5px]">
                                <span className="inline-flex items-center gap-1.5 text-slate-600 min-w-0"><Cpu className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" /><span className="truncate">{eq.equipment}{eq.model ? ` · ${eq.model}` : ""}</span></span>
                                <span className={`inline-flex items-center gap-1 flex-shrink-0 ${eq.health === "Online" ? "text-emerald-700" : "text-slate-500"}`}>{eq.health === "Online" ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}{eq.health}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </Block>
          )}

          {detail && tab === "compliance" && (
            <>
              <Block title="E911 emergency record" icon={ShieldCheck}>
                <div className="rounded-lg border border-slate-200 p-3 space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[12.5px] text-slate-700 flex items-start gap-1.5"><MapPin className="w-3.5 h-3.5 mt-0.5 text-slate-400" />{ws?.e911?.dispatch_address || e911?.emergency_dispatch_address || "No dispatch address on file yet"}</p>
                    <Pill tone={e911State.tone}>{e911State.label}</Pill>
                  </div>
                  {e911State.reason && <p className="text-[11.5px] text-slate-500">{e911State.reason}</p>}
                  {ws?.e911?.provenance?.verification_method === "customer_attestation" && (
                    <p className="text-[11px] text-slate-400">Confirmed by {ws.e911.provenance.attested_by} · awaiting official verification</p>
                  )}
                  {selfServiceOn && canVerifyE911(caps, ws.e911) && (
                    <p className="text-[11.5px] text-slate-600">Use <strong>Confirm E911</strong> at the top to review the address and numbers — you can correct anything there.</p>
                  )}
                  {/* Self-service OFF only: the older confirm / request-correction controls. */}
                  {!selfServiceOn && canSubmitLegacyE911 && e911State.rawLabel !== "Verified" && (
                    legacyForm == null ? (
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Btn disabled={busy} onClick={legacyConfirm}>Confirm emergency record</Btn>
                        <Btn disabled={busy} onClick={() => setLegacyForm({})}>Request correction</Btn>
                      </div>
                    ) : (
                      <div className="space-y-2 pt-1">
                        {[["address", "Corrected address"], ["suite", "Suite / unit"], ["floor", "Floor"], ["callback", "Callback number"], ["note", "Note / reason"]].map(([k, label]) => (
                          <input key={k} type="text" aria-label={label} placeholder={label} value={legacyForm[k] || ""}
                            onChange={(e) => setLegacyForm((f) => ({ ...f, [k]: e.target.value }))}
                            className="w-full px-2.5 py-1.5 text-[12px] border border-slate-200 rounded-lg" />
                        ))}
                        <div className="flex gap-2"><Btn primary disabled={busy} onClick={legacyCorrection}>Submit correction</Btn><Btn onClick={() => setLegacyForm(null)}>Cancel</Btn></div>
                      </div>
                    )
                  )}
                </div>
                {(e911?.emergency_endpoints || []).length > 0 && (
                  <div className="space-y-1.5">
                    {e911.emergency_endpoints.map((ep, i) => (
                      <div key={i} className="rounded-lg border border-slate-200 px-3 py-2 text-[11.5px] text-slate-600">
                        <span className="font-medium text-slate-800">{ep.service_type}</span>
                        {ep.where && <span> · {ep.where}</span>}{ep.floor && <span> · Floor {ep.floor}</span>}
                        {ep.callback_number && <span> · Callback {ep.callback_number}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {(e911?.address_history || []).length > 0 && (
                  <div className="text-[11.5px] text-slate-600 space-y-0.5">
                    <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.08em]">Verification history</p>
                    {e911.address_history.map((h, i) => <p key={i}><span className="text-slate-400 tabular-nums">{h.when || "—"}</span> · {h.change} · {h.by}</p>)}
                  </div>
                )}
              </Block>

              <Block title="Inspections" icon={ClipboardCheck}
                action={<Contribute type="inspection" canContribute={canContribute} selfService={selfServiceOn} onSubmit={submitContribution} />}>
                {(inspections?.items || []).length === 0 && contribOf("inspection").length === 0 && <Muted>No inspections recorded yet.</Muted>}
                {(inspections?.items || []).map((it, i) => <p key={i} className="text-[11.5px] text-slate-700">{it.when} · {it.kind}</p>)}
                <Pending items={contribOf("inspection")} render={(c) => [c.payload?.date, c.payload?.kind].filter(Boolean).join(" · ") || c.note || "Inspection"} />
              </Block>

              <Block title="Emergency procedures" icon={LifeBuoy}
                action={<Contribute type="procedure" canContribute={canContribute} selfService={selfServiceOn} onSubmit={submitContribution} />}>
                {contribOf("procedure").length === 0 ? <Muted>No procedures recorded yet.</Muted>
                  : <Pending items={contribOf("procedure")} render={(c) => c.payload?.title || c.note || "Procedure"} />}
              </Block>
            </>
          )}

          {detail && tab === "records" && (
            <>
              <Block title="Contacts" icon={Users}
                action={selfServiceOn
                  ? (caps.can_manage_contacts && <Btn onClick={() => setModal({ type: "update_contacts" })}>Edit contacts</Btn>)
                  : <Contribute type="contact" canContribute={canContribute} selfService={false} onSubmit={submitContribution} />}>
                {selfServiceOn && (
                  <dl className="grid grid-cols-[170px_1fr] gap-y-1.5 text-[12.5px]">
                    {CONTACT_ROLES.map((r) => {
                      const c = ws.contacts.contacts[r.value];
                      return (
                        <div key={r.value} className="contents">
                          <dt className="text-slate-500">{r.label}</dt>
                          <dd className={c ? "text-slate-800" : "text-slate-400"}>{c ? [c.name, c.title, c.phone, c.email].filter(Boolean).join(" · ") : "Not added yet"}</dd>
                        </div>
                      );
                    })}
                  </dl>
                )}
                {(contacts?.contacts || []).length > 0 && (
                  <p className="text-[11.5px] text-slate-500">On file: {contacts.contacts.map((c) => [c.name || c.role, c.phone, c.email].filter(Boolean).join(" · ")).join("; ")}</p>
                )}
                {!selfServiceOn && <Pending items={contribOf("contact")} render={(c) => [c.payload?.name, c.payload?.phone].filter(Boolean).join(" · ") || "Contact"} />}
              </Block>

              <Block title="Notes" icon={Edit3}
                action={<Contribute type="note" canContribute={canContribute} selfService={selfServiceOn} onSubmit={submitContribution} />}>
                {ws?.profile?.location_notes && <p className="text-[12.5px] text-slate-700"><span className="text-slate-500">Location notes: </span>{ws.profile.location_notes}</p>}
                {ws?.profile?.access_notes && <p className="text-[12.5px] text-slate-700"><span className="text-slate-500">Access: </span>{ws.profile.access_notes}</p>}
                {!ws?.profile?.location_notes && !ws?.profile?.access_notes && contribOf("note").length === 0 && <Muted>No notes yet.{caps.can_manage_location ? " Location and access notes are edited under Manage Location." : ""}</Muted>}
                <Pending items={contribOf("note")} render={(c) => c.note || "Note"} />
              </Block>

              <Block title="Activity" icon={ClipboardCheck}>
                <p className="text-[11px] text-slate-400 mb-1.5">Already done, for your records. Open requests and their status are on the Overview tab.</p>
                {activity.length === 0 ? <Muted>No activity yet.</Muted> : (
                  <div className="rounded-lg border border-slate-200 divide-y divide-slate-100 max-h-72 overflow-y-auto">
                    {activity.slice(0, 40).map((a, i) => (
                      <div key={i} className="px-3 py-1.5 flex items-center gap-2 text-[12px]">
                        <span className="text-slate-800 flex-1">{a.text}</span>
                        <span className="text-[11px] text-slate-400 tabular-nums">{a.when ? new Date(a.when).toLocaleString() : ""}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Block>

              {/* Roadmap — kept, clearly disabled, and compact. */}
              <div className="rounded-lg border border-dashed border-slate-200 px-3 py-2.5 flex flex-wrap items-center gap-2">
                <span className="text-[11.5px] text-slate-500 flex-1 min-w-[180px]">Documents, photos and billing are coming soon.</span>
                <Contribute type="document" canContribute={canContribute} selfService={selfServiceOn} onSubmit={submitContribution} />
                <Contribute type="photo" canContribute={canContribute} selfService={selfServiceOn} onSubmit={submitContribution} />
              </div>

              <p className="text-[11px] text-slate-400">Urgent or unsure? <a className="underline hover:text-slate-600" href="mailto:support@manleysolutions.com">Contact support</a></p>
            </>
          )}
        </div>
      </motion.div>

      <LocationModals modal={modal} ws={ws} api={api} onClose={() => setModal(null)} onDone={done} />
    </div>
  );
}
