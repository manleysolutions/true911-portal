import { useState, useEffect, useCallback } from "react";
import { Recording, Site } from "@/api/entities";
import { Disc3, Search, RefreshCw, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "---";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function timeAgo(iso) {
  if (!iso) return "---";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STATUS_BADGE = {
  available: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-blue-50 text-blue-700 border-blue-200",
  failed: "bg-red-50 text-red-700 border-red-200",
};

export default function Recordings() {
  const [recordings, setRecordings] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [dirFilter, setDirFilter] = useState("");

  const fetchData = useCallback(async () => {
    const [recData, siteData] = await Promise.all([
      Recording.list("-created_at", 200),
      Site.list("-last_checkin", 200),
    ]);
    setRecordings(recData);
    setSites(siteData);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const siteMap = Object.fromEntries(sites.map(s => [s.site_id, s]));

  const filtered = recordings.filter(r => {
    if (dirFilter && r.direction !== dirFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      const site = siteMap[r.site_id];
      return (
        (r.recording_id || "").toLowerCase().includes(q) ||
        (r.caller || "").toLowerCase().includes(q) ||
        (r.callee || "").toLowerCase().includes(q) ||
        (r.line_id || "").toLowerCase().includes(q) ||
        (site?.site_name || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Recordings</h1>
            <p className="text-sm text-gray-500 mt-0.5">{recordings.length} call recordings</p>
          </div>
          <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search by caller, callee, line, site..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <select value={dirFilter} onChange={e => setDirFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">All Directions</option>
            <option value="inbound">Inbound</option>
            <option value="outbound">Outbound</option>
          </select>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Disc3 className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <div className="text-sm font-semibold text-gray-500">
                {recordings.length === 0 ? "No recordings yet" : "No recordings match your filters"}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {recordings.length === 0
                  ? "Call recordings will appear here once provider integration is active."
                  : "Try adjusting your search or filter."}
              </div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Direction</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Caller</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Callee</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Site</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Line</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Duration</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(r => {
                  const site = siteMap[r.site_id];
                  return (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5">
                        {r.direction === "inbound"
                          ? <span className="inline-flex items-center gap-1 text-xs text-blue-600"><PhoneIncoming className="w-3 h-3" /> In</span>
                          : <span className="inline-flex items-center gap-1 text-xs text-emerald-600"><PhoneOutgoing className="w-3 h-3" /> Out</span>
                        }
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{r.caller || "---"}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{r.callee || "---"}</td>
                      <td className="px-4 py-2.5 text-gray-800">{site?.site_name || r.site_id || "---"}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.line_id || "---"}</td>
                      <td className="px-4 py-2.5 text-gray-600">{formatDuration(r.duration_seconds)}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[r.status] || STATUS_BADGE.pending}`}>
                          {r.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-500">{timeAgo(r.started_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}
