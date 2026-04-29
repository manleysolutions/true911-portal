import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { apiFetch } from "@/api/client";
import {
  Building2, Users, Cpu, Disc3, ShieldCheck, CheckCircle2, ChevronRight, ChevronLeft,
  Loader2, AlertTriangle, Plus, Trash2, MapPin, Phone, Search, Info, Star,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const STEPS = [
  { key: "account", label: "Account", icon: Users },
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


/* ═══════════════════════════════════════════════════════════════════
   Step 1 — Account / Customer / Reseller
   ═══════════════════════════════════════════════════════════════════ */
function StepAccount({ data, setData, tenants, customers, isSuperAdmin }) {
  const [mode, setMode] = useState(data.tenant_id ? "existing" : "new");

  // Filter sites for the selected tenant
  const tenantsForDisplay = tenants || [];
  const customersForTenant = (customers || []).filter(
    c => !data.tenant_id || c.tenant_id === data.tenant_id
  );

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Account</h2>
        <p className="text-sm text-gray-500">Which customer or reseller account owns this site?</p>
      </div>

      {/* Tenant selection (SuperAdmin only) */}
      {isSuperAdmin && tenantsForDisplay.length > 0 && (
        <div>
          <label className={LABEL}>Tenant Account</label>
          <div className="flex gap-3 mb-3">
            <button onClick={() => setMode("existing")}
              className={`flex-1 p-2.5 rounded-xl border text-sm font-medium transition-all ${mode === "existing" ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
              Select Existing
            </button>
            <button onClick={() => setMode("new")}
              className={`flex-1 p-2.5 rounded-xl border text-sm font-medium transition-all ${mode === "new" ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
              New Account
            </button>
          </div>

          {mode === "existing" ? (
            <select value={data.tenant_id || ""} onChange={e => {
              const t = tenantsForDisplay.find(x => x.tenant_id === e.target.value);
              setData(d => ({ ...d, tenant_id: e.target.value, customer_name: t?.name || d.customer_name }));
            }} className={INPUT}>
              <option value="">-- Select account --</option>
              {tenantsForDisplay.map(t => (
                <option key={t.tenant_id} value={t.tenant_id}>
                  {t.name} ({t.tenant_id})
                </option>
              ))}
            </select>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL}>Account Slug *</label>
                <input value={data.new_tenant_id || ""} onChange={e => setData(d => ({ ...d, new_tenant_id: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") }))}
                  placeholder="e.g. benson-systems" className={INPUT} />
              </div>
              <div>
                <label className={LABEL}>Display Name *</label>
                <input value={data.new_tenant_name || ""} onChange={e => setData(d => ({ ...d, new_tenant_name: e.target.value, customer_name: e.target.value }))}
                  placeholder="e.g. Benson Systems" className={INPUT} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Customer name */}
      <div>
        <label className={LABEL}>Customer / Company Name</label>
        <input value={data.customer_name || ""} onChange={e => setData(d => ({ ...d, customer_name: e.target.value }))}
          placeholder="e.g. Benson Systems LLC" className={INPUT} list="cust-list" />
        <datalist id="cust-list">
          {customersForTenant.map(c => <option key={c.id} value={c.name} />)}
        </datalist>
      </div>

      {/* Contact info */}
      <div>
        <label className={LABEL}>Primary Contact</label>
        <div className="grid grid-cols-3 gap-2">
          <input value={data.poc_name || ""} onChange={e => setData(d => ({ ...d, poc_name: e.target.value }))}
            placeholder="Name" className={INPUT} />
          <input value={data.poc_phone || ""} onChange={e => setData(d => ({ ...d, poc_phone: e.target.value }))}
            placeholder="Phone" className={INPUT} />
          <input value={data.poc_email || ""} onChange={e => setData(d => ({ ...d, poc_email: e.target.value }))}
            placeholder="Email" className={INPUT} />
        </div>
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════
   Step 2 — Site Details
   ═══════════════════════════════════════════════════════════════════ */
function StepSite({ data, setData, sites }) {
  const [mode, setMode] = useState(data.existing_site_id ? "existing" : "new");
  const filteredSites = data.tenant_id
    ? sites.filter(s => s.tenant_id === data.tenant_id)
    : sites;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Site Details</h2>
        <p className="text-sm text-gray-500">Where is this equipment being installed?</p>
      </div>

      <div className="flex gap-3">
        <button onClick={() => setMode("new")}
          className={`flex-1 p-2.5 rounded-xl border text-sm font-medium transition-all ${mode === "new" ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
          New Site
        </button>
        <button onClick={() => setMode("existing")}
          className={`flex-1 p-2.5 rounded-xl border text-sm font-medium transition-all ${mode === "existing" ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
          Existing Site
        </button>
      </div>

      {mode === "existing" ? (
        <select value={data.existing_site_id || ""} onChange={e => {
          const s = sites.find(x => x.site_id === e.target.value);
          setData(d => ({
            ...d,
            existing_site_id: e.target.value,
            site_name: s?.site_name || "",
            e911_street: s?.e911_street || d.e911_street,
            e911_city: s?.e911_city || d.e911_city,
            e911_state: s?.e911_state || d.e911_state,
            e911_zip: s?.e911_zip || d.e911_zip,
          }));
        }} className={INPUT}>
          <option value="">-- Select a site --</option>
          {filteredSites.map(s => <option key={s.site_id} value={s.site_id}>{s.site_name} ({s.site_id})</option>)}
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
                placeholder="e.g. Benson Tower — Main Elevators" className={INPUT} />
            </div>
          </div>

          {/* Address */}
          <div className="bg-gray-50 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2 mb-1">
              <MapPin className="w-3.5 h-3.5 text-gray-400" />
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wide">Service Address</span>
              <span className="text-[10px] text-gray-400 ml-auto">Can be completed later</span>
            </div>
            <input value={data.e911_street || ""} onChange={e => setData(d => ({ ...d, e911_street: e.target.value }))}
              placeholder="Street address" className={INPUT} />
            <div className="grid grid-cols-3 gap-2">
              <input value={data.e911_city || ""} onChange={e => setData(d => ({ ...d, e911_city: e.target.value }))}
                placeholder="City" className={INPUT} />
              <input value={data.e911_state || ""} onChange={e => setData(d => ({ ...d, e911_state: e.target.value }))}
                placeholder="ST" maxLength={2} className={`${INPUT} uppercase`} />
              <input value={data.e911_zip || ""} onChange={e => setData(d => ({ ...d, e911_zip: e.target.value }))}
                placeholder="ZIP" className={INPUT} />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className={LABEL}>Site Notes</label>
            <textarea value={data.site_notes || ""} onChange={e => setData(d => ({ ...d, site_notes: e.target.value }))}
              placeholder="Building access instructions, parking info, etc." className={`${INPUT} resize-none`} rows={2} />
          </div>
        </div>
      )}
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════
   Step 3 — Service Units (unchanged from prior version)
   ═══════════════════════════════════════════════════════════════════ */
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
      <div>
        <h2 className="text-lg font-bold text-gray-900">Service Units</h2>
        <p className="text-sm text-gray-500">What emergency communications endpoints are at this site?</p>
      </div>

      {units.length === 0 && (
        <div className="text-center py-8 bg-gray-50 rounded-xl border border-dashed border-gray-300">
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


/* ═══════════════════════════════════════════════════════════════════
   Step 4 — SIMs with tenant-aware grouping
   ═══════════════════════════════════════════════════════════════════ */
function StepSims({ data, setData }) {
  const [allSims, setAllSims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const selected = new Set(data.selected_sim_ids || []);
  const tenantId = data.tenant_id || data.new_tenant_id;

  useEffect(() => {
    (async () => {
      try {
        const result = await apiFetch("/sims?has_site=false&limit=300");
        setAllSims(result);
      } catch { setAllSims([]); }
      setLoading(false);
    })();
  }, []);

  const toggle = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setData(d => ({ ...d, selected_sim_ids: [...next] }));
  };

  const filtered = allSims.filter(s => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (s.iccid || "").toLowerCase().includes(q) || (s.msisdn || "").toLowerCase().includes(q) ||
           (s.carrier || "").toLowerCase().includes(q) || (s.imei || "").toLowerCase().includes(q);
  });

  // Split into recommended (same tenant) and other
  const recommended = tenantId ? filtered.filter(s => s.tenant_id === tenantId) : [];
  const other = tenantId ? filtered.filter(s => s.tenant_id !== tenantId) : filtered;

  const SimRow = ({ s }) => (
    <label className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selected.has(s.id) ? "bg-red-50" : "hover:bg-gray-50"}`}>
      <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggle(s.id)} className="rounded border-gray-300 text-red-600 focus:ring-red-500" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-mono text-gray-700">{s.iccid}</div>
        <div className="text-[10px] text-gray-500">{s.carrier} {s.msisdn ? `| ${s.msisdn}` : ""} {s.imei ? `| IMEI ${s.imei}` : ""}</div>
      </div>
      {s.data_source === "carrier_sync" && (
        <span className="text-[9px] bg-indigo-50 text-indigo-600 border border-indigo-200 px-1.5 py-0.5 rounded-full font-bold">sync</span>
      )}
    </label>
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Assign SIMs</h2>
        <p className="text-sm text-gray-500">Select SIMs from the inventory pool. This step is optional.</p>
      </div>

      {selected.size > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700 font-semibold">
          {selected.size} SIM(s) selected
        </div>
      )}

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search ICCID, MSISDN, carrier, IMEI..."
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
      </div>

      <div className="max-h-72 overflow-y-auto border border-gray-200 rounded-xl">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-gray-400 py-6 justify-center"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-xs text-gray-400 text-center py-6">
            No unassigned SIMs available.{" "}
            <Link to={createPageUrl("SimManagement")} className="text-red-600 hover:underline">
              Manage SIM inventory
            </Link>
          </div>
        ) : (
          <div className="p-2 space-y-0.5">
            {recommended.length > 0 && (
              <>
                <div className="flex items-center gap-1.5 px-2 py-1.5 text-[10px] font-bold text-amber-700 uppercase">
                  <Star className="w-3 h-3 text-amber-500" /> Recommended for this account
                </div>
                {recommended.map(s => <SimRow key={s.id} s={s} />)}
                {other.length > 0 && (
                  <div className="px-2 py-1.5 text-[10px] font-bold text-gray-400 uppercase border-t border-gray-100 mt-2 pt-2">
                    Other Available SIMs
                  </div>
                )}
              </>
            )}
            {other.map(s => <SimRow key={s.id} s={s} />)}
          </div>
        )}
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════
   Step 5 — Devices with tenant-aware grouping
   ═══════════════════════════════════════════════════════════════════ */
function StepDevices({ data, setData }) {
  const [allDevices, setAllDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const selected = new Set(data.selected_device_ids || []);
  const tenantId = data.tenant_id || data.new_tenant_id;

  useEffect(() => {
    (async () => {
      try {
        const result = await apiFetch("/devices?limit=300");
        setAllDevices(result.filter(d => !d.site_id));
      } catch { setAllDevices([]); }
      setLoading(false);
    })();
  }, []);

  const toggle = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setData(d => ({ ...d, selected_device_ids: [...next] }));
  };

  const filtered = allDevices.filter(d => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (d.device_id || "").toLowerCase().includes(q) || (d.model || "").toLowerCase().includes(q) ||
           (d.serial_number || "").toLowerCase().includes(q) || (d.imei || "").toLowerCase().includes(q);
  });

  const recommended = tenantId ? filtered.filter(d => d.tenant_id === tenantId) : [];
  const other = tenantId ? filtered.filter(d => d.tenant_id !== tenantId) : filtered;

  const DevRow = ({ d }) => (
    <label className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selected.has(d.id) ? "bg-red-50" : "hover:bg-gray-50"}`}>
      <input type="checkbox" checked={selected.has(d.id)} onChange={() => toggle(d.id)} className="rounded border-gray-300 text-red-600 focus:ring-red-500" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-mono text-gray-700">{d.device_id}</div>
        <div className="text-[10px] text-gray-500">{d.device_type || d.model || "—"} | {d.status} {d.imei ? `| IMEI ${d.imei}` : ""}</div>
      </div>
    </label>
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Assign Devices</h2>
        <p className="text-sm text-gray-500">Select devices to assign to this site. This step is optional.</p>
      </div>

      {selected.size > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700 font-semibold">
          {selected.size} device(s) selected
        </div>
      )}

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search device ID, model, serial, IMEI..."
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
      </div>

      <div className="max-h-72 overflow-y-auto border border-gray-200 rounded-xl">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-gray-400 py-6 justify-center"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-xs text-gray-400 text-center py-6">
            No unassigned devices available.{" "}
            <Link to={createPageUrl("Devices")} className="text-red-600 hover:underline">
              Manage device inventory
            </Link>
          </div>
        ) : (
          <div className="p-2 space-y-0.5">
            {recommended.length > 0 && (
              <>
                <div className="flex items-center gap-1.5 px-2 py-1.5 text-[10px] font-bold text-amber-700 uppercase">
                  <Star className="w-3 h-3 text-amber-500" /> Recommended for this account
                </div>
                {recommended.map(d => <DevRow key={d.id} d={d} />)}
                {other.length > 0 && (
                  <div className="px-2 py-1.5 text-[10px] font-bold text-gray-400 uppercase border-t border-gray-100 mt-2 pt-2">
                    Other Available Devices
                  </div>
                )}
              </>
            )}
            {other.map(d => <DevRow key={d.id} d={d} />)}
          </div>
        )}
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════
   Step 6 — Review with executive summary
   ═══════════════════════════════════════════════════════════════════ */
function StepReview({ data, sites }) {
  const siteLabel = data.existing_site_id
    ? (sites.find(s => s.site_id === data.existing_site_id)?.site_name || data.existing_site_id)
    : (data.site_name || "New Site");
  const hasAddress = !!(data.e911_street && data.e911_city && data.e911_state);
  const units = data.service_units || [];
  const simCount = (data.selected_sim_ids || []).length;
  const devCount = (data.selected_device_ids || []).length;
  const hasInfra = units.length > 0 || simCount > 0 || devCount > 0;
  const elevatorUnits = units.filter(u => u.unit_type === "elevator_phone");
  const missingInstallType = elevatorUnits.some(u => !u.install_type);

  // Determine compliance review status
  let complianceLabel = "N/A";
  let complianceBadge = "bg-gray-100 text-gray-500";
  if (elevatorUnits.length > 0) {
    if (missingInstallType || !hasAddress) {
      complianceLabel = "Review Needed";
      complianceBadge = "bg-amber-50 text-amber-700 border-amber-200";
    } else {
      complianceLabel = "Ready for Review";
      complianceBadge = "bg-blue-50 text-blue-700 border-blue-200";
    }
  }

  const Row = ({ label, value, badge, badgeClass }) => (
    <div className="flex items-center justify-between px-4 py-3">
      <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</span>
      {badge ? (
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${badgeClass}`}>{badge}</span>
      ) : (
        <span className="text-sm text-gray-800 font-medium">{value}</span>
      )}
    </div>
  );

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Review & Complete</h2>
        <p className="text-sm text-gray-500">Confirm the setup. Missing details can always be completed later.</p>
      </div>

      {/* Executive summary cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-gray-900">{units.length}</div>
          <div className="text-[10px] text-gray-500 uppercase font-semibold">Service Units</div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-gray-900">{simCount}</div>
          <div className="text-[10px] text-gray-500 uppercase font-semibold">SIMs</div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-gray-900">{devCount}</div>
          <div className="text-[10px] text-gray-500 uppercase font-semibold">Devices</div>
        </div>
      </div>

      {/* Detail rows */}
      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        <Row label="Account" value={data.customer_name || data.new_tenant_name || "—"} />
        <Row label="Site" value={siteLabel} />
        <Row label="Contact" value={data.poc_name ? `${data.poc_name}${data.poc_phone ? ` | ${data.poc_phone}` : ""}` : "Not set"} />
        <Row label="E911 Address" badge={hasAddress ? "Provided" : "Missing"} badgeClass={hasAddress ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-amber-50 text-amber-700 border-amber-200"} />
        <Row label="Compliance" badge={complianceLabel} badgeClass={complianceBadge} />
      </div>

      {/* Soft warnings */}
      <div className="space-y-2">
        {!hasAddress && hasInfra && (
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
            <span className="text-xs text-amber-700">E911 address not set — emergency routing cannot be confirmed. You can update this after onboarding.</span>
          </div>
        )}
        {missingInstallType && (
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2.5">
            <Info className="w-4 h-4 text-blue-500 flex-shrink-0" />
            <span className="text-xs text-blue-700">Some elevator units have no install type set. Compliance review will be needed.</span>
          </div>
        )}
      </div>

      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs text-emerald-700">
        <strong>Ready to save.</strong> All relationships will be created. The site will appear in your fleet immediately.
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════
   Main Wizard
   ═══════════════════════════════════════════════════════════════════ */
export default function SiteOnboarding() {
  const { can, isSuperAdmin, user } = useAuth();
  const [step, setStep] = useState(0);
  const [data, setData] = useState({ service_units: [], tenant_id: user?.tenant_id || "" });
  const [sites, setSites] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const [createdSiteId, setCreatedSiteId] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [s, c] = await Promise.all([
          apiFetch("/sites?limit=300"),
          apiFetch("/customers?limit=300").catch(() => []),
        ]);
        setSites(s);
        setCustomers(c);
        // SuperAdmin can see all tenants
        if (isSuperAdmin) {
          try {
            const t = await apiFetch("/admin/tenants");
            setTenants(t);
          } catch { /* ok — not SuperAdmin or endpoint unavailable */ }
        }
      } catch { /* ok */ }
    })();
  }, [isSuperAdmin]);

  const handleNext = () => setStep(s => Math.min(s + 1, STEPS.length - 1));
  const handleBack = () => setStep(s => Math.max(s - 1, 0));

  // Phase 2 guardrail: SuperAdmin must explicitly choose an existing
  // tenant or define a new one before leaving the Account step.  Other
  // roles always use their own tenant_id and are unaffected.
  const accountStepBlockedForSuperAdmin = (
    isSuperAdmin
    && !data.tenant_id
    && !(data.new_tenant_id && data.new_tenant_name)
  );
  const nextDisabled = step === 0 && accountStepBlockedForSuperAdmin;

  const handleComplete = async () => {
    setError("");
    setSubmitting(true);
    try {
      // 0. Create tenant if new (SuperAdmin only)
      let tenantId = data.tenant_id;
      if (!tenantId && data.new_tenant_id && isSuperAdmin) {
        await apiFetch("/admin/tenants", {
          method: "POST",
          body: JSON.stringify({ tenant_id: data.new_tenant_id, name: data.new_tenant_name || data.new_tenant_id }),
        });
        tenantId = data.new_tenant_id;
      }

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
            poc_email: data.poc_email || undefined,
            notes: data.site_notes || undefined,
          }),
        });
        siteId = site.site_id;
      }

      if (!siteId) {
        setError("No site selected or created. Go back to the Site step.");
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

  if (!can("CREATE_SITES")) {
    return (
      <PageWrapper>
        <div className="p-6 text-center text-gray-500">You do not have permission to access this page.</div>
      </PageWrapper>
    );
  }

  if (complete) {
    const units = data.service_units || [];
    const simCount = (data.selected_sim_ids || []).length;
    const devCount = (data.selected_device_ids || []).length;

    return (
      <PageWrapper>
        <div className="p-6 max-w-2xl mx-auto text-center py-16">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-100 rounded-full mb-4">
            <CheckCircle2 className="w-8 h-8 text-emerald-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Site Onboarded</h1>
          <p className="text-sm text-gray-500 mb-2">
            <span className="font-semibold text-gray-800">{data.site_name || createdSiteId}</span>
            {data.customer_name && <> for <span className="font-semibold text-gray-800">{data.customer_name}</span></>}
          </p>
          <div className="flex justify-center gap-6 text-center mb-8">
            <div><div className="text-xl font-bold text-gray-900">{units.length}</div><div className="text-[10px] text-gray-500 uppercase">Units</div></div>
            <div><div className="text-xl font-bold text-gray-900">{simCount}</div><div className="text-[10px] text-gray-500 uppercase">SIMs</div></div>
            <div><div className="text-xl font-bold text-gray-900">{devCount}</div><div className="text-[10px] text-gray-500 uppercase">Devices</div></div>
          </div>
          <div className="flex justify-center gap-3">
            <Link to={createPageUrl("Sites")} className="px-5 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-semibold">
              View Sites
            </Link>
            <button onClick={() => { setComplete(false); setStep(0); setData({ service_units: [], tenant_id: user?.tenant_id || "" }); setCreatedSiteId(null); }}
              className="px-5 py-2.5 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-xl text-sm font-medium">
              Onboard Another
            </button>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const stepComponents = [
    <StepAccount key="account" data={data} setData={setData} tenants={tenants} customers={customers} isSuperAdmin={isSuperAdmin} />,
    <StepSite key="site" data={data} setData={setData} sites={sites} />,
    <StepUnits key="units" data={data} setData={setData} />,
    <StepSims key="sims" data={data} setData={setData} />,
    <StepDevices key="devices" data={data} setData={setData} />,
    <StepReview key="review" data={data} sites={sites} />,
  ];

  return (
    <PageWrapper>
      <div className="p-6 max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-2">
          <Building2 className="w-5 h-5 text-red-600" />
          <h1 className="text-2xl font-bold text-gray-900">Site Onboarding</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">Provision a customer site with service units, SIMs, and devices.</p>

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
            <div className="flex flex-col items-end gap-1">
              <button
                onClick={handleNext}
                disabled={nextDisabled}
                title={nextDisabled ? "Select an existing tenant or define a new one to continue." : undefined}
                className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 disabled:bg-red-300 disabled:cursor-not-allowed rounded-xl"
              >
                Next <ChevronRight className="w-4 h-4" />
              </button>
              {nextDisabled && (
                <span className="text-[11px] text-amber-700">
                  Select an existing tenant or define a new one to continue.
                </span>
              )}
            </div>
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
