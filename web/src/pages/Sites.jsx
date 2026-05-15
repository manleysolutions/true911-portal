import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { Site, ActionAudit, Customer } from "@/api/entities";
import { Search, Filter, ChevronDown, Building2, RefreshCw, ArrowRight, X, Plus } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import StatusBadge from "@/components/ui/StatusBadge";
import CustomerStatusBadge from "@/components/ui/CustomerStatusBadge";
import KitTypeBadge from "@/components/ui/KitTypeBadge";
import ServiceClassBadge from "@/components/ui/ServiceClassBadge";
import SiteDrawer from "@/components/SiteDrawer";
import CustomerSiteDetailDrawer from "@/components/CustomerSiteDetailDrawer";
import { useAuth } from "@/contexts/AuthContext";
import { isCustomerRole } from "@/lib/attention";

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
const KIT_OPTIONS = ["Elevator", "Fire Alarm Control Panel", "Emergency Phone", "Burglar Alarm", "Fax", "SCADA / Industrial", "Other"];
const CARRIER_OPTIONS = ["T-Mobile", "Verizon", "AT&T", "Teal", "Napco", "Other"];
const STATES_OPTIONS = ["All States", "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"];

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

// Add Site captures location-level data only.
// Service-level fields (carrier, service_class, transport, voice_provider, endpoint_type, kit_type)
// belong on devices/lines and are intentionally not exposed here. Their DB columns remain for
// backward compatibility with existing records, filters, reports, and importers.
const EMPTY_FORM = {
  site_name: "",
  customer_name: "",
  e911_street: "",
  e911_city: "",
  e911_state: "",
  e911_zip: "",
  poc_name: "",
  poc_phone: "",
  poc_email: "",
  notes: "",
};

export default function Sites() {
  const { user, can } = useAuth();
  const isAdmin = can("VIEW_ADMIN");
  const canCreateSite = can("CREATE_SITES");
  // Customer-facing roles see the calm presentation layer; internal
  // roles continue to see raw operational labels so admin
  // troubleshooting is unchanged.
  const showCustomerStatus = isCustomerRole(user?.role);
  const navigate = useNavigate();
  const location = useLocation();

  // Auto-open Add Site modal when ?action=add is in URL
  useEffect(() => {
    if (canCreateSite && new URLSearchParams(location.search).get("action") === "add") {
      setShowAddModal(true);
    }
  }, [location.search, canCreateSite]);

  const [sites, setSites] = useState([]);
  const [totalSites, setTotalSites] = useState(null);
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

  // Customer typeahead state for the Add Site modal
  const [customers, setCustomers] = useState([]);
  const [customersLoaded, setCustomersLoaded] = useState(false);
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerOpen, setCustomerOpen] = useState(false);
  const customerBlurTimer = useRef(null);

  // Load customers when the modal opens (lazy)
  useEffect(() => {
    if (!showAddModal || customersLoaded) return;
    let cancelled = false;
    Customer.list("name", 500)
      .then(rows => {
        if (cancelled) return;
        setCustomers(Array.isArray(rows) ? rows : []);
        setCustomersLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setCustomers([]);
        setCustomersLoaded(true);
      });
    return () => { cancelled = true; };
  }, [showAddModal, customersLoaded]);

  const filteredCustomers = useMemo(() => {
    const q = customerQuery.trim().toLowerCase();
    if (!q) return customers.slice(0, 50);
    return customers.filter(c => (c.name || "").toLowerCase().includes(q)).slice(0, 50);
  }, [customers, customerQuery]);

  const fetchData = useCallback(async () => {
    // Load up to 1000 rows (backend max) so search/filter cover the full
    // tenant; the header count comes from a dedicated count endpoint so it
    // is accurate regardless of the loaded page size.
    const [sitesData, auditData, countData] = await Promise.all([
      Site.list("-last_checkin", 1000),
      ActionAudit.list("-timestamp", 100),
      Site.count().catch(() => null),
    ]);
    setSites(sitesData);
    setAudits(auditData);
    if (countData && typeof countData.total === "number") {
      setTotalSites(countData.total);
    } else {
      setTotalSites(Array.isArray(sitesData) ? sitesData.length : 0);
    }
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

  const resetAddForm = () => {
    setAddForm(EMPTY_FORM);
    setAddError("");
    setCustomerQuery("");
    setCustomerOpen(false);
  };

  const handleAddSite = async (e) => {
    e.preventDefault();
    setAddError("");

    if (!addForm.site_name.trim()) {
      setAddError("Site name is required.");
      return;
    }

    // Customer must resolve to a real loaded customer (no free-text creation).
    //
    // Recover the selection if the typeahead query matches a loaded customer,
    // even when addForm.customer_name was cleared by a stray keystroke after
    // the click (the onChange handler clears it on every key event so any
    // edit-after-click leaves the input visually populated but the form
    // state empty — which silently blocked DataEntry users on submit).
    let selectedCustomerName = addForm.customer_name.trim();
    if (!selectedCustomerName && customersLoaded && customerQuery.trim()) {
      const typedLower = customerQuery.trim().toLowerCase();
      const match = customers.find(
        c => (c.name || "").trim().toLowerCase() === typedLower,
      );
      if (match) selectedCustomerName = match.name;
    }

    if (!selectedCustomerName) {
      const typed = customerQuery.trim();
      setAddError(
        typed
          ? `Customer "${typed}" not found. Pick one from the list.`
          : "Customer is required. Select one from the list.",
      );
      return;
    }
    if (customersLoaded && !customers.some(c => (c.name || "") === selectedCustomerName)) {
      setAddError("Customer must be selected from the list. Add the customer first if it doesn't exist.");
      return;
    }

    setAddSaving(true);
    try {
      await Site.create({
        site_id: `SITE-${Date.now()}`,
        site_name: addForm.site_name.trim(),
        customer_name: selectedCustomerName,
        status: "Not Connected",
        e911_street: addForm.e911_street.trim() || undefined,
        e911_city: addForm.e911_city.trim() || undefined,
        e911_state: addForm.e911_state.trim() || undefined,
        e911_zip: addForm.e911_zip.trim() || undefined,
        poc_name: addForm.poc_name.trim() || undefined,
        poc_phone: addForm.poc_phone.trim() || undefined,
        poc_email: addForm.poc_email.trim() || undefined,
        notes: addForm.notes.trim() || undefined,
      });
      setShowAddModal(false);
      resetAddForm();
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
            <p className="text-sm text-gray-500 mt-0.5">
              {totalSites ?? sites.length}
              {" "}
              {showCustomerStatus
                ? "registered location" + ((totalSites ?? sites.length) === 1 ? "" : "s")
                : "monitored sites"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canCreateSite && (
              <button
                onClick={() => { resetAddForm(); setShowAddModal(true); }}
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
              {/* Status filter is gated on internal roles because the raw
                  Connected / Not Connected / Attention Needed / Unknown
                  options leak operational terminology to customers.
                  Phase 2 introduces a customer-facing status filter. */}
              {!showCustomerStatus && (
                <SelectFilter label="All Statuses" value={filterStatus} onChange={setFilterStatus} options={STATUS_OPTIONS} />
              )}
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
                    {/* The backend-computed Health column (healthy / warning /
                        critical / unknown) is shown to internal roles only.
                        For customer roles it produced contradictions like
                        "Monitoring Pending" status + "healthy" health on
                        imported sites — confusing and trust-destroying.
                        Phase 4 will introduce a customer-facing health view
                        derived from the normalized status. */}
                    {!showCustomerStatus && (
                      <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Health</th>
                    )}
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
                        onClick={() => {
                          // Customer roles open the calm, inventory-model
                          // drawer in place; internal roles continue to
                          // navigate to the full SiteDetail page.
                          if (showCustomerStatus) {
                            setSelectedSite(site);
                          } else {
                            navigate(`${createPageUrl("SiteDetail")}?id=${site.site_id}`);
                          }
                        }}
                      >
                        <td className="px-5 py-3.5">
                          <div className="font-medium text-gray-900">{site.site_name}</div>
                          <div className="text-xs text-gray-400 mt-0.5">{site.customer_name} · <span className="font-mono">{site.site_id}</span></div>
                        </td>
                        <td className="px-3 py-3.5">
                          {showCustomerStatus
                            ? <CustomerStatusBadge site={site} role={user.role} />
                            : <StatusBadge status={site.status} />}
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
                        {!showCustomerStatus && (
                          <td className="px-3 py-3.5">
                            {(() => {
                              const h = site.health_status || "unknown";
                              const styles = {
                                healthy:  "bg-emerald-50 text-emerald-700 border-emerald-200",
                                warning:  "bg-amber-50 text-amber-700 border-amber-200",
                                critical: "bg-red-50 text-red-700 border-red-200",
                                unknown:  "bg-gray-50 text-gray-500 border-gray-200",
                              };
                              const dots = { healthy: "bg-emerald-500", warning: "bg-amber-500", critical: "bg-red-500", unknown: "bg-gray-400" };
                              return (
                                <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full border ${styles[h] || styles.unknown}`}>
                                  <span className={`w-1.5 h-1.5 rounded-full ${dots[h] || dots.unknown}`} />
                                  {h}
                                </span>
                              );
                            })()}
                          </td>
                        )}
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

      {/* Internal/admin drawer (legacy path — preserved for internal roles).
          The Sites page row click navigates to SiteDetail for internal roles,
          so this drawer is rarely opened, but the render is left intact for
          compatibility with anything that sets selectedSite externally. */}
      {!showCustomerStatus && (
        <SiteDrawer
          site={selectedSite}
          onClose={() => setSelectedSite(null)}
          onSiteUpdated={fetchData}
        />
      )}

      {/* Customer-facing drawer — opened by row click for User / Manager. */}
      {showCustomerStatus && (
        <CustomerSiteDetailDrawer
          site={selectedSite}
          onClose={() => setSelectedSite(null)}
        />
      )}

      {/* Add Site Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-gray-900">Add Site</h2>
              <button onClick={() => { setShowAddModal(false); resetAddForm(); }} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
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
                  required
                />
              </div>

              {/* Customer typeahead (no free-text) */}
              <div className="relative">
                <label className="block text-sm font-medium text-gray-700 mb-1">Customer *</label>
                <input
                  value={customerQuery || addForm.customer_name}
                  onChange={e => {
                    const v = e.target.value;
                    setCustomerQuery(v);
                    // Clear any prior selection until the user picks again
                    setAddForm(f => ({ ...f, customer_name: "" }));
                    setCustomerOpen(true);
                  }}
                  onFocus={() => setCustomerOpen(true)}
                  onBlur={() => {
                    // Delay so a click on a list item registers before close
                    customerBlurTimer.current = setTimeout(() => setCustomerOpen(false), 150);
                  }}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                  placeholder={customersLoaded && customers.length === 0 ? "No customers yet" : "Search customers…"}
                  autoComplete="off"
                  disabled={customersLoaded && customers.length === 0}
                />
                {customerOpen && customersLoaded && customers.length > 0 && (
                  <div className="absolute z-10 mt-1 w-full max-h-56 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
                    {filteredCustomers.length === 0 ? (
                      <div className="px-3 py-2 text-sm text-gray-400">No matches</div>
                    ) : (
                      filteredCustomers.map(c => (
                        <button
                          type="button"
                          key={c.id ?? c.name}
                          onMouseDown={e => e.preventDefault()}
                          onClick={() => {
                            if (customerBlurTimer.current) clearTimeout(customerBlurTimer.current);
                            setAddForm(f => ({ ...f, customer_name: c.name || "" }));
                            setCustomerQuery(c.name || "");
                            setCustomerOpen(false);
                          }}
                          className="block w-full text-left px-3 py-2 text-sm hover:bg-gray-50"
                        >
                          {c.name}
                        </button>
                      ))
                    )}
                  </div>
                )}
                {customersLoaded && customers.length === 0 && (
                  <p className="mt-1 text-xs text-gray-500">
                    No customers found. <Link to={createPageUrl("Customers")} className="text-red-600 hover:underline">Add one in Customers</Link> first.
                  </p>
                )}
              </div>

              {/* Address (also serves as the E911 / location address) */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Street Address</label>
                <input
                  value={addForm.e911_street}
                  onChange={e => setAddForm(f => ({ ...f, e911_street: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                  placeholder="Street address"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Used as the E911 / location address. Compliance status is set automatically — leaving fields blank will not block creation.
                </p>
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
                    placeholder="TX"
                    maxLength={2}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">ZIP</label>
                  <input
                    value={addForm.e911_zip}
                    onChange={e => setAddForm(f => ({ ...f, e911_zip: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                    placeholder="75201"
                    maxLength={10}
                  />
                </div>
              </div>

              {/* Site Contact (optional). Service-level fields like carrier, service class,
                  transport, and voice provider live on devices/lines, not the site. */}
              <div className="space-y-3 pt-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Site Contact (optional)</p>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Contact Name</label>
                  <input
                    value={addForm.poc_name}
                    onChange={e => setAddForm(f => ({ ...f, poc_name: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                    placeholder="On-site point of contact"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Contact Phone</label>
                    <input
                      type="tel"
                      value={addForm.poc_phone}
                      onChange={e => setAddForm(f => ({ ...f, poc_phone: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                      placeholder="(555) 555-0100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Contact Email</label>
                    <input
                      type="email"
                      value={addForm.poc_email}
                      onChange={e => setAddForm(f => ({ ...f, poc_email: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                      placeholder="contact@example.com"
                    />
                  </div>
                </div>
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
                  onClick={() => { setShowAddModal(false); resetAddForm(); }}
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