import { useState, useEffect, useCallback } from "react";
import { Vola, Provider, Site, Device, Customer } from "@/api/entities";
import { apiFetch } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import PageWrapper from "@/components/PageWrapper";
import { toast } from "sonner";
import {
  Radio, RefreshCw, Loader2, CheckCircle2, XCircle, X,
  Download, RotateCcw, Settings, Link2, Wifi, WifiOff,
  ChevronDown, ChevronUp, Play, Eye, Rocket, Plus,
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
            <div><span className="text-gray-400 block">Model</span><span className="font-mono">{device.model || "---"}</span></div>
            <div><span className="text-gray-400 block">Org</span><span>{device.org_name || device.org_id || "---"}</span></div>
            <div><span className="text-gray-400 block">Last Update</span><span>{device.last_update || "---"}</span></div>
          </div>
          {device.line_accounts?.filter(Boolean).length > 0 && (
            <div className="text-xs text-gray-500">Lines: {device.line_accounts.filter(Boolean).join(", ")}</div>
          )}

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

/* ── Step indicator ── */
function StepDot({ step, current, label }) {
  const done = current > step;
  const active = current === step;
  return (
    <div className="flex items-center gap-2">
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border-2 ${
        done ? "bg-emerald-600 border-emerald-600 text-white" :
        active ? "bg-red-600 border-red-600 text-white" :
        "bg-white border-gray-300 text-gray-400"
      }`}>
        {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : step}
      </div>
      <span className={`text-xs font-medium ${active ? "text-gray-900" : done ? "text-emerald-700" : "text-gray-400"}`}>{label}</span>
    </div>
  );
}

/* ── Deploy result row ── */
function DeployResultRow({ r }) {
  const ok = r.status === "success";
  const partial = r.status === "partial";
  return (
    <div className={`flex items-start gap-3 px-4 py-3 rounded-lg border ${ok ? "bg-emerald-50 border-emerald-200" : partial ? "bg-amber-50 border-amber-200" : "bg-red-50 border-red-200"}`}>
      <div className="flex-shrink-0 mt-0.5">
        {ok ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <XCircle className="w-4 h-4 text-red-600" />}
      </div>
      <div className="flex-1 min-w-0 text-xs">
        <div className="font-semibold text-gray-900">{r.device_sn}</div>
        {r.device_id && <div className="text-gray-500">Device: {r.device_id}</div>}
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
          {Object.entries(r.steps || {}).map(([k, v]) => (
            <span key={k} className={`font-mono ${v === "ok" || v === "success" ? "text-emerald-700" : "text-red-700"}`}>
              {k}: {v}
            </span>
          ))}
        </div>
        {r.applied && Object.keys(r.applied).length > 0 && (
          <div className="mt-1 text-gray-600">
            Applied: {Object.entries(r.applied).map(([k, v]) => `${k.split(".").pop()}=${v}`).join(", ")}
          </div>
        )}
        {r.error && <div className="mt-1 text-red-700">{r.error}</div>}
      </div>
    </div>
  );
}

/* ── Quick Deploy Modal ── */
function QuickDeployModal({ onClose }) {
  const [step, setStep] = useState(1);

  // Step 1: Site
  const [sites, setSites] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [loadingSites, setLoadingSites] = useState(true);
  // Inline create
  const [showNewSite, setShowNewSite] = useState(false);
  const [newSiteName, setNewSiteName] = useState("");
  const [newSiteId, setNewSiteId] = useState("");
  const [newSiteCustomer, setNewSiteCustomer] = useState("");
  const [creatingSite, setCreatingSite] = useState(false);
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [newCustomerName, setNewCustomerName] = useState("");
  const [creatingCustomer, setCreatingCustomer] = useState(false);

  // Step 2: Devices
  const [volaDevices, setVolaDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [selectedSns, setSelectedSns] = useState(new Set());

  // Step 3: Config + Deploy
  const [siteCode, setSiteCode] = useState("");
  const [informInterval, setInformInterval] = useState("300");
  const [deploying, setDeploying] = useState(false);
  const [deployResult, setDeployResult] = useState(null);

  // Load sites + customers on mount
  useEffect(() => {
    (async () => {
      try {
        const [s, c] = await Promise.all([
          Site.list("-created_at", 200),
          Customer.list("-created_at", 200).catch(() => []),
        ]);
        setSites(s);
        setCustomers(c);
      } catch {}
      setLoadingSites(false);
    })();
  }, []);

  const handleCreateCustomer = async () => {
    if (!newCustomerName.trim()) return;
    setCreatingCustomer(true);
    try {
      const c = await Customer.create({ name: newCustomerName.trim() });
      setCustomers(prev => [c, ...prev]);
      setNewSiteCustomer(c.name);
      setShowNewCustomer(false);
      setNewCustomerName("");
      toast.success(`Customer "${c.name}" created`);
    } catch (err) {
      toast.error(err?.message || "Failed to create customer");
    }
    setCreatingCustomer(false);
  };

  const handleCreateSite = async () => {
    if (!newSiteName.trim() || !newSiteId.trim()) return;
    setCreatingSite(true);
    try {
      const s = await Site.create({
        site_id: newSiteId.trim(),
        site_name: newSiteName.trim(),
        customer_name: newSiteCustomer || "Default",
        status: "Pending",
      });
      setSites(prev => [s, ...prev]);
      setSelectedSiteId(s.site_id);
      setShowNewSite(false);
      setSiteCode(s.site_id);
      toast.success(`Site "${s.site_name}" created`);
    } catch (err) {
      toast.error(err?.message || "Failed to create site");
    }
    setCreatingSite(false);
  };

  // When moving to step 2, auto-fetch devices
  const goToStep2 = async () => {
    setStep(2);
    if (volaDevices.length === 0) {
      setLoadingDevices(true);
      try {
        const res = await Vola.listDevices();
        setVolaDevices(res.devices || []);
      } catch (err) {
        toast.error(err?.message || "Failed to fetch VOLA devices");
      }
      setLoadingDevices(false);
    }
  };

  const toggleDevice = (sn) => {
    setSelectedSns(prev => {
      const next = new Set(prev);
      next.has(sn) ? next.delete(sn) : next.add(sn);
      return next;
    });
  };

  const handleDeploy = async () => {
    setDeploying(true);
    setDeployResult(null);
    try {
      const res = await Vola.deploy(
        selectedSiteId,
        [...selectedSns],
        siteCode.trim(),
        parseInt(informInterval, 10) || 300,
      );
      setDeployResult(res);
      if (res.failed === 0) {
        toast.success(`All ${res.succeeded} device(s) deployed successfully`);
      } else {
        toast.warning(`${res.succeeded} succeeded, ${res.failed} failed`);
      }
    } catch (err) {
      toast.error(err?.message || "Deploy failed");
      setDeployResult({ total: selectedSns.size, succeeded: 0, failed: selectedSns.size, results: [], error: err?.message });
    }
    setDeploying(false);
  };

  const selectedSite = sites.find(s => s.site_id === selectedSiteId);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Rocket className="w-5 h-5 text-red-600" />
            <h3 className="text-base font-bold text-gray-900">Quick Deploy PR12</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Steps indicator */}
        <div className="flex items-center gap-6 px-6 py-3 border-b border-gray-50 bg-gray-50/50">
          <StepDot step={1} current={step} label="Site" />
          <div className="flex-1 h-px bg-gray-200" />
          <StepDot step={2} current={step} label="Devices" />
          <div className="flex-1 h-px bg-gray-200" />
          <StepDot step={3} current={step} label="Deploy" />
        </div>

        <div className="p-6">
          {/* ── Step 1: Site ── */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Select Site *</label>
                {loadingSites ? (
                  <div className="flex items-center gap-2 text-xs text-gray-400 py-2"><Loader2 className="w-3 h-3 animate-spin" /> Loading sites...</div>
                ) : (
                  <select
                    value={selectedSiteId}
                    onChange={e => {
                      setSelectedSiteId(e.target.value);
                      const s = sites.find(x => x.site_id === e.target.value);
                      if (s && !siteCode) setSiteCode(s.site_id);
                    }}
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
                  >
                    <option value="">-- Choose a site --</option>
                    {sites.map(s => (
                      <option key={s.site_id} value={s.site_id}>{s.site_name} ({s.site_id})</option>
                    ))}
                  </select>
                )}
              </div>

              {!showNewSite && (
                <button onClick={() => setShowNewSite(true)} className="flex items-center gap-1.5 text-xs text-red-600 hover:text-red-700 font-medium">
                  <Plus className="w-3 h-3" /> Create new site
                </button>
              )}

              {showNewSite && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
                  <div className="text-xs font-bold text-blue-800 uppercase tracking-wide">New Site</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Site ID *</label>
                      <input value={newSiteId} onChange={e => setNewSiteId(e.target.value)} placeholder="e.g. SITE-001" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Site Name *</label>
                      <input value={newSiteName} onChange={e => setNewSiteName(e.target.value)} placeholder="e.g. Main Office" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Customer</label>
                    <div className="flex gap-2">
                      <select value={newSiteCustomer} onChange={e => setNewSiteCustomer(e.target.value)} className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm">
                        <option value="">-- Select customer --</option>
                        {customers.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
                      </select>
                      {!showNewCustomer && (
                        <button onClick={() => setShowNewCustomer(true)} className="px-3 py-2 text-xs text-red-600 border border-red-200 rounded-lg hover:bg-red-50 font-medium">
                          <Plus className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>

                  {showNewCustomer && (
                    <div className="flex gap-2">
                      <input value={newCustomerName} onChange={e => setNewCustomerName(e.target.value)} placeholder="Customer name" className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                      <button onClick={handleCreateCustomer} disabled={creatingCustomer || !newCustomerName.trim()} className="px-3 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg text-xs font-semibold">
                        {creatingCustomer ? <Loader2 className="w-3 h-3 animate-spin" /> : "Add"}
                      </button>
                      <button onClick={() => setShowNewCustomer(false)} className="px-3 py-2 text-xs text-gray-600 border border-gray-200 rounded-lg">Cancel</button>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button onClick={handleCreateSite} disabled={creatingSite || !newSiteName.trim() || !newSiteId.trim()} className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg text-xs font-semibold">
                      {creatingSite ? <Loader2 className="w-3 h-3 animate-spin" /> : "Create Site"}
                    </button>
                    <button onClick={() => setShowNewSite(false)} className="px-4 py-2 text-xs text-gray-600 border border-gray-200 rounded-lg">Cancel</button>
                  </div>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button onClick={goToStep2} disabled={!selectedSiteId} className="px-5 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white rounded-xl text-sm font-semibold">
                  Next: Select Devices
                </button>
              </div>
            </div>
          )}

          {/* ── Step 2: Select Devices ── */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="text-xs text-gray-500">
                Site: <span className="font-semibold text-gray-800">{selectedSite?.site_name || selectedSiteId}</span>
              </div>

              {loadingDevices ? (
                <div className="flex items-center justify-center py-8 gap-2 text-sm text-gray-400"><Loader2 className="w-4 h-4 animate-spin" /> Loading VOLA devices...</div>
              ) : volaDevices.length === 0 ? (
                <div className="text-center py-8 text-sm text-gray-400">No VOLA devices found. Check your VOLA provider configuration.</div>
              ) : (
                <div className="space-y-1.5 max-h-64 overflow-y-auto">
                  {volaDevices.map(d => {
                    const checked = selectedSns.has(d.device_sn);
                    const isOnline = d.status === "online";
                    return (
                      <label key={d.device_sn} className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors ${checked ? "bg-red-50 border-red-200" : "bg-white border-gray-200 hover:bg-gray-50"}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleDevice(d.device_sn)} className="rounded border-gray-300 text-red-600 focus:ring-red-500" />
                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isOnline ? "bg-emerald-500" : "bg-gray-400"}`} />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold text-gray-900">{d.device_sn}</div>
                          <div className="text-xs text-gray-500">{d.model} | MAC: {d.mac || "---"} | {d.status || "unknown"}</div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}

              {selectedSns.size > 0 && (
                <div className="text-xs text-gray-600 font-medium">{selectedSns.size} device(s) selected</div>
              )}

              <div className="flex justify-between pt-2">
                <button onClick={() => setStep(1)} className="px-5 py-2.5 text-sm font-semibold text-gray-700 border border-gray-200 rounded-xl hover:bg-gray-50">
                  Back
                </button>
                <button onClick={() => { setStep(3); if (!siteCode) setSiteCode(selectedSiteId); }} disabled={selectedSns.size === 0} className="px-5 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white rounded-xl text-sm font-semibold">
                  Next: Configure & Deploy
                </button>
              </div>
            </div>
          )}

          {/* ── Step 3: Config + Deploy ── */}
          {step === 3 && !deployResult && (
            <div className="space-y-4">
              <div className="text-xs text-gray-500">
                Site: <span className="font-semibold text-gray-800">{selectedSite?.site_name || selectedSiteId}</span>
                {" | "}
                Devices: <span className="font-semibold text-gray-800">{selectedSns.size}</span>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Site Code *</label>
                  <input value={siteCode} onChange={e => setSiteCode(e.target.value)} placeholder="e.g. SITE-001" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Inform Interval (sec)</label>
                  <input value={informInterval} onChange={e => setInformInterval(e.target.value)} type="number" min="60" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                </div>
              </div>

              <div className="bg-gray-50 rounded-xl p-3 text-xs text-gray-600">
                <div className="font-semibold text-gray-700 mb-1">What will happen:</div>
                <ol className="list-decimal list-inside space-y-0.5">
                  <li>Each device will be created in True911 (if not already synced)</li>
                  <li>Each device will be bound to <strong>{selectedSite?.site_name || selectedSiteId}</strong></li>
                  <li>ProvisioningCode = <strong>{siteCode || "..."}</strong> and PeriodicInformInterval = <strong>{informInterval}s</strong> will be pushed</li>
                  <li>Each device will be rebooted to apply the configuration</li>
                </ol>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-xs text-amber-800">
                Deploying {selectedSns.size} device(s). This may take up to {selectedSns.size * 30} seconds.
              </div>

              <div className="flex justify-between pt-2">
                <button onClick={() => setStep(2)} disabled={deploying} className="px-5 py-2.5 text-sm font-semibold text-gray-700 border border-gray-200 rounded-xl hover:bg-gray-50">
                  Back
                </button>
                <button onClick={handleDeploy} disabled={deploying || !siteCode.trim()} className="flex items-center gap-2 px-6 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-xl text-sm font-bold">
                  {deploying ? <><Loader2 className="w-4 h-4 animate-spin" /> Deploying...</> : <><Rocket className="w-4 h-4" /> Deploy {selectedSns.size} Device(s)</>}
                </button>
              </div>
            </div>
          )}

          {/* ── Results ── */}
          {step === 3 && deployResult && (
            <div className="space-y-4">
              <div className={`flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold ${
                deployResult.failed === 0 ? "bg-emerald-50 text-emerald-800 border border-emerald-200" :
                deployResult.succeeded > 0 ? "bg-amber-50 text-amber-800 border border-amber-200" :
                "bg-red-50 text-red-800 border border-red-200"
              }`}>
                {deployResult.failed === 0 ? <CheckCircle2 className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                {deployResult.failed === 0
                  ? `All ${deployResult.succeeded} device(s) deployed successfully`
                  : `${deployResult.succeeded} succeeded, ${deployResult.failed} failed`
                }
              </div>

              <div className="space-y-2">
                {(deployResult.results || []).map(r => (
                  <DeployResultRow key={r.device_sn} r={r} />
                ))}
              </div>

              {deployResult.error && !deployResult.results?.length && (
                <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-xs text-red-800">
                  {deployResult.error}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <button onClick={() => { setDeployResult(null); setSelectedSns(new Set()); setStep(2); }} className="px-5 py-2.5 text-sm font-semibold text-gray-700 border border-gray-200 rounded-xl hover:bg-gray-50">
                  Deploy More
                </button>
                <button onClick={onClose} className="px-5 py-2.5 bg-gray-900 hover:bg-gray-800 text-white rounded-xl text-sm font-semibold">
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
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
  const [showQuickDeploy, setShowQuickDeploy] = useState(false);
  const [fetchAttempted, setFetchAttempted] = useState(false);

  const fetchSites = useCallback(async () => {
    try {
      const data = await Site.list("-created_at", 200);
      setSites(data);
    } catch {}
  }, []);

  useEffect(() => { fetchSites(); }, [fetchSites]);

  const handleFetchDevices = async () => {
    setLoading(true);
    setFetchAttempted(true);
    try {
      const res = await Vola.listDevices();
      setVolaDevices(res.devices || []);
      if (res.total > 0) {
        toast.success(`Found ${res.total} VOLA device(s)`);
      } else {
        toast.warning("Authenticated but 0 devices returned. Check org filter or device status in VOLA Cloud.");
      }
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

        {/* Quick Deploy CTA */}
        {can("MANAGE_DEVICES") && (
          <div className="bg-gradient-to-r from-red-600 to-red-700 rounded-xl p-5 text-white flex items-center justify-between">
            <div>
              <div className="text-base font-bold">PR12 Quick Deploy</div>
              <div className="text-sm text-red-100 mt-0.5">Select a site, pick devices, deploy in 3 steps</div>
            </div>
            <button onClick={() => setShowQuickDeploy(true)} className="flex items-center gap-2 px-5 py-2.5 bg-white text-red-700 rounded-xl text-sm font-bold hover:bg-red-50 transition-colors">
              <Rocket className="w-4 h-4" /> Quick Deploy
            </button>
          </div>
        )}

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
            {fetchAttempted ? (
              <>
                <div className="text-sm font-semibold text-amber-600">Authenticated, but no devices were returned</div>
                <div className="text-xs text-gray-500 mt-1 max-w-md mx-auto">
                  This may indicate an org filter mismatch, empty device scope, or different usage status.
                  Check your VOLA Cloud dashboard to confirm devices are under "In Use" for this organization.
                  If you have an org ID, set it in your VOLA provider config.
                </div>
              </>
            ) : (
              <>
                <div className="text-sm font-semibold text-gray-500">No VOLA devices loaded</div>
                <div className="text-xs text-gray-400 mt-1">Click "Fetch VOLA Devices" to pull the device list from VOLA Cloud.</div>
              </>
            )}
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

      {showQuickDeploy && (
        <QuickDeployModal onClose={() => setShowQuickDeploy(false)} />
      )}
    </PageWrapper>
  );
}
