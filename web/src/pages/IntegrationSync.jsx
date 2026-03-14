import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { ArrowDownUp, RefreshCw, AlertTriangle, CheckCircle2, Clock, XCircle, Search, ChevronLeft, ChevronRight, Loader2, Radio, Wifi, WifiOff, Play, Eye } from "lucide-react";
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


/* ── Verizon Sync Tab ── */
function VerizonTab() {
  const { can } = useAuth();
  const [config, setConfig] = useState(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncMode, setSyncMode] = useState("preview"); // "preview" or "live"
  const [syncHistory, setSyncHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [pollResult, setPollResult] = useState(null);

  const fetchConfig = useCallback(async () => {
    setConfigLoading(true);
    try {
      const data = await apiFetch("/carriers/verizon/config");
      setConfig(data);
    } catch {
      setConfig({ configured: false, error: "Failed to load Verizon config" });
    }
    setConfigLoading(false);
  }, []);

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const data = await apiFetch("/carriers/verizon/sync-history?limit=10");
      setSyncHistory(data);
    } catch { /* silently fail */ }
    setHistoryLoading(false);
  }, []);

  useEffect(() => { fetchConfig(); fetchHistory(); }, [fetchConfig, fetchHistory]);

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const data = await apiFetch("/carriers/verizon/test-connection", { method: "POST" });
      setTestResult(data);
      if (data.ok) {
        toast.success("Verizon connection successful");
      } else {
        toast.error(data.message || "Connection test failed");
      }
    } catch (err) {
      setTestResult({ ok: false, message: err?.message || "Connection test failed" });
      toast.error("Connection test failed");
    }
    setTesting(false);
  };

  const handleSync = async () => {
    const isDryRun = syncMode === "preview";
    if (!isDryRun && !confirm("Run live sync? This will create/update SIM records in the database.")) return;
    setSyncing(true);
    setSyncResult(null);
    try {
      const data = await apiFetch(`/carriers/verizon/sync?dry_run=${isDryRun}`, { method: "POST" });
      setSyncResult(data);
      if (!isDryRun) fetchHistory();
      if (isDryRun) {
        toast.success(`Preview complete: ${data.created} to create, ${data.updated} to update`);
      } else {
        toast.success(`Sync complete: ${data.created} created, ${data.updated} updated`);
      }
    } catch (err) {
      toast.error(err?.message || "Sync failed");
    }
    setSyncing(false);
  };

  if (configLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const isConfigured = config?.configured || config?.is_configured;

  return (
    <div className="space-y-6">
      {/* Config Status */}
      <div className={`rounded-xl border p-4 ${isConfigured ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {isConfigured ? (
              <Wifi className="w-5 h-5 text-emerald-600" />
            ) : (
              <WifiOff className="w-5 h-5 text-amber-600" />
            )}
            <div>
              <div className={`text-sm font-semibold ${isConfigured ? "text-emerald-800" : "text-amber-800"}`}>
                {isConfigured ? "Verizon ThingSpace Configured" : "Verizon ThingSpace Not Configured"}
              </div>
              <div className={`text-xs mt-0.5 ${isConfigured ? "text-emerald-600" : "text-amber-600"}`}>
                {isConfigured
                  ? `Auth mode: ${config.auth_mode || "—"} | M2M: ${config.m2m_auth_mode || "—"}`
                  : config?.error || "Set VERIZON_THINGSPACE_* environment variables to enable"
                }
              </div>
            </div>
          </div>
          <button
            onClick={fetchConfig}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-white/50 rounded-lg"
            title="Refresh config"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        {config?.missing_vars?.length > 0 && (
          <div className="mt-3 text-xs text-amber-700">
            Missing: <span className="font-mono">{config.missing_vars.join(", ")}</span>
          </div>
        )}
      </div>

      {/* Actions */}
      {isConfigured && can("MANAGE_INTEGRATIONS") && (
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Radio className="w-4 h-4" />}
            Test Connection
          </button>

          <button
            onClick={async () => {
              setPolling(true);
              setPollResult(null);
              try {
                const data = await apiFetch("/carriers/verizon/poll-telemetry", { method: "POST" });
                setPollResult(data);
                toast.success(`Telemetry polled: ${data.updated} device(s) updated`);
              } catch (err) {
                toast.error(err?.message || "Telemetry poll failed");
              }
              setPolling(false);
            }}
            disabled={polling}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {polling ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Poll Telemetry
          </button>

          <div className="flex items-center gap-1 bg-white border border-gray-200 rounded-lg overflow-hidden">
            <select
              value={syncMode}
              onChange={(e) => setSyncMode(e.target.value)}
              className="px-3 py-2 text-sm border-none focus:outline-none bg-transparent"
            >
              <option value="preview">Preview (Dry Run)</option>
              <option value="live">Live Sync</option>
            </select>
            <button
              onClick={handleSync}
              disabled={syncing}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
                syncMode === "live"
                  ? "bg-red-600 hover:bg-red-700 text-white"
                  : "bg-blue-600 hover:bg-blue-700 text-white"
              } disabled:opacity-50`}
            >
              {syncing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : syncMode === "preview" ? (
                <Eye className="w-4 h-4" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {syncing ? "Syncing..." : syncMode === "preview" ? "Preview" : "Sync Now"}
            </button>
          </div>
        </div>
      )}

      {/* Test Connection Result */}
      {testResult && (
        <div className={`rounded-xl border p-4 ${testResult.ok ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}>
          <div className="flex items-center gap-2 mb-2">
            {testResult.ok ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            ) : (
              <XCircle className="w-5 h-5 text-red-600" />
            )}
            <span className={`text-sm font-semibold ${testResult.ok ? "text-emerald-800" : "text-red-800"}`}>
              {testResult.ok ? "Connection Successful" : "Connection Failed"}
            </span>
          </div>
          <p className={`text-xs ${testResult.ok ? "text-emerald-700" : "text-red-700"}`}>
            {testResult.message}
          </p>
          {testResult.account_name && (
            <div className="mt-2 text-xs text-gray-600">
              Account: <span className="font-mono">{testResult.account_name}</span>
              {testResult.m2m_account_id && <> | M2M ID: <span className="font-mono">{testResult.m2m_account_id}</span></>}
            </div>
          )}
        </div>
      )}

      {/* Poll Telemetry Result */}
      {pollResult && (
        <div className="rounded-xl border p-4 bg-indigo-50 border-indigo-200">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle2 className="w-5 h-5 text-indigo-600" />
            <span className="text-sm font-semibold text-indigo-800">Telemetry Poll Complete</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Fetched", value: pollResult.total_fetched, color: "text-gray-700" },
              { label: "Checked", value: pollResult.checked, color: "text-blue-700" },
              { label: "Updated", value: pollResult.updated, color: "text-emerald-700" },
              { label: "Errors", value: pollResult.errors, color: pollResult.errors > 0 ? "text-red-700" : "text-gray-500" },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-lg p-3 text-center border border-gray-100">
                <div className={`text-2xl font-bold ${color}`}>{value}</div>
                <div className="text-[11px] text-gray-500 uppercase font-medium">{label}</div>
              </div>
            ))}
          </div>
          {pollResult.fields_not_available?.length > 0 && (
            <div className="mt-3 text-xs text-indigo-700">
              Not available from Verizon: {pollResult.fields_not_available.join(", ")}
            </div>
          )}
        </div>
      )}

      {/* Sync Result */}
      {syncResult && (
        <div className="space-y-4">
          <div className={`rounded-xl border p-4 ${syncResult.dry_run ? "bg-blue-50 border-blue-200" : "bg-emerald-50 border-emerald-200"}`}>
            <div className="flex items-center gap-2 mb-3">
              {syncResult.dry_run ? (
                <Eye className="w-5 h-5 text-blue-600" />
              ) : (
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              )}
              <span className={`text-sm font-semibold ${syncResult.dry_run ? "text-blue-800" : "text-emerald-800"}`}>
                {syncResult.dry_run ? "Sync Preview" : "Sync Complete"}
              </span>
              <span className="text-xs text-gray-500 ml-auto">
                Tenant: <span className="font-mono">{syncResult.tenant_id}</span>
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "Fetched", value: syncResult.total_fetched, color: "text-gray-700" },
                { label: syncResult.dry_run ? "SIMs to Create" : "SIMs Created", value: syncResult.created, color: "text-emerald-700" },
                { label: syncResult.dry_run ? "SIMs to Update" : "SIMs Updated", value: syncResult.updated, color: "text-blue-700" },
                { label: "Skipped", value: syncResult.skipped, color: syncResult.skipped > 0 ? "text-amber-700" : "text-gray-500" },
                { label: syncResult.dry_run ? "Devices to Create" : "Devices Created", value: syncResult.devices_created || 0, color: "text-violet-700" },
                { label: syncResult.dry_run ? "Links to Create" : "Devices Linked", value: syncResult.devices_linked || 0, color: "text-indigo-700" },
                { label: "Carrier Set", value: syncResult.carrier_set || 0, color: "text-teal-700" },
                { label: "Unchanged", value: syncResult.unchanged, color: "text-gray-500" },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-white rounded-lg p-3 text-center border border-gray-100">
                  <div className={`text-2xl font-bold ${color}`}>{value}</div>
                  <div className="text-[11px] text-gray-500 uppercase font-medium">{label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Conflicts */}
          {syncResult.conflicts?.length > 0 && (
            <div className="bg-white rounded-xl border border-amber-200 overflow-hidden">
              <div className="px-4 py-3 bg-amber-50 border-b border-amber-200 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                <span className="text-sm font-semibold text-amber-800">Conflicts ({syncResult.conflicts.length})</span>
              </div>
              <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-gray-50">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <th className="px-4 py-2">ICCID</th>
                      <th className="px-4 py-2">MSISDN</th>
                      <th className="px-4 py-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {syncResult.conflicts.map((c, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-4 py-2 font-mono text-xs">{c.iccid || "—"}</td>
                        <td className="px-4 py-2 font-mono text-xs">{c.msisdn || "—"}</td>
                        <td className="px-4 py-2 text-xs text-red-600">{c.reason || c.conflict || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Details (first 50) */}
          {syncResult.details?.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <span className="text-sm font-semibold text-gray-700">
                  Actions ({syncResult.details.length}{syncResult.details.length >= 100 ? "+" : ""})
                </span>
              </div>
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-gray-50">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <th className="px-4 py-2">Action</th>
                      <th className="px-4 py-2">ICCID</th>
                      <th className="px-4 py-2">MSISDN</th>
                      <th className="px-4 py-2">Status</th>
                      <th className="px-4 py-2">Carrier</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {syncResult.details.map((d, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-4 py-2">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${
                            d.action === "create" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                            d.action === "update" ? "bg-blue-50 text-blue-700 border-blue-200" :
                            "bg-gray-100 text-gray-600 border-gray-200"
                          }`}>
                            {d.action}
                          </span>
                        </td>
                        <td className="px-4 py-2 font-mono text-xs">{d.iccid || "—"}</td>
                        <td className="px-4 py-2 font-mono text-xs">{d.msisdn || "—"}</td>
                        <td className="px-4 py-2 text-xs">{d.status || "—"}</td>
                        <td className="px-4 py-2 text-xs">{d.carrier || "verizon"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sync History */}
      {isConfigured && syncHistory.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-500" />
              <span className="text-sm font-semibold text-gray-700">Sync History</span>
            </div>
            <button onClick={fetchHistory} className="text-xs text-gray-400 hover:text-gray-600">
              <RefreshCw className={`w-3.5 h-3.5 ${historyLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
          <div className="divide-y divide-gray-100 max-h-[300px] overflow-y-auto">
            {syncHistory.map(h => {
              const m = h.metadata || {};
              const isLive = m.mode === "live";
              return (
                <div key={h.id} className="px-4 py-3 flex items-start gap-3">
                  <div className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${isLive ? "bg-emerald-500" : "bg-blue-400"}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border ${
                        isLive ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-blue-50 text-blue-700 border-blue-200"
                      }`}>
                        {isLive ? "Live" : "Preview"}
                      </span>
                      <span className="text-xs text-gray-400">{timeSince(h.created_at)}</span>
                      {m.initiated_by && <span className="text-[10px] text-gray-400 ml-auto truncate">{m.initiated_by}</span>}
                    </div>
                    <div className="text-xs text-gray-600">
                      {m.total_fetched ?? 0} fetched
                      {" / "}{m.sims_created ?? 0} created
                      {" / "}{m.sims_updated ?? 0} updated
                      {m.devices_created ? ` / ${m.devices_created} devices` : ""}
                      {m.conflicts ? ` / ${m.conflicts} conflicts` : ""}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Empty state when no results yet */}
      {!syncResult && !testResult && isConfigured && syncHistory.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400">
          <Radio className="w-8 h-8 mx-auto mb-2 text-gray-300" />
          <div className="text-sm">Use the buttons above to test connectivity or preview a sync.</div>
        </div>
      )}
    </div>
  );
}


/* ── Main Page ── */
/* ── Zoho CRM Tab ── */
function ZohoCRMTab() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiFetch("/zoho-crm/config");
        setConfig(data);
      } catch { setConfig({ configured: false }); }
      setLoading(false);
    })();
  }, []);

  const handleSync = async (type) => {
    setSyncing(type);
    try {
      const result = await apiFetch(`/zoho-crm/sync/${type}`, { method: "POST" });
      setLastResult({ type, ...result, time: new Date().toISOString() });
      toast.success(`Zoho ${type} sync: ${result.created || 0} created, ${result.updated || 0} updated`);
    } catch (err) {
      toast.error(err?.message || `Zoho ${type} sync failed`);
      setLastResult({ type, error: err?.message, time: new Date().toISOString() });
    }
    setSyncing(null);
  };

  const handleTest = async () => {
    setSyncing("test");
    try {
      const result = await apiFetch("/zoho-crm/test-connection", { method: "POST" });
      if (result.ok) toast.success("Zoho CRM connected successfully");
      else toast.error(result.message || "Connection failed");
    } catch (err) {
      toast.error(err?.message || "Connection test failed");
    }
    setSyncing(null);
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-sm text-gray-400 py-8 justify-center"><Loader2 className="w-4 h-4 animate-spin" /> Loading...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Connection status */}
      <div className={`rounded-xl border p-5 ${config?.configured ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${config?.configured ? "bg-emerald-100" : "bg-amber-100"}`}>
              {config?.configured ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> : <AlertTriangle className="w-5 h-5 text-amber-600" />}
            </div>
            <div>
              <div className={`text-sm font-bold ${config?.configured ? "text-emerald-800" : "text-amber-800"}`}>
                Zoho CRM {config?.configured ? "Connected" : "Not Configured"}
              </div>
              <div className="text-xs text-gray-500 mt-0.5">
                {config?.configured ? `API: ${config.api_domain}` : "Set ZOHO_CRM_CLIENT_ID, ZOHO_CRM_CLIENT_SECRET, ZOHO_CRM_REFRESH_TOKEN"}
              </div>
            </div>
          </div>
          {config?.configured && (
            <button onClick={handleTest} disabled={syncing === "test"}
              className="px-3 py-1.5 border border-gray-200 bg-white hover:bg-gray-50 rounded-lg text-xs font-medium text-gray-700">
              {syncing === "test" ? <Loader2 className="w-3 h-3 animate-spin" /> : "Test Connection"}
            </button>
          )}
        </div>
      </div>

      {/* Sync actions */}
      {config?.configured && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="text-sm font-bold text-gray-800 mb-1">Accounts → Customers</div>
            <p className="text-xs text-gray-500 mb-3">Pull Zoho CRM Accounts and create/update True911 Customer records.</p>
            <button onClick={() => handleSync("accounts")} disabled={!!syncing}
              className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-lg text-xs font-semibold">
              {syncing === "accounts" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowDownUp className="w-3.5 h-3.5" />}
              Sync Accounts
            </button>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="text-sm font-bold text-gray-800 mb-1">Contacts → Customer Details</div>
            <p className="text-xs text-gray-500 mb-3">Pull Zoho CRM Contacts and update primary contact info on linked Customers.</p>
            <button onClick={() => handleSync("contacts")} disabled={!!syncing}
              className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-lg text-xs font-semibold">
              {syncing === "contacts" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowDownUp className="w-3.5 h-3.5" />}
              Sync Contacts
            </button>
          </div>
        </div>
      )}

      {/* Last result */}
      {lastResult && (
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-500 uppercase mb-2">Last Sync Result</div>
          <div className="text-sm text-gray-800">
            <span className="font-semibold">{lastResult.type}</span>
            {lastResult.error ? (
              <span className="text-red-600 ml-2">Error: {lastResult.error}</span>
            ) : (
              <span className="text-gray-600 ml-2">
                {lastResult.created != null && `${lastResult.created} created`}
                {lastResult.updated != null && `, ${lastResult.updated} updated`}
                {lastResult.skipped != null && `, ${lastResult.skipped} skipped`}
              </span>
            )}
          </div>
          <div className="text-[10px] text-gray-400 mt-1">{timeSince(lastResult.time)}</div>
        </div>
      )}
    </div>
  );
}


export default function IntegrationSync() {
  const [tab, setTab] = useState("verizon");

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <ArrowDownUp className="w-6 h-6 text-red-600" />
              Integration Sync
            </h1>
            <p className="text-sm text-gray-500 mt-1">Carrier sync, CRM sync, webhook events, and billing reconciliation</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
          {[
            { key: "verizon", label: "Verizon Sync" },
            { key: "zoho", label: "Zoho CRM" },
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

        {tab === "verizon" && <VerizonTab />}
        {tab === "zoho" && <ZohoCRMTab />}
        {tab === "events" && <EventsTab />}
        {tab === "reconciliation" && <ReconciliationTab />}
      </div>
    </PageWrapper>
  );
}
