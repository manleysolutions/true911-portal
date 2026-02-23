import { useState, useEffect } from "react";
import { Incident } from "@/api/entities";
import { AlertOctagon, CheckCircle, Loader2, RefreshCw } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ackIncident, closeIncident } from "../actions";
import { toast } from "sonner";

const SEV_DOT = {
  critical: "bg-red-500",
  warning: "bg-amber-400",
  info: "bg-blue-400",
};

const STATUS_BADGE = {
  open: "bg-red-50 text-red-700 border-red-200",
  acknowledged: "bg-amber-50 text-amber-700 border-amber-200",
  closed: "bg-gray-100 text-gray-500 border-gray-200",
};

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function IncidentStatus({ site, refreshKey }) {
  const { user, can } = useAuth();
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(null);

  const fetchIncidents = async () => {
    const data = await Incident.filter({ site_id: site.site_id }, "-opened_at", 5);
    setIncidents(data.filter(i => i.status !== "closed"));
    setLoading(false);
  };

  useEffect(() => {
    fetchIncidents();
  }, [site.site_id, refreshKey]);

  const handleAck = async (incident) => {
    setActing(incident.id);
    await ackIncident(user, incident);
    toast.success("Acknowledged.");
    await fetchIncidents();
    setActing(null);
  };

  const handleClose = async (incident) => {
    setActing(incident.id);
    await closeIncident(user, incident, "Closed via site drawer.");
    toast.success("Incident closed.");
    await fetchIncidents();
    setActing(null);
  };

  return (
    <div className="mb-5">
      <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Open Incidents</div>
      {loading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
        </div>
      ) : incidents.length === 0 ? (
        <div className="flex items-center gap-2 px-3 py-2.5 bg-emerald-50 rounded-lg border border-emerald-100">
          <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
          <span className="text-xs text-emerald-700">No open incidents for this site.</span>
        </div>
      ) : (
        <div className="space-y-2">
          {incidents.map(incident => (
            <div key={incident.id} className="border border-gray-200 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${SEV_DOT[incident.severity] || "bg-gray-400"}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap mb-1">
                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border ${STATUS_BADGE[incident.status]}`}>
                      {incident.status}
                    </span>
                    <span className="text-[10px] text-gray-400">{timeSince(incident.opened_at)}</span>
                  </div>
                  <p className="text-xs text-gray-700 leading-relaxed">{incident.summary}</p>
                  {can("ACK_INCIDENT") && (
                    <div className="flex gap-1.5 mt-2">
                      {incident.status === "open" && (
                        <button
                          onClick={() => handleAck(incident)}
                          disabled={acting === incident.id}
                          className="px-2.5 py-1 text-[10px] font-semibold bg-amber-100 text-amber-700 rounded-md hover:bg-amber-200 transition-colors disabled:opacity-60"
                        >
                          {acting === incident.id ? <Loader2 className="w-3 h-3 animate-spin inline" /> : "Acknowledge"}
                        </button>
                      )}
                      <button
                        onClick={() => handleClose(incident)}
                        disabled={acting === incident.id}
                        className="px-2.5 py-1 text-[10px] font-semibold bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors disabled:opacity-60"
                      >
                        {acting === incident.id ? <Loader2 className="w-3 h-3 animate-spin inline" /> : "Close"}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}