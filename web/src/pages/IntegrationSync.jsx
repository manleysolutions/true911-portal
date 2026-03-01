import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { ArrowDownUp, RefreshCw, AlertTriangle, CheckCircle2, Clock, XCircle, Search, ChevronLeft, ChevronRight } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { toast } from "sonner";

const STATUS_BADGE = {
  received:      "bg-blue-50 text-blue-700 border-blue-200",
  processing:    "bg-yellow-50 text-yellow-700 border-yellow-200",
  processed:     "bg-emerald-50 text-emerald-700 border-emerald-200",
  failed:        "bg-red-50 text-red-700 border-red-200",
  needs_mapping: "bg-orange-50 text-orange-700 border-orange-200",
};

const MISMATCH_BADGE = {
  billed_gt_deployed:     "bg-amber-50 text-amber-700 border-amber-200",
  deployed_gt_billed:     "bg-blue-50 text-blue-700 border-blue-200",
  active_sub_no_lines:    "bg-red-50 text-red-700 border-red-200",
  line_active_no_sub:     "bg-purple-50 text-purple-700 border-purple-200",
  unlinked_deployed_lines:"bg-gray-100 text-gray-600 border-gray-200",
};

function timeSince(iso) {
  if (!iso) return "\u2014";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/* ── Events Tab ── */
function EventsTab() {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (source) params.set("source", source);
      if (statusFilter) params.set("status", statusFilter);
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      const data = await apiFetch(`/integrations/events?${params}`);
      setEvents(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error("Failed to load events");
    }
    setLoading(false);
  }, [source, statusFilter, offset]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={source}
          onChange={(e) => { setSource(e.target.value); setOffset(0); }}
          className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
        >
          <option value="">All Sources</option>
          <option value="zoho">Zoho CRM</option>
          <option value="qb">QuickBooks</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
          className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
        >
          <option value="">All Statuses</option>
          <option value="received">Received</option>
          <option value="processing">Processing</option>
          <option value="processed">Processed</option>
          <option value="failed">Failed</option>
          <option value="needs_mapping">Needs Mapping</option>
        </select>
        <button onClick={fetchEvents} className="px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg flex items-center gap-1">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">External ID</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">Loading...</td></tr>
              ) : events.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No events found</td></tr>
              ) : events.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{timeSince(e.received_at)}</td>
                  <td className="px-4 py-3 font-medium">{e.source}</td>
                  <td className="px-4 py-3 font-mono text-xs">{e.event_type}</td>
                  <td className="px-4 py-3 text-gray-500 font-mono text-xs">{e.external_id || "\u2014"}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${STATUS_BADGE[e.status] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                      {e.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-red-600 text-xs max-w-[200px] truncate" title={e.error || ""}>{e.error || "\u2014"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > limit && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <span className="text-xs text-gray-500">Showing {offset + 1}\u2013{Math.min(offset + limit, total)} of {total}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="p-1.5 rounded hover:bg-gray-100 disabled:opacity-30"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
                className="p-1.5 rounded hover:bg-gray-100 disabled:opacity-30"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Reconciliation Tab ── */
function ReconciliationTab() {
  const { can } = useAuth();
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [filter, setFilter] = useState("");

  const fetchLatest = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/integrations/reconciliation/latest");
      setSnapshot(data.snapshot || null);
    } catch {
      toast.error("Failed to load reconciliation data");
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchLatest(); }, [fetchLatest]);

  const runRecon = async () => {
    setRunning(true);
    try {
      await apiFetch("/integrations/reconciliation/run", { method: "POST" });
      toast.success("Reconciliation job queued. Refresh in a moment.");
      setTimeout(fetchLatest, 3000);
    } catch (err) {
      toast.error(err.message || "Failed to queue reconciliation");
    }
    setRunning(false);
  };

  const mismatches = snapshot?.results_json?.mismatches || [];
  const summary = snapshot?.results_json?.summary || {};
  const filtered = filter
    ? mismatches.filter(m => (m.customer || "").toLowerCase().includes(filter.toLowerCase()))
    : mismatches;

  return (
    <div>
      {/* Actions */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-gray-500">
          {snapshot ? `Last run: ${timeSince(snapshot.created_at)}` : "No reconciliation data yet"}
        </div>
        {can("RUN_RECONCILIATION") && (
          <button
            onClick={runRecon}
            disabled={running}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${running ? "animate-spin" : ""}`} />
            {running ? "Running..." : "Run Reconciliation"}
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !snapshot ? (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400">
          No reconciliation has been run yet. Click "Run Reconciliation" to start.
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            {[
              { label: "Customers", value: snapshot.total_customers, icon: CheckCircle2, color: "text-emerald-600" },
              { label: "Subscriptions", value: snapshot.total_subscriptions, icon: Clock, color: "text-blue-600" },
              { label: "Billed Lines", value: snapshot.total_billed_lines, icon: ArrowDownUp, color: "text-indigo-600" },
              { label: "Deployed Lines", value: snapshot.total_deployed_lines, icon: CheckCircle2, color: "text-emerald-600" },
              { label: "Mismatches", value: snapshot.mismatches_count, icon: snapshot.mismatches_count > 0 ? AlertTriangle : CheckCircle2, color: snapshot.mismatches_count > 0 ? "text-amber-600" : "text-emerald-600" },
            ].map((card) => (
              <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-center gap-2 mb-1">
                  <card.icon className={`w-4 h-4 ${card.color}`} />
                  <span className="text-xs text-gray-500 font-medium">{card.label}</span>
                </div>
                <div className="text-2xl font-bold text-gray-900">{card.value}</div>
              </div>
            ))}
          </div>

          {/* Mismatches Table */}
          {mismatches.length > 0 && (
            <>
              <div className="flex items-center gap-3 mb-3">
                <h3 className="text-sm font-semibold text-gray-700">Mismatches ({mismatches.length})</h3>
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Filter by customer..."
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    className="w-full pl-8 pr-3 py-2 border border-gray-200 rounded-lg text-sm"
                  />
                </div>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        <th className="px-4 py-3">Type</th>
                        <th className="px-4 py-3">Customer</th>
                        <th className="px-4 py-3">Plan</th>
                        <th className="px-4 py-3">Billed</th>
                        <th className="px-4 py-3">Deployed</th>
                        <th className="px-4 py-3">Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {filtered.map((m, idx) => (
                        <tr key={idx} className="hover:bg-gray-50">
                          <td className="px-4 py-3">
                            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${MISMATCH_BADGE[m.type] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                              {m.type.replace(/_/g, " ")}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-medium">{m.customer || "\u2014"}</td>
                          <td className="px-4 py-3 text-gray-500">{m.plan || "\u2014"}</td>
                          <td className="px-4 py-3 font-mono">{m.billed ?? "\u2014"}</td>
                          <td className="px-4 py-3 font-mono">{m.deployed ?? "\u2014"}</td>
                          <td className="px-4 py-3 text-gray-600 text-xs max-w-[300px] truncate" title={m.message}>{m.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {mismatches.length === 0 && (
            <div className="bg-emerald-50 rounded-xl border border-emerald-200 p-6 text-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto mb-2" />
              <div className="text-emerald-800 font-semibold">All Clear</div>
              <div className="text-emerald-600 text-sm mt-1">Deployed lines match billed lines. No mismatches detected.</div>
            </div>
          )}
        </>
      )}
    </div>
  );
}


/* ── Main Page ── */
export default function IntegrationSync() {
  const [tab, setTab] = useState("events");

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <ArrowDownUp className="w-6 h-6 text-red-600" />
              Integration Sync
            </h1>
            <p className="text-sm text-gray-500 mt-1">Zoho CRM + QuickBooks webhook events and billing reconciliation</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
          {[
            { key: "events", label: "Latest Events" },
            { key: "reconciliation", label: "Reconciliation" },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                tab === key
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "events" && <EventsTab />}
        {tab === "reconciliation" && <ReconciliationTab />}
      </div>
    </PageWrapper>
  );
}
