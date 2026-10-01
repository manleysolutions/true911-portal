import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import {
  Shield, RefreshCw, MapPin, ChevronRight, Search, List as ListIcon, Map as MapIcon,
  UserCheck, Wrench,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import LocationCommandCenter from "@/components/customer/LocationCommandCenter";
import ActionCenter from "@/components/customer/ActionCenter";
import { portfolioHero, locationOperational, customerLocationName } from "@/components/customer/selfService";
import { mapMarkers, pointsSignature, filterLocations } from "@/components/customer/portfolioMap";
import { TILE_CONFIG, TILE_FAILURE_THRESHOLD } from "@/lib/mapTiles";

// ════════════════════════════════════════════════════════════════════
// CustomerAssuranceView — the customer's portfolio home.
//
// Answers, in order: (1) what is the operational condition of my portfolio,
// (2) is anything KNOWN to be wrong, (3) what do I need to do, (4) what is
// True911 still working on, (5) where do I drill in.
//
// Customer trust rule (DECISIONS D-022): KNOWN GOOD · KNOWN PROBLEM · UNKNOWN.
// A location without linked monitoring is "Monitoring record being confirmed"
// (neutral, True911's work) — never
// "unprotected"; nothing is green without evidence.  No blended health score is
// shown to customers: service status, monitoring coverage, E911 readiness and
// portfolio setup are separate dimensions.
//
// Data: GET /customer/portfolio/summary, /customer/locations, /customer/search,
// and (self-service) /customer/action-center — 404 there just hides actions.
// ════════════════════════════════════════════════════════════════════

const TONE = {
  good:    { dot: "bg-emerald-500", text: "text-emerald-700", hex: "#10b981", ring: "" },
  problem: { dot: "bg-amber-500",   text: "text-amber-700",   hex: "#f59e0b", ring: "" },
  urgent:  { dot: "bg-red-500",     text: "text-red-700",     hex: "#ef4444", ring: "" },
  // neutral = unknown / incomplete evidence: hollow grey, never red or green
  neutral: { dot: "bg-white border border-slate-400", text: "text-slate-500", hex: "#cbd5e1", ring: "#94a3b8" },
};
const MAP_LEGEND = [["Monitored", "good"], ["Needs attention", "problem"], ["Being confirmed by True911", "neutral"]];
const e911Text = (state) => (state === "Verified" ? "text-emerald-700" : "text-slate-500");

// Backend caps /customer/locations page_size at 100 — fetch every page.
const LOCATIONS_PAGE_SIZE = 100;

// Normalize legacy-Site and registry-backed items to one shape.
function normLocation(it) {
  return {
    ...it,
    location_ref: it.building_ref || it.location_ref,
    location: customerLocationName(it.display_name || it.canonical_name || it.location),
    op: locationOperational(it),
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

// ── Portfolio hero ───────────────────────────────────────────────────
const DIM_TONE = {
  good: "border-emerald-200 bg-emerald-50/40",
  problem: "border-amber-300 bg-amber-50/60",
  neutral: "border-slate-200 bg-white",
};

function PortfolioHero({ name, summary, actionCenter }) {
  const hero = portfolioHero(summary, actionCenter);
  return (
    <section aria-label="Portfolio overview" className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div className="min-w-[200px]">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.08em]">Life-Safety Portfolio</p>
          <h1 className="text-[18px] font-semibold text-slate-900 leading-tight">{name}</h1>
        </div>
        <dl className="flex flex-wrap gap-x-8 gap-y-2">
          {hero.facts.map((f) => (
            <div key={f.key}>
              <dt className="text-[11px] text-slate-500">{f.label}</dt>
              <dd className={f.pending
                ? "text-[14px] font-medium text-slate-600 leading-none pt-1.5"
                : "text-[22px] font-semibold text-slate-900 tabular-nums leading-none"}>{f.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {hero.dimensions.map((d) => (
          <div key={d.key} className={`rounded-lg border px-3.5 py-3 ${DIM_TONE[d.tone] || DIM_TONE.neutral}`}>
            <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.07em]">{d.title}</p>
            <p className={`text-[14px] font-semibold mt-1 ${d.tone === "problem" ? "text-amber-800" : d.tone === "good" ? "text-emerald-800" : "text-slate-900"}`}>{d.value}</p>
            <p className="text-[11px] text-slate-500 mt-0.5">{d.detail}</p>
          </div>
        ))}
      </div>

      {(hero.customerActions.length > 0 || hero.operationsActions.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
          <div className="flex items-start gap-2.5">
            <UserCheck className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-[12px] font-semibold text-slate-800">For you</p>
              <p className="text-[12px] text-slate-600">{hero.customerActions.map((a) => a.text).join(" · ") || "Nothing right now."}</p>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <Wrench className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-[12px] font-semibold text-slate-800">True911 is working on</p>
              <p className="text-[12px] text-slate-600">{hero.operationsActions.map((a) => a.text).join(" · ") || "Nothing outstanding."}</p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ── Map ──────────────────────────────────────────────────────────────
// Refit only when the plotted point SET changes (signature), not on every
// render — hover, the 60 s refresh and drawer state all re-render the map.
function FitBounds({ points, signature }) {
  const map = useMap();
  const pointsRef = useRef(points);
  pointsRef.current = points;
  useEffect(() => {
    const pts = pointsRef.current;
    if (pts.length === 0) return;
    if (pts.length === 1) { map.setView(pts[0], 11); return; }
    map.fitBounds(pts, { padding: [40, 40], maxZoom: 12 });
  }, [signature, map]);
  return null;
}

function PortfolioMap({ locations, highlightRef, onSelect, onHover }) {
  const { markers, hidden } = useMemo(() => mapMarkers(locations), [locations]);
  const signature = pointsSignature(markers);
  const points = useMemo(() => markers.map((m) => m.point), [markers]);
  // Basemap failure: markers and the list stay accurate; say so plainly.
  const [tiles, setTiles] = useState({ loaded: 0, failed: 0 });
  const tileEvents = useMemo(() => ({
    tileload: () => setTiles((t) => (t.loaded ? t : { ...t, loaded: 1 })),
    tileerror: () => setTiles((t) => (t.failed >= TILE_FAILURE_THRESHOLD ? t : { ...t, failed: t.failed + 1 })),
  }), []);
  const basemapDown = tiles.loaded === 0 && tiles.failed >= TILE_FAILURE_THRESHOLD;
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="relative h-[480px] w-full">
        {markers.length === 0 ? (
          <div className="h-full flex items-center justify-center"><p className="text-xs text-slate-400">No locations have map coordinates yet.</p></div>
        ) : (
          <MapContainer center={[38.5, -97]} zoom={4} className="h-full w-full" style={{ background: "#e8ecf1" }} zoomControl={false}>
            <TileLayer attribution={TILE_CONFIG.attribution} url={TILE_CONFIG.url} maxZoom={TILE_CONFIG.maxZoom} eventHandlers={tileEvents} />
            <FitBounds points={points} signature={signature} />
            {markers.map(({ loc: l, point }) => {
              const hl = highlightRef === l.location_ref;
              const t = TONE[l.op.tone];
              return (
                <CircleMarker key={l.location_ref} center={point}
                  radius={hl ? 12 : 8}
                  pathOptions={{ fillColor: t.hex, color: hl ? "#1f2937" : (t.ring || "#fff"), weight: hl ? 3 : 2, fillOpacity: 0.9 }}
                  eventHandlers={{ click: () => onSelect({ ref: l.location_ref, name: l.location }), mouseover: () => onHover(l.location_ref), mouseout: () => onHover(null) }}>
                  <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
                    <div style={{ fontFamily: "inherit", fontSize: 12 }}><strong>{l.location}</strong><br /><span style={{ color: "#6b7280" }}>{l.op.label}</span></div>
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </MapContainer>
        )}
        {basemapDown && markers.length > 0 && (
          <div role="status" className="absolute top-3 left-1/2 -translate-x-1/2 bg-white/95 rounded-lg border border-slate-200 shadow-sm px-3 py-1.5 text-[11px] text-slate-600" style={{ zIndex: 500 }}>
            Map background is temporarily unavailable. Location markers and the list are unaffected.
          </div>
        )}
        <div className="absolute bottom-3 left-3 bg-white/95 backdrop-blur rounded-lg border border-slate-200 shadow-sm px-3 py-2" style={{ zIndex: 500 }}>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {MAP_LEGEND.map(([label, tone]) => (
              <span key={label} className="inline-flex items-center gap-1 text-[10px] text-slate-600"><span className={`w-2 h-2 rounded-full ${TONE[tone].dot}`} />{label}</span>
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
  const [actionCenter, setActionCenter] = useState(null);
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

  // Permanent, shareable, customer-safe deep-link: ?location=<ref>.
  const openLocation = useCallback((loc) => {
    setDrawer(loc);
    const next = new URLSearchParams(searchParams);
    next.set("location", loc.ref);
    setSearchParams(next, { replace: false });
  }, [searchParams, setSearchParams]);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [s, items, ac] = await Promise.all([
        apiFetch("/customer/portfolio/summary"),
        fetchAllLocations(),
        apiFetch("/customer/action-center").then((r) => r.data).catch(() => null),
      ]);
      setSummary(s.data);
      setLocations(items);
      setActionCenter(ac);
    } catch (e) {
      setError(e.status === 404 ? "Your portal is being finalized. Please check back shortly." : (e.message || "Unable to load your dashboard right now."));
    } finally {
      setLoading(false);
    }
  }, []);

  const closeLocation = useCallback(() => {
    setDrawer(null);
    const next = new URLSearchParams(searchParams);
    next.delete("location");
    setSearchParams(next, { replace: true });
    fetchData();                       // reflect anything done in the location
  }, [searchParams, setSearchParams, fetchData]);

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 60000);
    return () => clearInterval(t);
  }, [fetchData]);

  useEffect(() => {
    const ref = searchParams.get("location");
    if (ref) {
      setDrawer((cur) => (cur && cur.ref === ref) ? cur : { ref, name: locations.find((l) => l.location_ref === ref)?.location });
    } else {
      setDrawer((cur) => (cur ? null : cur));
    }
  }, [searchParams, locations]);

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

  const statusOptions = useMemo(() => Array.from(new Set(locations.map((l) => l.op.label))).sort(), [locations]);
  const e911Options = useMemo(() => Array.from(new Set(locations.map((l) => l.emergency_address_state).filter(Boolean))).sort(), [locations]);
  const filtered = useMemo(() => filterLocations(locations, { status: statusFilter, e911: e911Filter }),
    [locations, statusFilter, e911Filter]);

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
  const selectCls = "px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300";

  return (
    <PageWrapper>
      <div className="min-h-screen bg-slate-50">
        <div className="px-5 lg:px-8 py-6 lg:py-8 max-w-[1240px] mx-auto space-y-5">

          {/* Toolbar: welcome + enterprise search */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 bg-slate-800 rounded-lg flex items-center justify-center"><Shield className="w-4 h-4 text-white" /></div>
              <p className="text-[12px] text-slate-500">Welcome, {user?.name}</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input type="text" aria-label="Search locations" placeholder="Search locations, phone #, service…" value={search} onChange={(e) => setSearch(e.target.value)}
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
              <PortfolioHero name={m.portfolio_name || "Your Portfolio"} summary={m} actionCenter={actionCenter} />

              <ActionCenter data={actionCenter} onOpenLocation={openLocation} />

              {/* Locations — drill-down */}
              <section aria-label="Locations" className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-5 py-3.5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
                  <h2 className="text-[13px] font-semibold text-slate-900">Locations</h2>
                  <div className="flex items-center gap-2">
                    <select aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={selectCls}>
                      <option value="all">All statuses</option>{statusOptions.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <select aria-label="Filter by E911" value={e911Filter} onChange={(e) => setE911Filter(e.target.value)} className={selectCls}>
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
                        className={`w-full flex items-center gap-3 px-5 py-3 transition-colors text-left ${highlightRef === loc.location_ref ? "bg-slate-50" : "hover:bg-slate-50"}`}>
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${TONE[loc.op.tone].dot}`} aria-hidden="true" />
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-medium text-slate-900 truncate leading-tight">{loc.location}</p>
                          <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-500">
                            {(loc.city || loc.state) && <span>{[loc.city, loc.state].filter(Boolean).join(", ")}</span>}
                            <span className={TONE[loc.op.tone].text}>{loc.op.label}</span>
                            {loc.emergency_address_state && <span className={e911Text(loc.emergency_address_state)}>E911: {loc.emergency_address_state}</span>}
                          </div>
                        </div>
                        <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>

      {drawer && <LocationCommandCenter locationRef={drawer.ref} locationName={drawer.name} intent={drawer.intent} onClose={closeLocation} />}
    </PageWrapper>
  );
}
