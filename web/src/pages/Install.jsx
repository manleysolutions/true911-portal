import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, Building2, Cpu, Wifi, MapPin, CheckCircle2, ChevronRight,
  ChevronLeft, Loader2, Plus, Search, Radio, X, Activity,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { Site, Device, HardwareModel } from "@/api/entities";
import { toast } from "sonner";

const STEPS = [
  { id: "site", label: "Site", icon: Building2 },
  { id: "device", label: "Device", icon: Cpu },
  { id: "service", label: "Service", icon: Wifi },
  { id: "status", label: "Status", icon: Activity },
  { id: "confirm", label: "Confirm", icon: CheckCircle2 },
];

const ENDPOINT_TYPES = ["Elevator", "Emergency Phone", "Fire Alarm Control Panel", "Burglar Alarm Control Panel", "Fax", "SCADA / Industrial", "Other"];
const SERVICE_CLASSES = ["VoIP (SIP)", "VoLTE (Cellular Voice)", "Analog (POTS Replacement)", "Data Only"];
const TRANSPORTS = ["Cellular", "Ethernet (LAN)", "Wi-Fi", "Satellite"];
const CARRIERS = ["T-Mobile", "Verizon", "AT&T", "Teal", "Napco", "Other"];
const VOICE_PROVIDERS = ["Telnyx", "Twilio", "Bandwidth", "Other"];

function StepBar({ current, steps }) {
  const ci = steps.findIndex(s => s.id === current);
  return (
    <div className="flex items-center gap-1">
      {steps.map((step, i) => {
        const done = i < ci;
        const active = i === ci;
        const Icon = step.icon;
        return (
          <div key={step.id} className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium ${
            active ? "bg-red-600 text-white" : done ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-gray-100 text-gray-400"
          }`}>
            {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{step.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function F({ label, required, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}{required && <span className="text-red-500 ml-0.5">*</span>}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500";
const selectCls = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500 bg-white";

export default function Install() {
  const { can } = useAuth();
  const [step, setStep] = useState("site");
  const [sites, setSites] = useState([]);
  const [hwModels, setHwModels] = useState([]);
  const [loading, setLoading] = useState(true);

  // Persistent form state across all steps
  const [siteMode, setSiteMode] = useState("existing"); // existing | new
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [siteForm, setSiteForm] = useState({ site_name: "", customer_name: "", e911_street: "", e911_city: "", e911_state: "", e911_zip: "" });
  const [deviceForm, setDeviceForm] = useState({ device_id: "", model: "", manufacturer: "", serial_number: "", imei: "", iccid: "", carrier: "", hardware_model_id: "" });
  const [serviceForm, setServiceForm] = useState({ endpoint_type: "", service_class: "", transport: "", carrier: "", voice_provider: "" });

  const [createdSite, setCreatedSite] = useState(null);
  const [createdDevice, setCreatedDevice] = useState(null);
  const [deploying, setDeploying] = useState(false);
  const [siteSearch, setSiteSearch] = useState("");

  useEffect(() => {
    Promise.all([
      Site.list("-last_checkin", 300),
      HardwareModel.list().catch(() => []),
    ]).then(([s, h]) => { setSites(s); setHwModels(h); setLoading(false); });
  }, []);

  const stepIdx = STEPS.findIndex(s => s.id === step);
  const next = () => stepIdx < STEPS.length - 1 && setStep(STEPS[stepIdx + 1].id);
  const prev = () => stepIdx > 0 && setStep(STEPS[stepIdx - 1].id);

  const canNext = () => {
    if (step === "site") return siteMode === "existing" ? !!selectedSiteId : !!siteForm.site_name.trim();
    if (step === "device") return !!deviceForm.device_id.trim();
    return true;
  };

  const handleDeploy = async () => {
    setDeploying(true);
    try {
      // 1. Create site if new
      let siteId = selectedSiteId;
      let siteName = sites.find(s => s.site_id === selectedSiteId)?.site_name || "";
      if (siteMode === "new") {
        const site = await Site.create({
          site_id: `SITE-${Date.now()}`,
          site_name: siteForm.site_name.trim(),
          customer_name: siteForm.customer_name.trim() || siteForm.site_name.trim(),
          status: "Not Connected",
          e911_street: siteForm.e911_street.trim() || undefined,
          e911_city: siteForm.e911_city.trim() || undefined,
          e911_state: siteForm.e911_state.trim() || undefined,
          e911_zip: siteForm.e911_zip.trim() || undefined,
          endpoint_type: serviceForm.endpoint_type || undefined,
          service_class: serviceForm.service_class || undefined,
          carrier: serviceForm.carrier || deviceForm.carrier || undefined,
          kit_type: serviceForm.endpoint_type || undefined,
        });
        siteId = site.site_id;
        siteName = site.site_name;
        setCreatedSite(site);
      }

      // 2. Create device
      const hmId = deviceForm.hardware_model_id && deviceForm.hardware_model_id !== "__custom" ? deviceForm.hardware_model_id : undefined;
      const device = await Device.create({
        device_id: deviceForm.device_id.trim(),
        site_id: siteId,
        status: "provisioning",
        hardware_model_id: hmId,
        manufacturer: deviceForm.manufacturer || undefined,
        model: deviceForm.model || undefined,
        device_type: serviceForm.endpoint_type || "Other",
        serial_number: deviceForm.serial_number || undefined,
        imei: deviceForm.imei || undefined,
        iccid: deviceForm.iccid || undefined,
        carrier: deviceForm.carrier || serviceForm.carrier || undefined,
      });
      setCreatedDevice(device);

      toast.success("Installation complete");
      setStep("confirm");
    } catch (err) {
      toast.error(err.message || "Installation failed");
    } finally {
      setDeploying(false);
    }
  };

  if (!can("MANAGE_DEVICES")) {
    return <PageWrapper><div className="p-6 text-center text-gray-500">Insufficient permissions.</div></PageWrapper>;
  }

  if (loading) {
    return <PageWrapper><div className="min-h-screen bg-gray-50 flex items-center justify-center"><Loader2 className="w-6 h-6 text-gray-400 animate-spin" /></div></PageWrapper>;
  }

  const filteredSites = sites.filter(s => !siteSearch || s.site_name?.toLowerCase().includes(siteSearch.toLowerCase()));
  const mfrs = [...new Set(hwModels.map(m => m.manufacturer))].sort();

  return (
    <PageWrapper>
      <div className="min-h-screen bg-gray-50">
        <div className="p-5 lg:p-6 max-w-[700px] mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-red-600 rounded-xl flex items-center justify-center shadow-sm">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">New Installation</h1>
              <p className="text-[11px] text-gray-400">Site → Device → Service → Activate</p>
            </div>
          </div>

          <StepBar current={step} steps={STEPS} />

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">

            {/* STEP 1: SITE */}
            {step === "site" && (
              <div className="space-y-4">
                <h2 className="text-sm font-semibold text-gray-900">Select or Create Site</h2>
                <div className="flex gap-2">
                  <button onClick={() => setSiteMode("existing")} className={`flex-1 py-2 rounded-lg text-sm font-medium border ${siteMode === "existing" ? "bg-red-50 text-red-700 border-red-200" : "bg-white text-gray-500 border-gray-200"}`}>Existing Site</button>
                  <button onClick={() => setSiteMode("new")} className={`flex-1 py-2 rounded-lg text-sm font-medium border ${siteMode === "new" ? "bg-red-50 text-red-700 border-red-200" : "bg-white text-gray-500 border-gray-200"}`}>New Site</button>
                </div>
                {siteMode === "existing" ? (
                  <div>
                    <div className="relative mb-2">
                      <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-gray-400" />
                      <input type="text" value={siteSearch} onChange={e => setSiteSearch(e.target.value)} placeholder="Search sites..." className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg" />
                    </div>
                    <div className="max-h-[240px] overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-50">
                      {filteredSites.map(s => (
                        <button key={s.site_id} onClick={() => setSelectedSiteId(s.site_id)}
                          className={`w-full text-left px-4 py-3 text-sm ${selectedSiteId === s.site_id ? "bg-red-50 text-red-700 font-medium" : "hover:bg-gray-50"}`}>
                          {s.site_name}
                          {s.e911_city && <span className="text-xs text-gray-400 ml-2">{s.e911_city}, {s.e911_state}</span>}
                        </button>
                      ))}
                      {filteredSites.length === 0 && <p className="p-4 text-xs text-gray-400 text-center">No sites found</p>}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <F label="Site Name" required><input value={siteForm.site_name} onChange={e => setSiteForm(f => ({...f, site_name: e.target.value}))} className={inputCls} placeholder="e.g. 123 Main St Elevator" /></F>
                    <F label="Customer"><input value={siteForm.customer_name} onChange={e => setSiteForm(f => ({...f, customer_name: e.target.value}))} className={inputCls} placeholder="Customer name" /></F>
                    <F label="Street Address"><input value={siteForm.e911_street} onChange={e => setSiteForm(f => ({...f, e911_street: e.target.value}))} className={inputCls} placeholder="Street address" /></F>
                    <div className="grid grid-cols-3 gap-3">
                      <F label="City"><input value={siteForm.e911_city} onChange={e => setSiteForm(f => ({...f, e911_city: e.target.value}))} className={inputCls} placeholder="City" /></F>
                      <F label="State"><input value={siteForm.e911_state} onChange={e => setSiteForm(f => ({...f, e911_state: e.target.value}))} className={inputCls} placeholder="TX" maxLength={2} /></F>
                      <F label="ZIP"><input value={siteForm.e911_zip} onChange={e => setSiteForm(f => ({...f, e911_zip: e.target.value}))} className={inputCls} placeholder="75201" /></F>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* STEP 2: DEVICE */}
            {step === "device" && (
              <div className="space-y-4">
                <h2 className="text-sm font-semibold text-gray-900">Register Device</h2>
                <F label="Device ID" required><input value={deviceForm.device_id} onChange={e => setDeviceForm(f => ({...f, device_id: e.target.value}))} className={inputCls} placeholder="e.g. PR12-001" /></F>
                <div className="grid grid-cols-2 gap-3">
                  <F label="Hardware Model">
                    <select value={deviceForm.hardware_model_id} onChange={e => {
                      const id = e.target.value;
                      if (id === "__custom") { setDeviceForm(f => ({...f, hardware_model_id: "__custom", model: "", manufacturer: ""})); return; }
                      const hm = hwModels.find(m => m.id === id);
                      setDeviceForm(f => ({...f, hardware_model_id: id, model: hm?.model_name || "", manufacturer: hm?.manufacturer || ""}));
                    }} className={selectCls}>
                      <option value="">Select...</option>
                      {mfrs.map(mfr => (
                        <optgroup key={mfr} label={mfr}>
                          {hwModels.filter(m => m.manufacturer === mfr).map(m => <option key={m.id} value={m.id}>{m.model_name}</option>)}
                        </optgroup>
                      ))}
                      <optgroup label="Other"><option value="__custom">Custom manufacturer / model</option></optgroup>
                    </select>
                  </F>
                  <F label="Model Name"><input value={deviceForm.model} onChange={e => setDeviceForm(f => ({...f, model: e.target.value}))} className={inputCls} placeholder="Model name" readOnly={deviceForm.hardware_model_id && deviceForm.hardware_model_id !== "__custom"} /></F>
                </div>
                {deviceForm.hardware_model_id === "__custom" && (
                  <F label="Manufacturer"><input value={deviceForm.manufacturer} onChange={e => setDeviceForm(f => ({...f, manufacturer: e.target.value}))} className={inputCls} placeholder="e.g. FlyingVoice" /></F>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <F label="Serial Number"><input value={deviceForm.serial_number} onChange={e => setDeviceForm(f => ({...f, serial_number: e.target.value}))} className={inputCls} placeholder="Board serial" /></F>
                  <F label="IMEI"><input value={deviceForm.imei} onChange={e => setDeviceForm(f => ({...f, imei: e.target.value}))} className={inputCls} placeholder="15-digit IMEI" maxLength={15} /></F>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <F label="SIM ICCID"><input value={deviceForm.iccid} onChange={e => setDeviceForm(f => ({...f, iccid: e.target.value}))} className={inputCls} placeholder="SIM ICCID" /></F>
                  <F label="Carrier">
                    <select value={deviceForm.carrier} onChange={e => setDeviceForm(f => ({...f, carrier: e.target.value}))} className={selectCls}>
                      <option value="">Select...</option>
                      {CARRIERS.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </F>
                </div>
              </div>
            )}

            {/* STEP 3: SERVICE */}
            {step === "service" && (
              <div className="space-y-4">
                <h2 className="text-sm font-semibold text-gray-900">Service Configuration</h2>
                <div className="grid grid-cols-2 gap-3">
                  <F label="Endpoint Type">
                    <select value={serviceForm.endpoint_type} onChange={e => setServiceForm(f => ({...f, endpoint_type: e.target.value}))} className={selectCls}>
                      <option value="">Select...</option>
                      {ENDPOINT_TYPES.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </F>
                  <F label="Service Class">
                    <select value={serviceForm.service_class} onChange={e => setServiceForm(f => ({...f, service_class: e.target.value}))} className={selectCls}>
                      <option value="">Select...</option>
                      {SERVICE_CLASSES.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </F>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <F label="Transport">
                    <select value={serviceForm.transport} onChange={e => setServiceForm(f => ({...f, transport: e.target.value}))} className={selectCls}>
                      <option value="">Select...</option>
                      {TRANSPORTS.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </F>
                  <F label="Voice Provider">
                    <select value={serviceForm.voice_provider} onChange={e => setServiceForm(f => ({...f, voice_provider: e.target.value}))} className={selectCls}>
                      <option value="">Select...</option>
                      {VOICE_PROVIDERS.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </F>
                </div>
              </div>
            )}

            {/* STEP 4: STATUS */}
            {step === "status" && (
              <div className="space-y-4">
                <h2 className="text-sm font-semibold text-gray-900">Activation Status</h2>
                <p className="text-xs text-gray-500">Click Deploy to create the site and device. The system will begin monitoring immediately.</p>
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center"><Loader2 className="w-4 h-4 text-amber-600" /></div>
                    <div><p className="text-sm font-medium text-gray-900">Provisioning</p><p className="text-xs text-gray-500">Device will be created in provisioning status</p></div>
                  </div>
                  <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center"><Activity className="w-4 h-4 text-blue-600" /></div>
                    <div><p className="text-sm font-medium text-gray-900">Awaiting Heartbeat</p><p className="text-xs text-gray-500">Monitoring begins once device sends first heartbeat</p></div>
                  </div>
                  <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center"><CheckCircle2 className="w-4 h-4 text-emerald-600" /></div>
                    <div><p className="text-sm font-medium text-gray-900">Active</p><p className="text-xs text-gray-500">Device connected and reporting normally</p></div>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 5: CONFIRM */}
            {step === "confirm" && createdDevice && (
              <div className="text-center space-y-4">
                <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
                <h2 className="text-xl font-bold text-gray-900">Installation Complete</h2>
                <div className="grid grid-cols-2 gap-3 text-left">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase">Site</p>
                    <p className="text-sm text-gray-900">{createdSite?.site_name || sites.find(s => s.site_id === selectedSiteId)?.site_name || "—"}</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase">Device</p>
                    <p className="text-sm text-gray-900">{createdDevice.device_id}</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase">Status</p>
                    <p className="text-sm text-amber-600 font-medium">Provisioning</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase">Carrier</p>
                    <p className="text-sm text-gray-900">{deviceForm.carrier || "—"}</p>
                  </div>
                </div>
                {createdDevice.api_key && (
                  <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-left">
                    <p className="text-xs font-semibold text-red-700 mb-1">Copy device API key now — shown once only</p>
                    <div className="bg-gray-900 text-emerald-400 font-mono text-xs p-2 rounded-lg break-all select-all">{createdDevice.api_key}</div>
                  </div>
                )}
                <div className="flex gap-3 pt-2">
                  <button onClick={() => { setStep("site"); setCreatedSite(null); setCreatedDevice(null); setDeviceForm({ device_id: "", model: "", manufacturer: "", serial_number: "", imei: "", iccid: "", carrier: "", hardware_model_id: "" }); }}
                    className="flex-1 py-2.5 border border-gray-200 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50">New Installation</button>
                  <Link to={createPageUrl("Devices")} className="flex-1 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium text-center">View Devices</Link>
                </div>
              </div>
            )}
          </div>

          {/* Nav buttons */}
          {step !== "confirm" && (
            <div className="flex justify-between">
              <button onClick={prev} disabled={stepIdx === 0} className="flex items-center gap-1.5 px-4 py-2.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40">
                <ChevronLeft className="w-4 h-4" /> Back
              </button>
              {step === "status" ? (
                <button onClick={handleDeploy} disabled={deploying} className="flex items-center gap-2 px-6 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold disabled:opacity-60">
                  {deploying ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  {deploying ? "Deploying..." : "Deploy"}
                </button>
              ) : (
                <button onClick={next} disabled={!canNext()} className="flex items-center gap-1.5 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium disabled:opacity-40">
                  Continue <ChevronRight className="w-4 h-4" />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}
