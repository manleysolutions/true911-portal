import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { MapPin, ChevronRight, Search, Map as MapIcon, TriangleAlert, X } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { apiFetch } from "@/api/client";
import LocationCommandCenter from "@/components/customer/LocationCommandCenter";
import ActionCenter from "@/components/customer/ActionCenter";
import { locationOperational, customerLocationName } from "@/components/customer/selfService";
import { filterLocations } from "@/components/customer/portfolioMap";
import { statusStatement, opTiles, tokenFor, OP_TOKEN, e911Display, parseView, exceptionsPreview } from "@/components/customer/commandCenter";
import { StatusStatement, OpTile, StatusChip, E911Badge, CommandSkeleton } from "@/components/customer/command/CommandParts";
import CommandMap from "@/components/customer/command/CommandMap";
import { useCustomerNav } from "@/components/customer/command/CustomerShell";

// ════════════════════════════════════════════════════════════════════
// CustomerAssuranceView — the customer's Life-Safety Command Center.
//
// Answers, in order: (1) what is the operational condition of my portfolio,
// (2) is anything KNOWN to be wrong, (3) what do I need to do, (4) what is
// True911 still working on, (5) where — on the map and in the list.
//
// Customer trust rule (DECISIONS D-022): KNOWN GOOD · KNOWN PROBLEM · UNKNOWN.
// A location without linked monitoring is "Monitoring record being confirmed"
// (neutral, True911's work) — never "unprotected"; nothing is green without
// evidence.  No blended health score; no service / connection totals until the
// canonical inventory is certified; no green E911 until it is provider-backed.
// Every word / colour decision lives in commandCenter.js + selfService.js.
//
// Data: GET /customer/portfolio/summary, /customer/locations, /customer/search,
// and (self-service) /customer/action-center — 404 there just hides actions.
// ════════════════════════════════════════════════════════════════════

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

function useIsDesktop() {
  const q = "(min-width: 1024px)";
  const [on, setOn] = useState(() => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(q).matches : true));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(q);
    const fn = (e) => setOn(e.matches);
    mq.addEventListener?.("change", fn);
    return () => mq.removeEventListener?.("change", fn);
  }, []);
  return on;
}

// ── Enterprise search ────────────────────────────────────────────────
function SearchBox({ search, setSearch, searchResults, onPick }) {
  return (
    <div className="relative w-full sm:w-80">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
      <input type="text" aria-label="Search locations" placeholder="Search locations, phone #, service…" value={search} onChange={(e) => setSearch(e.target.value)}
        className="cc-focus w-full h-10 pl-9 pr-3 text-[13px] rounded-lg bg-slate-50 ring-1 ring-inset ring-slate-200 text-slate-800 placeholder-slate-400 focus:bg-white" />
      {searchResults != null && (
        <div className="absolute z-30 mt-1 w-full sm:w-96 right-0 bg-white rounded-xl ring-1 ring-slate-200 shadow-lg max-h-72 overflow-y-auto">
          {searchResults.length === 0 ? (
            <p className="px-3 py-2.5 text-[12px] text-slate-500">No matches.</p>
          ) : searchResults.map((r) => (
            <button key={r.location_ref} type="button" onClick={() => onPick(r)}
              className="cc-focus w-full text-left px-3 py-2.5 min-h-[44px] hover:bg-slate-50 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-slate-400 flex-shrink-0" aria-hidden="true" />
              <span className="min-w-0"><span className="text-[13px] text-slate-800 block truncate">{r.location}</span><span className="text-[11px] text-slate-500">{[r.city, r.state].filter(Boolean).join(", ")}</span></span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── One location row (Overview preview + Locations workspace) ─────────
function LocationRow({ loc, actionRefs, highlightRef, setHighlightRef, onOpen }) {
  const tok = OP_TOKEN[loc.op.tone];
  const needsYou = actionRefs.has(loc.location_ref);
  const e9 = needsYou ? e911Display("customer_confirmation_required")
    : loc.emergency_address_state ? e911Display(loc.emergency_address_state) : null;
  return (
    <li>
      <button type="button" onClick={() => onOpen({ ref: loc.location_ref, name: loc.location })}
        onMouseEnter={() => setHighlightRef(loc.location_ref)} onMouseLeave={() => setHighlightRef(null)}
        onFocus={() => setHighlightRef(loc.location_ref)} onBlur={() => setHighlightRef(null)}
        className={`cc-focus w-full flex items-center gap-3 px-4 sm:px-5 py-3 min-h-[56px] text-left transition-colors ${highlightRef === loc.location_ref ? "bg-slate-50" : "hover:bg-slate-50"}`}>
        <span className={`w-1 self-stretch rounded-full ${tokenFor(loc.op.tone).accent}`} aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <p className="text-[13.5px] font-medium text-slate-900 truncate leading-tight">{loc.location}</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[11.5px] text-slate-500">
            {(loc.city || loc.state) && <span>{[loc.city, loc.state].filter(Boolean).join(", ")}</span>}
            <StatusChip token={tok}>{loc.op.label}</StatusChip>
            {e9 && <span className="inline-flex items-center gap-1"><E911Badge />
              {needsYou ? <StatusChip token="attention">{e9.label}</StatusChip> : <span className="text-slate-600">{e9.label}</span>}</span>}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" aria-hidden="true" />
      </button>
    </li>
  );
}

// ── Exceptions rail (shown when self-service / Action Center is off) ──
function ExceptionsRail({ locations, onOpen }) {
  const ex = locations.filter((l) => l.op.tone === "problem" || l.op.tone === "urgent");
  return (
    <section aria-labelledby="cc-exceptions" className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80 p-5">
      <h2 id="cc-exceptions" className="text-[13px] font-semibold text-slate-900">Exceptions</h2>
      {ex.length === 0 ? (
        <p className="mt-2 text-[12.5px] text-slate-600">No location has a known service problem.</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100">
          {ex.map((l) => (
            <li key={l.location_ref}>
              <button type="button" onClick={() => onOpen({ ref: l.location_ref, name: l.location })}
                className="cc-focus w-full flex items-center gap-2 py-2.5 min-h-[44px] text-left">
                <TriangleAlert className="w-4 h-4 text-amber-700 flex-shrink-0" aria-hidden="true" />
                <span className="flex-1 min-w-0 text-[13px] text-slate-800 truncate">{l.location}</span>
                <StatusChip token={OP_TOKEN[l.op.tone]}>{l.op.label}</StatusChip>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function CustomerAssuranceView() {
  const [summary, setSummary] = useState(null);
  const [actionCenter, setActionCenter] = useState(null);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [error, setError] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const [mobileMap, setMobileMap] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [e911Filter, setE911Filter] = useState("all");
  const [highlightRef, setHighlightRef] = useState(null);
  const [searchResults, setSearchResults] = useState(null);
  const searchAbort = useRef(0);
  const [searchParams, setSearchParams] = useSearchParams();
  const isDesktop = useIsDesktop();

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
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e.status === 404 ? "Your portal is being finalized. Please check back shortly." : (e.message || "Unable to load your dashboard right now."));
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try { await fetchData(); } finally { setRefreshing(false); }
  }, [fetchData]);

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
  // Locations the customer can act on (E911 confirmation) — a marker BADGE, not a state.
  const actionRefs = useMemo(() => new Set((actionCenter?.e911_confirmation_required || []).map((x) => x.location_ref)), [actionCenter]);
  const statement = useMemo(() => statusStatement(summary, actionCenter, locations), [summary, actionCenter, locations]);
  const tiles = useMemo(() => opTiles(summary, actionCenter, locations), [summary, actionCenter, locations]);

  // ── Workspace views: Overview · Action Center · Locations (?view=) ──
  const view = parseView(searchParams.get("view"), { hasActions: loading || Boolean(actionCenter) });
  const setView = useCallback((v) => {
    const next = new URLSearchParams(searchParams);
    if (v === "overview") next.delete("view"); else next.set("view", v);
    setSearchParams(next, { replace: false });
    window.scrollTo({ top: 0 });
  }, [searchParams, setSearchParams]);
  const hrefFor = (v) => (v === "overview" ? "?" : `?view=${v}`);
  // Primary navigation = the views that really exist (no fake items).
  useCustomerNav([
    { id: "overview", label: "Overview", icon: "overview", href: hrefFor("overview"), current: view === "overview", onSelect: () => setView("overview") },
    ...(actionCenter ? [{ id: "actions", label: "Action Center", icon: "actions", href: hrefFor("actions"), current: view === "actions", onSelect: () => setView("actions") }] : []),
    { id: "locations", label: "Locations", icon: "locations", href: hrefFor("locations"), current: view === "locations", onSelect: () => setView("locations") },
  ]);

  const tileClick = (tile) => {
    if (tile.target === "locations") return () => setView("locations");
    if (tile.target === "attention" && tile.value > 0) return () => { setStatusFilter("Needs attention"); setView("locations"); };
    if (tile.target === "actions" && actionCenter) return () => setView("actions");
    return null;
  };

  const m = summary || {};
  const selectCls = "cc-focus h-10 px-3 text-[12.5px] rounded-lg bg-white ring-1 ring-inset ring-slate-200 text-slate-700";
  const single = locations.length === 1;
  const filtersOn = statusFilter !== "all" || e911Filter !== "all";
  const preview = exceptionsPreview(filtered, actionRefs, 5);
  const rowProps = { actionRefs, highlightRef, setHighlightRef, onOpen: openLocation };
  const searchBox = (
    <SearchBox search={search} setSearch={setSearch} searchResults={searchResults}
      onPick={(r) => { openLocation({ ref: r.location_ref, name: r.location }); setSearch(""); setSearchResults(null); }} />
  );
  const clearFilters = () => { setStatusFilter("all"); setE911Filter("all"); };
  const go = (v) => (e) => { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); setView(v); };

  return (
    <PageWrapper>
      <div className="mx-auto max-w-[1440px] px-4 sm:px-6 py-4 space-y-3 lg:space-y-3.5">
        {loading ? <CommandSkeleton /> : error ? (
          <div className="rounded-2xl bg-white ring-1 ring-slate-200 p-6"><p className="text-[13px] text-slate-600">{error}</p></div>
        ) : view === "actions" ? (
          /* ACTION CENTER view: the complete queues, full width */
          <div id="cc-actions" className="max-w-[1100px] mx-auto">
            <ActionCenter data={actionCenter} onOpenLocation={openLocation} mode="full" />
          </div>
        ) : view === "locations" ? (
          /* LOCATIONS view: the inventory workspace */
          <section id="cc-locations" aria-labelledby="cc-locations-title" className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80 overflow-hidden">
            <div className="px-4 sm:px-5 py-3.5 border-b border-slate-100 flex flex-col lg:flex-row lg:items-center gap-3 lg:justify-between">
              <h1 id="cc-locations-title" className="text-[18px] font-semibold text-slate-900 tracking-tight">
                Locations <span className="ml-1 text-[13px] font-medium text-slate-400 tabular-nums">{filtered.length} of {locations.length}</span>
              </h1>
              <div className="flex flex-wrap items-center gap-2">
                {searchBox}
                <select aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={selectCls}>
                  <option value="all">All statuses</option>{statusOptions.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
                <select aria-label="Filter by E911" value={e911Filter} onChange={(e) => setE911Filter(e.target.value)} className={selectCls}>
                  <option value="all">All E911</option>{e911Options.map((o) => <option key={o} value={o}>{e911Display(o).label}</option>)}
                </select>
                <button type="button" onClick={() => setMobileMap((v) => !v)} aria-pressed={mobileMap}
                  className="cc-focus inline-flex items-center gap-1.5 h-10 px-3 rounded-lg ring-1 ring-inset ring-slate-200 text-[12.5px] font-medium text-slate-700">
                  <MapIcon className="w-4 h-4" aria-hidden="true" />{mobileMap ? "Hide map" : "Show map"}
                </button>
              </div>
            </div>
            {mobileMap && (
              <div className="p-3 h-[380px] lg:h-[440px]"><CommandMap locations={filtered} actionRefs={actionRefs} highlightRef={highlightRef}
                onHover={setHighlightRef} onOpen={openLocation} single={single} className="h-full" /></div>
            )}
            <ul className="divide-y divide-slate-100" aria-label="Location list">
              {filtered.length === 0 && <li className="px-5 py-10 text-center text-[12.5px] text-slate-500">No locations match your filters.</li>}
              {filtered.map((loc) => <LocationRow key={loc.location_ref} loc={loc} {...rowProps} />)}
            </ul>
          </section>
        ) : (
          /* OVERVIEW view: statement, instrument row, map + summary rail, exceptions preview */
          <>
            <div id="cc-overview">
              <StatusStatement statement={statement} name={m.portfolio_name || "Your Portfolio"}
                freshness={updatedAt} onRefresh={refresh} refreshing={refreshing}>
                {searchBox}
              </StatusStatement>
            </div>

            <div className="flex flex-col gap-3 lg:gap-3.5">
              {/* instrument row: after the Action Center on mobile, before it on desktop */}
              <section aria-label="Operational summary" className="order-2 lg:order-1 grid grid-cols-1 min-[420px]:grid-cols-2 lg:grid-cols-4 gap-3">
                {tiles.map((t, i) => <OpTile key={t.key} tile={t} index={i} onClick={tileClick(t)} />)}
              </section>

              <div id="cc-command" className="order-1 lg:order-2 grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-3.5 items-start">
                {isDesktop && (
                  // stretches to the rail's height (aligned bottoms), within a 430-480px base and a 560px cap
                  <div className={`lg:col-span-8 relative self-stretch ${single ? "min-h-[380px]" : "min-h-[clamp(430px,calc(100vh-400px),480px)]"} max-h-[560px]`}>
                    <CommandMap locations={filtered} actionRefs={actionRefs} highlightRef={highlightRef}
                      onHover={setHighlightRef} onOpen={openLocation} single={single} className="h-full" />
                    {filtersOn && (
                      <button type="button" onClick={clearFilters}
                        className="cc-focus absolute top-3 right-14 inline-flex items-center gap-1 rounded-full bg-white px-3 py-1 text-[11.5px] font-medium text-slate-700 shadow ring-1 ring-slate-200" style={{ zIndex: 600 }}>
                        Showing filtered locations <X className="w-3.5 h-3.5" aria-hidden="true" /><span className="sr-only">Clear filters</span>
                      </button>
                    )}
                  </div>
                )}
                <div id="cc-actions" className={isDesktop ? "lg:col-span-4" : ""}>
                  {actionCenter
                    ? <ActionCenter data={actionCenter} onOpenLocation={openLocation} mode="summary" onViewAll={() => setView("actions")} />
                    : <ExceptionsRail locations={locations} onOpen={openLocation} />}
                </div>
              </div>

              {/* concise exceptions-first preview; the full inventory is the Locations view */}
              <section id="cc-locations" aria-labelledby="cc-preview-title" className="order-3 rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80 overflow-hidden">
                <div className="px-4 sm:px-5 py-3 border-b border-slate-100 flex items-center justify-between gap-3">
                  <h2 id="cc-preview-title" className="text-[14px] font-semibold text-slate-900">
                    Locations <span className="ml-1 text-[12px] font-medium text-slate-400">exceptions first</span>
                  </h2>
                  <a href={hrefFor("locations")} onClick={go("locations")}
                    className="cc-focus inline-flex items-center gap-1 min-h-[36px] text-[12.5px] font-semibold text-slate-900 hover:underline">
                    View all {locations.length} locations <ChevronRight className="w-4 h-4" aria-hidden="true" />
                  </a>
                </div>
                <ul className="divide-y divide-slate-100" aria-label="Location preview">
                  {preview.map((loc) => <LocationRow key={loc.location_ref} loc={loc} {...rowProps} />)}
                </ul>
              </section>
            </div>
          </>
        )}
      </div>

      {drawer && <LocationCommandCenter locationRef={drawer.ref} locationName={drawer.name} intent={drawer.intent} onClose={closeLocation} />}
    </PageWrapper>
  );
}
