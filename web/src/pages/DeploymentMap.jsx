import { useState, useEffect, useCallback, useMemo } from "react";
import { Site } from "@/api/entities";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import PageWrapper from "@/components/PageWrapper";
import SiteDrawer from "@/components/SiteDrawer";
import { MapPin, Layers, RefreshCw, AlertTriangle, ChevronRight, X, Crosshair, Navigation, Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { isCustomerRole, toCustomerStatus, CUSTOMER_STATUS } from "@/lib/attention";

// Raw operational colors — used by internal/operations roles.
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

// Customer-facing palette — only Confirmed Offline is red.
// Imported / no-telemetry sites use a calm slate so customers
// don't see a sea of red on first login.
const CUSTOMER_MARKER_COLORS = {
  operational:         "#10b981", // emerald
  monitoring_pending:  "#94a3b8", // slate-400
  attention_needed:    "#f59e0b", // amber-500
  confirmed_offline:   "#ef4444", // red-500
  integration_pending: "#3b82f6", // blue-500
};

const CUSTOMER_LEGEND = [
  { key: "operational",         label: "Operational",         color: CUSTOMER_MARKER_COLORS.operational },
  { key: "monitoring_pending",  label: "Monitoring Pending",  color: CUSTOMER_MARKER_COLORS.monitoring_pending },
  { key: "attention_needed",    label: "Attention Needed",    color: CUSTOMER_MARKER_COLORS.attention_needed },
  { key: "confirmed_offline",   label: "Confirmed Offline",   color: CUSTOMER_MARKER_COLORS.confirmed_offline },
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
  const { user, can } = useAuth();
  const isAdmin = can("VIEW_ADMIN");
  // Customer roles (User / Manager) see the calm presentation layer.
  // Internal/operations roles continue to see the raw operational
  // labels, colors, and filter chips so admin workflows are unchanged.
  const customerView = isCustomerRole(user?.role);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [filterStatus, setFilterStatus] = useState("All");
  const [showMissingCoords, setShowMissingCoords] = useState(false);
  const [geocodingId, setGeocodingId] = useState(null);
  const [editingCoordsId, setEditingCoordsId] = useState(null);
  const [manualLat, setManualLat] = useState("");
  const [manualLng, setManualLng] = useState("");
  const [savingCoords, setSavingCoords] = useState(false);
  const [bulkGeocoding, setBulkGeocoding] = useState(false);

  const fetchData = useCallback(async () => {
    const data = await Site.list("-last_checkin", 500);
    setSites(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Filter predicate adapts to the active view.  Customer filters
  // use the customer-status bucket key (operational, monitoring_pending,
  // attention_needed, confirmed_offline).  Internal filters use the
  // raw `Connected | Not Connected | Attention Needed` strings.
  const filteredSites = useMemo(() => {
    if (filterStatus === "All") return sites;
    if (customerView) {
      return sites.filter(s => toCustomerStatus(s) === filterStatus);
    }
    return sites.filter(s => s.status === filterStatus);
  }, [sites, filterStatus, customerView]);
  const mappableSites = filteredSites.filter(s => s.has_coords);
  const missingCoordsSites = sites.filter(s => !s.has_coords);

  const hasE911 = (site) => !!(site.e911_street || site.e911_city || site.e911_state || site.e911_zip);

  const handleGeocode = async (site) => {
    setGeocodingId(site.id);
    try {
      await Site.geocode(site.id);
      toast.success(`Geocoded ${site.site_name}`);
      await fetchData();
    } catch (err) {
      toast.error(err?.message || "Geocoding failed");
    }
    setGeocodingId(null);
  };

  const handleStartManual = (site) => {
    setEditingCoordsId(site.id);
    setManualLat(site.lat != null ? String(site.lat) : "");
    setManualLng(site.lng != null ? String(site.lng) : "");
  };

  const handleSaveManual = async (site) => {
    const lat = parseFloat(manualLat);
    const lng = parseFloat(manualLng);
    if (isNaN(lat) || isNaN(lng)) {
      toast.error("Enter valid numeric coordinates");
      return;
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      toast.error("Coordinates out of range");
      return;
    }
    setSavingCoords(true);
    try {
      await Site.update(site.id, { lat, lng });
      toast.success(`Coordinates saved for ${site.site_name}`);
      setEditingCoordsId(null);
      await fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to save coordinates");
    }
    setSavingCoords(false);
  };

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

          <div className="flex items-center gap-1.5 ml-4 flex-wrap">
            <Layers className="w-3.5 h-3.5 text-gray-400" />
            {(customerView
              ? [
                  { value: "All", label: "All" },
                  { value: CUSTOMER_STATUS.OPERATIONAL,       label: "Operational" },
                  { value: CUSTOMER_STATUS.MONITORING_PENDING, label: "Monitoring Pending" },
                  { value: CUSTOMER_STATUS.ATTENTION_NEEDED,   label: "Attention Needed" },
                  { value: CUSTOMER_STATUS.CONFIRMED_OFFLINE,  label: "Confirmed Offline" },
                ]
              : [
                  { value: "All",               label: "All" },
                  { value: "Connected",         label: "Connected" },
                  { value: "Attention Needed",  label: "Attention Needed" },
                  { value: "Not Connected",     label: "Not Connected" },
                ]
            ).map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setFilterStatus(value)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-all ${
                  filterStatus === value
                    ? "bg-gray-900 text-white border-gray-900"
                    : "border-gray-200 text-gray-600 hover:border-gray-400"
                }`}
              >
                {label}
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
            ) : mappableSites.length === 0 ? (
              <div className="flex items-center justify-center h-full bg-gray-50">
                <div className="text-center max-w-xs">
                  <MapPin className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                  <h3 className="text-sm font-semibold text-gray-700 mb-1">No sites on the map</h3>
                  <p className="text-xs text-gray-500 leading-relaxed">
                    {missingCoordsSites.length > 0
                      ? `${missingCoordsSites.length} site${missingCoordsSites.length > 1 ? "s" : ""} missing coordinates. Click "Missing Coords" above to fix them.`
                      : "No sites have been created yet."}
                  </p>
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
                  // Customer view: Confirmed Offline is the only red.
                  // Internal view: existing raw-status colors.
                  const fillColor = customerView
                    ? (CUSTOMER_MARKER_COLORS[toCustomerStatus(site)] || "#9ca3af")
                    : (STATUS_COLORS[site.status] || "#9ca3af");
                  return (
                    <CircleMarker
                      key={site.id}
                      center={[site.lat, site.lng]}
                      radius={isSelected ? 11 : 7}
                      pathOptions={{
                        fillColor,
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
            {mappableSites.length > 0 && (
              <div className="absolute bottom-4 left-4 bg-white/95 backdrop-blur rounded-lg border border-gray-200 shadow-md px-3 py-2.5 pointer-events-none" style={{ zIndex: 10 }}>
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Legend</div>
                <div className="space-y-1">
                  {(customerView ? CUSTOMER_LEGEND : LEGEND).map(item => (
                    <div key={item.key ?? item.status} className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: item.color }} />
                      <span className="text-[11px] text-gray-600">{item.label ?? item.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Network Summary — top left */}
            {mappableSites.length > 0 && (
              <div className="absolute top-4 left-4 bg-white/95 backdrop-blur rounded-lg border border-gray-200 shadow-md px-3 py-2.5" style={{ zIndex: 10 }}>
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Summary</div>
                {customerView
                  ? CUSTOMER_LEGEND.map(({ key, label, color }) => {
                      const count = sites.filter(s => toCustomerStatus(s) === key).length;
                      return (
                        <div key={key} className="flex items-center justify-between gap-4 py-0.5">
                          <div className="flex items-center gap-1.5">
                            <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                            <span className="text-[11px] text-gray-600">{label}</span>
                          </div>
                          <span className="text-[11px] font-bold text-gray-900 tabular-nums">{count}</span>
                        </div>
                      );
                    })
                  : LEGEND.map(({ status, color }) => {
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
                    })
                }
              </div>
            )}
          </div>

          {/* Missing Coordinates Sidebar */}
          {showMissingCoords && missingCoordsSites.length > 0 && (
            <div className="w-80 bg-white border-l border-gray-200 flex flex-col overflow-hidden flex-shrink-0" style={{ zIndex: 1 }}>
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
                  <div key={site.id} className="px-4 py-2.5">
                    <button
                      onClick={() => setSelectedSite(site)}
                      className="w-full text-left hover:opacity-80 transition-opacity"
                    >
                      <div className="text-xs font-medium text-gray-900 truncate">{site.site_name}</div>
                      <div className="text-[10px] text-gray-400 font-mono">{site.site_id}</div>
                      {site.e911_city && (
                        <div className="text-[10px] text-gray-500 mt-0.5">{site.e911_city}, {site.e911_state}</div>
                      )}
                    </button>

                    {/* Admin action buttons */}
                    {isAdmin && (
                      <div className="mt-2 space-y-2">
                        <div className="flex gap-1.5">
                          {hasE911(site) && (
                            <button
                              onClick={() => handleGeocode(site)}
                              disabled={geocodingId === site.id}
                              className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200 rounded-md hover:bg-blue-100 disabled:opacity-60 transition-colors"
                            >
                              {geocodingId === site.id ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Navigation className="w-3 h-3" />
                              )}
                              Geocode
                            </button>
                          )}
                          <button
                            onClick={() => editingCoordsId === site.id ? setEditingCoordsId(null) : handleStartManual(site)}
                            className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium bg-gray-50 text-gray-700 border border-gray-200 rounded-md hover:bg-gray-100 transition-colors"
                          >
                            <Crosshair className="w-3 h-3" />
                            Set Coords
                          </button>
                        </div>

                        {/* Inline manual coord editor */}
                        {editingCoordsId === site.id && (
                          <div className="bg-gray-50 rounded-lg p-2 space-y-1.5">
                            <div className="flex gap-1.5">
                              <input
                                type="number"
                                step="any"
                                placeholder="Lat"
                                value={manualLat}
                                onChange={e => setManualLat(e.target.value)}
                                className="flex-1 px-2 py-1 text-[10px] border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-400"
                              />
                              <input
                                type="number"
                                step="any"
                                placeholder="Lng"
                                value={manualLng}
                                onChange={e => setManualLng(e.target.value)}
                                className="flex-1 px-2 py-1 text-[10px] border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-400"
                              />
                            </div>
                            <div className="flex gap-1.5">
                              <button
                                onClick={() => handleSaveManual(site)}
                                disabled={savingCoords}
                                className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-60 transition-colors"
                              >
                                {savingCoords ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                                Save
                              </button>
                              <button
                                onClick={() => setEditingCoordsId(null)}
                                className="px-2 py-1 text-[10px] font-medium text-gray-600 border border-gray-200 rounded hover:bg-gray-100 transition-colors"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="px-3 py-2 border-t border-gray-100 bg-amber-50/50 flex-shrink-0 space-y-2">
                {isAdmin && (
                  <button
                    onClick={async () => {
                      setBulkGeocoding(true);
                      try {
                        const res = await Site.bulkGeocode();
                        toast.success(`Geocoded ${res.geocoded} sites (${res.failed} failed, ${res.no_address} have no address)`);
                        await fetchData();
                      } catch (err) {
                        toast.error(err?.message || "Bulk geocoding failed");
                      }
                      setBulkGeocoding(false);
                    }}
                    disabled={bulkGeocoding}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-[11px] font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60 transition-colors"
                  >
                    {bulkGeocoding ? <Loader2 className="w-3 h-3 animate-spin" /> : <Navigation className="w-3 h-3" />}
                    {bulkGeocoding ? "Geocoding..." : "Bulk Geocode All"}
                  </button>
                )}
                <p className="text-[10px] text-amber-700 leading-relaxed">
                  {isAdmin
                    ? "Use Bulk Geocode for all sites, or Geocode/Set Coords individually."
                    : "Click a site to open the drawer and view details."}
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
