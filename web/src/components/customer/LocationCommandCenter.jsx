import { useState, useEffect } from "react";
import {
  X, PhoneCall, CheckCircle2, AlertTriangle, MapPin, Cpu, Wifi, WifiOff,
  Clock, FileText, CreditCard, StickyNote, Image as ImageIcon, ShieldCheck,
  ClipboardCheck, LifeBuoy, Gauge, Link2, Check, Wrench, ChevronRight, Users,
  Edit3, Send, Award, Plus,
} from "lucide-react";
import { apiFetch } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";

// ════════════════════════════════════════════════════════════════════
// LocationCommandCenter — the collaborative Building Workspace (Digital Twin).
//
// A complete, improvable operational record for ONE building, organised into
// four workspaces — Building Summary · Operations · Compliance · Administration
// — composed from customer-safe APIs. Life-safety SERVICES are the primary
// objects; equipment supports them. Customers contribute (contacts, inspections,
// photos, documents, procedures, notes, service requests) through a review
// workflow — nothing they submit overwrites a protected record automatically.
// No device jargon, no fabricated E911, no internal/operating-company references.
// ════════════════════════════════════════════════════════════════════

const STATUS_STYLE = {
  "Protected":        { dot: "bg-emerald-500", chip: "bg-emerald-50 border-emerald-200 text-emerald-800" },
  "Attention Needed": { dot: "bg-amber-500",   chip: "bg-amber-50 border-amber-200 text-amber-800" },
  "Critical":         { dot: "bg-red-500",     chip: "bg-red-50 border-red-200 text-red-800" },
  "Pending Install":  { dot: "bg-blue-500",    chip: "bg-blue-50 border-blue-200 text-blue-800" },
  "Inactive":         { dot: "bg-slate-400",   chip: "bg-slate-50 border-slate-200 text-slate-700" },
  "Unknown":          { dot: "bg-slate-400",   chip: "bg-slate-50 border-slate-200 text-slate-700" },
};
const chip = (s) => (STATUS_STYLE[s] || STATUS_STYLE.Unknown).chip;
const dot = (s) => (STATUS_STYLE[s] || STATUS_STYLE.Unknown).dot;
const barTone = (v) => (v == null ? "bg-slate-300" : v >= 80 ? "bg-emerald-500" : v >= 50 ? "bg-amber-500" : "bg-red-500");

const TIER_STYLE = {
  Bronze:   "bg-amber-100 text-amber-800 border-amber-200",
  Silver:   "bg-slate-100 text-slate-700 border-slate-300",
  Gold:     "bg-yellow-100 text-yellow-800 border-yellow-300",
  Platinum: "bg-indigo-100 text-indigo-800 border-indigo-200",
};

function StatusChip({ status }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium ${chip(status)}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot(status)}`} />{status || "Unknown"}
    </span>
  );
}

// A top-level workspace heading (Phase 1: Building Summary / Operations / …).
function Group({ title }) {
  return (
    <h3 className="text-[11px] font-bold text-slate-700 uppercase tracking-[0.12em] border-b border-slate-200 pb-1.5 pt-1">
      {title}
    </h3>
  );
}

function Section({ title, icon: Icon, children, soon, count, action }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5 text-slate-400" />
        <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em]">{title}</p>
        {count != null && <span className="text-[10px] text-slate-400 tabular-nums">{count}</span>}
        {soon && <span className="text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5">Soon</span>}
        <div className="ml-auto">{action}</div>
      </div>
      {children}
    </div>
  );
}

function MaturityBadge({ maturity }) {
  if (!maturity) return null;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10.5px] font-semibold ${TIER_STYLE[maturity.tier] || TIER_STYLE.Bronze}`}>
      <Award className="w-3 h-3" />{maturity.tier}
    </span>
  );
}

// Phase 7 — maturity tier + progress + next steps.
function MaturityCard({ maturity }) {
  if (!maturity) return null;
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-100 p-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[11.5px] font-medium text-slate-600 inline-flex items-center gap-1.5"><Award className="w-3.5 h-3.5 text-slate-400" />Digital Twin maturity</span>
        <MaturityBadge maturity={maturity} />
      </div>
      <div className="mt-2 h-1.5 bg-slate-200 rounded-full overflow-hidden"><div className="h-full bg-indigo-500" style={{ width: `${maturity.score}%` }} /></div>
      <p className="text-[10.5px] text-slate-400 mt-1">
        {maturity.met} of {maturity.total} complete
        {(maturity.next_steps || []).length ? ` · Next: ${maturity.next_steps.join(", ")}` : ""}
      </p>
    </div>
  );
}

// Phase 4 — health separated into factors, composite shown AFTER the factors.
function SeparatedHealth({ data, fallback }) {
  if (!data) {
    // Backward-compat: older API shape (single composite) still renders.
    if (!fallback) return null;
    const { score, confidence, grade } = fallback;
    return (
      <div className="rounded-lg border border-slate-200 p-3">
        <div className="flex items-center justify-between">
          <span className="text-[12px] text-slate-500 inline-flex items-center gap-1.5"><Gauge className="w-3.5 h-3.5 text-slate-400" />Building health</span>
          <span className="text-[13px] font-semibold text-slate-900 tabular-nums">{score != null ? `${score}/100` : "—"}</span>
        </div>
        {score != null && <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className={`h-full ${barTone(score)}`} style={{ width: `${score}%` }} /></div>}
        <p className="text-[10.5px] text-slate-400 mt-1.5">{grade}{confidence != null ? ` · ${confidence}% confidence` : ""}</p>
      </div>
    );
  }
  const { composite, confidence, factors } = data;
  return (
    <div className="rounded-lg border border-slate-200 p-3 space-y-3">
      <p className="text-[10.5px] text-slate-400">Building health is made up of these factors — the overall score follows.</p>
      <div className="space-y-2">
        {(factors || []).map((f) => (
          <div key={f.key}>
            <div className="flex items-center justify-between text-[11.5px]">
              <span className="text-slate-600">{f.label} <span className="text-slate-300">· {f.weight}%</span></span>
              <span className="tabular-nums text-slate-800">{f.known ? `${f.value}/100` : "—"}</span>
            </div>
            <div className="mt-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">{f.known && <div className={`h-full ${barTone(f.value)}`} style={{ width: `${f.value}%` }} />}</div>
            {!f.known && <p className="text-[10px] text-slate-400 mt-0.5">Not enough information yet</p>}
          </div>
        ))}
      </div>
      <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
        <span className="text-[12px] font-medium text-slate-700 inline-flex items-center gap-1.5"><Gauge className="w-3.5 h-3.5 text-slate-400" />Overall building health</span>
        <span className="text-[13px] font-semibold text-slate-900 tabular-nums">{composite != null ? `${composite}/100` : "—"}</span>
      </div>
      {confidence != null && <p className="text-[10px] text-slate-400 -mt-1.5">Based on the factors above · {confidence}% confidence</p>}
    </div>
  );
}

// Contribution form definitions (Phase 2/6). Each button routes a REQUEST through
// the review workflow — no protected data is written directly.
const CONTRIB = {
  contact:         { label: "Add Contact",     fields: [["name", "Name"], ["phone", "Phone"], ["email", "Email"], ["role", "Role (e.g. Facilities)"]], noteLabel: "Note (optional)" },
  inspection:      { label: "Record Inspection", fields: [["date", "Date"], ["kind", "Inspection type"]], noteLabel: "Findings / notes" },
  photo:           { label: "Upload Photo",    fields: [["filename", "File name"], ["caption", "Caption"]], noteLabel: "Note (optional)", hint: "Photo details are recorded now; file upload arrives soon." },
  document:        { label: "Upload Document", fields: [["filename", "File name"], ["category", "Category"]], noteLabel: "Note (optional)", hint: "Document details are recorded now; file upload arrives soon." },
  procedure:       { label: "Upload Procedure", fields: [["title", "Procedure title"]], noteLabel: "Details", hint: "Procedure details are recorded now; file upload arrives soon." },
  note:            { label: "Add Note",        fields: [], noteLabel: "Note", noteOnly: true },
  service_request: { label: "Create Request",  fields: [["summary", "What do you need?"]], noteLabel: "Details" },
};

function Contribute({ type, canContribute, onSubmit }) {
  const cfg = CONTRIB[type];
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);
  if (!canContribute || !cfg) return null;

  const submit = async () => {
    setBusy(true); setFlash(null);
    const payload = {};
    for (const [k] of cfg.fields) if (f[k]) payload[k] = f[k];
    try {
      const res = await onSubmit(type, payload, note);
      setFlash({ ok: true, text: res?.message || "Submitted — awaiting review" });
      setOpen(false); setF({}); setNote("");
    } catch (e) {
      setFlash({ ok: false, text: e.message || "Could not submit — please try again." });
    } finally { setBusy(false); }
  };

  if (!open) {
    return (
      <div>
        <button onClick={() => { setOpen(true); setFlash(null); }}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50">
          <Plus className="w-3 h-3" />{cfg.label}
        </button>
        {flash && <p className={`mt-1 text-[11px] ${flash.ok ? "text-emerald-700" : "text-red-600"}`}>{flash.text}</p>}
      </div>
    );
  }
  return (
    <div className="mt-2 rounded-lg border border-slate-200 p-3 space-y-2">
      {cfg.hint && <p className="text-[10.5px] text-slate-400">{cfg.hint}</p>}
      {cfg.fields.map(([k, label]) => (
        <input key={k} type="text" placeholder={label} value={f[k] || ""}
          onChange={(e) => setF((prev) => ({ ...prev, [k]: e.target.value }))}
          className="w-full px-2.5 py-1.5 text-[12px] border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-300" />
      ))}
      <textarea placeholder={cfg.noteLabel} rows={2} value={note}
        onChange={(e) => setNote(e.target.value)}
        className="w-full px-2.5 py-1.5 text-[12px] border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-300" />
      <div className="flex gap-2">
        <button onClick={submit} disabled={busy || (cfg.noteOnly && !note)}
          className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50">
          <Send className="w-3.5 h-3.5" />Submit
        </button>
        <button onClick={() => { setOpen(false); setF({}); setNote(""); }} disabled={busy}
          className="text-[11.5px] px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50">Cancel</button>
      </div>
    </div>
  );
}

// Pending customer contributions of a given type (awaiting review).
function Pending({ items, render }) {
  if (!items.length) return null;
  return (
    <div className="mt-1.5 space-y-1">
      {items.map((c, i) => (
        <div key={c.contribution_id || i} className="flex items-start gap-2 text-[11px] rounded-lg border border-dashed border-slate-200 px-2.5 py-1.5">
          <span className="mt-1 w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
          <div className="min-w-0">
            <span className="text-slate-700">{render(c)}</span>
            <span className="block text-[10px] text-slate-400">{c.status === "recorded" ? "Recorded" : "Awaiting review"}{c.when ? ` · ${c.when.slice(0, 10)}` : ""}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function LocationCommandCenter({ locationRef, locationName, onClose }) {
  const { can } = useAuth();
  const canSubmit = typeof can === "function" && can("CUSTOMER_SUBMIT_E911_REVIEW");
  const canContribute = typeof can === "function" && can("CUSTOMER_CONTRIBUTE");
  const [d, setD] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);

  const enc = encodeURIComponent(locationRef);
  const get = (p) => apiFetch(`/customer/locations/${enc}${p}`).then((r) => r.data).catch(() => null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const detail = await apiFetch(`/customer/locations/${enc}`).then((r) => r.data);
        const [services, e911, timeline, contacts, documents, photos, inspections, health, review, contributions] = await Promise.all([
          get("/services"), get("/e911"), get("/timeline"), get("/contacts"),
          get("/documents"), get("/photos"), get("/inspections"), get("/health"),
          get("/e911/review-status"), get("/contributions"),
        ]);
        if (alive) setD({ detail, services, e911, timeline, contacts, documents, photos, inspections, health, review, contributions });
      } catch (err) {
        if (alive) setError(err.message || "Unable to load this location");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [locationRef]);

  const refreshReview = async () => {
    const r = await get("/e911/review-status");
    setD((prev) => ({ ...prev, review: r }));
  };

  // Phase 2/6 — submit a contribution, then refresh the log + health/maturity.
  const submitContribution = async (type, payload, note) => {
    const res = await apiFetch(`/customer/locations/${enc}/contributions`, {
      method: "POST", body: JSON.stringify({ type, payload: payload || {}, note: note || null }),
    }).then((r) => r.data);
    const [c, h] = await Promise.all([get("/contributions"), get("/health")]);
    setD((prev) => ({ ...prev, contributions: c, health: h }));
    return res;
  };

  const confirmRecord = async () => {
    setBusy(true); setFlash(null);
    try {
      await apiFetch(`/customer/locations/${enc}/e911/confirm`, { method: "POST", body: JSON.stringify({}) });
      setFlash({ ok: true, text: "Thank you — your confirmation was submitted. Verification Requested." });
      await refreshReview();
    } catch (e) {
      setFlash({ ok: false, text: e.message || "Could not submit — please try again." });
    } finally { setBusy(false); }
  };

  const submitCorrection = async () => {
    setBusy(true); setFlash(null);
    try {
      await apiFetch(`/customer/locations/${enc}/e911/correction-request`, {
        method: "POST",
        body: JSON.stringify({
          corrected_address: form.address || null, suite: form.suite || null,
          floor: form.floor || null, unit: form.unit || null,
          callback_number: form.callback || null, service_identifier: form.identifier || null,
          note: form.note || null,
        }),
      });
      setShowForm(false); setForm({});
      setFlash({ ok: true, text: "Correction submitted — Awaiting Review." });
      await refreshReview();
    } catch (e) {
      setFlash({ ok: false, text: e.message || "Could not submit — please try again." });
    } finally { setBusy(false); }
  };

  const { detail, services, e911, timeline, contacts, documents, photos, inspections, health, review, contributions } = d;
  const contribOf = (t) => (contributions?.contributions || []).filter((c) => c.type === t);
  const v = e911?.verification || {};
  const e911Verified = detail?.emergency_address_state === "Verified" || v.verified;
  const e911Tone = e911Verified
    ? { text: "text-emerald-700", chip: "bg-emerald-50 border-emerald-200 text-emerald-800", icon: CheckCircle2 }
    : { text: "text-amber-700", chip: "bg-amber-50 border-amber-200 text-amber-800", icon: AlertTriangle };

  const shareLink = () => {
    const url = `${window.location.origin}${window.location.pathname}?location=${encodeURIComponent(locationRef)}`;
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); });
  };

  return (
    <div className="fixed inset-0 z-[1000] flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-slate-900/30" />
      <div className="relative w-full max-w-lg bg-white h-full shadow-xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* Header + breadcrumb + navigation */}
        <div className="px-5 py-4 border-b border-slate-100 sticky top-0 bg-white z-10">
          <div className="flex items-center justify-between">
            <nav className="flex items-center gap-1 text-[11px] text-slate-400 min-w-0">
              <span>Portfolio</span><ChevronRight className="w-3 h-3" />
              <span className="text-slate-700 font-medium truncate">{detail?.display_name || detail?.location || locationName}</span>
            </nav>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" aria-label="Close"><X className="w-4 h-4" /></button>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <ShieldCheck className="w-4 h-4 text-slate-700 flex-shrink-0" />
            <h2 className="text-[15px] font-semibold text-slate-900 truncate flex-1">{detail?.display_name || detail?.location || locationName}</h2>
            {health?.maturity && <MaturityBadge maturity={health.maturity} />}
            {detail && <StatusChip status={detail.protection?.status} />}
          </div>
          {/* Quick actions */}
          <div className="flex items-center gap-2 mt-3">
            <button onClick={shareLink} className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50">
              {copied ? <><Check className="w-3.5 h-3.5 text-emerald-600" />Copied</> : <><Link2 className="w-3.5 h-3.5" />Share link</>}
            </button>
          </div>
        </div>

        <div className="p-5 space-y-6">
          {loading && <p className="text-xs text-slate-400">Loading…</p>}
          {error && <p className="text-xs text-red-600">{error}</p>}

          {detail && (
            <>
              {/* ══ BUILDING SUMMARY ══ */}
              <Group title="Building Summary" />

              <Section title="Overview" icon={MapPin}
                action={<Contribute type="photo" canContribute={canContribute} onSubmit={submitContribution} />}>
                <div className="rounded-lg border border-slate-200 bg-slate-50 h-24 flex items-center justify-center mb-3">
                  <div className="text-center text-slate-400"><ImageIcon className="w-5 h-5 mx-auto mb-1" /><p className="text-[11px]">Location photo — coming soon</p></div>
                </div>
                {detail.building_type && <div className="flex items-center justify-between mb-2"><span className="text-[12px] text-slate-500">Building</span><span className="text-[12px] text-slate-800">{detail.building_type}</span></div>}
                <div className="flex items-start justify-between gap-4"><span className="text-[12px] text-slate-500">Address</span><span className="text-[12px] text-slate-800 text-right">{detail.service_address || "Not yet on file"}</span></div>
              </Section>

              <Section title="Building Health" icon={Gauge}>
                <SeparatedHealth data={health?.building_health} fallback={health?.health} />
                {health?.maturity && <div className="mt-3"><MaturityCard maturity={health.maturity} /></div>}
              </Section>

              {/* ══ OPERATIONS ══ */}
              <Group title="Operations" />

              {/* Life Safety Services — the primary objects (Phase 5) */}
              <Section title="Life Safety Services" icon={ShieldCheck} count={services?.services?.length}
                action={<Contribute type="service_request" canContribute={canContribute} onSubmit={submitContribution} />}>
                {!services || services.services?.length === 0 ? (
                  <p className="text-[12px] text-slate-400">No life-safety services on file yet.</p>
                ) : (
                  <div className="space-y-2.5">
                    {services.services.map((svc) => (
                      <div key={svc.service_ref} className="rounded-lg border border-slate-200 overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-2.5 bg-slate-50/60">
                          <div className="min-w-0">
                            <p className="text-[13px] font-semibold text-slate-900 truncate">{svc.service}</p>
                            {(svc.where || svc.floor) && <p className="text-[11px] text-slate-500">{[svc.where, svc.floor && `Floor ${svc.floor}`].filter(Boolean).join(" · ")}</p>}
                          </div>
                          <StatusChip status={svc.status?.status} />
                        </div>
                        <div className="px-3 py-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500 border-b border-slate-100">
                          <span>{svc.equipment_count} device{svc.equipment_count === 1 ? "" : "s"}</span>
                          {svc.carrier && <span>Carrier: {svc.carrier}</span>}
                          {(svc.phone_numbers || []).length > 0 && <span className="inline-flex items-center gap-1"><PhoneCall className="w-3 h-3" />{svc.phone_numbers.join(", ")}</span>}
                          <span>Last test: {svc.last_test || "—"}</span>
                          <span>Last inspection: {svc.last_inspection || "—"}</span>
                          {svc.confidence && svc.confidence !== "Confirmed" && (
                            <span className="text-slate-400" title="Classified from equipment signals">Inferred · {svc.confidence}</span>
                          )}
                        </div>
                        {(svc.attention_items || []).length > 0 && (
                          <div className="px-3 py-1.5 text-[11px] text-amber-700 bg-amber-50/50">{svc.attention_items.join(" · ")}</div>
                        )}
                        {(svc.equipment || []).length > 0 && (
                          <div className="divide-y divide-slate-100">
                            {svc.equipment.map((eq, i) => (
                              <div key={i} className="flex items-center justify-between px-3 py-2 text-[11.5px]">
                                <span className="inline-flex items-center gap-1.5 text-slate-700 min-w-0"><Cpu className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" /><span className="truncate">{eq.equipment}{eq.model ? ` · ${eq.model}` : ""}</span></span>
                                <span className={`inline-flex items-center gap-1 flex-shrink-0 ${eq.health === "Online" ? "text-emerald-600" : "text-slate-500"}`}>{eq.health === "Online" ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}{eq.health}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <Pending items={contribOf("service_request")} render={(c) => c.payload?.summary || c.note || "Service request"} />
              </Section>

              {/* Equipment — de-emphasised, supporting detail (Phase 5) */}
              <details className="rounded-lg border border-slate-100">
                <summary className="cursor-pointer list-none px-3 py-2 flex items-center gap-2 text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.08em]">
                  <Cpu className="w-3.5 h-3.5 text-slate-300" />Supporting Equipment
                  <span className="text-[10px] text-slate-400 tabular-nums">{(detail.devices || []).length}</span>
                  <ChevronRight className="w-3 h-3 ml-auto" />
                </summary>
                <div className="px-3 pb-3">
                  {(detail.devices || []).length === 0 ? (
                    <p className="text-[12px] text-slate-400">No equipment on file.</p>
                  ) : (
                    <div className="space-y-1.5">
                      {detail.devices.map((dev, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-[11.5px]">
                          <span className="inline-flex items-center gap-1.5 text-slate-700 min-w-0"><Cpu className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" /><span className="truncate">{dev.equipment}{dev.model ? ` · ${dev.model}` : ""}</span></span>
                          <span className="flex items-center gap-3 flex-shrink-0">
                            {dev.identifier && <span className="inline-flex items-center gap-1 text-slate-500"><PhoneCall className="w-3 h-3" />{dev.identifier}</span>}
                            <span className={dev.health === "Online" ? "text-emerald-600" : "text-slate-500"}>{dev.health}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </details>

              <Section title="Service Requests" icon={Wrench} count={contribOf("service_request").length || null}
                action={<Contribute type="service_request" canContribute={canContribute} onSubmit={submitContribution} />}>
                {contribOf("service_request").length === 0
                  ? <p className="text-[12px] text-slate-400">No open service requests.</p>
                  : <Pending items={contribOf("service_request")} render={(c) => c.payload?.summary || c.note || "Service request"} />}
              </Section>

              <Section title="Recent Activity" icon={Clock} count={(timeline?.timeline || []).length}
                action={<Contribute type="note" canContribute={canContribute} onSubmit={submitContribution} />}>
                {!timeline || timeline.timeline?.length === 0 ? (
                  <p className="text-[12px] text-slate-400">No recorded activity yet.</p>
                ) : (
                  <div className="space-y-2">
                    {timeline.timeline.map((it, i) => (
                      <div key={i} className="flex items-start gap-2.5"><span className={`mt-1 w-1.5 h-1.5 rounded-full ${it.kind === "e911_verified" ? "bg-emerald-500" : "bg-slate-300"}`} /><div><p className="text-[12.5px] text-slate-800">{it.title}</p><p className="text-[11px] text-slate-400 tabular-nums">{it.when || "—"} · {it.by}</p></div></div>
                    ))}
                  </div>
                )}
                <Pending items={contribOf("note")} render={(c) => c.note || "Note"} />
              </Section>

              {/* ══ COMPLIANCE ══ */}
              <Group title="Compliance" />

              <Section title="E911 — Emergency Record" icon={PhoneCall}>
                <div className={`rounded-lg border p-3 ${e911Tone.chip}`}>
                  <div className="flex items-center gap-2"><e911Tone.icon className={`w-4 h-4 ${e911Tone.text}`} /><p className={`text-[13px] font-medium ${e911Tone.text}`}>{review?.state || (e911Verified ? "Verified" : "Verification Pending")}</p></div>
                  {e911?.emergency_dispatch_address && <p className="text-[12px] text-slate-600 mt-1">{e911.emergency_dispatch_address}</p>}
                  {!e911Verified && <p className="text-[11.5px] text-slate-500 mt-1">This emergency record is awaiting verification.</p>}
                </div>

                {flash && (
                  <p className={`mt-2 text-[11.5px] ${flash.ok ? "text-emerald-700" : "text-red-600"}`}>{flash.text}</p>
                )}
                {canSubmit && !e911Verified && (
                  <div className="mt-2">
                    {!showForm ? (
                      <div className="flex flex-wrap gap-2">
                        <button onClick={confirmRecord} disabled={busy}
                          className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg border border-emerald-200 text-emerald-700 hover:bg-emerald-50 disabled:opacity-50">
                          <CheckCircle2 className="w-3.5 h-3.5" />Confirm Emergency Record
                        </button>
                        <button onClick={() => { setShowForm(true); setFlash(null); }} disabled={busy}
                          className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
                          <Edit3 className="w-3.5 h-3.5" />Request Correction
                        </button>
                      </div>
                    ) : (
                      <div className="rounded-lg border border-slate-200 p-3 space-y-2">
                        <p className="text-[11px] text-slate-500">Tell us what should change — your request will be reviewed. Nothing is changed automatically.</p>
                        {[["address", "Corrected address"], ["suite", "Suite / unit"], ["floor", "Floor"],
                          ["callback", "Callback number"], ["identifier", "Elevator / FACP identifier"]].map(([k, label]) => (
                          <input key={k} type="text" placeholder={label} value={form[k] || ""}
                            onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
                            className="w-full px-2.5 py-1.5 text-[12px] border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-300" />
                        ))}
                        <textarea placeholder="Note / reason" rows={2} value={form.note || ""}
                          onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                          className="w-full px-2.5 py-1.5 text-[12px] border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-300" />
                        <div className="flex gap-2">
                          <button onClick={submitCorrection} disabled={busy}
                            className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50">
                            <Send className="w-3.5 h-3.5" />Submit correction
                          </button>
                          <button onClick={() => { setShowForm(false); setForm({}); }} disabled={busy}
                            className="text-[11.5px] px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50">Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {(e911?.emergency_endpoints || []).length > 0 && (
                  <div className="mt-2 space-y-2">
                    {e911.emergency_endpoints.map((ep, i) => (
                      <div key={i} className="rounded-lg border border-slate-200 p-2.5">
                        <p className="text-[12.5px] font-medium text-slate-900">{ep.service_type}</p>
                        <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-600">
                          {ep.where && <span>{ep.where}</span>}{ep.floor && <span>Floor {ep.floor}</span>}
                          {ep.callback_number && <span className="inline-flex items-center gap-1"><PhoneCall className="w-3 h-3" />{ep.callback_number}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {(e911?.address_history || []).length > 0 && (
                  <div className="mt-3">
                    <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.08em] mb-1">Verification history</p>
                    {e911.address_history.map((h, i) => (
                      <div key={i} className="flex items-center gap-2 text-[11.5px] text-slate-600"><span className="w-1.5 h-1.5 rounded-full bg-slate-300" /><span className="tabular-nums text-slate-400">{h.when || "—"}</span><span>{h.change}</span><span className="text-slate-400">· {h.by}</span></div>
                    ))}
                  </div>
                )}
              </Section>

              <Section title="Inspection History" icon={ClipboardCheck} count={(inspections?.items || []).length || null}
                action={<Contribute type="inspection" canContribute={canContribute} onSubmit={submitContribution} />}>
                {(inspections?.items || []).length === 0 ? (
                  <p className="text-[12px] text-slate-400">No inspections recorded yet.</p>
                ) : (
                  <div className="space-y-1.5">{inspections.items.map((it, i) => (<div key={i} className="text-[11.5px] text-slate-700">{it.when} · {it.kind}</div>))}</div>
                )}
                <Pending items={contribOf("inspection")} render={(c) => [c.payload?.date, c.payload?.kind].filter(Boolean).join(" · ") || c.note || "Inspection"} />
              </Section>

              <Section title="Emergency Procedures" icon={LifeBuoy}
                action={<Contribute type="procedure" canContribute={canContribute} onSubmit={submitContribution} />}>
                {contribOf("procedure").length === 0
                  ? <p className="text-[12px] text-slate-400">Building emergency procedures will appear here.</p>
                  : <Pending items={contribOf("procedure")} render={(c) => c.payload?.title || c.note || "Procedure"} />}
              </Section>

              {/* ══ ADMINISTRATION ══ */}
              <Group title="Administration" />

              <Section title="Site Contacts" icon={Users} count={(contacts?.contacts || []).length || null}
                action={<Contribute type="contact" canContribute={canContribute} onSubmit={submitContribution} />}>
                {!(contacts?.contacts || []).length && !contribOf("contact").length ? (
                  <p className="text-[12px] text-slate-400">No site contact on file.</p>
                ) : (
                  <div className="space-y-1.5">
                    {(contacts?.contacts || []).map((c, i) => (
                      <div key={i} className="rounded-lg border border-slate-200 p-2.5 text-[11.5px]">
                        <p className="text-slate-800 font-medium">{c.name || c.role}</p>
                        <div className="flex flex-wrap gap-x-3 text-slate-500">{c.phone && <span>{c.phone}</span>}{c.email && <span>{c.email}</span>}</div>
                      </div>
                    ))}
                  </div>
                )}
                <Pending items={contribOf("contact")} render={(c) => [c.payload?.name, c.payload?.phone].filter(Boolean).join(" · ") || c.note || "Contact"} />
              </Section>

              <Section title="Documents" icon={FileText} count={contribOf("document").length || null}
                action={<Contribute type="document" canContribute={canContribute} onSubmit={submitContribution} />}>
                <div className="flex flex-wrap gap-1.5">
                  {(documents?.categories || ["permit", "floor_plan", "inspection_report", "photo", "carrier_paperwork", "service_contract", "e911_documentation"]).map((c) => (
                    <span key={c} className="text-[10.5px] text-slate-500 bg-slate-100 rounded px-1.5 py-0.5">{c.replace(/_/g, " ")}</span>
                  ))}
                </div>
                <Pending items={contribOf("document")} render={(c) => [c.payload?.filename, c.payload?.category].filter(Boolean).join(" · ") || c.note || "Document"} />
                {contribOf("document").length === 0 && <p className="text-[11.5px] text-slate-400 mt-2">Floor plans, permits, and inspection reports will appear here.</p>}
              </Section>

              <Section title="Photos" icon={ImageIcon} count={contribOf("photo").length || null}
                action={<Contribute type="photo" canContribute={canContribute} onSubmit={submitContribution} />}>
                {contribOf("photo").length === 0
                  ? <p className="text-[12px] text-slate-400">Site and equipment photos will appear here.</p>
                  : <Pending items={contribOf("photo")} render={(c) => c.payload?.caption || c.payload?.filename || c.note || "Photo"} />}
              </Section>

              <Section title="Notes" icon={StickyNote} count={contribOf("note").length || null}
                action={<Contribute type="note" canContribute={canContribute} onSubmit={submitContribution} />}>
                {contribOf("note").length === 0
                  ? <p className="text-[12px] text-slate-400">No notes for this location.</p>
                  : <Pending items={contribOf("note")} render={(c) => c.note || "Note"} />}
              </Section>

              <Section title="Billing" icon={CreditCard} soon><p className="text-[12px] text-slate-400">Billing details will appear here.</p></Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
