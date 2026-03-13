import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/api/client";
import {
  Building2, Users, Cpu, Disc3, ShieldCheck, CheckCircle2, ChevronRight, ChevronLeft,
  Loader2, AlertTriangle, Plus, Trash2, MapPin, Phone, X, Search,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const STEPS = [
  { key: "customer", label: "Customer", icon: Users },
  { key: "site", label: "Site", icon: Building2 },
  { key: "units", label: "Service Units", icon: Phone },
  { key: "sims", label: "SIMs", icon: Disc3 },
  { key: "devices", label: "Devices", icon: Cpu },
  { key: "review", label: "Review", icon: ShieldCheck },
];

function StepBar({ current }) {
  return (
    <div className="flex items-center gap-1 mb-8 overflow-x-auto pb-1">
      {STEPS.map((s, i) => {
        const Icon = s.icon;
        const done = i < current;
        const active = i === current;
        return (
          <div key={s.key} className="flex items-center gap-1 flex-shrink-0">
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              done ? "bg-emerald-50 text-emerald-700" :
              active ? "bg-red-50 text-red-700 ring-2 ring-red-200" :
              "bg-gray-50 text-gray-400"
            }`}>
              {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && <ChevronRight className="w-3 h-3 text-gray-300" />}
          </div>
        );
      })}
    </div>
  );
}

const INPUT = "w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent";
const LABEL = "block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide";

/* ── Step 1: Customer ── */
function StepCustomer({ data, setData, customers }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Customer / Reseller</h2>
      <p className="text-sm text-gray-500">Who is this site for?</p>
      <div>
        <label className={LABEL}>Customer Name</label>
        <input value={data.customer_name || ""} onChange={e => setData(d => ({ ...d, customer_name: e.target.value }))}
          placeholder="e.g. Benson Systems" className={INPUT} list="customer-list" />
        <datalist id="customer-list">
          {customers.map(c => <option key={c.id} value={c.name} />)}
        </datalist>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={LABEL}>Contact Name</label>
          <input value={data.poc_name || ""} onChange={e => setData(d => ({ ...d, poc_name: e.target.value }))}
            placeholder="Optional" className={INPUT} />
        </div>
        <div>
          <label className={LABEL}>Contact Phone</label>
          <input value={data.poc_phone || ""} onChange={e => setData(d => ({ ...d, poc_phone: e.target.value }))}
            placeholder="Optional" className={INPUT} />
        </div>
      </div>
    </div>
  );
}

/* ── Step 2: Site ── */
function StepSite({ data, setData, sites }) {
  const [mode, setMode] = useState(data.existing_site_id ? "existing" : "new");

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Site</h2>
      <p className="text-sm text-gray-500">Create a new site or select an existing one.</p>

      <div className="flex gap-3">
        <button onClick={() => setMode("new")}
          className={`flex-1 p-3 rounded-xl border text-sm font-medium transition-all ${mode === "new" ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
          Create New
        </button>
        <button onClick={() => setMode("existing")}
          className={`flex-1 p-3 rounded-xl border text-sm font-medium transition-all ${mode === "existing" ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
          Select Existing
        </button>
      </div>

      {mode === "existing" ? (
        <select value={data.existing_site_id || ""} onChange={e => {
          const s = sites.find(x => x.site_id === e.target.value);
          setData(d => ({ ...d, existing_site_id: e.target.value, site_name: s?.site_name || "", customer_name: d.customer_name || s?.customer_name || "" }));
        }} className={INPUT}>
          <option value="">-- Select a site --</option>
          {sites.map(s => <option key={s.site_id} value={s.site_id}>{s.site_name} ({s.site_id})</option>)}
        </select>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>Site ID *</label>
              <input value={data.new_site_id || ""} onChange={e => setData(d => ({ ...d, new_site_id: e.target.value, existing_site_id: "" }))}
                placeholder="e.g. SITE-100" className={INPUT} />
            </div>
            <div>
              <label className={LABEL}>Site Name *</label>
              <input value={data.site_name || ""} onChange={e => setData(d => ({ ...d, site_name: e.target.value }))}
                placeholder="e.g. Benson HQ Elevator" className={INPUT} />
            </div>
          </div>
          <div>
            <label className={LABEL}>Street Address</label>
            <input value={data.e911_street || ""} onChange={e => setData(d => ({ ...d, e911_street: e.target.value }))}
              placeholder="Optional — can be added later" className={INPUT} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <input value={data.e911_city || ""} onChange={e => setData(d => ({ ...d, e911_city: e.target.value }))}
              placeholder="City" className={INPUT} />
            <input value={data.e911_state || ""} onChange={e => setData(d => ({ ...d, e911_state: e.target.value }))}
              placeholder="ST" maxLength={2} className={`${INPUT} uppercase`} />
            <input value={data.e911_zip || ""} onChange={e => setData(d => ({ ...d, e911_zip: e.target.value }))}
              placeholder="ZIP" className={INPUT} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Step 3: Service Units ── */
const UNIT_TYPES = [
  { value: "elevator_phone", label: "Elevator Emergency Phone" },
  { value: "fire_alarm", label: "Fire Alarm Communicator" },
  { value: "emergency_call_station", label: "Emergency Call Station" },
  { value: "fax_line", label: "Fax Line" },
  { value: "voice_line", label: "Generic Voice Line" },
];
const INSTALL_TYPES = [
  { value: "new", label: "New Installation" },
  { value: "modernization", label: "Modernization" },
  { value: "existing", label: "Existing System" },
];

function StepUnits({ data, setData }) {
  const units = data.service_units || [];

  const addUnit = () => {
    const idx = units.length + 1;
    setData(d => ({
      ...d,
      service_units: [...units, { unit_name: `Unit ${idx}`, unit_type: "elevator_phone", install_type: "new", notes: "" }],
    }));
  };

  const updateUnit = (idx, field, value) => {
    setData(d => ({
      ...d,
      service_units: d.service_units.map((u, i) => i === idx ? { ...u, [field]: value } : u),
    }));
  };

  const removeUnit = (idx) => {
    setData(d => ({ ...d, service_units: d.service_units.filter((_, i) => i !== idx) }));
  };

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Service Units</h2>
      <p className="text-sm text-gray-500">Add the emergency communications endpoints at this site.</p>

      {units.length === 0 && (
        <div className="text-center py-6 bg-gray-50 rounded-xl border border-dashed border-gray-300">
          <Phone className="w-6 h-6 text-gray-300 mx-auto mb-2" />
          <p className="text-sm text-gray-400 mb-3">No service units added yet.</p>
          <button onClick={addUnit} className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold">
            <Plus className="w-4 h-4" /> Add Service Unit
          </button>
        </div>
      )}

      {units.map((u, idx) => (
        <div key={idx} className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-gray-500 uppercase">Unit {idx + 1}</span>
            <button onClick={() => removeUnit(idx)} className="p-1 text-gray-400 hover:text-red-600 rounded hover:bg-red-50">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>Name</label>
              <input value={u.unit_name} onChange={e => updateUnit(idx, "unit_name", e.target.value)} className={INPUT} placeholder="e.g. Elevator #1 Phone" />
            </div>
            <div>
              <label className={LABEL}>Type</label>
              <select value={u.unit_type} onChange={e => updateUnit(idx, "unit_type", e.target.value)} className={INPUT}>
                {UNIT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>Install Type</label>
              <select value={u.install_type || ""} onChange={e => updateUnit(idx, "install_type", e.target.value)} className={INPUT}>
                <option value="">-- Select --</option>
                {INSTALL_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label className={LABEL}>Notes</label>
              <input value={u.notes || ""} onChange={e => updateUnit(idx, "notes", e.target.value)} className={INPUT} placeholder="Optional" />
            </div>
          </div>
        </div>
      ))}

      {units.length > 0 && (
        <button onClick={addUnit} className="flex items-center gap-1.5 text-sm text-red-600 hover:text-red-700 font-medium">
          <Plus className="w-4 h-4" /> Add Another Unit
        </button>
      )}
    </div>
  );
}

/* ── Step 4: Assign SIMs ── */
function StepSims({ data, setData }) {
  const [sims, setSims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const selected = new Set(data.selected_sim_ids || []);

  useEffect(() => {
    (async () => {
      try {
        const result = await apiFetch("/sims?has_site=false&limit=200");
        setSims(result);
      } catch { setSims([]); }
      setLoading(false);
    })();
  }, []);

  const toggle = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setData(d => ({ ...d, selected_sim_ids: [...next] }));
  };

  const filtered = sims.filter(s => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (s.iccid || "").toLowerCase().includes(q) || (s.msisdn || "").toLowerCase().includes(q) || (s.carrier || "").toLowerCase().includes(q);
  });

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Assign SIMs</h2>
      <p className="text-sm text-gray-500">Select SIMs from the inventory pool to assign to this site. You can skip this step.</p>

      {selected.size > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700 font-semibold">
          {selected.size} SIM(s) selected
        </div>
      )}

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search ICCID, MSISDN, carrier..."
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
      </div>

      <div className="max-h-64 overflow-y-auto space-y-1 border border-gray-200 rounded-xl p-2">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-gray-400 py-4 justify-center"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-xs text-gray-400 text-center py-4">No unassigned SIMs available.</div>
        ) : filtered.map(s => (
          <label key={s.id} className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selected.has(s.id) ? "bg-red-50" : "hover:bg-gray-50"}`}>
            <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggle(s.id)} className="rounded border-gray-300 text-red-600 focus:ring-red-500" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-mono text-gray-700">{s.iccid}</div>
              <div className="text-[10px] text-gray-500">{s.carrier} {s.msisdn ? `| ${s.msisdn}` : ""} | {s.status}</div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

/* ── Step 5: Assign Devices ── */
function StepDevices({ data, setData }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const selected = new Set(data.selected_device_ids || []);

  useEffect(() => {
    (async () => {
      try {
        const result = await apiFetch("/devices?limit=200");
        // Show devices without a site or all devices
        setDevices(result.filter(d => !d.site_id || d.site_id === ""));
      } catch { setDevices([]); }
      setLoading(false);
    })();
  }, []);

  const toggle = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setData(d => ({ ...d, selected_device_ids: [...next] }));
  };

  const filtered = devices.filter(d => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (d.device_id || "").toLowerCase().includes(q) || (d.model || "").toLowerCase().includes(q) || (d.serial_number || "").toLowerCase().includes(q);
  });

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Assign Devices</h2>
      <p className="text-sm text-gray-500">Select devices to assign to this site. You can skip this step.</p>

      {selected.size > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700 font-semibold">
          {selected.size} device(s) selected
        </div>
      )}

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search device ID, model, serial..."
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
      </div>

      <div className="max-h-64 overflow-y-auto space-y-1 border border-gray-200 rounded-xl p-2">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-gray-400 py-4 justify-center"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-xs text-gray-400 text-center py-4">No unassigned devices available.</div>
        ) : filtered.map(d => (
          <label key={d.id} className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selected.has(d.id) ? "bg-red-50" : "hover:bg-gray-50"}`}>
            <input type="checkbox" checked={selected.has(d.id)} onChange={() => toggle(d.id)} className="rounded border-gray-300 text-red-600 focus:ring-red-500" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-mono text-gray-700">{d.device_id}</div>
              <div className="text-[10px] text-gray-500">{d.device_type || d.model || "—"} | {d.status}</div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

/* ── Step 6: Review ── */
function StepReview({ data, sites }) {
  const siteLabel = data.existing_site_id
    ? (sites.find(s => s.site_id === data.existing_site_id)?.site_name || data.existing_site_id)
    : (data.site_name || "New Site");
  const hasAddress = !!(data.e911_street && data.e911_city);
  const units = data.service_units || [];
  const simCount = (data.selected_sim_ids || []).length;
  const devCount = (data.selected_device_ids || []).length;
  const hasInfra = units.length > 0 || simCount > 0 || devCount > 0;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Review & Complete</h2>
      <p className="text-sm text-gray-500">Review your configuration. Missing fields can be updated later.</p>

      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-xs font-semibold text-gray-500 uppercase">Customer</span>
          <span className="text-sm text-gray-800">{data.customer_name || "Not set"}</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-xs font-semibold text-gray-500 uppercase">Site</span>
          <span className="text-sm text-gray-800">{siteLabel}</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-xs font-semibold text-gray-500 uppercase">Service Units</span>
          <span className="text-sm text-gray-800">{units.length} unit(s)</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-xs font-semibold text-gray-500 uppercase">SIMs</span>
          <span className="text-sm text-gray-800">{simCount} SIM(s)</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-xs font-semibold text-gray-500 uppercase">Devices</span>
          <span className="text-sm text-gray-800">{devCount} device(s)</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-xs font-semibold text-gray-500 uppercase">E911 Address</span>
          <span className="text-sm text-gray-800">{hasAddress ? `${data.e911_street}, ${data.e911_city}` : "Not set"}</span>
        </div>
      </div>

      {/* Warnings */}
      <div className="space-y-2">
        {!hasAddress && hasInfra && (
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
            <span className="text-xs text-amber-700">E911 address not set — emergency routing cannot be confirmed. You can update this later.</span>
          </div>
        )}
        {units.some(u => u.unit_type === "elevator_phone" && !u.install_type) && (
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2.5">
            <AlertTriangle className="w-4 h-4 text-blue-500 flex-shrink-0" />
            <span className="text-xs text-blue-700">Some elevator units have no install type set. Compliance review may be needed later.</span>
          </div>
        )}
      </div>

      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs text-emerald-700">
        <strong>Ready to save.</strong> The site, service units, and assignments will be created. Missing details can be completed later.
      </div>
    </div>
  );
}


/* ── Main Wizard ── */
export default function SiteOnboarding() {
  const { can } = useAuth();
  const [step, setStep] = useState(0);
  const [data, setData] = useState({ service_units: [] });
  const [sites, setSites] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const [createdSiteId, setCreatedSiteId] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [s, c] = await Promise.all([
          apiFetch("/sites?limit=200"),
          apiFetch("/customers?limit=200").catch(() => []),
        ]);
        setSites(s);
        setCustomers(c);
      } catch { /* ok */ }
    })();
  }, []);

  const handleNext = () => setStep(s => Math.min(s + 1, STEPS.length - 1));
  const handleBack = () => setStep(s => Math.max(s - 1, 0));

  const handleComplete = async () => {
    setError("");
    setSubmitting(true);
    try {
      // 1. Create site if new
      let siteId = data.existing_site_id;
      if (!siteId && data.new_site_id) {
        const site = await apiFetch("/sites", {
          method: "POST",
          body: JSON.stringify({
            site_id: data.new_site_id,
            site_name: data.site_name || data.new_site_id,
            customer_name: data.customer_name || "TBD",
            status: "Connected",
            e911_street: data.e911_street || undefined,
            e911_city: data.e911_city || undefined,
            e911_state: data.e911_state || undefined,
            e911_zip: data.e911_zip || undefined,
            poc_name: data.poc_name || undefined,
            poc_phone: data.poc_phone || undefined,
          }),
        });
        siteId = site.site_id;
      }

      if (!siteId) {
        setError("No site selected or created.");
        setSubmitting(false);
        return;
      }

      // 2. Create service units
      for (const [idx, unit] of (data.service_units || []).entries()) {
        await apiFetch("/service-units", {
          method: "POST",
          body: JSON.stringify({
            site_id: siteId,
            unit_id: `${siteId}-U${String(idx + 1).padStart(2, "0")}`,
            unit_name: unit.unit_name,
            unit_type: unit.unit_type,
            install_type: unit.install_type || undefined,
            notes: unit.notes || undefined,
          }),
        });
      }

      // 3. Bulk assign SIMs
      if ((data.selected_sim_ids || []).length > 0) {
        await apiFetch("/sims/bulk-assign-site", {
          method: "POST",
          body: JSON.stringify({ sim_ids: data.selected_sim_ids, site_id: siteId }),
        });
      }

      // 4. Bulk assign devices
      if ((data.selected_device_ids || []).length > 0) {
        await apiFetch("/devices/bulk-assign-site", {
          method: "POST",
          body: JSON.stringify({ device_ids: data.selected_device_ids, site_id: siteId }),
        });
      }

      setCreatedSiteId(siteId);
      setComplete(true);
      toast.success("Site onboarding complete!");
    } catch (err) {
      setError(err?.message || "Onboarding failed. Check details and try again.");
      setSubmitting(false);
    }
  };

  if (complete) {
    return (
      <PageWrapper>
        <div className="p-6 max-w-2xl mx-auto text-center py-20">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-100 rounded-full mb-4">
            <CheckCircle2 className="w-8 h-8 text-emerald-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Site Onboarded</h1>
          <p className="text-sm text-gray-500 mb-6">
            {data.site_name || createdSiteId} has been set up with {(data.service_units || []).length} service unit(s),
            {" "}{(data.selected_sim_ids || []).length} SIM(s), and {(data.selected_device_ids || []).length} device(s).
          </p>
          <div className="flex justify-center gap-3">
            <a href="/Sites" className="px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-semibold">
              View Sites
            </a>
            <button onClick={() => { setComplete(false); setStep(0); setData({ service_units: [] }); setCreatedSiteId(null); }}
              className="px-4 py-2.5 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-xl text-sm font-medium">
              Onboard Another
            </button>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const stepComponents = [
    <StepCustomer data={data} setData={setData} customers={customers} />,
    <StepSite data={data} setData={setData} sites={sites} />,
    <StepUnits data={data} setData={setData} />,
    <StepSims data={data} setData={setData} />,
    <StepDevices data={data} setData={setData} />,
    <StepReview data={data} sites={sites} />,
  ];

  return (
    <PageWrapper>
      <div className="p-6 max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-2">
          <Building2 className="w-5 h-5 text-red-600" />
          <h1 className="text-2xl font-bold text-gray-900">Site Onboarding</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">Set up a new site with service units, SIMs, and devices in one guided flow.</p>

        <StepBar current={step} />

        <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-6">
          {stepComponents[step]}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl mb-4">{error}</div>
        )}

        <div className="flex items-center justify-between">
          <button onClick={handleBack} disabled={step === 0}
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-xl hover:bg-gray-50 disabled:opacity-40">
            <ChevronLeft className="w-4 h-4" /> Back
          </button>

          {step < STEPS.length - 1 ? (
            <button onClick={handleNext}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-xl">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={handleComplete} disabled={submitting}
              className="flex items-center gap-1.5 px-6 py-2.5 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 rounded-xl">
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</> : <><CheckCircle2 className="w-4 h-4" /> Complete</>}
            </button>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}
