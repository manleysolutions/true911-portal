import { useState, useEffect, useCallback, useMemo } from "react";
import { Site, ActionAudit } from "@/api/entities";
import { Search, Filter, ChevronDown, Building2, RefreshCw, ArrowRight, X, Plus } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import StatusBadge from "@/components/ui/StatusBadge";
import KitTypeBadge from "@/components/ui/KitTypeBadge";
import ServiceClassBadge from "@/components/ui/ServiceClassBadge";
import SiteDrawer from "@/components/SiteDrawer";
import { useAuth } from "@/contexts/AuthContext";

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STATUS_OPTIONS = ["Connected", "Not Connected", "Attention Needed", "Unknown"];
const KIT_OPTIONS = ["Elevator", "FACP", "Fax", "SCADA", "Emergency Call Box", "Other"];
const CARRIER_OPTIONS = ["AT&T", "Verizon", "T-Mobile", "Comcast"];
const STATES_OPTIONS = ["All States", "NY", "IL", "FL", "TX", "WA", "CA", "MA", "AZ", "CO", "GA", "NV", "TN", "OR", "MN", "MI", "LA", "OH", "MO", "UT", "PA", "NM"];

function SelectFilter({ label, value, onChange, options }) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="appearance-none pl-3 pr-8 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-red-500"
      >
        <option value="">{label}</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
      <ChevronDown className="w-3.5 h-3.5 absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
    </div>
  );
}

const ENDPOINT_TYPE_OPTIONS = ["Elevator", "FACP", "Fax", "SCADA", "Emergency Call Box", "Other"];
const SERVICE_CLASS_OPTIONS = ["E911", "POTS", "SIP", "PRI", "Analog", "Digital"];

const EMPTY_FORM = {
  site_name: "",
  customer_name: "",
  e911_street: "",
  e911_city: "",
  e911_state: "",
  e911_zip: "",
  endpoint_type: "",
  service_class: "",
  carrier: "",
  notes: "",
};

export default function Sites() {
  const { can } = useAuth();
  const isAdmin = can("VIEW_ADMIN");

  const [sites, setSites] = useState([]);
  const [audits, setAudits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterKit, setFilterKit] = useState("");
  const [filterCarrier, setFilterCarrier] = useState("");
  const [filterState, setFilterState] = useState("");

  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState(EMPTY_FORM);
  const [addError, setAddError] = useState("");
  const [addSaving, setAddSaving] = useState(false);

  const fetchData = useCallback(async () => {
    const [sitesData, auditData] = await Promise.all([
      Site.list("-last_checkin", 100),
      ActionAudit.list("-timestamp", 100),
    ]);
    setSites(sitesData);
    setAudits(auditData);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Map site_id → last audit action
  const lastAuditBySite = useMemo(() => {
    const map = {};
    for (const a of audits) {
      if (a.site_id && !map[a.site_id]) map[a.site_id] = a;
    }
    return map;
  }, [audits]);

  const activeFilters = [filterStatus, filterKit, filterCarrier, filterState].filter(Boolean).length;

  const filtered = useMemo(() => {
    return sites.filter(s => {
      if (filterStatus && s.status !== filterStatus) return false;
      if (filterKit && s.kit_type !== filterKit) return false;
      if (filterCarrier && s.carrier !== filterCarrier) return false;
      if (filterState && filterState !== "All States" && s.e911_state !== filterState) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          s.site_name?.toLowerCase().includes(q) ||
          s.site_id?.toLowerCase().includes(q) ||
          s.customer_name?.toLowerCase().includes(q) ||
          s.e911_city?.toLowerCase().includes(q) ||
          s.e911_state?.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [sites, filterStatus, filterKit, filterCarrier, filterState, search]);

  const clearFilters = () => {
    setFilterStatus("");
    setFilterKit("");
    setFilterCarrier("");
    setFilterState("");
    setSearch("");
  };

  const handleAddSite = async (e) => {
    e.preventDefault();
    setAddError("");

    if (!addForm.site_name.trim()) {
      setAddError("Site name is required.");
      return;
    }

    setAddSaving(true);
    try {
      await Site.create({
        site_id: `SITE-${Date.now()}`,
        site_name: addForm.site_name.trim(),
        customer_name: addForm.site_name.trim(),
        status: "Unknown",
        e911_street: addForm.e911_street.trim() || undefined,
        e911_city: addForm.e911_city.trim() || undefined,
        e911_state: addForm.e911_state.trim() || undefined,
        e911_zip: addForm.e911_zip.trim() || undefined,
        endpoint_type: addForm.endpoint_type || undefined,
        service_class: addForm.service_class || undefined,
        carrier: addForm.carrier || undefined,
        notes: addForm.notes.trim() || undefined,
      });
      setShowAddModal(false);
      setAddForm(EMPTY_FORM);
      fetchData();
    } catch (err) {
      setAddError(err?.message || "Failed to create site.");
    } finally {
      setAddSaving(false);
    }
  };

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Sites</h1>
            <p className="text-sm text-gray-500 mt-0.5">{sites.length} monitored sites</p>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button
                onClick={() => { setAddForm(EMPTY_FORM); setAddError(""); setShowAddModal(true); }}
                className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold"
              >
                <Plus className="w-4 h-4" /> Add Site
              </button>
            )}
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-5">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search sites, customers, addresses..."
                className="w-full pl-8 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
              />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Filter className="w-3.5 h-3.5 text-gray-400" />
              <SelectFilter label="All Statuses" value={filterStatus} onChange={setFilterStatus} options={STATUS_OPTIONS} />
              <SelectFilter label="All Kit Types" value={filterKit} onChange={setFilterKit} options={KIT_OPTIONS} />
              <SelectFilter label="All Carriers" value={filterCarrier} onChange={setFilterCarrier} options={CARRIER_OPTIONS} />
              <SelectFilter label="All States" value={filterState} onChange={setFilterState} options={STATES_OPTIONS} />
              {activeFilters > 0 && (
                <button onClick={clearFilters} className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 px-2 py-2 rounded-lg hover:bg-red-50 transition-colors">
                  <X className="w-3 h-3" /> Clear ({activeFilters})
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-gray-400" />
              <span className="text-sm font-semibold text-gray-700">
                {filtered.length} {filtered.length === 1 ? "site" : "sites"}
                {activeFilters > 0 && <span className="text-gray-400 font-normal ml-1">(filtered)</span>}
              </span>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Site</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Endpoint Type</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Service Class</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Location</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Network</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Last Check-in</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Last Action</th>
                    <th className="px-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {filtered.map(site => {
                    const lastAudit = lastAuditBySite[site.site_id];
                    return (
                      <tr
                        key={site.id}
                        className="hover:bg-gray-50 cursor-pointer transition-colors"
                        onClick={() => setSelectedSite(site)}
                      >
                        <td className="px-5 py-3.5">
                          <div className="font-medium text-gray-900">{site.site_name}</div>
                          <div className="text-xs text-gray-400 mt-0.5">{site.customer_name} · <span className="font-mono">{site.site_id}</span></div>
                        </td>
                        <td className="px-3 py-3.5">
                          <StatusBadge status={site.status} />
                        </td>
                        <td className="px-3 py-3.5">
                          <KitTypeBadge type={site.endpoint_type || site.kit_type} />
                        </td>
                        <td className="px-3 py-3.5">
                          <ServiceClassBadge serviceClass={site.service_class} />
                        </td>
                        <td className="px-3 py-3.5">
                          <div className="text-xs text-gray-700">{site.e911_city}, {site.e911_state}</div>
                        </td>
                        <td className="px-3 py-3.5">
                          <div className="text-xs text-gray-700">{site.network_tech}</div>
                          <div className="text-[11px] text-gray-400">{site.carrier}</div>
                        </td>
                        <td className="px-3 py-3.5 text-xs text-gray-600">{timeSince(site.last_checkin)}</td>
                        <td className="px-3 py-3.5">
                          {lastAudit ? (
                            <div>
                              <div className="text-xs text-gray-700 font-medium">{lastAudit.action_type}</div>
                              <div className="text-[11px] text-gray-400">{lastAudit.user_email?.split('@')[0]}</div>
                            </div>
                          ) : <span className="text-xs text-gray-300">—</span>}
                        </td>
                        <td className="px-3 py-3.5">
                          <ArrowRight className="w-3.5 h-3.5 text-gray-300" />
                        </td>
                      </tr>
                    );
                  })}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-5 py-12 text-center text-sm text-gray-400">
                        No sites match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <SiteDrawer
        site={selectedSite}
        onClose={() => setSelectedSite(null)}
        onSiteUpdated={fetchData}
      />

      {/* Add Site Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-gray-900">Add Site</h2>
              <button onClick={() => setShowAddModal(false)} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAddSite} className="space-y-4">
              {/* Site Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Site Name *</label>
                <input
                  value={addForm.site_name}
                  onChange={e => setAddForm(f => ({ ...f, site_name: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                  placeholder="e.g. 123 Main St Elevator"
                />
              </div>

              {/* Address row */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Address</label>
                <input
                  value={addForm.e911_street}
                  onChange={e => setAddForm(f => ({ ...f, e911_street: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                  placeholder="Street address"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">City</label>
                  <input
                    value={addForm.e911_city}
                    onChange={e => setAddForm(f => ({ ...f, e911_city: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                    placeholder="City"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
                  <input
                    value={addForm.e911_state}
                    onChange={e => setAddForm(f => ({ ...f, e911_state: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                    placeholder="NY"
                    maxLength={2}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">ZIP</label>
                  <input
                    value={addForm.e911_zip}
                    onChange={e => setAddForm(f => ({ ...f, e911_zip: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                    placeholder="10001"
                    maxLength={10}
                  />
                </div>
              </div>

              {/* Endpoint Type + Service Class */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Endpoint Type</label>
                  <select
                    value={addForm.endpoint_type}
                    onChange={e => setAddForm(f => ({ ...f, endpoint_type: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500 bg-white"
                  >
                    <option value="">Select...</option>
                    {ENDPOINT_TYPE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Service Class</label>
                  <select
                    value={addForm.service_class}
                    onChange={e => setAddForm(f => ({ ...f, service_class: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500 bg-white"
                  >
                    <option value="">Select...</option>
                    {SERVICE_CLASS_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              </div>

              {/* Carrier */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Carrier</label>
                <select
                  value={addForm.carrier}
                  onChange={e => setAddForm(f => ({ ...f, carrier: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500 bg-white"
                >
                  <option value="">Select...</option>
                  {CARRIER_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                <textarea
                  value={addForm.notes}
                  onChange={e => setAddForm(f => ({ ...f, notes: e.target.value }))}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500 resize-none"
                  placeholder="Optional notes..."
                />
              </div>

              {addError && (
                <p className="text-sm text-red-600">{addError}</p>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 rounded-lg hover:bg-gray-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addSaving}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
                >
                  {addSaving ? "Creating..." : "Create Site"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </PageWrapper>
  );
}