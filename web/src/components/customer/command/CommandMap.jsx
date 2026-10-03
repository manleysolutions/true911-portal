import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, ZoomControl, useMap } from "react-leaflet";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { X, ChevronRight, MapPin, Info } from "lucide-react";
import { mapMarkers, pointsSignature } from "@/components/customer/portfolioMap";
import { TILE_CONFIG, TILE_FAILURE_THRESHOLD } from "@/lib/mapTiles";
import { STATUS_TOKENS, markerView, MAP_LEGEND_ITEMS, e911Display, missingPointsText } from "@/components/customer/commandCenter";
import { StatusChip, E911Badge } from "@/components/customer/command/CommandParts";

// ════════════════════════════════════════════════════════════════════
// CommandMap — the portfolio map as a first-class command surface.
// Plots ONLY the server map_point (portfolioMap.js: invalid points excluded,
// one marker per location, missing coordinates disclosed — never fabricated).
// Markers differ by SHAPE and GLYPH (circle ✓ / diamond ! / hollow ring), carry
// an accessible label, and are keyboard-focusable.  Selecting a marker opens a
// small preview; "Open location" reaches the existing location record.
// ════════════════════════════════════════════════════════════════════

// Refit only when the plotted point SET changes (signature), not on every
// render — hover, the 60 s refresh and drawer state all re-render the map.
function FitBounds({ points, signature, single }) {
  const map = useMap();
  const pointsRef = useRef(points);
  pointsRef.current = points;
  useEffect(() => {
    const pts = pointsRef.current;
    if (pts.length === 0) return;
    if (pts.length === 1) { map.setView(pts[0], single ? 14 : 11); return; }
    map.fitBounds(pts, { padding: [48, 48], maxZoom: 12 });
  }, [signature, map, single]);
  return null;
}

function markerHtml(v, selected) {
  const t = STATUS_TOKENS[v.token] || STATUS_TOKENS.unknown;
  const size = (v.large ? 26 : 20) + (selected ? 6 : 0);
  const stroke = selected ? "#0f172a" : "#ffffff";
  let shape;
  if (v.shape === "diamond") {
    shape = `<rect x="4" y="4" width="16" height="16" rx="2.5" transform="rotate(45 12 12)" fill="${t.hex}" stroke="${stroke}" stroke-width="2"/>
      <text x="12" y="16" text-anchor="middle" font-size="11" font-weight="700" fill="#fff" font-family="Inter,system-ui,sans-serif">!</text>`;
  } else if (v.shape === "ring") {
    shape = `<circle cx="12" cy="12" r="7.5" fill="#ffffff" stroke="${selected ? "#0f172a" : "#64748b"}" stroke-width="2.5" stroke-dasharray="3 2"/>`;
  } else {
    shape = `<circle cx="12" cy="12" r="8.5" fill="${t.hex}" stroke="${stroke}" stroke-width="2"/>
      <path d="M8.2 12.3l2.5 2.4 5-5.2" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  const badge = v.action
    ? `<circle cx="20" cy="4" r="4" fill="${STATUS_TOKENS.attention.hex}" stroke="#fff" stroke-width="1.5"/>`
    : "";
  return `<svg width="${size}" height="${size}" viewBox="-1 -3 27 27" aria-hidden="true" style="overflow:visible;filter:drop-shadow(0 1px 1.5px rgba(15,23,42,.35))">${shape}${badge}</svg>`;
}

function iconFor(v, selected) {
  const size = (v.large ? 26 : 20) + (selected ? 6 : 0);
  return L.divIcon({ className: "cc-marker", html: markerHtml(v, selected), iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

function LegendShape({ item }) {
  if (item.shape === "badge") return <span className="inline-block w-2.5 h-2.5 rounded-full ring-2 ring-white" style={{ background: STATUS_TOKENS.attention.hex }} aria-hidden="true" />;
  const v = { token: item.token, shape: item.shape };
  return <span className="inline-flex" aria-hidden="true" dangerouslySetInnerHTML={{ __html: markerHtml(v, false).replace(/width="\d+" height="\d+"/, 'width="14" height="14"') }} />;
}

export default function CommandMap({ locations, actionRefs, highlightRef, onHover, onOpen, single = false, className = "" }) {
  const reduce = useReducedMotion();
  const { markers, hidden } = useMemo(() => mapMarkers(locations), [locations]);
  const signature = pointsSignature(markers);
  const points = useMemo(() => markers.map((m) => m.point), [markers]);
  const [selected, setSelected] = useState(null);
  // Basemap failure: markers and the list stay accurate; say so plainly.
  const [tiles, setTiles] = useState({ loaded: 0, failed: 0 });
  const tileEvents = useMemo(() => ({
    tileload: () => setTiles((t) => (t.loaded ? t : { ...t, loaded: 1 })),
    tileerror: () => setTiles((t) => (t.failed >= TILE_FAILURE_THRESHOLD ? t : { ...t, failed: t.failed + 1 })),
  }), []);
  const basemapDown = tiles.loaded === 0 && tiles.failed >= TILE_FAILURE_THRESHOLD;
  const sel = markers.find((m) => m.loc.location_ref === selected)?.loc || null;
  const selView = sel ? markerView(sel, actionRefs) : null;

  return (
    <div className={`relative flex flex-col overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80 ${className}`}>
      <div className="relative flex-1 min-h-[320px] w-full" style={{ zIndex: 0, isolation: "isolate" }}>
        {markers.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-50">
            <MapPin className="w-6 h-6 text-slate-300" aria-hidden="true" />
            <p className="text-[12px] text-slate-500">No locations have map coordinates yet.</p>
          </div>
        ) : (
          <MapContainer center={[38.5, -97]} zoom={4} className="h-full w-full absolute inset-0" style={{ background: "#e8ecf1" }} zoomControl={false}>
            <TileLayer attribution={TILE_CONFIG.attribution} url={TILE_CONFIG.url} maxZoom={TILE_CONFIG.maxZoom} eventHandlers={tileEvents} />
            <ZoomControl position="topright" />
            <FitBounds points={points} signature={signature} single={single} />
            {markers.map(({ loc: l, point }) => {
              const v = markerView(l, actionRefs);
              const on = selected === l.location_ref || highlightRef === l.location_ref;
              return (
                <Marker key={l.location_ref} position={point} icon={iconFor(v, on)} title={v.ariaLabel} alt={v.ariaLabel}
                  keyboard riseOnHover zIndexOffset={on ? 1000 : v.token === "unknown" ? 0 : 500}
                  eventHandlers={{
                    click: () => setSelected(l.location_ref),
                    mouseover: () => onHover?.(l.location_ref), mouseout: () => onHover?.(null),
                  }} />
              );
            })}
          </MapContainer>
        )}

        {basemapDown && markers.length > 0 && (
          <div role="status" className="absolute top-3 left-1/2 -translate-x-1/2 bg-white/95 rounded-lg ring-1 ring-slate-200 shadow-sm px-3 py-1.5 text-[11px] text-slate-600" style={{ zIndex: 500 }}>
            Map background is temporarily unavailable. Location markers and the list are unaffected.
          </div>
        )}

        <AnimatePresence>
          {sel && (
            <motion.div key={sel.location_ref} role="dialog" aria-label={`${sel.location} preview`}
              initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={reduce ? undefined : { opacity: 0, y: 8 }}
              transition={{ duration: 0.18 }}
              className="absolute left-3 right-3 sm:right-auto sm:w-[320px] top-3 rounded-xl bg-white shadow-lg ring-1 ring-slate-200 p-4" style={{ zIndex: 600 }}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold text-slate-900 truncate">{sel.location}</p>
                  {(sel.city || sel.state) && <p className="text-[11.5px] text-slate-500">{[sel.city, sel.state].filter(Boolean).join(", ")}</p>}
                </div>
                <button type="button" onClick={() => setSelected(null)} aria-label="Close preview"
                  className="cc-focus -m-1 p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"><X className="w-4 h-4" /></button>
              </div>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                <StatusChip token={selView.token}>{selView.label}</StatusChip>
                {(selView.action || sel.emergency_address_state) && (() => {
                  // in the E911 confirmation list -> the customer's action; else the API's E911 word
                  const e9 = e911Display(selView.action ? "customer_confirmation_required" : sel.emergency_address_state);
                  return <span className="inline-flex items-center gap-1"><E911Badge /><StatusChip token={e9.token}>{e9.label}</StatusChip></span>;
                })()}
              </div>
              {sel.op?.summary && <p className="mt-2 text-[12px] text-slate-600 leading-snug">{sel.op.summary}</p>}
              <button type="button" onClick={() => onOpen({ ref: sel.location_ref, name: sel.location })}
                className="cc-focus mt-3 w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 min-h-[40px] text-[12.5px] font-medium text-white hover:bg-slate-800">
                Open location <ChevronRight className="w-4 h-4" aria-hidden="true" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="absolute bottom-3 left-3 rounded-lg bg-white/95 ring-1 ring-slate-200 shadow-sm px-3 py-2" style={{ zIndex: 500 }}>
          <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Map legend">
            {MAP_LEGEND_ITEMS.map((item) => (
              <li key={item.label} className="inline-flex items-center gap-1.5 text-[10.5px] text-slate-700"><LegendShape item={item} />{item.label}</li>
            ))}
          </ul>
        </div>
      </div>
      {/* the count stays visible; a location without a point is never placed (D-027) */}
      {hidden > 0 && (
        <div role="note" title="Their location records remain available in the Locations view."
          className="px-4 py-2 border-t border-slate-100 flex items-center gap-1.5 text-[11.5px] text-slate-600">
          <Info className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" aria-hidden="true" />
          <span>{missingPointsText(hidden)}<span className="sr-only"> Their location records remain available in the Locations view.</span></span>
        </div>
      )}
    </div>
  );
}
