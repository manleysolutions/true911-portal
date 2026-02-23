import { useState, useEffect, useCallback } from "react";
import { Site } from "@/api/entities";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import PageWrapper from "@/components/PageWrapper";
import SiteDrawer from "@/components/SiteDrawer";
import StatusBadge from "@/components/ui/StatusBadge";
import { MapPin, Layers, RefreshCw } from "lucide-react";

const STATUS_MAP_COLORS = {
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

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function DeploymentMap() {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [filterStatus, setFilterStatus] = useState("All");

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

  return (
    <PageWrapper>
      <div className="h-screen flex flex-col">
        {/* Top bar */}
        <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3 flex-shrink-0">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-red-600" />
            <h1 className="font-semibold text-gray-900">Deployment Map</h1>
            <span className="text-xs text-gray-400 font-mono">{filteredSites.length} sites</span>
          </div>

          <div className="flex items-center gap-2 ml-4">
            <Layers className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs text-gray-500">Filter:</span>
            {["All", "Connected", "Attention Needed", "Not Connected", "Unknown"].map(s => (
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

          <button onClick={fetchData} className="ml-auto p-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex-1 relative">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <MapContainer
              center={[38.5, -97]}
              zoom={4}
              className="h-full w-full"
              style={{ background: "#f8fafc" }}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {selectedSite && <FlyTo site={selectedSite} />}
              {filteredSites.filter(s => s.lat && s.lng).map(site => (
                <CircleMarker
                  key={site.id}
                  center={[site.lat, site.lng]}
                  radius={8}
                  pathOptions={{
                    fillColor: STATUS_MAP_COLORS[site.status] || "#9ca3af",
                    color: "#fff",
                    weight: 2,
                    fillOpacity: 0.9,
                  }}
                  eventHandlers={{
                    click: () => setSelectedSite(site),
                  }}
                >
                  <Popup>
                    <div className="text-xs">
                      <div className="font-semibold text-gray-900 mb-1">{site.site_name}</div>
                      <div className="text-gray-500 mb-1">{site.customer_name}</div>
                      <div className="text-gray-400">{site.e911_city}, {site.e911_state}</div>
                      <div className="mt-2 flex items-center gap-1">
                        <span
                          className="w-2 h-2 rounded-full inline-block"
                          style={{ background: STATUS_MAP_COLORS[site.status] }}
                        />
                        <span className="font-medium">{site.status}</span>
                      </div>
                      <button
                        onClick={() => setSelectedSite(site)}
                        className="mt-2 text-red-600 font-medium text-xs hover:underline"
                      >
                        View Details →
                      </button>
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          )}

          {/* Legend */}
          <div className="absolute bottom-6 left-4 bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 z-[400]">
            <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-2">Status Legend</div>
            <div className="space-y-1.5">
              {LEGEND.map(({ status, color }) => (
                <div key={status} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full border-2 border-white shadow-sm" style={{ background: color }} />
                  <span className="text-xs text-gray-700">{status}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Site count by status */}
          <div className="absolute top-4 right-4 bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 z-[400]">
            <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-2">Network Summary</div>
            {LEGEND.map(({ status, color }) => {
              const count = sites.filter(s => s.status === status).length;
              return (
                <div key={status} className="flex items-center justify-between gap-6 py-0.5">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                    <span className="text-xs text-gray-600">{status}</span>
                  </div>
                  <span className="text-xs font-bold text-gray-900">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <SiteDrawer
        site={selectedSite}
        onClose={() => setSelectedSite(null)}
        onSiteUpdated={fetchData}
      />
    </PageWrapper>
  );
}