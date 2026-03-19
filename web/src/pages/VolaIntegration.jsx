import { useState, useEffect, useCallback } from "react";
import { Vola, Provider, Site, Device } from "@/api/entities";
import { apiFetch } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import PageWrapper from "@/components/PageWrapper";
import { toast } from "sonner";
import {
  Radio, RefreshCw, Loader2, CheckCircle2, XCircle,
  Download, RotateCcw, Settings, Link2, Wifi, WifiOff,
  ChevronDown, ChevronUp, Play, Eye,
} from "lucide-react";

/* ── Test Connection Panel ── */
function ConnectionPanel() {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await Vola.testConnection();
      setResult(res);
    } catch (err) {
      setResult({ ok: false, message: err?.message || "Connection test failed" });
    }
    setTesting(false);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-gray-900">VOLA Connection</h3>
        <button
          onClick={handleTest}
          disabled={testing}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg text-xs font-semibold"
        >
          {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
          Test Connection
        </button>
      </div>
      {result && (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${result.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
          {result.ok ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          <span>{result.message}</span>
          {result.vola_base_url && <span className="text-gray-500 ml-2">({result.vola_base_url})</span>}
        </div>
      )}
    </div>
  );
}

/* ── Last Action Result banner ── */
const ACTION_STYLES = {
  success: "bg-emerald-50 border-emerald-200 text-emerald-800",
  failed: "bg-red-50 border-red-200 text-red-800",
  error: "bg-red-50 border-red-200 text-red-800",
  pending: "bg-amber-50 border-amber-200 text-amber-800",
};

function ActionResult({ result, onDismiss }) {
  if (!result) return null;
  const style = ACTION_STYLES[result.status] || ACTION_STYLES.pending;
  const icon = result.status === "success"
    ? <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
    : <XCircle className="w-3.5 h-3.5 flex-shrink-0" />;

  return (
    <div className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-xs ${style}`}>
      {icon}
      <div className="flex-1 min-w-0">
        <span className="font-semibold">{result.action}:</span>{" "}
        <span>{result.message}</span>
        {result.details && (
          <div className="mt-1 font-mono text-[11px] opacity-80 break-all">{result.details}</div>
        )}
      </div>
      <button onClick={onDismiss} className="text-gray-400 hover:text-gray-600 flex-shrink-0">
        <XCircle className="w-3 h-3" />
      </button>
    </div>
  );
}

/* ── VOLA Device Card ── */
function VolaDeviceCard({ device, sites }) {
  const [expanded, setExpanded] = useState(false);
  const [rebooting, setRebooting] = useState(false);
  const [reading, setReading] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [siteCode, setSiteCode] = useState("");
  const [readResult, setReadResult] = useState(null);
  const [lastAction, setLastAction] = useState(null);

  const handleReboot = async () => {
    setRebooting(true);
    setLastAction(null);
    try {
      const res = await Vola.reboot(device.device_sn);
      setLastAction({ action: "Reboot", status: "success", message: `Task created`, details: `task_id: ${res.task_id}` });
    } catch (err) {
      setLastAction({ action: "Reboot", status: "error", message: err?.message || "Failed to create reboot task" });
    }
    setRebooting(false);
  };

  const handleReadStatus = async () => {
    setReading(true);
    setLastAction(null);
    try {
      const res = await Vola.readParams(device.device_sn, [
        "Device.DeviceInfo.SoftwareVersion",
        "Device.DeviceInfo.ModelName",
        "Device.DeviceInfo.ProvisioningCode",
        "Device.ManagementServer.PeriodicInformInterval",
      ]);
      setReadResult(res);
      const count = Object.keys(res.extracted_values || {}).length;
      setLastAction({ action: "Read Status", status: res.status, message: `${count} parameter(s) returned`, details: `task_id: ${res.task_id}` });
    } catch (err) {
      setLastAction({ action: "Read Status", status: "error", message: err?.message || "Failed to read parameters" });
    }
    setReading(false);
  };

  const handleProvision = async () => {
    if (!siteCode.trim()) {
      toast.error("Enter a site code first");
      return;
    }
    setProvisioning(true);
    setLastAction(null);
    try {
      const res = await Vola.provisionBasic(device.device_sn, siteCode.trim());
      const appliedStr = Object.entries(res.applied || {}).map(([k, v]) => `${k.split(".").pop()}=${v}`).join(", ");
      setLastAction({ action: "Provision", status: res.status, message: appliedStr || "Parameters sent", details: `task_id: ${res.task_id}` });
    } catch (err) {
      setLastAction({ action: "Provision", status: "error", message: err?.message || "Provisioning failed" });
    }
    setProvisioning(false);
  };

  const isOnline = device.status === "online";

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${isOnline ? "bg-emerald-500" : "bg-gray-400"}`} />
          <div>
            <div className="text-sm font-semibold text-gray-900">{device.device_sn}</div>
            <div className="text-xs text-gray-500">{device.model} | MAC: {device.mac || "---"}</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${isOnline ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
            {device.status || "unknown"}
          </span>
          <span className="text-xs text-gray-400">{device.firmware_version}</span>
          {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-100 pt-3">
          {/* Info */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div><span className="text-gray-400 block">SN</span><span className="font-mono">{device.device_sn}</span></div>
            <div><span className="text-gray-400 block">MAC</span><span className="font-mono">{device.mac || "---"}</span></div>
            <div><span className="text-gray-400 block">IP</span><span className="font-mono">{device.ip || "---"}</span></div>
            <div><span className="text-gray-400 block">Org</span><span>{device.org_name || device.org_id || "---"}</span></div>
          </div>

          {/* Last action result */}
          <ActionResult result={lastAction} onDismiss={() => setLastAction(null)} />

          {/* Actions */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleReboot}
              disabled={rebooting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 rounded-lg text-xs font-medium"
            >
              {rebooting ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
              Reboot
            </button>
            <button
              onClick={handleReadStatus}
              disabled={reading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-lg text-xs font-medium"
            >
              {reading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />}
              Read Status
            </button>
          </div>

          {/* Read result — parameter values table */}
          {readResult && (
            <div className="bg-gray-50 rounded-lg p-3 text-xs space-y-1">
              <div className="font-semibold text-gray-700 mb-1">Parameters ({readResult.status})</div>
              {Object.entries(readResult.extracted_values || {}).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-gray-500 font-mono truncate mr-2">{k}</span>
                  <span className="font-mono text-gray-800">{v}</span>
                </div>
              ))}
              {Object.keys(readResult.extracted_values || {}).length === 0 && (
                <div className="text-gray-400">No values returned</div>
              )}
            </div>
          )}

          {/* Provisioning */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-2">
            <div className="text-xs font-semibold text-gray-700">Quick Provision</div>
            <div className="flex gap-2">
              <input
                value={siteCode}
                onChange={e => setSiteCode(e.target.value)}
                placeholder="Site code (e.g. SITE-001)"
                className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-xs"
              />
              <button
                onClick={handleProvision}
                disabled={provisioning || !siteCode.trim()}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg text-xs font-semibold"
              >
                {provisioning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                Provision
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main VOLA Integration Page ── */
export default function VolaIntegration() {
  const { can } = useAuth();
  const [volaDevices, setVolaDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  const fetchSites = useCallback(async () => {
    try {
      const data = await Site.list("-created_at", 200);
      setSites(data);
    } catch {}
  }, []);

  useEffect(() => { fetchSites(); }, [fetchSites]);

  const handleFetchDevices = async () => {
    setLoading(true);
    try {
      const res = await Vola.listDevices();
      setVolaDevices(res.devices || []);
      toast.success(`Found ${res.total} VOLA device(s)`);
    } catch (err) {
      toast.error(err?.message || "Failed to fetch VOLA devices");
    }
    setLoading(false);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await Vola.syncDevices();
      setSyncResult(res);
      toast.success(`Sync complete: ${res.imported} imported, ${res.updated} updated, ${res.skipped} skipped`);
    } catch (err) {
      toast.error(err?.message || "Sync failed");
    }
    setSyncing(false);
  };

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">VOLA / PR12 Integration</h1>
            <p className="text-sm text-gray-500 mt-0.5">Manage FlyingVoice PR12 devices via VOLA Cloud TR-069</p>
          </div>
        </div>

        {/* Connection test */}
        <ConnectionPanel />

        {/* Actions bar */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleFetchDevices}
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-2 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg text-sm font-semibold text-gray-700"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Fetch VOLA Devices
          </button>
          {can("MANAGE_DEVICES") && (
            <button
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg text-sm font-semibold"
            >
              {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              Sync to True911
            </button>
          )}
        </div>

        {/* Sync result banner */}
        {syncResult && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-sm text-emerald-800">
            <span className="font-semibold">Last sync:</span>{" "}
            {syncResult.imported} imported, {syncResult.updated} updated, {syncResult.skipped} skipped
          </div>
        )}

        {/* Device list */}
        {volaDevices.length > 0 && (
          <div className="space-y-2">
            <h2 className="text-sm font-bold text-gray-700">{volaDevices.length} VOLA Device(s)</h2>
            {volaDevices.map(d => (
              <VolaDeviceCard key={d.device_sn} device={d} sites={sites} />
            ))}
          </div>
        )}

        {volaDevices.length === 0 && !loading && (
          <div className="text-center py-12">
            <Radio className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <div className="text-sm font-semibold text-gray-500">No VOLA devices loaded</div>
            <div className="text-xs text-gray-400 mt-1">Click "Fetch VOLA Devices" to pull the device list from VOLA Cloud.</div>
          </div>
        )}

        {/* Quick guide */}
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-bold text-gray-900 mb-2">PR12 Deployment Workflow</h3>
          <ol className="text-xs text-gray-600 space-y-1.5 list-decimal list-inside">
            <li>Create a <strong>Customer</strong> (Customers page) and a <strong>Site</strong> (Sites page)</li>
            <li>Create a <strong>VOLA Provider</strong> (Providers page, type "vola", store credentials in config_json)</li>
            <li>Click <strong>"Test Connection"</strong> above to verify VOLA API access</li>
            <li>Click <strong>"Fetch VOLA Devices"</strong> to see available PR12s</li>
            <li>Click <strong>"Sync to True911"</strong> to import them as device records</li>
            <li>Go to <strong>Devices page</strong> to assign synced PR12s to your site</li>
            <li>Use <strong>"Quick Provision"</strong> on each device to push site code and inform interval</li>
            <li>Use <strong>"Reboot"</strong> if the device needs to pick up new config</li>
            <li>Use <strong>"Read Status"</strong> to verify parameters were applied</li>
          </ol>
        </div>
      </div>
    </PageWrapper>
  );
}
