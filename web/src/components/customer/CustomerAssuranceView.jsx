import { useState, useEffect, useCallback } from "react";
import {
  Shield, Building2, RefreshCw, CheckCircle2, AlertTriangle,
  MapPin, ChevronRight, X, PhoneCall,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";

// ════════════════════════════════════════════════════════════════════
// CustomerAssuranceView
//
// The dashboard for the ISOLATED customer-plane roles (CUSTOMER_ADMIN /
// MANAGER / VIEWER / SUPPORT / …).  These roles cannot call /command/summary
// (no INTERNAL_OPS), so this view is sourced ENTIRELY from the read-only
// customer Assurance API:
//   * GET /customer/dashboard            — portfolio counts + attention feed
//   * GET /customer/locations            — location list (operational status)
//   * GET /customer/locations/{ref}/e911 — the E911 record (real stored data)
//
// The operational status shown here is the customer Assurance/Preview label
// (Protected / Attention Needed / …) computed server-side — greened for a
// preview tenant, evidence-backed, never fabricated, and free of any
// "API pending" / "telemetry pending" language.  E911 is the safety-critical
// axis: it is NEVER greened by preview and its "verified" flag comes only from
// the API's E911 summary.
// ════════════════════════════════════════════════════════════════════

// Six-label vocabulary -> calm color treatment (customer-facing).
const STATUS_STYLE = {
  "Protected":        { dot: "bg-emerald-500", text: "text-emerald-700", chip: "bg-emerald-50 border-emerald-200 text-emerald-800", icon: CheckCircle2 },
  "Attention Needed": { dot: "bg-amber-500",   text: "text-amber-700",   chip: "bg-amber-50 border-amber-200 text-amber-800",     icon: AlertTriangle },
  "Critical":         { dot: "bg-red-500",     text: "text-red-700",     chip: "bg-red-50 border-red-200 text-red-800",           icon: AlertTriangle },
  "Pending Install":  { dot: "bg-blue-500",    text: "text-blue-700",    chip: "bg-blue-50 border-blue-200 text-blue-800",        icon: MapPin },
  "Inactive":         { dot: "bg-slate-400",   text: "text-slate-600",   chip: "bg-slate-50 border-slate-200 text-slate-700",     icon: MapPin },
  "Unknown":          { dot: "bg-slate-400",   text: "text-slate-600",   chip: "bg-slate-50 border-slate-200 text-slate-700",     icon: MapPin },
};

function styleFor(status) {
  return STATUS_STYLE[status] || STATUS_STYLE["Unknown"];
}

function StatusChip({ status }) {
  const s = styleFor(status);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium ${s.chip}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {status}
    </span>
  );
}

function StatusCard({ label, value, tone = "slate" }) {
  const toneMap = {
    slate:   "border-slate-200 bg-white",
    emerald: "border-emerald-200 bg-emerald-50/50",
    amber:   "border-amber-200 bg-amber-50/50",
    red:     "border-red-200 bg-red-50/50",
    blue:    "border-blue-200 bg-blue-50/50",
  };
  return (
    <div className={`rounded-xl border px-4 py-3.5 ${toneMap[tone] || toneMap.slate}`}>
      <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-2">{label}</p>
      <p className="text-[26px] font-semibold text-slate-900 tabular-nums leading-none">{value ?? "—"}</p>
    </div>
  );
}

// ── E911 drawer — real stored emergency record via the customer API ──
function E911Drawer({ locationRef, locationName, onClose }) {
  const [e911, setE911] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await apiFetch(`/customer/locations/${encodeURIComponent(locationRef)}/e911`);
        if (alive) setE911(r.data);
      } catch (e) {
        if (alive) setError(e.message || "Unable to load emergency address");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [locationRef]);

  const v = e911?.verification || {};

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-slate-900/30" />
      <div className="relative w-full max-w-md bg-white h-full shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 sticky top-0 bg-white">
          <div>
            <h2 className="text-[15px] font-semibold text-slate-900">{locationName}</h2>
            <p className="text-[11.5px] text-slate-500">Emergency (E911) record</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {loading && <p className="text-xs text-slate-400">Loading emergency record…</p>}
          {error && <p className="text-xs text-red-600">{error}</p>}
          {e911 && (
            <>
              <div>
                <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-1">Emergency dispatch address</p>
                <p className="text-[13px] text-slate-900">
                  {e911.emergency_dispatch_address || <span className="text-slate-400">Not yet on file — setup in progress</span>}
                </p>
              </div>

              {/* Verification — the ONLY source is the API's verified flag. */}
              <div className={`rounded-lg border p-3 ${v.verified ? "border-emerald-200 bg-emerald-50" : v.is_critical ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}>
                <div className="flex items-center gap-2">
                  {v.verified
                    ? <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    : <AlertTriangle className={`w-4 h-4 ${v.is_critical ? "text-red-600" : "text-amber-600"}`} />}
                  <p className={`text-[13px] font-medium ${v.verified ? "text-emerald-800" : v.is_critical ? "text-red-800" : "text-amber-800"}`}>
                    {v.verified ? "Emergency address verified" : (v.state || "Not yet verified")}
                  </p>
                </div>
                {!v.verified && (
                  <p className={`text-[11.5px] mt-1 ${v.is_critical ? "text-red-700" : "text-amber-700"}`}>
                    {v.is_critical
                      ? "This location is active but its emergency address is not yet verified — Manley Solutions is verifying it."
                      : "Manley Solutions is verifying this emergency address."}
                  </p>
                )}
              </div>

              {/* Emergency endpoints — real ServiceUnit / callback detail. */}
              <div>
                <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-2">Emergency endpoints</p>
                {(e911.emergency_endpoints || []).length === 0 && (
                  <p className="text-[12px] text-slate-400">No emergency endpoints on file yet.</p>
                )}
                <div className="space-y-2">
                  {(e911.emergency_endpoints || []).map((ep, i) => (
                    <div key={i} className="rounded-lg border border-slate-200 p-3">
                      <p className="text-[13px] font-medium text-slate-900">{ep.service_type}</p>
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11.5px] text-slate-600">
                        {ep.where && <span>{ep.where}</span>}
                        {ep.floor && <span>Floor {ep.floor}</span>}
                        {ep.callback_number && (
                          <span className="inline-flex items-center gap-1"><PhoneCall className="w-3 h-3" />{ep.callback_number}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {(e911.customer_actions || []).length > 0 && (
                <div className="pt-1">
                  <p className="text-[11px] text-slate-500">
                    Need a correction? {e911.customer_actions.join(" · ")} — contact Manley Solutions.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────
export default function CustomerAssuranceView() {
  const { user } = useAuth();
  const [dash, setDash] = useState(null);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawer, setDrawer] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [d, l] = await Promise.all([
        apiFetch("/customer/dashboard"),
        apiFetch("/customer/locations?page_size=100"),
      ]);
      setDash(d.data);
      setLocations(l.data?.items || []);
    } catch (e) {
      // 404 here means the customer API / preview flag is not enabled for this
      // tenant yet — show a calm, honest setup message (never a raw error).
      setError(e.status === 404
        ? "Your portal is being finalized. Please check back shortly."
        : (e.message || "Unable to load your dashboard right now."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 60000);
    return () => clearInterval(t);
  }, [fetchData]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-slate-50 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-slate-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-xs text-slate-400">Loading…</p>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const p = dash?.portfolio || {};
  const allProtected = (p.total || 0) > 0 &&
    (p.critical || 0) === 0 && (p.attention_needed || 0) === 0 &&
    (p.pending_install || 0) === 0 && (p.unknown || 0) === 0;
  const feed = dash?.attention_feed || [];

  return (
    <PageWrapper>
      <div className="min-h-screen bg-slate-50">
        <div className="px-5 lg:px-8 py-6 lg:py-8 max-w-[1200px] mx-auto space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-slate-800 rounded-xl flex items-center justify-center shadow-sm ring-1 ring-slate-700/40">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-[17px] font-semibold text-slate-900 leading-tight">
                  {dash?.company || "Your Portfolio"}
                </h1>
                <p className="text-[11.5px] text-slate-500 mt-0.5">Welcome, {user?.name}</p>
              </div>
            </div>
            <button onClick={fetchData}
              className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors"
              aria-label="Refresh">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {error && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="text-[13px] text-slate-600">{error}</p>
            </div>
          )}

          {!error && (
            <>
              {/* Headline banner */}
              <div className={`rounded-xl border p-5 ${allProtected ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white"}`}>
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${allProtected ? "bg-emerald-100" : "bg-slate-100"}`}>
                    {allProtected ? <CheckCircle2 className="w-5 h-5 text-emerald-500" /> : <Building2 className="w-5 h-5 text-slate-400" />}
                  </div>
                  <div>
                    <p className={`text-[15px] font-semibold ${allProtected ? "text-emerald-800" : "text-slate-800"}`}>
                      {dash?.headline || `${p.total || 0} locations`}
                    </p>
                    <p className={`text-[13px] mt-0.5 ${allProtected ? "text-emerald-700" : "text-slate-500"}`}>
                      {allProtected
                        ? "All locations are Protected and monitored by Manley Solutions."
                        : "Manley Solutions is actively managing your locations."}
                    </p>
                  </div>
                </div>
              </div>

              {/* Status cards */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                <StatusCard label="Locations" value={p.total || 0} />
                <StatusCard label="Protected" value={p.protected || 0} tone={(p.protected || 0) > 0 ? "emerald" : "slate"} />
                <StatusCard label="Attention" value={p.attention_needed || 0} tone={(p.attention_needed || 0) > 0 ? "amber" : "slate"} />
                <StatusCard label="Critical" value={p.critical || 0} tone={(p.critical || 0) > 0 ? "red" : "slate"} />
                <StatusCard label="Setting Up" value={p.pending_install || 0} tone={(p.pending_install || 0) > 0 ? "blue" : "slate"} />
              </div>

              {/* Attention feed */}
              {feed.length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-100">
                    <h2 className="text-[13px] font-semibold text-slate-900">Needs Attention</h2>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {feed.map((it) => (
                      <div key={it.location_ref} className="flex items-center gap-3 px-5 py-3.5">
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${styleFor(it.status).dot}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] text-slate-900 font-medium leading-tight">{it.location}</p>
                          <p className="text-[11.5px] text-slate-500 mt-0.5">{it.reason || it.action}</p>
                        </div>
                        <StatusChip status={it.status} />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Locations */}
              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
                  <h2 className="text-[13px] font-semibold text-slate-900">Your Locations</h2>
                  <span className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-slate-400 tabular-nums">
                    {locations.length} {locations.length === 1 ? "location" : "locations"}
                  </span>
                </div>
                <div className="divide-y divide-slate-100 max-h-[560px] overflow-y-auto">
                  {locations.length === 0 && (
                    <div className="px-5 py-10 text-center text-xs text-slate-400">No locations yet.</div>
                  )}
                  {locations.map((loc) => (
                    <button key={loc.location_ref} type="button"
                      onClick={() => setDrawer({ ref: loc.location_ref, name: loc.location })}
                      className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 transition-colors text-left">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${styleFor(loc.protection?.status).dot}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] font-medium text-slate-900 truncate leading-tight">{loc.location}</p>
                        <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-500">
                          {(loc.city || loc.state) && <span>{[loc.city, loc.state].filter(Boolean).join(", ")}</span>}
                          <span className={styleFor(loc.protection?.status).text}>{loc.protection?.status || "Unknown"}</span>
                          {loc.emergency_address_state && (
                            <span className={loc.emergency_address_state === "Verified" ? "text-emerald-600" : "text-amber-600"}>
                              E911: {loc.emergency_address_state}
                            </span>
                          )}
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {drawer && (
        <E911Drawer locationRef={drawer.ref} locationName={drawer.name} onClose={() => setDrawer(null)} />
      )}
    </PageWrapper>
  );
}
