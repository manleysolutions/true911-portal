import { useState, useEffect, useCallback, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import {
  Shield, Building2, RefreshCw, CheckCircle2, AlertTriangle,
  MapPin, ChevronRight, X, PhoneCall, Search, List as ListIcon,
  Map as MapIcon, Cpu, Wifi, WifiOff,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";

// ════════════════════════════════════════════════════════════════════
// CustomerAssuranceView
//
// Dashboard for the ISOLATED customer-plane roles (CUSTOMER_ADMIN / MANAGER /
// VIEWER / SUPPORT / …).  Sourced ENTIRELY from the read-only customer Assurance
// API (no /command/summary — those roles hold no INTERNAL_OPS):
//   GET /customer/dashboard             — portfolio counts + attention feed
//   GET /customer/locations             — location list (status + map_point)
//   GET /customer/locations/{ref}       — detail (address, services, devices)
//   GET /customer/locations/{ref}/e911  — E911 record (real stored data)
//
// Operational status is the preview-greened, evidence-backed Assurance label;
// never fabricated and free of any "API/telemetry pending" language.  E911 is
// the safety-critical axis — always the truth, never preview-greened, and shown
// calmly (amber, not alarming) when "Not yet verified".
// ════════════════════════════════════════════════════════════════════

// Six-label vocabulary -> calm treatment + map hex.
const STATUS_STYLE = {
  "Protected":        { dot: "bg-emerald-500", text: "text-emerald-700", chip: "bg-emerald-50 border-emerald-200 text-emerald-800", hex: "#10b981", icon: CheckCircle2 },
  "Attention Needed": { dot: "bg-amber-500",   text: "text-amber-700",   chip: "bg-amber-50 border-amber-200 text-amber-800",     hex: "#f59e0b", icon: AlertTriangle },
  "Critical":         { dot: "bg-red-500",     text: "text-red-700",     chip: "bg-red-50 border-red-200 text-red-800",           hex: "#ef4444", icon: AlertTriangle },
  "Pending Install":  { dot: "bg-blue-500",    text: "text-blue-700",    chip: "bg-blue-50 border-blue-200 text-blue-800",        hex: "#3b82f6", icon: MapPin },
  "Inactive":         { dot: "bg-slate-400",   text: "text-slate-600",   chip: "bg-slate-50 border-slate-200 text-slate-700",     hex: "#94a3b8", icon: MapPin },
  "Unknown":          { dot: "bg-slate-400",   text: "text-slate-600",   chip: "bg-slate-50 border-slate-200 text-slate-700",     hex: "#94a3b8", icon: MapPin },
};
const styleFor = (s) => STATUS_STYLE[s] || STATUS_STYLE["Unknown"];

// E911 state -> calm treatment.  "Not yet verified" is amber (informative), not
// red — visible but never alarming (req 8). "Verified" is emerald.
function e911Tone(state) {
  if (state === "Verified") return { text: "text-emerald-700", chip: "bg-emerald-50 border-emerald-200 text-emerald-800", icon: CheckCircle2 };
  return { text: "text-amber-700", chip: "bg-amber-50 border-amber-200 text-amber-800", icon: AlertTriangle };
}

function StatusChip({ status }) {
  const s = styleFor(status);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium ${s.chip}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />{status}
    </span>
  );
}

function StatusCard({ label, value, tone = "slate" }) {
  const toneMap = {
    slate: "border-slate-200 bg-white", emerald: "border-emerald-200 bg-emerald-50/50",
    amber: "border-amber-200 bg-amber-50/50", red: "border-red-200 bg-red-50/50",
    blue: "border-blue-200 bg-blue-50/50",
  };
  return (
    <div className={`rounded-xl border px-4 py-3.5 ${toneMap[tone] || toneMap.slate}`}>
      <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-2">{label}</p>
      <p className="text-[26px] font-semibold text-slate-900 tabular-nums leading-none">{value ?? "—"}</p>
    </div>
  );
}

// ── Location detail drawer — detail + E911 from the customer API ─────
function LocationDrawer({ locationRef, locationName, onClose }) {
  const [detail, setDetail] = useState(null);
  const [e911, setE911] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [d, e] = await Promise.all([
          apiFetch(`/customer/locations/${encodeURIComponent(locationRef)}`),
          apiFetch(`/customer/locations/${encodeURIComponent(locationRef)}/e911`),
        ]);
        if (alive) { setDetail(d.data); setE911(e.data); }
      } catch (err) {
        if (alive) setError(err.message || "Unable to load this location");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [locationRef]);

  const v = e911?.verification || {};
  const vTone = e911Tone(detail?.emergency_address_state);

  return (
    <div className="fixed inset-0 z-[1000] flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-slate-900/30" />
      <div className="relative w-full max-w-md bg-white h-full shadow-xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 sticky top-0 bg-white z-10">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-slate-900 truncate">{detail?.location || locationName}</h2>
            {detail?.building_type && <p className="text-[11.5px] text-slate-500">{detail.building_type}</p>}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-5 space-y-5">
          {loading && <p className="text-xs text-slate-400">Loading…</p>}
          {error && <p className="text-xs text-red-600">{error}</p>}

          {detail && (
            <>
              {/* Operational status */}
              <div className="flex items-center justify-between">
                <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em]">Status</p>
                <StatusChip status={detail.protection?.status || "Unknown"} />
              </div>

              {/* Service address */}
              <div>
                <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-1">Service address</p>
                <p className="text-[13px] text-slate-900">
                  {detail.service_address || <span className="text-slate-400">Not yet on file</span>}
                </p>
              </div>

              {/* E911 — always the truth; calm amber when not verified */}
              <div className={`rounded-lg border p-3 ${vTone.chip}`}>
                <div className="flex items-center gap-2">
                  <vTone.icon className={`w-4 h-4 ${vTone.text}`} />
                  <p className={`text-[13px] font-medium ${vTone.text}`}>
                    Emergency address: {detail.emergency_address_state || (v.verified ? "Verified" : "Not yet verified")}
                  </p>
                </div>
                {e911?.emergency_dispatch_address && (
                  <p className="text-[12px] text-slate-600 mt-1">{e911.emergency_dispatch_address}</p>
                )}
                {!v.verified && (
                  <p className="text-[11.5px] text-slate-500 mt-1">Manley Solutions is verifying this emergency address.</p>
                )}
              </div>

              {/* Emergency endpoints (real service-unit / line data) */}
              {(e911?.emergency_endpoints || []).length > 0 && (
                <div>
                  <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-2">Emergency endpoints</p>
                  <div className="space-y-2">
                    {e911.emergency_endpoints.map((ep, i) => (
                      <div key={i} className="rounded-lg border border-slate-200 p-3">
                        <p className="text-[13px] font-medium text-slate-900">{ep.service_type}</p>
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11.5px] text-slate-600">
                          {ep.where && <span>{ep.where}</span>}
                          {ep.floor && <span>Floor {ep.floor}</span>}
                          {ep.callback_number && <span className="inline-flex items-center gap-1"><PhoneCall className="w-3 h-3" />{ep.callback_number}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Devices tied to this location (customer-safe) */}
              {(detail.devices || []).length > 0 && (
                <div>
                  <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-2">Devices</p>
                  <div className="space-y-2">
                    {detail.devices.map((dev, i) => (
                      <div key={i} className="rounded-lg border border-slate-200 p-3">
                        <div className="flex items-center justify-between">
                          <p className="text-[13px] font-medium text-slate-900 inline-flex items-center gap-1.5">
                            <Cpu className="w-3.5 h-3.5 text-slate-400" />{dev.equipment}
                          </p>
                          <span className={`inline-flex items-center gap-1 text-[11px] ${dev.health === "Online" ? "text-emerald-600" : "text-slate-500"}`}>
                            {dev.health === "Online" ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}{dev.health}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11.5px] text-slate-600">
                          {dev.model && <span>{dev.model}</span>}
                          {dev.identifier && <span className="inline-flex items-center gap-1"><PhoneCall className="w-3 h-3" />{dev.identifier}</span>}
                          {dev.in_service_since && <span>In service since {dev.in_service_since.slice(0, 10)}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(e911?.customer_actions || []).length > 0 && (
                <p className="text-[11px] text-slate-500 pt-1">
                  Need a correction? {e911.customer_actions.join(" · ")} — contact Manley Solutions.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Map ──────────────────────────────────────────────────────────────
function LocationsMap({ locations, onSelect }) {
  const mappable = locations.filter((l) => l.map_point);
  const hidden = locations.length - mappable.length;
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="h-[460px] w-full">
        {mappable.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-slate-400">No locations have map coordinates yet.</p>
          </div>
        ) : (
          <MapContainer center={[38.5, -97]} zoom={4} className="h-full w-full" style={{ background: "#e8ecf1" }} zoomControl={false}>
            <TileLayer
              attribution='&copy; <a href="https://carto.com">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
              url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            />
            {mappable.map((l) => (
              <CircleMarker
                key={l.location_ref}
                center={[l.map_point.lat, l.map_point.lng]}
                radius={8}
                pathOptions={{ fillColor: styleFor(l.protection?.status).hex, color: "#fff", weight: 2, fillOpacity: 0.9 }}
                eventHandlers={{ click: () => onSelect({ ref: l.location_ref, name: l.location }) }}
              >
                <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
                  <div style={{ fontFamily: "inherit", fontSize: 12, lineHeight: 1.4 }}>
                    <strong>{l.location}</strong><br />
                    <span style={{ color: "#6b7280" }}>{[l.city, l.state].filter(Boolean).join(", ")}</span>
                  </div>
                </Tooltip>
              </CircleMarker>
            ))}
          </MapContainer>
        )}
      </div>
      {hidden > 0 && (
        <div className="px-4 py-2 border-t border-slate-100 text-[11px] text-slate-500">
          {hidden} location{hidden === 1 ? "" : "s"} not shown on the map (no coordinates on file).
        </div>
      )}
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
  const [view, setView] = useState("list");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [e911Filter, setE911Filter] = useState("all");

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

  const statusOptions = useMemo(
    () => Array.from(new Set(locations.map((l) => l.protection?.status).filter(Boolean))).sort(),
    [locations]);
  const e911Options = useMemo(
    () => Array.from(new Set(locations.map((l) => l.emergency_address_state).filter(Boolean))).sort(),
    [locations]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return locations.filter((l) => {
      if (statusFilter !== "all" && l.protection?.status !== statusFilter) return false;
      if (e911Filter !== "all" && l.emergency_address_state !== e911Filter) return false;
      if (q) {
        const hay = `${l.location || ""} ${l.city || ""} ${l.state || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [locations, search, statusFilter, e911Filter]);

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
  // Customer-safe headline — no exact timestamp (req 8).
  const headline = allProtected
    ? "All listed locations are currently protected."
    : `${p.protected || 0} of ${p.total || 0} locations protected.`;

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
                <h1 className="text-[17px] font-semibold text-slate-900 leading-tight">{dash?.company || "Your Portfolio"}</h1>
                <p className="text-[11.5px] text-slate-500 mt-0.5">Welcome, {user?.name}</p>
              </div>
            </div>
            <button onClick={fetchData} className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors" aria-label="Refresh">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {error && (
            <div className="rounded-xl border border-slate-200 bg-white p-5"><p className="text-[13px] text-slate-600">{error}</p></div>
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
                    <p className={`text-[15px] font-semibold ${allProtected ? "text-emerald-800" : "text-slate-800"}`}>{headline}</p>
                    <p className={`text-[13px] mt-0.5 ${allProtected ? "text-emerald-700" : "text-slate-500"}`}>
                      {allProtected ? "Monitored by Manley Solutions." : "Manley Solutions is actively managing your locations."}
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
                  <div className="px-5 py-3.5 border-b border-slate-100"><h2 className="text-[13px] font-semibold text-slate-900">Needs Attention</h2></div>
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

              {/* Locations — search / filters + list|map toggle */}
              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-5 py-3.5 border-b border-slate-100 space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-[13px] font-semibold text-slate-900">Your Locations</h2>
                    <div className="flex items-center gap-2">
                      <span className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-slate-400 tabular-nums">
                        {filtered.length} of {locations.length}
                      </span>
                      <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                        <button onClick={() => setView("list")} className={`px-2 py-1 ${view === "list" ? "bg-slate-800 text-white" : "bg-white text-slate-500"}`} aria-label="List view"><ListIcon className="w-3.5 h-3.5" /></button>
                        <button onClick={() => setView("map")} className={`px-2 py-1 ${view === "map" ? "bg-slate-800 text-white" : "bg-white text-slate-500"}`} aria-label="Map view"><MapIcon className="w-3.5 h-3.5" /></button>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="relative flex-1">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                      <input type="text" placeholder="Search name, city, or state…" value={search} onChange={(e) => setSearch(e.target.value)}
                        className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300" />
                    </div>
                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                      className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300">
                      <option value="all">All statuses</option>
                      {statusOptions.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <select value={e911Filter} onChange={(e) => setE911Filter(e.target.value)}
                      className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300">
                      <option value="all">All E911</option>
                      {e911Options.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                </div>

                {view === "map" ? (
                  <div className="p-4"><LocationsMap locations={filtered} onSelect={setDrawer} /></div>
                ) : (
                  <div className="divide-y divide-slate-100 max-h-[560px] overflow-y-auto">
                    {filtered.length === 0 && <div className="px-5 py-10 text-center text-xs text-slate-400">No locations match your filters.</div>}
                    {filtered.map((loc) => (
                      <button key={loc.location_ref} type="button" onClick={() => setDrawer({ ref: loc.location_ref, name: loc.location })}
                        className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 transition-colors text-left">
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${styleFor(loc.protection?.status).dot}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-medium text-slate-900 truncate leading-tight">{loc.location}</p>
                          <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-500">
                            {(loc.city || loc.state) && <span>{[loc.city, loc.state].filter(Boolean).join(", ")}</span>}
                            <span className={styleFor(loc.protection?.status).text}>{loc.protection?.status || "Unknown"}</span>
                            {loc.emergency_address_state && (
                              <span className={e911Tone(loc.emergency_address_state).text}>E911: {loc.emergency_address_state}</span>
                            )}
                          </div>
                        </div>
                        <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {drawer && <LocationDrawer locationRef={drawer.ref} locationName={drawer.name} onClose={() => setDrawer(null)} />}
    </PageWrapper>
  );
}
