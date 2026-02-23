import { useState, useEffect, useCallback, useMemo } from "react";
import { Incident, Site } from "@/api/entities";
import { AlertOctagon, CheckCircle, XCircle, Clock, RefreshCw, X, User, Filter, Plus, ChevronDown } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { ackIncident, closeIncident } from "@/components/actions";
import { toast } from "sonner";
import SiteDrawer from "@/components/SiteDrawer";

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const SEV_STYLES = {
  critical: { badge: "bg-red-50 text-red-700 border-red-200", dot: "bg-red-500", row: "border-l-red-500" },
  warning:  { badge: "bg-amber-50 text-amber-700 border-amber-200", dot: "bg-amber-400", row: "border-l-amber-400" },
  info:     { badge: "bg-blue-50 text-blue-700 border-blue-200", dot: "bg-blue-400", row: "border-l-blue-400" },
};

const STATUS_STYLES = {
  open:         "bg-red-50 text-red-700 border-red-200",
  acknowledged: "bg-amber-50 text-amber-700 border-amber-200",
  closed:       "bg-gray-100 text-gray-500 border-gray-200",
};

const CATEGORY_OPTIONS = ["Connectivity", "Voice", "Power", "Compliance", "Other"];

function IncidentDetailPanel({ incident, site, onClose, onUpdated, onOpenSite }) {
  const { user, can } = useAuth();
  const [closeNotes, setCloseNotes] = useState("");
  const [loading, setLoading] = useState(null);
  const sev = SEV_STYLES[incident.severity] || SEV_STYLES.info;

  const handleAck = async () => {
    setLoading("ack");
    await ackIncident(user, incident);
    setLoading(null);
    toast.success("Incident acknowledged.");
    onUpdated();
  };

  const handleClose = async () => {
    setLoading("close");
    await closeIncident(user, incident, closeNotes);
    setLoading(null);
    toast.success("Incident closed.");
    onUpdated();
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/30 z-40 flex justify-end" onClick={onClose}>
      <div className="w-full max-w-sm bg-white h-full shadow-2xl border-l border-gray-200 flex flex-col" onClick={e => e.stopPropagation()}>
        <div className={`px-5 pt-5 pb-4 border-b border-gray-100 flex items-start justify-between flex-shrink-0`}>
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <div className={`w-2.5 h-2.5 rounded-full ${sev.dot}`} />
              <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded border ${sev.badge}`}>{incident.severity}</span>
              <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded border ${STATUS_STYLES[incident.status]}`}>{incident.status}</span>
            </div>
            <h2 className="font-semibold text-gray-900 text-sm leading-tight mt-1">{incident.summary}</h2>
            <p className="text-xs text-gray-400 mt-0.5">{site?.site_name || incident.site_id} · opened {timeSince(incident.opened_at)}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 ml-3 flex-shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Site context */}
          {site && (
            <div
              className="bg-gray-50 rounded-lg p-3 cursor-pointer hover:bg-gray-100 transition-colors"
              onClick={() => { onOpenSite(site); onClose(); }}
            >
              <div className="text-[10px] font-semibold text-gray-400 uppercase mb-1">Affected Site →</div>
              <div className="text-xs font-semibold text-gray-900">{site.site_name}</div>
              <div className="text-[10px] text-gray-500">{site.customer_name} · {site.e911_city}, {site.e911_state}</div>
              <div className="text-[10px] text-gray-400 mt-0.5">Last check-in: {timeSince(site.last_checkin)}</div>
            </div>
          )}

          {/* Timeline */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-3">Lifecycle Timeline</div>
            <div className="space-y-3">
              <TimelineEntry dot="bg-red-500" label="Incident opened" time={incident.opened_at} />
              {incident.ack_by && <TimelineEntry dot="bg-amber-400" label={`Acknowledged by ${incident.ack_by.split("@")[0]}`} time={incident.ack_at} />}
              {incident.closed_at && (
                <TimelineEntry dot="bg-emerald-500" label="Closed" time={incident.closed_at} note={incident.resolution_notes} last />
              )}
            </div>
          </div>

          {/* Linked actions */}
          {incident.assigned_to && (
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <User className="w-3.5 h-3.5 text-gray-400" />
              Assigned to: <span className="font-medium">{incident.assigned_to}</span>
            </div>
          )}

          {/* Runbook */}
          <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
            <div className="text-[10px] font-bold text-blue-700 mb-2 uppercase tracking-wide">Standard Runbook</div>
            <ol className="space-y-1.5">
              {[
                "Ping device to confirm connectivity",
                "Check signal strength (threshold: −85 dBm)",
                "Review telemetry for root cause",
                "Reboot device if unresponsive",
                "Update E911 if address changed",
                "Escalate to Zoho if unresolved >1h",
              ].map((step, i) => (
                <li key={i} className="flex gap-1.5 text-[11px] text-blue-700">
                  <span className="font-bold text-blue-400 flex-shrink-0">{i + 1}.</span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        </div>

        {/* Actions footer */}
        {can("ACK_INCIDENT") && incident.status !== "closed" && (
          <div className="px-5 py-4 border-t border-gray-100 flex-shrink-0 space-y-2">
            {incident.status === "open" && (
              <button
                onClick={handleAck}
                disabled={!!loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
              >
                {loading === "ack" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                Acknowledge
              </button>
            )}
            <textarea
              value={closeNotes}
              onChange={e => setCloseNotes(e.target.value)}
              placeholder="Resolution notes (optional)..."
              rows={2}
              className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500 resize-none"
            />
            <button
              onClick={handleClose}
              disabled={!!loading}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-900 hover:bg-gray-800 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              {loading === "close" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
              Close Incident
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function TimelineEntry({ dot, label, time, note, last }) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`w-2 h-2 rounded-full ${dot} mt-1 flex-shrink-0`} />
        {!last && <div className="flex-1 w-px bg-gray-100 my-1 min-h-[12px]" />}
      </div>
      <div className="pb-1">
        <div className="text-xs font-medium text-gray-800">{label}</div>
        <div className="text-[10px] text-gray-400">{time ? new Date(time).toLocaleString() : "—"}</div>
        {note && <div className="text-[10px] text-gray-500 italic mt-0.5">"{note}"</div>}
      </div>
    </div>
  );
}

export default function Incidents() {
  const { user, can } = useAuth();
  const [incidents, setIncidents] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [siteDrawer, setSiteDrawer] = useState(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState("open");
  const [filterSeverity, setFilterSeverity] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterAssigned, setFilterAssigned] = useState("");

  const fetchData = useCallback(async () => {
    const [incData, sitesData] = await Promise.all([
      Incident.list("-opened_at", 100),
      Site.list("-last_checkin", 100),
    ]);
    setIncidents(incData);
    setSites(sitesData);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const siteById = Object.fromEntries(sites.map(s => [s.site_id, s]));

  const filtered = useMemo(() => incidents.filter(inc => {
    if (filterStatus && inc.status !== filterStatus) return false;
    if (filterSeverity && inc.severity !== filterSeverity) return false;
    if (filterAssigned && inc.assigned_to !== filterAssigned) return false;
    return true;
  }), [incidents, filterStatus, filterSeverity, filterAssigned]);

  const counts = {
    open: incidents.filter(i => i.status === "open").length,
    acknowledged: incidents.filter(i => i.status === "acknowledged").length,
    closed: incidents.filter(i => i.status === "closed").length,
    critical: incidents.filter(i => i.severity === "critical" && i.status !== "closed").length,
  };

  const handleUpdated = () => {
    fetchData();
    setSelected(s => s ? { ...s } : null);
  };

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Incidents</h1>
            <p className="text-sm text-gray-500 mt-0.5">Grouped events requiring resolution</p>
          </div>
          <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Summary chips */}
        <div className="flex flex-wrap gap-2 mb-5">
          {[
            { label: "Open", count: counts.open, color: "bg-red-100 text-red-700 border-red-200", val: "open" },
            { label: "Acknowledged", count: counts.acknowledged, color: "bg-amber-100 text-amber-700 border-amber-200", val: "acknowledged" },
            { label: "Closed", count: counts.closed, color: "bg-gray-100 text-gray-600 border-gray-200", val: "closed" },
            { label: "All", count: incidents.length, color: "bg-blue-50 text-blue-700 border-blue-100", val: "" },
          ].map(chip => (
            <button
              key={chip.val}
              onClick={() => setFilterStatus(chip.val)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all ${chip.color} ${filterStatus === chip.val ? "ring-2 ring-offset-1 ring-gray-400" : "opacity-70 hover:opacity-100"}`}
            >
              {chip.label}
              <span className="font-bold">{chip.count}</span>
            </button>
          ))}
          {counts.critical > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold bg-red-600 text-white border-red-600">
              ⚡ {counts.critical} Critical Active
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4 flex flex-wrap items-center gap-3">
          <Filter className="w-3.5 h-3.5 text-gray-400" />
          <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)}
            className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
            <option value="">All Severities</option>
            {["critical", "warning", "info"].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          {(filterStatus || filterSeverity) && (
            <button onClick={() => { setFilterStatus("open"); setFilterSeverity(""); }} className="text-xs text-red-600 hover:text-red-700 flex items-center gap-1">
              <X className="w-3 h-3" /> Reset
            </button>
          )}
        </div>

        {/* Incident list */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.length === 0 && (
              <div className="bg-white rounded-xl border border-gray-200 px-5 py-12 text-center text-sm text-gray-400">
                No incidents match the current filters.
              </div>
            )}
            {filtered.map(incident => {
              const sev = SEV_STYLES[incident.severity] || SEV_STYLES.info;
              const site = siteById[incident.site_id];
              return (
                <div
                  key={incident.id}
                  onClick={() => setSelected(incident)}
                  className={`bg-white rounded-xl border border-l-4 ${sev.row} border-gray-200 px-5 py-4 flex items-start gap-4 cursor-pointer hover:shadow-sm transition-all`}
                >
                  <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 mt-1.5 ${sev.dot}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${sev.badge}`}>{incident.severity}</span>
                          <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${STATUS_STYLES[incident.status]}`}>{incident.status}</span>
                          {incident.incident_id && <span className="text-[10px] font-mono text-gray-400">{incident.incident_id}</span>}
                        </div>
                        <p className="text-sm font-semibold text-gray-900 leading-snug">{incident.summary}</p>
                        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                          <span className="text-xs text-gray-500">{site?.site_name || incident.site_id}</span>
                          {site?.customer_name && <span className="text-xs text-gray-400">· {site.customer_name}</span>}
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0 text-xs text-gray-400 space-y-0.5">
                        <div className="flex items-center gap-1 justify-end">
                          <Clock className="w-3 h-3" /> {timeSince(incident.opened_at)}
                        </div>
                        {incident.ack_by && (
                          <div className="text-[10px]">Ack: {incident.ack_by.split("@")[0]}</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Detail Panel */}
      {selected && (
        <IncidentDetailPanel
          incident={selected}
          site={siteById[selected.site_id]}
          onClose={() => setSelected(null)}
          onUpdated={handleUpdated}
          onOpenSite={s => { setSiteDrawer(s); setSelected(null); }}
        />
      )}

      <SiteDrawer
        site={siteDrawer}
        onClose={() => setSiteDrawer(null)}
        onSiteUpdated={fetchData}
      />
    </PageWrapper>
  );
}