import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import {
  Shield, Building2, RefreshCw, CheckCircle2, AlertTriangle, ShieldCheck,
  MapPin, ChevronRight, Search, List as ListIcon, Map as MapIcon, Cpu,
  PhoneCall, Activity, Wrench, Gauge,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import LocationCommandCenter from "@/components/customer/LocationCommandCenter";

// ════════════════════════════════════════════════════════════════════
// CustomerAssuranceView — the Customer Command Center (Phase 1/2/3).
//
// Sourced entirely from the read-only /api/customer Command Center API:
//   GET /customer/portfolio/summary  — executive metrics + health score
//   GET /customer/locations          — location list + map points
//   GET /customer/search             — enterprise search
// Life-safety first: an enterprise customer understands their whole portfolio
// in <30s without ever thinking about devices.
// ════════════════════════════════════════════════════════════════════

const STATUS_STYLE = {
  "Protected":        { dot: "bg-emerald-500", text: "text-emerald-700", hex: "#10b981" },
  "Attention Needed": { dot: "bg-amber-500",   text: "text-amber-700",   hex: "#f59e0b" },
  "Critical":         { dot: "bg-red-500",     text: "text-red-700",     hex: "#ef4444" },
  "Pending Install":  { dot: "bg-blue-500",    text: "text-blue-700",    hex: "#3b82f6" },
  "Inactive":         { dot: "bg-slate-400",   text: "text-slate-600",   hex: "#94a3b8" },
  "Unknown":          { dot: "bg-slate-400",   text: "text-slate-600",   hex: "#94a3b8" },
};
const styleFor = (s) => STATUS_STYLE[s] || STATUS_STYLE.Unknown;
const e911Text = (state) => (state === "Verified" ? "text-emerald-600" : "text-amber-600");
const MAP_LEGEND = ["Protected", "Attention Needed", "Critical", "Pending Install", "Unknown"];

// Backend caps /customer/locations page_size at 100.  Fetch every page (100 at a
// time) and accumulate, so portfolios larger than one page load fully — RH has
// 42, but this stays correct for any size.  Requesting >100 returns a 422 and
// blanks the dashboard (the bug this fixes).
const LOCATIONS_PAGE_SIZE = 100;

// Normalize a location/building item to one shape the UI reads, so the same
// components render whether the backend is in legacy-Site mode (location_ref /
// location) or registry-backed mode (building_ref / display_name).  Registry-backed
// items already carry customer-safe names only — no source-system internals.
function normLocation(it) {
  return {
    ...it,
    location_ref: it.building_ref || it.location_ref,
    location: it.display_name || it.canonical_name || it.location,
    emergency_address_state: it.emergency_address_state,
  };
}

async function fetchAllLocations() {
  const first = await apiFetch(`/customer/locations?page=1&page_size=${LOCATIONS_PAGE_SIZE}`);
  const d = first.data || {};
  let items = d.items || [];
  const total = d.total ?? items.length;
  const pages = Math.ceil(total / LOCATIONS_PAGE_SIZE);
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, i) =>
        apiFetch(`/customer/locations?page=${i + 2}&page_size=${LOCATIONS_PAGE_SIZE}`)
          .then((r) => r.data?.items || [])
          .catch(() => [])),
    );
    items = items.concat(...rest);
  }
  return items.map(normLocation);
}

function Metric({ label, value, sub, tone = "slate", icon: Icon }) {
  const toneMap = {
    slate: "border-slate-200 bg-white", emerald: "border-emerald-200 bg-emerald-50/50",
    amber: "border-amber-200 bg-amber-50/50", red: "border-red-200 bg-red-50/50",
    blue: "border-blue-200 bg-blue-50/50",
  };
  return (
    <div className={`rounded-xl border px-4 py-3.5 ${toneMap[tone] || toneMap.slate}`}>
      <div className="flex items-center gap-1.5 mb-2">
        {Icon && <Icon className="w-3.5 h-3.5 text-slate-400" />}
        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.07em]">{label}</p>
      </div>
      <p className="text-[24px] font-semibold text-slate-900 tabular-nums leading-none">{value ?? "—"}</p>
      {sub && <p className="text-[10.5px] text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

function HealthGauge({ health }) {
  if (!health) return null;
  const { score, confidence, grade } = health;
  const toneMap = { Excellent: "text-emerald-600", Good: "text-emerald-600", Fair: "text-amber-600", "Needs attention": "text-red-600", Unknown: "text-slate-500" };
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3.5">
      <div className="flex items-center gap-1.5 mb-2"><Gauge className="w-3.5 h-3.5 text-slate-400" /><p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.07em]">Monthly Health</p></div>
      <p className={`text-[24px] font-semibold tabular-nums leading-none ${toneMap[grade] || "text-slate-900"}`}>
        {score != null ? score : "—"}<span className="text-[13px] text-slate-400">{score != null ? "/100" : ""}</span>
      </p>
      <p className="text-[10.5px] text-slate-400 mt-1">{grade}{confidence != null ? ` · ${confidence}% confidence` : ""}</p>
    </div>
  );
}

// Fit the map to all pins whenever the set changes.
function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) { map.setView(points[0], 11); return; }
    map.fitBounds(points, { padding: [40, 40], maxZoom: 12 });
  }, [points, map]);
  return null;
}

function PortfolioMap({ locations, highlightRef, onSelect, onHover }) {
  const mappable = locations.filter((l) => l.map_point);
  const points = useMemo(() => mappable.map((l) => [l.map_point.lat, l.map_point.lng]), [mappable]);
  const hidden = locations.length - mappable.length;
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="relative h-[480px] w-full">
        {mappable.length === 0 ? (
          <div className="h-full flex items-center justify-center"><p className="text-xs text-slate-400">No locations have map coordinates yet.</p></div>
        ) : (
          <MapContainer center={[38.5, -97]} zoom={4} className="h-full w-full" style={{ background: "#e8ecf1" }} zoomControl={false}>
            <TileLayer attribution='&copy; <a href="https://carto.com">CARTO</a> &copy; OSM' url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" />
            <FitBounds points={points} />
            {mappable.map((l) => {
              const hl = highlightRef === l.location_ref;
              return (
                <CircleMarker key={l.location_ref} center={[l.map_point.lat, l.map_point.lng]}
                  radius={hl ? 12 : 8}
                  pathOptions={{ fillColor: styleFor(l.protection?.status).hex, color: hl ? "#1f2937" : "#fff", weight: hl ? 3 : 2, fillOpacity: 0.9 }}
                  eventHandlers={{ click: () => onSelect({ ref: l.location_ref, name: l.location }), mouseover: () => onHover(l.location_ref), mouseout: () => onHover(null) }}>
                  <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
                    <div style={{ fontFamily: "inherit", fontSize: 12 }}><strong>{l.location}</strong><br /><span style={{ color: "#6b7280" }}>{[l.city, l.state].filter(Boolean).join(", ")}</span></div>
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </MapContainer>
        )}
        {/* Legend */}
        <div className="absolute bottom-3 left-3 bg-white/95 backdrop-blur rounded-lg border border-slate-200 shadow-sm px-3 py-2" style={{ zIndex: 500 }}>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {MAP_LEGEND.map((s) => (
              <span key={s} className="inline-flex items-center gap-1 text-[10px] text-slate-600"><span className="w-2 h-2 rounded-full" style={{ background: styleFor(s).hex }} />{s}</span>
            ))}
          </div>
        </div>
      </div>
      {hidden > 0 && <div className="px-4 py-2 border-t border-slate-100 text-[11px] text-slate-500">{hidden} location{hidden === 1 ? "" : "s"} not shown on the map (no coordinates on file).</div>}
    </div>
  );
}

export default function CustomerAssuranceView() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const [view, setView] = useState("list");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [e911Filter, setE911Filter] = useState("all");
  const [highlightRef, setHighlightRef] = useState(null);
  const [searchResults, setSearchResults] = useState(null);
  const searchAbort = useRef(0);
  const [searchParams, setSearchParams] = useSearchParams();

  // Permanent, shareable, customer-safe deep-link: ?location=<ref> opens the
  // Location Workspace; the ref is opaque (HMAC-signed, no raw ids).
  const openLocation = useCallback((loc) => {
    setDrawer(loc);
    const next = new URLSearchParams(searchParams);
    next.set("location", loc.ref);
    setSearchParams(next, { replace: false });
  }, [searchParams, setSearchParams]);

  const closeLocation = useCallback(() => {
    setDrawer(null);
    const next = new URLSearchParams(searchParams);
    next.delete("location");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [s, items] = await Promise.all([
        apiFetch("/customer/portfolio/summary"),
        fetchAllLocations(),
      ]);
      setSummary(s.data);
      setLocations(items);
    } catch (e) {
      setError(e.status === 404 ? "Your portal is being finalized. Please check back shortly." : (e.message || "Unable to load your dashboard right now."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 60000);
    return () => clearInterval(t);
  }, [fetchData]);

  // Open the workspace from a shared/deep-linked ?location=<ref> URL.
  useEffect(() => {
    const ref = searchParams.get("location");
    if (ref) {
      setDrawer((cur) => (cur && cur.ref === ref) ? cur : { ref, name: locations.find((l) => l.location_ref === ref)?.location });
    } else {
      setDrawer((cur) => (cur ? null : cur));
    }
  }, [searchParams, locations]);

  // Enterprise search (debounced) — server-side across name/city/state/phone/service.
  useEffect(() => {
    const q = search.trim();
    if (q.length < 2) { setSearchResults(null); return; }
    const id = ++searchAbort.current;
    const timer = setTimeout(async () => {
      try {
        const r = await apiFetch(`/customer/search?q=${encodeURIComponent(q)}`);
        if (id === searchAbort.current) setSearchResults((r.data?.results || []).map(normLocation));
      } catch { if (id === searchAbort.current) setSearchResults([]); }
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const statusOptions = useMemo(() => Array.from(new Set(locations.map((l) => l.protection?.status).filter(Boolean))).sort(), [locations]);
  const e911Options = useMemo(() => Array.from(new Set(locations.map((l) => l.emergency_address_state).filter(Boolean))).sort(), [locations]);

  const filtered = useMemo(() => locations.filter((l) => {
    if (statusFilter !== "all" && l.protection?.status !== statusFilter) return false;
    if (e911Filter !== "all" && l.emergency_address_state !== e911Filter) return false;
    return true;
  }), [locations, statusFilter, e911Filter]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-slate-50 flex items-center justify-center">
          <div className="text-center"><div className="w-8 h-8 border-2 border-slate-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" /><p className="text-xs text-slate-400">Loading…</p></div>
        </div>
      </PageWrapper>
    );
  }

  const m = summary || {};
  const health = m.monthly_health_score;
  const allProtected = (m.locations_total || 0) > 0 && (m.critical_sites || 0) === 0 && (m.sites_requiring_attention || 0) === 0;

  return (
    <PageWrapper>
      <div className="min-h-screen bg-slate-50">
        <div className="px-5 lg:px-8 py-6 lg:py-8 max-w-[1240px] mx-auto space-y-6">

          {/* Header + enterprise search */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-slate-800 rounded-xl flex items-center justify-center shadow-sm ring-1 ring-slate-700/40"><Shield className="w-5 h-5 text-white" /></div>
              <div>
                <h1 className="text-[17px] font-semibold text-slate-900 leading-tight">{m.portfolio_name || "Your Portfolio"}</h1>
                <p className="text-[11.5px] text-slate-500 mt-0.5">Life-Safety Command Center · Welcome, {user?.name}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input type="text" placeholder="Search locations, phone #, service…" value={search} onChange={(e) => setSearch(e.target.value)}
                  className="w-64 pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300" />
                {searchResults != null && (
                  <div className="absolute z-30 mt-1 w-80 right-0 bg-white rounded-lg border border-slate-200 shadow-lg max-h-72 overflow-y-auto">
                    {searchResults.length === 0 ? (
                      <p className="px-3 py-2.5 text-[12px] text-slate-400">No matches.</p>
                    ) : searchResults.map((r) => (
                      <button key={r.location_ref} type="button" onClick={() => { openLocation({ ref: r.location_ref, name: r.location }); setSearch(""); setSearchResults(null); }}
                        className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-center gap-2">
                        <MapPin className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span className="min-w-0"><span className="text-[12.5px] text-slate-800 block truncate">{r.location}</span><span className="text-[11px] text-slate-400">{[r.city, r.state].filter(Boolean).join(", ")}</span></span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={fetchData} className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-500" aria-label="Refresh"><RefreshCw className="w-3.5 h-3.5" /></button>
            </div>
          </div>

          {error && <div className="rounded-xl border border-slate-200 bg-white p-5"><p className="text-[13px] text-slate-600">{error}</p></div>}

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
                      {allProtected ? "All listed locations are currently protected." : `${m.locations_protected || 0} of ${m.locations_total || 0} locations protected.`}
                    </p>
                    <p className={`text-[13px] mt-0.5 ${allProtected ? "text-emerald-700" : "text-slate-500"}`}>Continuously monitored.</p>
                  </div>
                </div>
              </div>

              {/* Executive metrics */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                <Metric label="Locations Protected" value={`${m.locations_protected ?? 0}/${m.locations_total ?? 0}`} icon={Building2} tone={allProtected ? "emerald" : "slate"} />
                <Metric label="Life Safety Services" value={m.life_safety_services ?? 0} sub={`${m.protected_services ?? 0} protected`} icon={ShieldCheck} />
                <Metric label="Requires Attention" value={m.sites_requiring_attention ?? 0} icon={AlertTriangle} tone={(m.sites_requiring_attention || 0) > 0 ? "amber" : "slate"} />
                <Metric label="Critical Sites" value={m.critical_sites ?? 0} icon={AlertTriangle} tone={(m.critical_sites || 0) > 0 ? "red" : "slate"} />
                <HealthGauge health={health} />
                <Metric label="Devices" value={m.devices ?? 0} icon={Cpu} />
                <Metric label="Telephone Numbers" value={m.total_phone_numbers ?? 0} icon={PhoneCall} />
                <Metric label="E911 Verified" value={m.e911_verification_pct != null ? `${m.e911_verification_pct}%` : "—"} icon={CheckCircle2} />
                <Metric label="Service Availability" value={m.service_availability_pct != null ? `${m.service_availability_pct}%` : "—"} icon={Activity} />
                <Metric label="Upcoming Maintenance" value={(m.upcoming_maintenance || []).length} icon={Wrench} />
              </div>

              {/* Recent activity */}
              {(m.recent_activity || []).length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-100"><h2 className="text-[13px] font-semibold text-slate-900">Recent Activity</h2></div>
                  <div className="divide-y divide-slate-100">
                    {m.recent_activity.map((it, i) => (
                      <div key={i} className="flex items-center gap-3 px-5 py-2.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${it.kind === "e911_verified" ? "bg-emerald-500" : "bg-slate-300"}`} />
                        <p className="text-[12.5px] text-slate-800 flex-1">{it.title}</p>
                        <span className="text-[11px] text-slate-400 tabular-nums">{it.when} · {it.by}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Locations — filters + list|map (map synced with list highlight) */}
              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-5 py-3.5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
                  <h2 className="text-[13px] font-semibold text-slate-900">Locations</h2>
                  <div className="flex items-center gap-2">
                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300">
                      <option value="all">All statuses</option>{statusOptions.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <select value={e911Filter} onChange={(e) => setE911Filter(e.target.value)} className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300">
                      <option value="all">All E911</option>{e911Options.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <span className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-slate-400 tabular-nums">{filtered.length}/{locations.length}</span>
                    <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                      <button onClick={() => setView("list")} className={`px-2 py-1 ${view === "list" ? "bg-slate-800 text-white" : "bg-white text-slate-500"}`} aria-label="List"><ListIcon className="w-3.5 h-3.5" /></button>
                      <button onClick={() => setView("map")} className={`px-2 py-1 ${view === "map" ? "bg-slate-800 text-white" : "bg-white text-slate-500"}`} aria-label="Map"><MapIcon className="w-3.5 h-3.5" /></button>
                    </div>
                  </div>
                </div>

                {view === "map" ? (
                  <div className="p-4"><PortfolioMap locations={filtered} highlightRef={highlightRef} onSelect={openLocation} onHover={setHighlightRef} /></div>
                ) : (
                  <div className="divide-y divide-slate-100 max-h-[560px] overflow-y-auto">
                    {filtered.length === 0 && <div className="px-5 py-10 text-center text-xs text-slate-400">No locations match your filters.</div>}
                    {filtered.map((loc) => (
                      <button key={loc.location_ref} type="button" onClick={() => openLocation({ ref: loc.location_ref, name: loc.location })}
                        onMouseEnter={() => setHighlightRef(loc.location_ref)} onMouseLeave={() => setHighlightRef(null)}
                        className={`w-full flex items-center gap-3 px-5 py-3.5 transition-colors text-left ${highlightRef === loc.location_ref ? "bg-slate-50" : "hover:bg-slate-50"}`}>
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${styleFor(loc.protection?.status).dot}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-medium text-slate-900 truncate leading-tight">{loc.location}</p>
                          <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-500">
                            {(loc.city || loc.state) && <span>{[loc.city, loc.state].filter(Boolean).join(", ")}</span>}
                            <span className={styleFor(loc.protection?.status).text}>{loc.protection?.status || "Unknown"}</span>
                            {loc.emergency_address_state && <span className={e911Text(loc.emergency_address_state)}>E911: {loc.emergency_address_state}</span>}
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

      {drawer && <LocationCommandCenter locationRef={drawer.ref} locationName={drawer.name} onClose={closeLocation} />}
    </PageWrapper>
  );
}
