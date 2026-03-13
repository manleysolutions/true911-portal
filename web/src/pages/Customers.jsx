import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/api/client";
import { Users, Plus, Loader2, Pencil, X, Search, ArrowLeft, ClipboardList, ChevronDown, ChevronUp } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const STATUS_BADGE = {
  active:    "bg-emerald-50 text-emerald-700 border-emerald-200",
  inactive:  "bg-gray-100 text-gray-600 border-gray-200",
  suspended: "bg-amber-50 text-amber-700 border-amber-200",
};

function CreateModal({ onClose, onCreated }) {
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    billing_email: "",
    billing_phone: "",
    billing_address: "",
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/customers", {
        method: "POST",
        body: JSON.stringify(form),
      });
      toast.success(`Customer "${form.name}" created`);
      onCreated();
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to create customer");
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">New Customer</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Customer Name *</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
              placeholder="e.g. R&R Technologies"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Billing Email</label>
            <input
              type="email"
              value={form.billing_email}
              onChange={(e) => setForm({ ...form, billing_email: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
              placeholder="billing@example.com"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Phone</label>
            <input
              type="text"
              value={form.billing_phone}
              onChange={(e) => setForm({ ...form, billing_phone: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
              placeholder="(555) 123-4567"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Billing Address</label>
            <textarea
              value={form.billing_address}
              onChange={(e) => setForm({ ...form, billing_address: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
              rows={2}
              placeholder="123 Main St, City, ST 12345"
            />
          </div>
          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Create Customer
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditModal({ customer, onClose, onUpdated }) {
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: customer.name,
    billing_email: customer.billing_email || "",
    billing_phone: customer.billing_phone || "",
    billing_address: customer.billing_address || "",
    status: customer.status,
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch(`/customers/${customer.id}`, {
        method: "PATCH",
        body: JSON.stringify(form),
      });
      toast.success("Customer updated");
      onUpdated();
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to update customer");
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Edit Customer</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Customer Name *</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Billing Email</label>
            <input
              type="email"
              value={form.billing_email}
              onChange={(e) => setForm({ ...form, billing_email: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Phone</label>
            <input
              type="text"
              value={form.billing_phone}
              onChange={(e) => setForm({ ...form, billing_phone: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Billing Address</label>
            <textarea
              value={form.billing_address}
              onChange={(e) => setForm({ ...form, billing_address: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
              rows={2}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Status</label>
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>
          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Pencil className="w-4 h-4" />}
              Save Changes
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function OnboardingChecklist() {
  const [open, setOpen] = useState(false);

  const steps = [
    {
      title: "1. Create Customer Record",
      items: ["Customer name", "Billing email", "Billing phone", "Billing address"],
      note: "Use the \"Add Customer\" button above.",
    },
    {
      title: "2. Run Verizon Sync (if applicable)",
      items: [
        "Go to Integration Sync > Verizon Sync",
        "Run Preview to see available devices/SIMs",
        "Run Live Sync to import SIMs and auto-create devices",
      ],
      note: "This imports ICCIDs, MSISDNs, IMEIs, and links SIMs to devices automatically.",
    },
    {
      title: "3. Import Sites via CSV",
      items: [
        "site_name — Site/location name (required)",
        "customer_name — Must match the customer record exactly",
        "address, city, state, zip — E911 address",
        "system_type — elevator_phone, fire_alarm, etc.",
        "device_serial, imei, sim_iccid, carrier — Device identifiers",
      ],
      note: "Go to Imports > Site Import. Download the template, fill it out, preview, then commit.",
    },
    {
      title: "4. Verify Device-SIM Linking",
      items: [
        "Check Devices page — each device should show its SIM",
        "Check SIM Inventory — SIMs should be in 'active' or 'inventory' status",
        "Devices from Verizon sync will have VZ- prefix IDs",
      ],
      note: "Use the device edit modal to manually link SIMs if needed.",
    },
    {
      title: "5. What Comes from Verizon vs Manual Entry",
      items: [
        "From Verizon: ICCID, MSISDN, IMEI, SIM status, carrier",
        "Manual: Site name, address, customer name, building type, system type",
        "Manual: Device-to-site assignment, E911 address, voice lines",
      ],
      note: null,
    },
  ];

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <ClipboardList className="w-4 h-4 text-red-600" />
          <span className="text-sm font-semibold text-gray-900">Verizon Customer Onboarding Checklist</span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-gray-100 pt-4 space-y-4">
          {steps.map((step, i) => (
            <div key={i}>
              <div className="text-xs font-bold text-gray-800 uppercase tracking-wide mb-1.5">{step.title}</div>
              <ul className="space-y-1 ml-4">
                {step.items.map((item, j) => (
                  <li key={j} className="text-xs text-gray-600 list-disc">{item}</li>
                ))}
              </ul>
              {step.note && <div className="text-[11px] text-gray-400 mt-1 ml-4">{step.note}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Customers() {
  const { can } = useAuth();
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState(null);

  const fetchCustomers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (statusFilter) params.set("status", statusFilter);
      const qs = params.toString() ? `?${params}` : "";
      const data = await apiFetch(`/customers${qs}`);
      setCustomers(data);
    } catch {
      toast.error("Failed to load customers");
    }
    setLoading(false);
  }, [search, statusFilter]);

  useEffect(() => { fetchCustomers(); }, [fetchCustomers]);

  const handleArchive = async (customer) => {
    if (!confirm(`Archive "${customer.name}"? This sets the customer to inactive.`)) return;
    try {
      await apiFetch(`/customers/${customer.id}`, { method: "DELETE" });
      toast.success(`"${customer.name}" archived`);
      fetchCustomers();
    } catch (err) {
      toast.error(err?.message || "Failed to archive customer");
    }
  };

  if (!can("VIEW_CUSTOMERS")) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-4xl mb-3">&#128274;</div>
            <div className="text-lg font-semibold text-gray-800">Access Restricted</div>
            <div className="text-sm text-gray-500 mt-1">This section requires Manager or Admin access.</div>
          </div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Users className="w-6 h-6 text-red-600" />
              Customers
            </h1>
            <p className="text-sm text-gray-500 mt-1">Manage customer accounts and billing contacts</p>
          </div>
          {can("MANAGE_CUSTOMERS") && (
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" /> Add Customer
            </button>
          )}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search customers..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="suspended">Suspended</option>
          </select>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-3">Customer Name</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Phone</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Updated</th>
                  {can("MANAGE_CUSTOMERS") && <th className="px-4 py-3 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center">
                      <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto" />
                    </td>
                  </tr>
                ) : customers.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                      {search || statusFilter ? "No customers match your filters" : "No customers yet. Click \"Add Customer\" to get started."}
                    </td>
                  </tr>
                ) : (
                  customers.map((c) => (
                    <tr key={c.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${STATUS_BADGE[c.status] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                          {c.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500">{c.billing_email || "\u2014"}</td>
                      <td className="px-4 py-3 text-gray-500">{c.billing_phone || "\u2014"}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {c.created_at ? new Date(c.created_at).toLocaleDateString() : "\u2014"}
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {c.updated_at ? new Date(c.updated_at).toLocaleDateString() : "\u2014"}
                      </td>
                      {can("MANAGE_CUSTOMERS") && (
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => setEditTarget(c)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-gray-300 transition-colors"
                            >
                              <Pencil className="w-3 h-3" /> Edit
                            </button>
                            {c.status === "active" && (
                              <button
                                onClick={() => handleArchive(c)}
                                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-red-600 border border-red-200 rounded-lg hover:bg-red-50 hover:border-red-300 transition-colors"
                              >
                                Archive
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Onboarding Checklist */}
      <div className="px-6 pb-6 max-w-6xl mx-auto">
        <OnboardingChecklist />
      </div>

      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onCreated={fetchCustomers} />}
      {editTarget && <EditModal customer={editTarget} onClose={() => setEditTarget(null)} onUpdated={fetchCustomers} />}
    </PageWrapper>
  );
}
