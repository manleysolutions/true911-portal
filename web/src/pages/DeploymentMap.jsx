import { useState, useEffect, useCallback } from "react";
import { Site } from "@/api/entities";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import PageWrapper from "@/components/PageWrapper";
import SiteDrawer from "@/components/SiteDrawer";
import { MapPin, Layers, RefreshCw, AlertTriangle, ChevronRight, X } from "lucide-react";

const STATUS_COLORS = {
  Connected: "#10b981",
  "Not Connected": "#ef4444",
  "Attention Needed": "#f59e0b",
  Unknown: "#9ca3af",
};

const LEGEND = [
  { status: "Connected", color: "#10b981" },
  { status: "Not Connected", color: "#ef4444" },
  { status: "Attention Needed", color: "#f59e0b" },
  { status: "Unknown", color: "#9ca3af" },
];

function FlyTo({ site }) {
  const map = useMap();
  useEffect(() => {
    if (site?.lat && site?.lng) {
      map.flyTo([site.lat, site.lng], 12, { duration: 1 });
    }
  }, [site, map]);
  return null;
}

export default function DeploymentMap() {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [filterStatus, setFilterStatus] = useState("All");
  const [showMissingCoords, setShowMissingCoords] = useState(false);

  const fetchData = useCallback(async () => {
    const data = await Site.list("-last_checkin", 100);
    setSites(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const filteredSites = filterStatus === "All" ? sites : sites.filter(s => s.status === filterStatus);
  const mappableSites = filteredSites.filter(s => s.lat && s.lng);
  const missingCoordsSites = sites.filter(s => !s.lat || !s.lng);

  return (
    <PageWrapper>
      <div className="h-screen flex flex-col">
        {/* Top bar */}
        <div className="bg-white border-b border-gray-200 px-4 sm:px-6 py-3 flex items-center gap-3 flex-shrink-0 flex-wrap">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-red-600" />
            <h1 className="font-semibold text-gray-900">Deployment Map</h1>
            <span className="text-xs text-gray-400 font-mono">{mappableSites.length} on map</span>
          </div>

          <div className="flex items-center gap-1.5 ml-4">
            <Layers className="w-3.5 h-3.5 text-gray-400" />
            {["All", "Connected", "Attention Needed", "Not Connected"].map(s => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-all ${
                  filterStatus === s
                    ? "bg-gray-900 text-white border-gray-900"
                    : "border-gray-200 text-gray-600 hover:border-gray-400"
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 ml-auto">
            {missingCoordsSites.length > 0 && (
              <button
                onClick={() => setShowMissingCoords(!showMissingCoords)}
                className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all ${
                  showMissingCoords
                    ? "bg-amber-600 text-white border-amber-600"
                    : "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
                }`}
              >
                <AlertTriangle className="w-3 h-3" />
                {missingCoordsSites.length} missing coords
              </button>
            )}
            <button onClick={fetchData} className="p-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Main area */}
        <div className="flex-1 relative flex overflow-hidden">
          {/* Map wrapper — z-0 keeps Leaflet internals contained below the SiteDrawer */}
          <div className="flex-1 relative" style={{ zIndex: 0, isolation: "isolate" }}>
            {loading ? (
              <div className="flex items-center justify-center h-full bg-gray-50">
                <div className="text-center">
                  <div className="w-8 h-8 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                  <span className="text-sm text-gray-500">Loading sites...</span>
                </div>
              </div>
            ) : (
              <MapContainer
                center={[38.5, -97]}
                zoom={4}
                className="h-full w-full"
                style={{ background: "#e8ecf1" }}
                zoomControl={false}
              >
                <TileLayer
                  attribution='&copy; <a href="https://carto.com">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
                  url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                />
                {selectedSite && <FlyTo site={selectedSite} />}
                {mappableSites.map(site => {
                  const isSelected = selectedSite?.id === site.id;
                  return (
                    <CircleMarker
                      key={site.id}
                      center={[site.lat, site.lng]}
                      radius={isSelected ? 11 : 7}
                      pathOptions={{
                        fillColor: STATUS_COLORS[site.status] || "#9ca3af",
                        color: isSelected ? "#1f2937" : "#fff",
                        weight: isSelected ? 3 : 2,
                        fillOpacity: 0.9,
                      }}
                      eventHandlers={{
                        click: () => setSelectedSite(site),
                      }}
                    >
                      <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
                        <div style={{ fontFamily: "inherit", fontSize: 12, lineHeight: 1.4 }}>
                          <strong>{site.site_name}</strong>
                          <br />
                          <span style={{ color: "#6b7280" }}>{site.e911_city}, {site.e911_state}</span>
                        </div>
                      </Tooltip>
                    </CircleMarker>
                  );
                })}
              </MapContainer>
            )}

            {/* Legend — bottom left */}
            <div className="absolute bottom-4 left-4 bg-white/95 backdrop-blur rounded-lg border border-gray-200 shadow-md px-3 py-2.5 pointer-events-none" style={{ zIndex: 10 }}>
              <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Legend</div>
              <div className="space-y-1">
                {LEGEND.map(({ status, color }) => (
                  <div key={status} className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
                    <span className="text-[11px] text-gray-600">{status}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Network Summary — top left */}
            <div className="absolute top-4 left-4 bg-white/95 backdrop-blur rounded-lg border border-gray-200 shadow-md px-3 py-2.5" style={{ zIndex: 10 }}>
              <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Summary</div>
              {LEGEND.map(({ status, color }) => {
                const count = sites.filter(s => s.status === status).length;
                return (
                  <div key={status} className="flex items-center justify-between gap-4 py-0.5">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                      <span className="text-[11px] text-gray-600">{status}</span>
                    </div>
                    <span className="text-[11px] font-bold text-gray-900 tabular-nums">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Missing Coordinates Sidebar */}
          {showMissingCoords && missingCoordsSites.length > 0 && (
            <div className="w-72 bg-white border-l border-gray-200 flex flex-col overflow-hidden flex-shrink-0" style={{ zIndex: 1 }}>
              <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2 flex-shrink-0">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                <h3 className="text-xs font-semibold text-gray-900">Missing Coordinates</h3>
                <span className="ml-auto bg-amber-100 text-amber-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {missingCoordsSites.length}
                </span>
                <button onClick={() => setShowMissingCoords(false)} className="p-0.5 hover:bg-gray-100 rounded text-gray-400">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto divide-y divide-gray-50">
                {missingCoordsSites.map(site => (
                  <button
                    key={site.id}
                    onClick={() => setSelectedSite(site)}
                    className="w-full text-left px-4 py-2.5 hover:bg-gray-50 transition-colors"
                  >
                    <div className="text-xs font-medium text-gray-900 truncate">{site.site_name}</div>
                    <div className="text-[10px] text-gray-400 font-mono">{site.site_id}</div>
                    {site.e911_city && (
                      <div className="text-[10px] text-gray-500 mt-0.5">{site.e911_city}, {site.e911_state}</div>
                    )}
                  </button>
                ))}
              </div>
              <div className="px-3 py-2 border-t border-gray-100 bg-amber-50/50 flex-shrink-0">
                <p className="text-[10px] text-amber-700 leading-relaxed">
                  Click a site to open the drawer and add coordinates.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* SiteDrawer renders at z-50 (fixed), safely above the map at z-0 */}
      <SiteDrawer
        site={selectedSite}
        onClose={() => setSelectedSite(null)}
        onSiteUpdated={fetchData}
      />
    </PageWrapper>
  );
}
