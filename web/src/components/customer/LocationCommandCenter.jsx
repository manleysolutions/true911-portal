import { useState, useEffect } from "react";
import {
  X, PhoneCall, CheckCircle2, AlertTriangle, MapPin, Cpu, Wifi, WifiOff,
  Clock, FileText, CreditCard, StickyNote, Image as ImageIcon, ShieldCheck,
} from "lucide-react";
import { apiFetch } from "@/api/client";

// ════════════════════════════════════════════════════════════════════
// LocationCommandCenter — the Phase 4 centerpiece drawer.
//
// A service-first view of ONE location, composed from customer-safe APIs:
//   GET /customer/locations/{ref}            — overview (address, status)
//   GET /customer/locations/{ref}/services   — Life-Safety Services + equipment
//   GET /customer/locations/{ref}/e911       — emergency record (truth)
//   GET /customer/locations/{ref}/timeline   — real activity
//
// Sections: Overview · Life Safety Services · E911 · Timeline · Documents ·
// Billing · Notes.  Equipment is grouped BENEATH the service it supports.
// Never shows device jargon (IMEI/ICCID/firmware/carrier); E911 is calm, never
// alarming; Documents/Billing/Notes are honest placeholders.
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

function Section({ title, icon: Icon, children, soon }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5 text-slate-400" />
        <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em]">{title}</p>
        {soon && <span className="text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5">Soon</span>}
      </div>
      {children}
    </div>
  );
}

export default function LocationCommandCenter({ locationRef, locationName, onClose }) {
  const [detail, setDetail] = useState(null);
  const [services, setServices] = useState(null);
  const [e911, setE911] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    const enc = encodeURIComponent(locationRef);
    (async () => {
      try {
        const [d, s, e, t] = await Promise.all([
          apiFetch(`/customer/locations/${enc}`),
          apiFetch(`/customer/locations/${enc}/services`).catch(() => null),
          apiFetch(`/customer/locations/${enc}/e911`).catch(() => null),
          apiFetch(`/customer/locations/${enc}/timeline`).catch(() => null),
        ]);
        if (!alive) return;
        setDetail(d.data); setServices(s?.data); setE911(e?.data); setTimeline(t?.data);
      } catch (err) {
        if (alive) setError(err.message || "Unable to load this location");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [locationRef]);

  const v = e911?.verification || {};
  const e911Verified = detail?.emergency_address_state === "Verified" || v.verified;
  const e911Tone = e911Verified
    ? { text: "text-emerald-700", chip: "bg-emerald-50 border-emerald-200 text-emerald-800", icon: CheckCircle2 }
    : { text: "text-amber-700", chip: "bg-amber-50 border-amber-200 text-amber-800", icon: AlertTriangle };

  return (
    <div className="fixed inset-0 z-[1000] flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-slate-900/30" />
      <div className="relative w-full max-w-lg bg-white h-full shadow-xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 sticky top-0 bg-white z-10">
          <div className="min-w-0 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-slate-700 flex-shrink-0" />
            <div className="min-w-0">
              <h2 className="text-[15px] font-semibold text-slate-900 truncate">{detail?.location || locationName}</h2>
              <p className="text-[11px] text-slate-500">Location Command Center</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-5 space-y-6">
          {loading && <p className="text-xs text-slate-400">Loading…</p>}
          {error && <p className="text-xs text-red-600">{error}</p>}

          {detail && (
            <>
              {/* Overview */}
              <Section title="Overview" icon={MapPin}>
                <div className="rounded-lg border border-slate-200 bg-slate-50 h-28 flex items-center justify-center mb-3">
                  <div className="text-center text-slate-400"><ImageIcon className="w-6 h-6 mx-auto mb-1" /><p className="text-[11px]">Location photo — coming soon</p></div>
                </div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[12px] text-slate-500">Protection</span>
                  <StatusChip status={detail.protection?.status} />
                </div>
                {detail.building_type && (
                  <div className="flex items-center justify-between mb-2"><span className="text-[12px] text-slate-500">Building</span><span className="text-[12px] text-slate-800">{detail.building_type}</span></div>
                )}
                <div className="flex items-start justify-between gap-4">
                  <span className="text-[12px] text-slate-500">Address</span>
                  <span className="text-[12px] text-slate-800 text-right">{detail.service_address || "Not yet on file"}</span>
                </div>
              </Section>

              {/* Life Safety Services (equipment grouped beneath) */}
              <Section title="Life Safety Services" icon={ShieldCheck}>
                {!services || services.services?.length === 0 ? (
                  <p className="text-[12px] text-slate-400">No life-safety services on file yet.</p>
                ) : (
                  <div className="space-y-2.5">
                    {services.services.map((svc) => (
                      <div key={svc.service_ref} className="rounded-lg border border-slate-200 overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-2.5 bg-slate-50/60">
                          <div className="min-w-0">
                            <p className="text-[13px] font-semibold text-slate-900 truncate">{svc.service}</p>
                            {(svc.where || svc.floor) && (
                              <p className="text-[11px] text-slate-500">{[svc.where, svc.floor && `Floor ${svc.floor}`].filter(Boolean).join(" · ")}</p>
                            )}
                          </div>
                          <StatusChip status={svc.status?.status} />
                        </div>
                        {(svc.equipment || []).length > 0 && (
                          <div className="divide-y divide-slate-100">
                            {svc.equipment.map((eq, i) => (
                              <div key={i} className="flex items-center justify-between px-3 py-2 text-[11.5px]">
                                <span className="inline-flex items-center gap-1.5 text-slate-700 min-w-0">
                                  <Cpu className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                  <span className="truncate">{eq.equipment}{eq.model ? ` · ${eq.model}` : ""}</span>
                                </span>
                                <span className="flex items-center gap-3 flex-shrink-0">
                                  {eq.identifier && <span className="inline-flex items-center gap-1 text-slate-500"><PhoneCall className="w-3 h-3" />{eq.identifier}</span>}
                                  <span className={`inline-flex items-center gap-1 ${eq.health === "Online" ? "text-emerald-600" : "text-slate-500"}`}>
                                    {eq.health === "Online" ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}{eq.health}
                                  </span>
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Section>

              {/* E911 — always the truth, calm when unverified */}
              <Section title="E911 — Emergency Record" icon={PhoneCall}>
                <div className={`rounded-lg border p-3 ${e911Tone.chip}`}>
                  <div className="flex items-center gap-2">
                    <e911Tone.icon className={`w-4 h-4 ${e911Tone.text}`} />
                    <p className={`text-[13px] font-medium ${e911Tone.text}`}>
                      {e911Verified ? "Verified" : "Not yet verified"}
                    </p>
                  </div>
                  {e911?.emergency_dispatch_address && <p className="text-[12px] text-slate-600 mt-1">{e911.emergency_dispatch_address}</p>}
                  {!e911Verified && <p className="text-[11.5px] text-slate-500 mt-1">Manley Solutions is verifying this emergency record.</p>}
                </div>
                {(e911?.emergency_endpoints || []).length > 0 && (
                  <div className="mt-2 space-y-2">
                    {e911.emergency_endpoints.map((ep, i) => (
                      <div key={i} className="rounded-lg border border-slate-200 p-2.5">
                        <p className="text-[12.5px] font-medium text-slate-900">{ep.service_type}</p>
                        <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-600">
                          {ep.where && <span>{ep.where}</span>}
                          {ep.floor && <span>Floor {ep.floor}</span>}
                          {ep.callback_number && <span className="inline-flex items-center gap-1"><PhoneCall className="w-3 h-3" />{ep.callback_number}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {(e911?.address_history || []).length > 0 && (
                  <div className="mt-3">
                    <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-[0.08em] mb-1">Verification history</p>
                    <div className="space-y-1">
                      {e911.address_history.map((h, i) => (
                        <div key={i} className="flex items-center gap-2 text-[11.5px] text-slate-600">
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
                          <span className="tabular-nums text-slate-400">{h.when || "—"}</span>
                          <span>{h.change}</span>
                          <span className="text-slate-400">· {h.by}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Section>

              {/* Timeline */}
              <Section title="Activity Timeline" icon={Clock}>
                {!timeline || timeline.timeline?.length === 0 ? (
                  <p className="text-[12px] text-slate-400">No recorded activity yet.</p>
                ) : (
                  <div className="space-y-2">
                    {timeline.timeline.map((it, i) => (
                      <div key={i} className="flex items-start gap-2.5">
                        <span className={`mt-1 w-1.5 h-1.5 rounded-full ${it.kind === "e911_verified" ? "bg-emerald-500" : "bg-slate-300"}`} />
                        <div>
                          <p className="text-[12.5px] text-slate-800">{it.title}</p>
                          <p className="text-[11px] text-slate-400 tabular-nums">{it.when || "—"} · {it.by}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Section>

              {/* Placeholders — honest, no fabricated data */}
              <Section title="Documents" icon={FileText} soon>
                <p className="text-[12px] text-slate-400">Floor plans, permits, and inspection reports will appear here.</p>
              </Section>
              <Section title="Billing" icon={CreditCard} soon>
                <p className="text-[12px] text-slate-400">Billing details will appear here.</p>
              </Section>
              <Section title="Notes" icon={StickyNote}>
                <p className="text-[12px] text-slate-400">No notes for this location.</p>
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
