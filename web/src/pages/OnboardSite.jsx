import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, Building2, Cpu, Phone, MapPin, CheckCircle2, ChevronRight,
  ChevronLeft, AlertTriangle, Loader2, Plus, Search, Radio,
  User, FileText, Wifi, ArrowRight, X,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";

// ═══════════════════════════════════════════════════════════════════
// STEP DEFINITIONS
// ═══════════════════════════════════════════════════════════════════

const STEPS = [
  { id: "customer", label: "Customer", icon: User },
  { id: "site", label: "Site", icon: Building2 },
  { id: "devices", label: "Devices", icon: Cpu },
  { id: "connectivity", label: "Connectivity", icon: Wifi },
  { id: "e911", label: "E911 / Location", icon: MapPin },
  { id: "review", label: "Review & Deploy", icon: CheckCircle2 },
];


// ═══════════════════════════════════════════════════════════════════
// STEP INDICATOR
// ═══════════════════════════════════════════════════════════════════

function StepIndicator({ current, steps, onNav }) {
  const ci = steps.findIndex(s => s.id === current);
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1">
      {steps.map((step, i) => {
        const done = i < ci;
        const active = i === ci;
        const Icon = step.icon;
        return (
          <button
            key={step.id}
            onClick={() => i <= ci && onNav(step.id)}
            disabled={i > ci}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
              active ? "bg-red-600 text-white" :
              done ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200" :
              "bg-gray-100 text-gray-400 cursor-default"
            }`}
          >
            {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{step.label}</span>
          </button>
        );
      })}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// STEP 1: CUSTOMER
// ═══════════════════════════════════════════════════════════════════

function CustomerStep({ form, setForm }) {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState(form.customer_id ? "existing" : "new");
  const [search, setSearch] = useState("");

  useEffect(() => {
    apiFetch("/customers?limit=300").then(setCustomers).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const filtered = customers.filter(c => !search || c.name?.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex gap-2 mb-4">
        <button onClick={() => setMode("existing")} className={`flex-1 py-2.5 rounded-lg text-sm font-medium border transition-colors ${mode === "existing" ? "bg-red-50 text-red-700 border-red-200" : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"}`}>
          Select Existing Customer
        </button>
        <button onClick={() => setMode("new")} className={`flex-1 py-2.5 rounded-lg text-sm font-medium border transition-colors ${mode === "new" ? "bg-red-50 text-red-700 border-red-200" : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"}`}>
          New Customer
        </button>
      </div>

      {mode === "existing" ? (
        <div>
          <div className="relative mb-3">
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-gray-400" />
            <input type="text" placeholder="Search customers..." value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg" />
          </div>
          <div className="max-h-[300px] overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-50">
            {loading ? <div className="p-4 text-center text-xs text-gray-400"><Loader2 className="w-4 h-4 animate-spin mx-auto" /></div> :
              filtered.length === 0 ? <div className="p-4 text-center text-xs text-gray-400">No customers found</div> :
              filtered.map(c => (
                <button key={c.id} onClick={() => setForm({ ...form, customer_id: c.id, customer_name: c.name })}
                  className={`w-full text-left px-4 py-3 text-sm transition-colors ${form.customer_id === c.id ? "bg-red-50 text-red-700 font-medium" : "hover:bg-gray-50"}`}>
                  {c.name}
                  {c.customer_number && <span className="text-xs text-gray-400 ml-2">({c.customer_number})</span>}
                </button>
              ))
            }
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <Field label="Customer Name" required value={form.customer_name} onChange={v => setForm({ ...form, customer_name: v, customer_id: null })} />
          <Field label="Account Number" value={form.account_number} onChange={v => setForm({ ...form, account_number: v })} placeholder="Optional" />
          <Field label="Contact Name" value={form.poc_name} onChange={v => setForm({ ...form, poc_name: v })} placeholder="Optional" />
          <Field label="Contact Email" value={form.poc_email} onChange={v => setForm({ ...form, poc_email: v })} placeholder="Optional" />
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// STEP 2: SITE
// ═══════════════════════════════════════════════════════════════════

function SiteStep({ form, setForm }) {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState(form.site_id_existing ? "existing" : "new");
  const [search, setSearch] = useState("");

  useEffect(() => {
    apiFetch("/sites?limit=500").then(setSites).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const filtered = sites.filter(s => !search || s.site_name?.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex gap-2 mb-4">
        <button onClick={() => setMode("existing")} className={`flex-1 py-2.5 rounded-lg text-sm font-medium border transition-colors ${mode === "existing" ? "bg-red-50 text-red-700 border-red-200" : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"}`}>
          Select Existing Site
        </button>
        <button onClick={() => setMode("new")} className={`flex-1 py-2.5 rounded-lg text-sm font-medium border transition-colors ${mode === "new" ? "bg-red-50 text-red-700 border-red-200" : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"}`}>
          New Site
        </button>
      </div>

      {mode === "existing" ? (
        <div>
          <div className="relative mb-3">
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-gray-400" />
            <input type="text" placeholder="Search sites..." value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg" />
          </div>
          <div className="max-h-[300px] overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-50">
            {loading ? <div className="p-4 text-center"><Loader2 className="w-4 h-4 animate-spin mx-auto text-gray-400" /></div> :
              filtered.length === 0 ? <div className="p-4 text-center text-xs text-gray-400">No sites found</div> :
              filtered.map(s => (
                <button key={s.site_id} onClick={() => setForm({ ...form, site_id_existing: s.site_id, site_name: s.site_name, e911_street: s.e911_street || "", e911_city: s.e911_city || "", e911_state: s.e911_state || "", e911_zip: s.e911_zip || "" })}
                  className={`w-full text-left px-4 py-3 text-sm transition-colors ${form.site_id_existing === s.site_id ? "bg-red-50 text-red-700 font-medium" : "hover:bg-gray-50"}`}>
                  {s.site_name}
                  {s.e911_city && <span className="text-xs text-gray-400 ml-2">{s.e911_city}, {s.e911_state}</span>}
                </button>
              ))
            }
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <Field label="Site Name" required value={form.site_name} onChange={v => setForm({ ...form, site_name: v, site_id_existing: null })} />
          <Field label="Site Code" value={form.site_code} onChange={v => setForm({ ...form, site_code: v })} placeholder="Auto-generated if blank" />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Building Type" value={form.building_type} onChange={v => setForm({ ...form, building_type: v })} placeholder="e.g., Commercial, Healthcare" />
            <Select label="System Type" value={form.endpoint_type} onChange={v => setForm({ ...form, endpoint_type: v })}
              options={[{ v: "", l: "Select..." }, { v: "elevator_phone", l: "Elevator Phone" }, { v: "fire_alarm", l: "Fire Alarm" }, { v: "call_station", l: "Call Station" }, { v: "das_radio", l: "DAS / Radio" }, { v: "backup_power", l: "Backup Power" }, { v: "other", l: "Other" }]} />
          </div>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// STEP 3: DEVICES
// ═══════════════════════════════════════════════════════════════════

function DevicesStep({ form, setForm }) {
  const [hwModels, setHwModels] = useState([]);

  useEffect(() => {
    apiFetch("/hardware-models?limit=100").then(setHwModels).catch(() => {});
  }, []);

  const devices = form.devices || [];
  const addDevice = () => setForm({ ...form, devices: [...devices, { device_type: form.endpoint_type || "", model: "", serial_number: "", imei: "", iccid: "", carrier: "" }] });
  const updateDevice = (i, field, val) => {
    const updated = [...devices];
    updated[i] = { ...updated[i], [field]: val };
    setForm({ ...form, devices: updated });
  };
  const removeDevice = (i) => setForm({ ...form, devices: devices.filter((_, j) => j !== i) });

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">Add one or more devices for this site. Each device will be registered and assigned.</p>

      {devices.map((dev, i) => (
        <div key={i} className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-3 relative">
          <button onClick={() => removeDevice(i)} className="absolute top-3 right-3 text-gray-400 hover:text-red-500"><X className="w-4 h-4" /></button>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Device {i + 1}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Select label="Device Type" value={dev.device_type} onChange={v => updateDevice(i, "device_type", v)}
              options={[{ v: "", l: "Select..." }, { v: "elevator_phone", l: "Elevator Phone" }, { v: "fire_alarm", l: "Fire Alarm" }, { v: "call_station", l: "Call Station" }, { v: "das_radio", l: "DAS / Radio" }, { v: "ata", l: "ATA / Router" }, { v: "other", l: "Other" }]} />
            {hwModels.length > 0 ? (
              <Select label="Hardware Model" value={dev.hardware_model_id || ""} onChange={v => updateDevice(i, "hardware_model_id", v)}
                options={[{ v: "", l: "Select or skip..." }, ...hwModels.map(m => ({ v: m.id, l: `${m.manufacturer} ${m.model_name}` }))]} />
            ) : (
              <Field label="Model" value={dev.model} onChange={v => updateDevice(i, "model", v)} placeholder="e.g., MS130v4" />
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Field label="Serial Number" value={dev.serial_number} onChange={v => updateDevice(i, "serial_number", v)} />
            <Field label="IMEI" value={dev.imei} onChange={v => updateDevice(i, "imei", v)} placeholder="15 digits" />
            <Field label="ICCID (SIM)" value={dev.iccid} onChange={v => updateDevice(i, "iccid", v)} placeholder="19-20 digits" />
          </div>
          <Field label="Carrier" value={dev.carrier} onChange={v => updateDevice(i, "carrier", v)} placeholder="e.g., T-Mobile, Verizon" />
        </div>
      ))}

      <button onClick={addDevice} className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border-2 border-dashed border-gray-300 text-sm text-gray-500 hover:border-red-300 hover:text-red-600 transition-colors">
        <Plus className="w-4 h-4" /> Add Device
      </button>
      {devices.length === 0 && <p className="text-[11px] text-gray-400 text-center">You can add devices now or assign them later.</p>}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// STEP 4: CONNECTIVITY
// ═══════════════════════════════════════════════════════════════════

function ConnectivityStep({ form, setForm }) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">Configure service and connectivity settings for this deployment.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Select label="Service Class" value={form.service_class} onChange={v => setForm({ ...form, service_class: v })}
          options={[{ v: "", l: "Select..." }, { v: "life_safety", l: "Life Safety" }, { v: "monitoring", l: "Monitoring" }, { v: "voice", l: "Voice / Communications" }, { v: "data", l: "Data" }]} />
        <Select label="Transport" value={form.transport} onChange={v => setForm({ ...form, transport: v })}
          options={[{ v: "", l: "Select..." }, { v: "cellular", l: "Cellular" }, { v: "ethernet", l: "Ethernet" }, { v: "wifi", l: "WiFi" }, { v: "pots", l: "POTS" }]} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Select label="Voice / SIP Provider" value={form.sip_provider} onChange={v => setForm({ ...form, sip_provider: v })}
          options={[{ v: "", l: "None / N/A" }, { v: "telnyx", l: "Telnyx" }, { v: "bandwidth", l: "Bandwidth" }, { v: "tmobile", l: "T-Mobile" }, { v: "other", l: "Other" }]} />
        <Field label="DID / Phone Number" value={form.did} onChange={v => setForm({ ...form, did: v })} placeholder="+1XXXXXXXXXX" />
      </div>
      <Field label="Notes" value={form.connectivity_notes} onChange={v => setForm({ ...form, connectivity_notes: v })} placeholder="Any special connectivity requirements" />
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// STEP 5: E911 / LOCATION
// ═══════════════════════════════════════════════════════════════════

function E911Step({ form, setForm }) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">E911 location data is required for life-safety compliance. This address will be registered with emergency services.</p>
      <Field label="Street Address" required value={form.e911_street} onChange={v => setForm({ ...form, e911_street: v })} placeholder="500 Medical Center Dr" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Field label="City" required value={form.e911_city} onChange={v => setForm({ ...form, e911_city: v })} />
        <Field label="State" required value={form.e911_state} onChange={v => setForm({ ...form, e911_state: v })} placeholder="TX" />
        <Field label="ZIP" required value={form.e911_zip} onChange={v => setForm({ ...form, e911_zip: v })} placeholder="75201" />
        <Field label="Country" value={form.e911_country || "US"} onChange={v => setForm({ ...form, e911_country: v })} />
      </div>
      <Select label="Heartbeat Schedule" value={form.heartbeat_frequency} onChange={v => setForm({ ...form, heartbeat_frequency: v })}
        options={[{ v: "", l: "Default (5 min)" }, { v: "60", l: "1 minute" }, { v: "300", l: "5 minutes" }, { v: "600", l: "10 minutes" }, { v: "900", l: "15 minutes" }]} />
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// STEP 6: REVIEW & DEPLOY
// ═══════════════════════════════════════════════════════════════════

function ReviewStep({ form }) {
  const devices = form.devices || [];
  const warnings = [];
  if (!form.customer_name && !form.customer_id) warnings.push("No customer selected");
  if (!form.site_name && !form.site_id_existing) warnings.push("No site specified");
  if (!form.e911_street) warnings.push("E911 street address missing — compliance risk");
  if (!form.e911_city || !form.e911_state || !form.e911_zip) warnings.push("E911 address incomplete");
  if (devices.length === 0) warnings.push("No devices added — site will be created without equipment");

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <ReviewCard title="Customer" icon={User} items={[
          form.customer_id ? `Existing: ${form.customer_name}` : `New: ${form.customer_name || "—"}`,
          form.account_number ? `Account: ${form.account_number}` : null,
        ]} />
        <ReviewCard title="Site" icon={Building2} items={[
          form.site_id_existing ? `Existing: ${form.site_name}` : `New: ${form.site_name || "—"}`,
          form.building_type || null,
          form.endpoint_type ? `Type: ${form.endpoint_type.replace(/_/g, " ")}` : null,
        ]} />
        <ReviewCard title="Devices" icon={Cpu} items={[
          `${devices.length} device${devices.length !== 1 ? "s" : ""}`,
          ...devices.map((d, i) => `${i + 1}. ${d.device_type || "device"} ${d.serial_number ? `(SN: ${d.serial_number})` : d.imei ? `(IMEI: ${d.imei})` : ""}`),
        ]} />
        <ReviewCard title="E911 Location" icon={MapPin} items={[
          form.e911_street || "Not set",
          [form.e911_city, form.e911_state, form.e911_zip].filter(Boolean).join(", ") || null,
        ]} />
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-xs font-semibold text-amber-800 mb-2 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Review Items
          </p>
          <ul className="space-y-1">
            {warnings.map((w, i) => <li key={i} className="text-xs text-amber-700">• {w}</li>)}
          </ul>
        </div>
      )}

      {warnings.length === 0 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-center">
          <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto mb-1.5" />
          <p className="text-sm text-emerald-700 font-medium">Ready to deploy</p>
          <p className="text-xs text-emerald-600">All required fields are complete.</p>
        </div>
      )}
    </div>
  );
}

function ReviewCard({ title, icon: Icon, items }) {
  const filtered = items.filter(Boolean);
  return (
    <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-4 h-4 text-gray-400" />
        <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">{title}</span>
      </div>
      {filtered.length > 0 ? filtered.map((item, i) => (
        <p key={i} className="text-xs text-gray-600 leading-relaxed">{item}</p>
      )) : <p className="text-xs text-gray-400 italic">Not configured</p>}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// SHARED FORM COMPONENTS
// ═══════════════════════════════════════════════════════════════════

function Field({ label, value, onChange, placeholder, required }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <input type="text" value={value || ""} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500" />
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">{label}</label>
      <select value={value || ""} onChange={e => onChange(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500">
        {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════

const INITIAL_FORM = {
  // Customer
  customer_id: null, customer_name: "", account_number: "", poc_name: "", poc_email: "",
  // Site
  site_id_existing: null, site_name: "", site_code: "", building_type: "", endpoint_type: "",
  // Devices
  devices: [],
  // Connectivity
  service_class: "", transport: "", sip_provider: "", did: "", connectivity_notes: "",
  // E911
  e911_street: "", e911_city: "", e911_state: "", e911_zip: "", e911_country: "US",
  heartbeat_frequency: "",
};

export default function OnboardSite() {
  const { user, can } = useAuth();
  const [step, setStep] = useState("customer");
  const [form, setForm] = useState(INITIAL_FORM);
  const [deploying, setDeploying] = useState(false);
  const [result, setResult] = useState(null);

  const stepIdx = STEPS.findIndex(s => s.id === step);
  const isFirst = stepIdx === 0;
  const isLast = stepIdx === STEPS.length - 1;

  const next = () => { if (!isLast) setStep(STEPS[stepIdx + 1].id); };
  const prev = () => { if (!isFirst) setStep(STEPS[stepIdx - 1].id); };

  const canProceed = useMemo(() => {
    if (step === "customer") return !!(form.customer_name || form.customer_id);
    if (step === "site") return !!(form.site_name || form.site_id_existing);
    return true; // Other steps are optional
  }, [step, form]);

  const handleDeploy = async () => {
    setDeploying(true);
    const created = { customer: null, site: null, devices: [], line: null };
    try {
      // 1. Create customer if new
      if (!form.customer_id && form.customer_name) {
        const cust = await apiFetch("/customers", {
          method: "POST",
          body: JSON.stringify({ name: form.customer_name, billing_email: form.poc_email || null }),
        });
        created.customer = cust;
      }

      // 2. Create site if new
      let siteId = form.site_id_existing;
      if (!siteId && form.site_name) {
        const code = form.site_code || `SITE-${Date.now().toString(36).toUpperCase()}`;
        const site = await apiFetch("/sites", {
          method: "POST",
          body: JSON.stringify({
            site_id: code,
            site_name: form.site_name,
            customer_name: form.customer_name || "Unknown",
            status: "Not Connected",
            e911_street: form.e911_street || null,
            e911_city: form.e911_city || null,
            e911_state: form.e911_state || null,
            e911_zip: form.e911_zip || null,
            building_type: form.building_type || null,
            endpoint_type: form.endpoint_type || null,
            service_class: form.service_class || null,
            kit_type: form.endpoint_type || null,
            poc_name: form.poc_name || null,
            poc_email: form.poc_email || null,
            heartbeat_frequency: form.heartbeat_frequency || null,
          }),
        });
        siteId = site.site_id;
        created.site = site;
      }

      // 3. Create devices
      for (const dev of (form.devices || [])) {
        const devId = `DEV-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
        const device = await apiFetch("/devices", {
          method: "POST",
          body: JSON.stringify({
            device_id: devId,
            site_id: siteId,
            status: "provisioning",
            device_type: dev.device_type || null,
            model: dev.model || null,
            serial_number: dev.serial_number || null,
            imei: dev.imei || null,
            iccid: dev.iccid || null,
            carrier: dev.carrier || null,
            hardware_model_id: dev.hardware_model_id || null,
          }),
        });
        created.devices.push(device);
      }

      // 4. Create line if DID provided
      if (form.did && siteId) {
        const lineId = `LINE-${Date.now().toString(36).toUpperCase()}`;
        const line = await apiFetch("/lines", {
          method: "POST",
          body: JSON.stringify({
            line_id: lineId,
            site_id: siteId,
            device_id: created.devices[0]?.device_id || null,
            provider: form.sip_provider || "other",
            did: form.did,
            protocol: form.transport === "pots" ? "POTS" : form.transport === "cellular" ? "cellular" : "SIP",
            status: "provisioning",
            e911_street: form.e911_street || null,
            e911_city: form.e911_city || null,
            e911_state: form.e911_state || null,
            e911_zip: form.e911_zip || null,
          }),
        });
        created.line = line;
      }

      setResult({ success: true, created });
      toast.success("Site onboarded successfully");
    } catch (err) {
      toast.error(err.message || "Deployment failed");
      setResult({ success: false, error: err.message, created });
    } finally {
      setDeploying(false);
    }
  };

  // Permission check
  if (!can("MANAGE_DEVICES")) {
    return (
      <PageWrapper>
        <div className="p-6 text-center text-gray-500">You do not have permission to onboard sites.</div>
      </PageWrapper>
    );
  }

  // Success result
  if (result?.success) {
    const c = result.created;
    return (
      <PageWrapper>
        <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
          <div className="max-w-lg w-full bg-white rounded-2xl border border-gray-200 shadow-sm p-8 text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-4" />
            <h2 className="text-xl font-bold text-gray-900 mb-2">Site Onboarded</h2>
            <p className="text-sm text-gray-500 mb-6">
              {c.site ? `${c.site.site_name} created` : "Site updated"} with {c.devices.length} device{c.devices.length !== 1 ? "s" : ""}.
            </p>
            <div className="flex gap-3 justify-center">
              <button onClick={() => { setForm(INITIAL_FORM); setResult(null); setStep("customer"); }}
                className="px-4 py-2.5 border border-gray-200 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50">
                Onboard Another
              </button>
              <Link to={createPageUrl("Sites")}
                className="px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium">
                View Sites
              </Link>
            </div>
          </div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="min-h-screen bg-gray-50">
        <div className="p-5 lg:p-6 max-w-[800px] mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-red-600 rounded-xl flex items-center justify-center shadow-sm">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">Onboard Site</h1>
              <p className="text-[11px] text-gray-400">Guided deployment workflow</p>
            </div>
          </div>

          {/* Step indicator */}
          <StepIndicator current={step} steps={STEPS} onNav={setStep} />

          {/* Step content */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">{STEPS[stepIdx].label}</h2>

            {step === "customer" && <CustomerStep form={form} setForm={setForm} />}
            {step === "site" && <SiteStep form={form} setForm={setForm} />}
            {step === "devices" && <DevicesStep form={form} setForm={setForm} />}
            {step === "connectivity" && <ConnectivityStep form={form} setForm={setForm} />}
            {step === "e911" && <E911Step form={form} setForm={setForm} />}
            {step === "review" && <ReviewStep form={form} />}
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between">
            <button onClick={prev} disabled={isFirst}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-default transition-colors">
              <ChevronLeft className="w-4 h-4" /> Back
            </button>

            {isLast ? (
              <button onClick={handleDeploy} disabled={deploying}
                className="flex items-center gap-2 px-6 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-lg disabled:opacity-60 transition-colors">
                {deploying ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                {deploying ? "Deploying..." : "Deploy Site"}
              </button>
            ) : (
              <button onClick={next} disabled={!canProceed}
                className="flex items-center gap-1.5 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg disabled:opacity-40 transition-colors">
                Continue <ChevronRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
