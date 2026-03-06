import { useState, useEffect, useCallback } from "react";
import {
  Radio, Wifi, WifiOff, Signal, SignalLow,
  Loader2, Filter, RefreshCw,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import NetworkStatus from "@/components/command/NetworkStatus";
import AuditTrail from "@/components/command/AuditTrail";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

function CarrierBar({ carrier, count, total }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-gray-700 w-20 truncate">{carrier}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{count}</span>
    </div>
  );
}

export default function NetworkDashboard() {
  const { can } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchSummary = useCallback(() => {
    setLoading(true);
    apiFetch("/command/network/summary")
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(fetchSummary, [fetchSummary]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  if (!summary) {
    return (
      <PageWrapper>
        <div className="p-6 text-center text-gray-500">Unable to load network data.</div>
      </PageWrapper>
    );
  }

  const carriers = Object.entries(summary.carrier_distribution || {}).sort((a, b) => b[1] - a[1]);

  return (
    <PageWrapper>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className="w-5 h-5 text-blue-600" />
            <h1 className="text-2xl font-bold text-gray-900">Network Dashboard</h1>
          </div>
          <button onClick={fetchSummary} className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Total Devices" value={summary.total_devices} icon={Signal} color="text-gray-600" />
          <StatCard label="Connected" value={summary.connected} icon={Wifi} color="text-emerald-600" />
          <StatCard label="Disconnected" value={summary.disconnected} icon={WifiOff} color="text-red-600" />
          <StatCard label="Degraded" value={summary.degraded} icon={SignalLow} color="text-amber-600" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Carrier Distribution */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Carrier Distribution</h3>
            {carriers.length === 0 ? (
              <p className="text-xs text-gray-500">No carrier data available.</p>
            ) : (
              <div className="space-y-2">
                {carriers.map(([carrier, count]) => (
                  <CarrierBar key={carrier} carrier={carrier} count={count} total={summary.total_devices} />
                ))}
              </div>
            )}
          </div>

          {/* Recent Network Events */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Recent Network Events</h3>
            {summary.recent_network_events.length === 0 ? (
              <p className="text-xs text-gray-500">No recent events.</p>
            ) : (
              <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
                {summary.recent_network_events.map(evt => (
                  <div key={evt.id} className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                      evt.severity === "critical" ? "bg-red-100 text-red-700" :
                      evt.severity === "warning" ? "bg-amber-100 text-amber-700" :
                      "bg-blue-100 text-blue-700"
                    }`}>{evt.severity}</span>
                    <span className="text-xs text-gray-900 flex-1 truncate">{evt.summary}</span>
                    <span className="text-[10px] text-gray-400">{evt.device_id}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Audit Trail */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <AuditTrail />
        </div>
      </div>
    </PageWrapper>
  );
}
