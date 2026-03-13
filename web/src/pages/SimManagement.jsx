import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/api/client";
import { Cpu, RefreshCw, Search, Play, Pause, RotateCcw, Loader2, AlertTriangle } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { config } from "@/config";
import { toast } from "sonner";

const STATUS_BADGE = {
  active:     "bg-emerald-50 text-emerald-700 border-emerald-200",
  inventory:  "bg-blue-50 text-blue-700 border-blue-200",
  suspended:  "bg-amber-50 text-amber-700 border-amber-200",
  terminated: "bg-red-50 text-red-700 border-red-200",
};

const CARRIER_BADGE = {
  verizon:  "bg-red-50 text-red-700 border-red-200",
  tmobile:  "bg-pink-50 text-pink-700 border-pink-200",
  telnyx:   "bg-indigo-50 text-indigo-700 border-indigo-200",
  att:      "bg-blue-50 text-blue-700 border-blue-200",
  teal:     "bg-teal-50 text-teal-700 border-teal-200",
};

const SIM_ACTIONS = {
  inventory: ["activate"],
  active: ["suspend"],
  suspended: ["activate", "resume"],
};

export default function SimManagement() {
  const { can } = useAuth();
  const [sims, setSims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [carrierFilter, setCarrierFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [actionLoading, setActionLoading] = useState(null);

  const carrierWriteEnabled = config.featureCarrierWriteOps;

  const handleSimAction = async (simId, action) => {
    if (!carrierWriteEnabled) {
      const confirmed = confirm(
        `Carrier API is not connected.\n\nThis will update the SIM status in the True911 database only. ` +
        `The actual SIM status on the carrier network will NOT change.\n\nProceed with local status update?`
      );
      if (!confirmed) return;
    }
    setActionLoading(`${simId}-${action}`);
    try {
      await apiFetch(`/sims/${simId}/${action}`, { method: "POST" });
      toast.success(
        carrierWriteEnabled
          ? `SIM ${action} queued`
          : `SIM ${action} queued (local status only — carrier not connected)`
      );
      fetchSims();
    } catch (err) {
      toast.error(err?.message || `Failed to ${action} SIM`);
    }
    setActionLoading(null);
  };

  const fetchSims = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (carrierFilter) params.set("carrier", carrierFilter);
      if (statusFilter) params.set("status", statusFilter);
      params.set("limit", "500");
      const data = await apiFetch(`/sims?${params}`);
      setSims(data);
    } catch {
      toast.error("Failed to load SIMs");
    }
    setLoading(false);
  }, [carrierFilter, statusFilter]);

  useEffect(() => { fetchSims(); }, [fetchSims]);

  const filtered = sims.filter(s => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (s.iccid || "").toLowerCase().includes(q) ||
      (s.msisdn || "").toLowerCase().includes(q) ||
      (s.imsi || "").toLowerCase().includes(q) ||
      (s.carrier || "").toLowerCase().includes(q) ||
      (s.plan || "").toLowerCase().includes(q)
    );
  });

  // Derive unique carriers from data for filter dropdown
  const carriers = [...new Set(sims.map(s => s.carrier).filter(Boolean))].sort();

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Cpu className="w-6 h-6 text-red-600" />
              SIM Inventory
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">{sims.length} SIMs tracked</p>
          </div>
          <button onClick={fetchSims} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search ICCID, MSISDN, IMSI..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <select
            value={carrierFilter}
            onChange={e => setCarrierFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
          >
            <option value="">All Carriers</option>
            {carriers.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
          >
            <option value="">All Statuses</option>
            <option value="inventory">Inventory</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="terminated">Terminated</option>
          </select>
        </div>

        {/* Carrier write ops warning */}
        {can("MANAGE_SIMS") && !carrierWriteEnabled && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <div>
              <span className="text-amber-800 text-xs font-semibold">Carrier API not connected</span>
              <span className="text-amber-700 text-xs"> — Activate/Suspend/Resume actions update local database status only. Verizon ThingSpace write operations are not yet enabled.</span>
            </div>
          </div>
        )}

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">ICCID</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">MSISDN</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">IMSI</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Carrier</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Plan</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Created</th>
                  {can("MANAGE_SIMS") && (
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase w-28">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center">
                      <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto" />
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-gray-400">
                      {search || carrierFilter || statusFilter
                        ? "No SIMs match your filters"
                        : "No SIMs in inventory. Use Verizon Sync to import SIMs."}
                    </td>
                  </tr>
                ) : (
                  filtered.map(s => (
                    <tr key={s.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{s.iccid}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{s.msisdn || "\u2014"}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{s.imsi || "\u2014"}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${CARRIER_BADGE[s.carrier] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                          {s.carrier}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[s.status] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                          {s.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-gray-500 text-xs">{s.plan || "\u2014"}</td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs">
                        {s.created_at ? new Date(s.created_at).toLocaleDateString() : "\u2014"}
                      </td>
                      {can("MANAGE_SIMS") && (
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1">
                            {(SIM_ACTIONS[s.status] || []).map(action => {
                              const isLoading = actionLoading === `${s.id}-${action}`;
                              const icons = { activate: Play, suspend: Pause, resume: RotateCcw };
                              const Icon = icons[action] || Play;
                              return (
                                <button
                                  key={action}
                                  onClick={() => handleSimAction(s.id, action)}
                                  disabled={!!actionLoading}
                                  className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors"
                                  title={`${action.charAt(0).toUpperCase() + action.slice(1)}${carrierWriteEnabled ? "" : " (local status only)"}`}
                                >
                                  {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
                                </button>
                              );
                            })}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
