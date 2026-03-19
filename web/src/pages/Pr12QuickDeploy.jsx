import { useState, useEffect, useCallback } from "react";
import { Vola, Site, Customer } from "@/api/entities";
import { useAuth } from "@/contexts/AuthContext";
import PageWrapper from "@/components/PageWrapper";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Rocket, RefreshCw, Loader2, CheckCircle2, XCircle, Plus, X,
  Wifi, WifiOff, Radio, Eye, ChevronRight, ExternalLink,
} from "lucide-react";

/* ── Status strip ── */
function StatusStrip({ connected, deviceCount, selectedSite, selectedCount }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {[
        {
          label: "VOLA Connection",
          value: connected === null ? "Checking..." : connected ? "Connected" : "Not connected",
          color: connected === null ? "text-gray-400" : connected ? "text-emerald-700" : "text-red-600",
          bg: connected === null ? "bg-gray-50" : connected ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200",
          icon: connected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />,
        },
        {
          label: "Available PR12s",
          value: deviceCount === null ? "---" : String(deviceCount),
          color: "text-gray-800",
          bg: "bg-gray-50 border-gray-200",
          icon: <Radio className="w-3.5 h-3.5 text-gray-400" />,
        },
        {
          label: "Target Site",
          value: selectedSite || "Not selected",
          color: selectedSite ? "text-gray-800" : "text-gray-400",
          bg: selectedSite ? "bg-blue-50 border-blue-200" : "bg-gray-50 border-gray-200",
        },
        {
          label: "Selected Devices",
          value: String(selectedCount),
          color: selectedCount > 0 ? "text-red-700" : "text-gray-400",
          bg: selectedCount > 0 ? "bg-red-50 border-red-200" : "bg-gray-50 border-gray-200",
        },
      ].map((s, i) => (
        <div key={i} className={`rounded-xl border px-4 py-3 ${s.bg}`}>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">{s.label}</div>
          <div className={`text-sm font-bold ${s.color} flex items-center gap-1.5`}>
            {s.icon}{s.value}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Step card wrapper ── */
function StepCard({ number, title, active, done, children }) {
  return (
    <div className={`rounded-xl border transition-colors ${active ? "border-red-300 bg-white shadow-sm" : done ? "border-emerald-200 bg-emerald-50/30" : "border-gray-200 bg-gray-50/50"}`}>
      <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-100">
        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
          done ? "bg-emerald-600 text-white" : active ? "bg-red-600 text-white" : "bg-gray-200 text-gray-500"
        }`}>
          {done ? <CheckCircle2 className="w-4 h-4" /> : number}
        </div>
        <h2 className={`text-sm font-bold ${active ? "text-gray-900" : done ? "text-emerald-800" : "text-gray-500"}`}>{title}</h2>
      </div>
      {(active || done) && <div className="p-5">{children}</div>}
    </div>
  );
}

/* ── Deploy result row ── */
function ResultRow({ r }) {
  const ok = r.status === "success";
  const partial = r.status === "partial";
  return (
    <div className={`flex items-start gap-3 px-4 py-3 rounded-xl border ${ok ? "bg-emerald-50 border-emerald-200" : partial ? "bg-amber-50 border-amber-200" : "bg-red-50 border-red-200"}`}>
      <div className="flex-shrink-0 mt-0.5">
        {ok ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> : <XCircle className="w-5 h-5 text-red-600" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-bold text-gray-900">{r.device_sn}</div>
        {r.device_id && <div className="text-xs text-gray-500 mt-0.5">Device: {r.device_id}</div>}
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
          {Object.entries(r.steps || {}).map(([k, v]) => {
            const isOk = v === "ok" || v === "success";
            return (
              <div key={k} className="flex items-center gap-1.5 text-xs">
                <div className={`w-1.5 h-1.5 rounded-full ${isOk ? "bg-emerald-500" : "bg-red-500"}`} />
                <span className="text-gray-600 capitalize">{k.replace(/_/g, " ")}</span>
                <span className={`font-mono ${isOk ? "text-emerald-700" : "text-red-700"}`}>{v}</span>
              </div>
            );
          })}
        </div>
        {r.applied && Object.keys(r.applied).length > 0 && (
          <div className="mt-1.5 text-xs text-gray-600">
            Applied: {Object.entries(r.applied).map(([k, v]) => `${k.split(".").pop()}=${v}`).join(", ")}
          </div>
        )}
        {r.error && <div className="mt-1.5 text-xs font-medium text-red-700">{r.error}</div>}
        {(r.provision_task_id || r.reboot_task_id) && (
          <div className="mt-1 text-[11px] font-mono text-gray-400">
            {r.provision_task_id && `provision: ${r.provision_task_id}`}
            {r.provision_task_id && r.reboot_task_id && " | "}
            {r.reboot_task_id && `reboot: ${r.reboot_task_id}`}
          </div>
        )}
      </div>
    </div>
  );
}


export default function Pr12QuickDeploy() {
  const { can } = useAuth();

  // Connection
  const [connected, setConnected] = useState(null);

  // Step 1: Customer & Site
  const [sites, setSites] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [loadingSites, setLoadingSites] = useState(true);
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [newCustomerName, setNewCustomerName] = useState("");
  const [creatingCustomer, setCreatingCustomer] = useState(false);
  const [showNewSite, setShowNewSite] = useState(false);
  const [newSiteName, setNewSiteName] = useState("");
  const [newSiteId, setNewSiteId] = useState("");
  const [newSiteCustomer, setNewSiteCustomer] = useState("");
  const [creatingSite, setCreatingSite] = useState(false);

  // Step 2: Devices
  const [volaDevices, setVolaDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [selectedSns, setSelectedSns] = useState(new Set());

  // Step 3: Config + Deploy
  const [siteCode, setSiteCode] = useState("");
  const [informInterval, setInformInterval] = useState("300");
  const [rebootAfter, setRebootAfter] = useState(true);

  // Results
  const [deploying, setDeploying] = useState(false);
  const [deployResult, setDeployResult] = useState(null);

  // ── Init: check connection, load sites/customers/devices ──
  useEffect(() => {
    (async () => {
      try {
        const connRes = await Vola.testConnection();
        setConnected(connRes.ok);
      } catch {
        setConnected(false);
      }

      try {
        const [s, c] = await Promise.all([
          Site.list("-created_at", 200),
          Customer.list("-created_at", 200).catch(() => []),
        ]);
        setSites(s);
        setCustomers(c);
      } catch {}
      setLoadingSites(false);

      // Auto-fetch VOLA devices
      try {
        setLoadingDevices(true);
        const res = await Vola.listDevices();
        setVolaDevices(res.devices || []);
      } catch {}
      setLoadingDevices(false);
    })();
  }, []);

  const refreshDevices = async () => {
    setLoadingDevices(true);
    try {
      const res = await Vola.listDevices();
      setVolaDevices(res.devices || []);
      toast.success(`Found ${res.total} device(s)`);
    } catch (err) {
      toast.error(err?.message || "Failed to fetch devices");
    }
    setLoadingDevices(false);
  };

  // ── Inline create ──
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
    } catch (err) { toast.error(err?.message || "Failed to create customer"); }
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
      setSiteCode(s.site_id);
      setShowNewSite(false);
      toast.success(`Site "${s.site_name}" created`);
    } catch (err) { toast.error(err?.message || "Failed to create site"); }
    setCreatingSite(false);
  };

  const toggleDevice = (sn) => {
    setSelectedSns(prev => {
      const next = new Set(prev);
      next.has(sn) ? next.delete(sn) : next.add(sn);
      return next;
    });
  };

  // ── Deploy ──
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
      if (res.failed === 0) toast.success(`All ${res.succeeded} device(s) deployed`);
      else toast.warning(`${res.succeeded} succeeded, ${res.failed} failed`);
    } catch (err) {
      toast.error(err?.message || "Deploy failed");
      setDeployResult({ total: selectedSns.size, succeeded: 0, failed: selectedSns.size, results: [] });
    }
    setDeploying(false);
  };

  // ── Derived state ──
  const selectedSite = sites.find(s => s.site_id === selectedSiteId);
  const step1Done = !!selectedSiteId;
  const step2Done = selectedSns.size > 0;
  const step3Ready = step1Done && step2Done && siteCode.trim();
  const currentStep = deployResult ? 4 : !step1Done ? 1 : !step2Done ? 2 : 3;

  if (!can("MANAGE_DEVICES")) {
    return (
      <PageWrapper>
        <div className="p-6 max-w-4xl mx-auto text-center py-16">
          <div className="text-sm text-gray-500">You need Admin permissions to deploy devices.</div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-4xl mx-auto space-y-5">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">PR12 Quick Deploy</h1>
          <p className="text-sm text-gray-500 mt-0.5">Deploy FlyingVoice PR12 devices to a customer site in a few guided steps</p>
        </div>

        {/* Status strip */}
        <StatusStrip
          connected={connected}
          deviceCount={loadingDevices ? null : volaDevices.length}
          selectedSite={selectedSite ? `${selectedSite.site_name} (${selectedSite.site_id})` : ""}
          selectedCount={selectedSns.size}
        />

        {/* No provider warning */}
        {connected === false && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 flex items-start gap-3">
            <WifiOff className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <div className="text-sm font-bold text-amber-800">VOLA provider not configured or unreachable</div>
              <div className="text-xs text-amber-700 mt-1">
                Go to <Link to={createPageUrl("Providers")} className="underline font-semibold">Providers</Link> and create a VOLA provider with your credentials, then return here.
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 1: Customer & Site ── */}
        <StepCard number={1} title="Select or Create Site" active={currentStep === 1} done={step1Done && currentStep > 1}>
          {step1Done && currentStep > 1 ? (
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-800">
                <span className="font-semibold">{selectedSite?.site_name}</span>
                <span className="text-gray-400 ml-2">({selectedSiteId})</span>
                {selectedSite?.customer_name && <span className="text-gray-400 ml-2">| {selectedSite.customer_name}</span>}
              </div>
              <button onClick={() => { setSelectedSiteId(""); setDeployResult(null); }} className="text-xs text-red-600 hover:text-red-700 font-medium">Change</button>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Site</label>
                {loadingSites ? (
                  <div className="flex items-center gap-2 text-xs text-gray-400 py-2"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</div>
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
                      <option key={s.site_id} value={s.site_id}>{s.site_name} ({s.site_id}){s.customer_name ? ` - ${s.customer_name}` : ""}</option>
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
                  <div className="text-xs font-bold text-blue-800 uppercase">New Site</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Site ID *</label>
                      <input value={newSiteId} onChange={e => setNewSiteId(e.target.value)} placeholder="SITE-001" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Site Name *</label>
                      <input value={newSiteName} onChange={e => setNewSiteName(e.target.value)} placeholder="Main Office" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Customer</label>
                    <div className="flex gap-2">
                      <select value={newSiteCustomer} onChange={e => setNewSiteCustomer(e.target.value)} className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm">
                        <option value="">-- Select --</option>
                        {customers.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
                      </select>
                      {!showNewCustomer && (
                        <button onClick={() => setShowNewCustomer(true)} className="px-3 py-2 text-xs text-red-600 border border-red-200 rounded-lg hover:bg-red-50"><Plus className="w-3 h-3" /></button>
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
            </div>
          )}
        </StepCard>

        {/* ── STEP 2: Select Devices ── */}
        <StepCard number={2} title="Select PR12 Devices" active={currentStep === 2} done={step2Done && currentStep > 2}>
          {step2Done && currentStep > 2 ? (
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-800">
                <span className="font-semibold">{selectedSns.size} device(s)</span>
                <span className="text-gray-400 ml-2">({[...selectedSns].join(", ")})</span>
              </div>
              <button onClick={() => { setSelectedSns(new Set()); setDeployResult(null); }} className="text-xs text-red-600 hover:text-red-700 font-medium">Change</button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-500">{volaDevices.length} device(s) available from VOLA Cloud</div>
                <button onClick={refreshDevices} disabled={loadingDevices} className="flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-800 font-medium">
                  {loadingDevices ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Refresh
                </button>
              </div>

              {loadingDevices ? (
                <div className="flex items-center justify-center py-8 gap-2 text-sm text-gray-400"><Loader2 className="w-4 h-4 animate-spin" /> Loading...</div>
              ) : volaDevices.length === 0 ? (
                <div className="text-center py-8 text-sm text-gray-400">No VOLA devices found. Check provider configuration.</div>
              ) : (
                <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                  {volaDevices.map(d => {
                    const checked = selectedSns.has(d.device_sn);
                    const isOnline = d.status === "online";
                    return (
                      <label key={d.device_sn} className={`flex items-center gap-3 px-4 py-3 rounded-xl border cursor-pointer transition-all ${checked ? "bg-red-50 border-red-300 shadow-sm" : "bg-white border-gray-200 hover:border-gray-300"}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleDevice(d.device_sn)} className="rounded border-gray-300 text-red-600 focus:ring-red-500" />
                        <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${isOnline ? "bg-emerald-500" : "bg-gray-400"}`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-gray-900">{d.device_sn}</span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${isOnline ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
                              {d.status || "unknown"}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 mt-0.5">{d.model} | MAC: {d.mac || "---"}{d.firmware_version ? ` | FW: ${d.firmware_version}` : ""}</div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </StepCard>

        {/* ── STEP 3: Config + Deploy ── */}
        <StepCard number={3} title="Deploy" active={currentStep === 3 || currentStep === 4} done={false}>
          {!deployResult ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Site Code *</label>
                  <input value={siteCode} onChange={e => setSiteCode(e.target.value)} placeholder="SITE-001" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                  <div className="text-[11px] text-gray-400 mt-1">Sets Device.DeviceInfo.ProvisioningCode on each device</div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Inform Interval (sec)</label>
                  <input value={informInterval} onChange={e => setInformInterval(e.target.value)} type="number" min="60" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                  <div className="text-[11px] text-gray-400 mt-1">How often the device checks in (default 300s = 5 min)</div>
                </div>
              </div>

              {/* Preview */}
              {step3Ready && (
                <div className="bg-gray-50 rounded-xl border border-gray-200 p-4 text-xs text-gray-600 space-y-1">
                  <div className="font-semibold text-gray-700 text-xs uppercase tracking-wide mb-2">Deploy Preview</div>
                  <div><span className="text-gray-400 w-24 inline-block">Site:</span> <span className="font-medium text-gray-800">{selectedSite?.site_name} ({selectedSiteId})</span></div>
                  <div><span className="text-gray-400 w-24 inline-block">Devices:</span> <span className="font-mono text-gray-800">{[...selectedSns].join(", ")}</span></div>
                  <div><span className="text-gray-400 w-24 inline-block">Site Code:</span> <span className="font-medium text-gray-800">{siteCode}</span></div>
                  <div><span className="text-gray-400 w-24 inline-block">Inform:</span> <span className="text-gray-800">{informInterval}s</span></div>
                  <div><span className="text-gray-400 w-24 inline-block">Reboot:</span> <span className="text-gray-800">Yes (automatic)</span></div>
                </div>
              )}

              {selectedSns.size > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-xs text-amber-800">
                  This will provision and reboot {selectedSns.size} device(s). Estimated time: ~{selectedSns.size * 30}s.
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  onClick={handleDeploy}
                  disabled={deploying || !step3Ready}
                  className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white rounded-xl text-sm font-bold shadow-sm transition-colors"
                >
                  {deploying ? <><Loader2 className="w-4 h-4 animate-spin" /> Deploying...</> : <><Rocket className="w-4 h-4" /> Deploy {selectedSns.size} PR12 Device(s)</>}
                </button>
              </div>
            </div>
          ) : (
            /* ── Results ── */
            <div className="space-y-4">
              <div className={`flex items-center gap-3 px-5 py-4 rounded-xl text-sm font-bold ${
                deployResult.failed === 0 ? "bg-emerald-50 text-emerald-800 border border-emerald-200" :
                deployResult.succeeded > 0 ? "bg-amber-50 text-amber-800 border border-amber-200" :
                "bg-red-50 text-red-800 border border-red-200"
              }`}>
                {deployResult.failed === 0 ? <CheckCircle2 className="w-6 h-6" /> : <XCircle className="w-6 h-6" />}
                {deployResult.failed === 0
                  ? `All ${deployResult.succeeded} device(s) deployed successfully`
                  : `${deployResult.succeeded} succeeded, ${deployResult.failed} failed`
                }
              </div>

              <div className="space-y-2">
                {(deployResult.results || []).map(r => (
                  <ResultRow key={r.device_sn} r={r} />
                ))}
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                <div className="flex items-center gap-3">
                  <Link to={createPageUrl("Devices")} className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 font-medium">
                    <ExternalLink className="w-3 h-3" /> View in Devices
                  </Link>
                  <Link to={createPageUrl("VolaIntegration")} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 font-medium">
                    <ExternalLink className="w-3 h-3" /> Advanced VOLA Page
                  </Link>
                </div>
                <button
                  onClick={() => { setDeployResult(null); setSelectedSns(new Set()); }}
                  className="px-5 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-semibold"
                >
                  Deploy More
                </button>
              </div>
            </div>
          )}
        </StepCard>
      </div>
    </PageWrapper>
  );
}
