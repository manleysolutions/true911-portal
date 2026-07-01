import { useState, useEffect } from "react";
import {
  X, PhoneCall, CheckCircle2, AlertTriangle, MapPin, Cpu, Wifi, WifiOff,
  Clock, FileText, CreditCard, StickyNote, Image as ImageIcon, ShieldCheck,
  ClipboardCheck, LifeBuoy, Gauge, Link2, Check, Wrench, ChevronRight, Users,
} from "lucide-react";
import { apiFetch } from "@/api/client";

// ════════════════════════════════════════════════════════════════════
// LocationCommandCenter — the Location Workspace (Digital Twin).
//
// A complete operational record for ONE building, composed from customer-safe
// APIs: overview, services (+ grouped equipment), E911, timeline, documents,
// photos, inspections, contacts, and building health. Customers reason in
// Buildings · Services · Protection · History · Documentation · Compliance —
// equipment supports those concepts. No device jargon, no fabricated E911,
// no internal/sensitive fields. Placeholders are honest ("coming soon").
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

function StatusChip({ status }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium ${chip(status)}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot(status)}`} />{status || "Unknown"}
    </span>
  );
}

function Section({ title, icon: Icon, children, soon, count }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5 text-slate-400" />
        <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em]">{title}</p>
        {count != null && <span className="text-[10px] text-slate-400 tabular-nums">{count}</span>}
        {soon && <span className="text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5">Soon</span>}
      </div>
      {children}
    </div>
  );
}

function HealthBar({ health }) {
  if (!health) return null;
  const { score, confidence, grade } = health;
  const barTone = grade === "Needs attention" ? "bg-red-500" : grade === "Fair" ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-center justify-between">
        <span className="text-[12px] text-slate-500 inline-flex items-center gap-1.5"><Gauge className="w-3.5 h-3.5 text-slate-400" />Building health</span>
        <span className="text-[13px] font-semibold text-slate-900 tabular-nums">{score != null ? `${score}/100` : "—"}</span>
      </div>
      {score != null && (
        <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className={`h-full ${barTone}`} style={{ width: `${score}%` }} /></div>
      )}
      <p className="text-[10.5px] text-slate-400 mt-1.5">{grade}{confidence != null ? ` · ${confidence}% confidence` : ""}</p>
    </div>
  );
}

export default function LocationCommandCenter({ locationRef, locationName, onClose }) {
  const [d, setD] = useState({});   // { detail, services, e911, timeline, contacts, documents, photos, inspections, health }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    const enc = encodeURIComponent(locationRef);
    const get = (p) => apiFetch(`/customer/locations/${enc}${p}`).then((r) => r.data).catch(() => null);
    (async () => {
      try {
        const detail = await apiFetch(`/customer/locations/${enc}`).then((r) => r.data);
        const [services, e911, timeline, contacts, documents, photos, inspections, health] = await Promise.all([
          get("/services"), get("/e911"), get("/timeline"), get("/contacts"),
          get("/documents"), get("/photos"), get("/inspections"), get("/health"),
        ]);
        if (alive) setD({ detail, services, e911, timeline, contacts, documents, photos, inspections, health });
      } catch (err) {
        if (alive) setError(err.message || "Unable to load this location");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [locationRef]);

  const { detail, services, e911, timeline, contacts, documents, photos, inspections, health } = d;
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
              <span className="text-slate-700 font-medium truncate">{detail?.location || locationName}</span>
            </nav>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" aria-label="Close"><X className="w-4 h-4" /></button>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <ShieldCheck className="w-4 h-4 text-slate-700 flex-shrink-0" />
            <h2 className="text-[15px] font-semibold text-slate-900 truncate flex-1">{detail?.location || locationName}</h2>
            {detail && <StatusChip status={detail.protection?.status} />}
          </div>
          {/* Quick actions */}
          <div className="flex items-center gap-2 mt-3">
            <button onClick={shareLink} className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50">
              {copied ? <><Check className="w-3.5 h-3.5 text-emerald-600" />Copied</> : <><Link2 className="w-3.5 h-3.5" />Share link</>}
            </button>
            <button className="inline-flex items-center gap-1.5 text-[11.5px] px-2.5 py-1 rounded-lg border border-slate-200 text-slate-400 cursor-default" title="Coming soon">
              <Wrench className="w-3.5 h-3.5" />Request service<span className="text-[9px] uppercase tracking-wide bg-slate-100 rounded px-1">Soon</span>
            </button>
          </div>
        </div>

        <div className="p-5 space-y-6">
          {loading && <p className="text-xs text-slate-400">Loading…</p>}
          {error && <p className="text-xs text-red-600">{error}</p>}

          {detail && (
            <>
              {/* Overview */}
              <Section title="Overview" icon={MapPin}>
                <div className="rounded-lg border border-slate-200 bg-slate-50 h-24 flex items-center justify-center mb-3">
                  <div className="text-center text-slate-400"><ImageIcon className="w-5 h-5 mx-auto mb-1" /><p className="text-[11px]">Location photo — coming soon</p></div>
                </div>
                {detail.building_type && <div className="flex items-center justify-between mb-2"><span className="text-[12px] text-slate-500">Building</span><span className="text-[12px] text-slate-800">{detail.building_type}</span></div>}
                <div className="flex items-start justify-between gap-4"><span className="text-[12px] text-slate-500">Address</span><span className="text-[12px] text-slate-800 text-right">{detail.service_address || "Not yet on file"}</span></div>
              </Section>

              {/* Digital Twin building health */}
              <Section title="Digital Twin Health" icon={Gauge}><HealthBar health={health?.health} /></Section>

              {/* Life Safety Services (enriched, equipment grouped beneath) */}
              <Section title="Life Safety Services" icon={ShieldCheck} count={services?.services?.length}>
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
                        {/* Service facts */}
                        <div className="px-3 py-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500 border-b border-slate-100">
                          <span>{svc.equipment_count} device{svc.equipment_count === 1 ? "" : "s"}</span>
                          {svc.carrier && <span>Carrier: {svc.carrier}</span>}
                          {(svc.phone_numbers || []).length > 0 && <span className="inline-flex items-center gap-1"><PhoneCall className="w-3 h-3" />{svc.phone_numbers.join(", ")}</span>}
                          <span>Last test: {svc.last_test || "—"}</span>
                          <span>Last inspection: {svc.last_inspection || "—"}</span>
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
              </Section>

              {/* Equipment (consolidated) */}
              <Section title="Equipment" icon={Cpu} count={(detail.devices || []).length}>
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
              </Section>

              {/* E911 */}
              <Section title="E911 — Emergency Record" icon={PhoneCall}>
                <div className={`rounded-lg border p-3 ${e911Tone.chip}`}>
                  <div className="flex items-center gap-2"><e911Tone.icon className={`w-4 h-4 ${e911Tone.text}`} /><p className={`text-[13px] font-medium ${e911Tone.text}`}>{e911Verified ? "Verified" : "Not yet verified"}</p></div>
                  {e911?.emergency_dispatch_address && <p className="text-[12px] text-slate-600 mt-1">{e911.emergency_dispatch_address}</p>}
                  {!e911Verified && <p className="text-[11.5px] text-slate-500 mt-1">Manley Solutions is verifying this emergency record.</p>}
                </div>
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

              {/* Documents */}
              <Section title="Documents" icon={FileText} soon>
                <div className="flex flex-wrap gap-1.5">
                  {(documents?.categories || ["permit", "floor_plan", "inspection_report", "photo", "carrier_paperwork", "service_contract", "e911_documentation"]).map((c) => (
                    <span key={c} className="text-[10.5px] text-slate-500 bg-slate-100 rounded px-1.5 py-0.5">{c.replace(/_/g, " ")}</span>
                  ))}
                </div>
                <p className="text-[11.5px] text-slate-400 mt-2">Floor plans, permits, and inspection reports will appear here.</p>
              </Section>

              {/* Photos */}
              <Section title="Photos" icon={ImageIcon} soon>
                <p className="text-[12px] text-slate-400">Site and equipment photos will appear here.</p>
              </Section>

              {/* Inspection History */}
              <Section title="Inspection History" icon={ClipboardCheck} soon={!(inspections?.items || []).length} count={(inspections?.items || []).length}>
                {(inspections?.items || []).length === 0 ? (
                  <p className="text-[12px] text-slate-400">No inspections recorded yet.</p>
                ) : (
                  <div className="space-y-1.5">{inspections.items.map((it, i) => (<div key={i} className="text-[11.5px] text-slate-700">{it.when} · {it.kind}</div>))}</div>
                )}
              </Section>

              {/* Recent Activity (timeline) */}
              <Section title="Recent Activity" icon={Clock} count={(timeline?.timeline || []).length}>
                {!timeline || timeline.timeline?.length === 0 ? (
                  <p className="text-[12px] text-slate-400">No recorded activity yet.</p>
                ) : (
                  <div className="space-y-2">
                    {timeline.timeline.map((it, i) => (
                      <div key={i} className="flex items-start gap-2.5"><span className={`mt-1 w-1.5 h-1.5 rounded-full ${it.kind === "e911_verified" ? "bg-emerald-500" : "bg-slate-300"}`} /><div><p className="text-[12.5px] text-slate-800">{it.title}</p><p className="text-[11px] text-slate-400 tabular-nums">{it.when || "—"} · {it.by}</p></div></div>
                    ))}
                  </div>
                )}
              </Section>

              {/* Site Contacts */}
              <Section title="Site Contacts" icon={Users}>
                {!(contacts?.contacts || []).length ? (
                  <p className="text-[12px] text-slate-400">No site contact on file. Support: Manley Solutions.</p>
                ) : (
                  <div className="space-y-1.5">
                    {contacts.contacts.map((c, i) => (
                      <div key={i} className="rounded-lg border border-slate-200 p-2.5 text-[11.5px]">
                        <p className="text-slate-800 font-medium">{c.name || c.role}</p>
                        <div className="flex flex-wrap gap-x-3 text-slate-500">{c.phone && <span>{c.phone}</span>}{c.email && <span>{c.email}</span>}</div>
                      </div>
                    ))}
                  </div>
                )}
              </Section>

              {/* Placeholders — honest, no fabricated data */}
              <Section title="Emergency Procedures" icon={LifeBuoy} soon><p className="text-[12px] text-slate-400">Building emergency procedures will appear here.</p></Section>
              <Section title="Service Requests" icon={Wrench} soon><p className="text-[12px] text-slate-400">Open and track service requests here.</p></Section>
              <Section title="Billing" icon={CreditCard} soon><p className="text-[12px] text-slate-400">Billing details will appear here.</p></Section>
              <Section title="Notes" icon={StickyNote}><p className="text-[12px] text-slate-400">No notes for this location.</p></Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
