import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, Building2, AlertOctagon, RefreshCw, ChevronRight,
  Clock, Search, Filter,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";

const STATUS_DOT = {
  Connected: "bg-emerald-500",
  "Attention Needed": "bg-amber-500",
  "Not Connected": "bg-red-500",
};

function timeSince(iso) {
  if (!iso) return "--";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function OperatorView() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");

  const fetchData = useCallback(async () => {
    try {
      const result = await apiFetch("/command/operator");
      setData(result);
    } catch (err) {
      console.error("Operator view fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  const sites = data?.sites || [];
  const filtered = sites.filter(s => {
    if (search) {
      const q = search.toLowerCase();
      if (!s.site_name.toLowerCase().includes(q) && !s.site_id.toLowerCase().includes(q) && !(s.customer_name || "").toLowerCase().includes(q)) {
        return false;
      }
    }
    if (filter === "attention") return s.needs_attention;
    if (filter === "connected") return s.status === "Connected" && !s.needs_attention;
    if (filter === "disconnected") return s.status === "Not Connected";
    return true;
  });

  return (
    <PageWrapper>
      <div className="min-h-screen bg-slate-950">
        <div className="p-6 max-w-[1000px] mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
                <Building2 className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">Operator View</h1>
                <p className="text-xs text-slate-500">
                  Site status overview &middot; {user?.name}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Link
                to={createPageUrl("Command")}
                className="flex items-center gap-1 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition-colors border border-slate-700/50"
              >
                <Shield className="w-3.5 h-3.5 text-red-500" />
                Full Command
              </Link>
              <button onClick={fetchData} className="p-2 rounded-lg border border-slate-700/50 hover:bg-slate-800 text-slate-500">
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Stats strip */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-slate-900 rounded-xl border border-slate-700/50 p-4 text-center">
              <p className="text-2xl font-bold text-white">{data?.total_sites || 0}</p>
              <p className="text-[11px] text-slate-500 uppercase font-semibold">Total Sites</p>
            </div>
            <div className={`bg-slate-900 rounded-xl border p-4 text-center ${
              data?.sites_needing_attention > 0 ? "border-amber-700/40" : "border-slate-700/50"
            }`}>
              <p className={`text-2xl font-bold ${data?.sites_needing_attention > 0 ? "text-amber-400" : "text-white"}`}>
                {data?.sites_needing_attention || 0}
              </p>
              <p className="text-[11px] text-slate-500 uppercase font-semibold">Need Attention</p>
            </div>
            <div className={`bg-slate-900 rounded-xl border p-4 text-center ${
              data?.active_incidents > 0 ? "border-red-700/40" : "border-slate-700/50"
            }`}>
              <p className={`text-2xl font-bold ${data?.active_incidents > 0 ? "text-red-400" : "text-white"}`}>
                {data?.active_incidents || 0}
              </p>
              <p className="text-[11px] text-slate-500 uppercase font-semibold">Active Incidents</p>
            </div>
          </div>

          {/* Search + filter */}
          <div className="flex items-center gap-3">
            <div className="flex-1 relative">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search sites..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 bg-slate-900 border border-slate-700/50 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-slate-600"
              />
            </div>
            <div className="flex items-center gap-1 bg-slate-900 border border-slate-700/50 rounded-lg p-1">
              {[
                ["all", "All"],
                ["attention", "Attention"],
                ["connected", "OK"],
                ["disconnected", "Down"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    filter === key
                      ? "bg-slate-700 text-white"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Site list */}
          <div className="space-y-2">
            {filtered.length === 0 && (
              <div className="text-center py-12 text-slate-600 text-sm">No sites match</div>
            )}
            {filtered.map(site => (
              <Link
                key={site.site_id}
                to={createPageUrl("CommandSite") + `?site=${site.site_id}`}
                className={`flex items-center justify-between px-4 py-3.5 rounded-xl border transition-colors hover:bg-slate-800/70 ${
                  site.needs_attention
                    ? site.critical_incidents > 0
                      ? "border-red-700/40 bg-red-900/10"
                      : "border-amber-700/40 bg-amber-900/10"
                    : "border-slate-700/50 bg-slate-900"
                }`}
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${STATUS_DOT[site.status] || "bg-slate-500"}`} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">{site.site_name}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-slate-500">{site.status}</span>
                      {site.customer_name && <span className="text-xs text-slate-600">{site.customer_name}</span>}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 flex-shrink-0">
                  {site.critical_incidents > 0 && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400">
                      <AlertOctagon className="w-3 h-3" />{site.critical_incidents}
                    </span>
                  )}
                  {site.active_incidents > 0 && site.critical_incidents === 0 && (
                    <span className="text-[10px] text-amber-400 font-bold">{site.active_incidents} incident{site.active_incidents !== 1 ? "s" : ""}</span>
                  )}
                  {site.overdue_tasks > 0 && (
                    <span className="text-[10px] text-red-400 font-bold">{site.overdue_tasks} overdue</span>
                  )}
                  {site.last_checkin && (
                    <span className="text-[10px] text-slate-600 flex items-center gap-0.5">
                      <Clock className="w-3 h-3" />{timeSince(site.last_checkin)}
                    </span>
                  )}
                  <ChevronRight className="w-4 h-4 text-slate-600" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
