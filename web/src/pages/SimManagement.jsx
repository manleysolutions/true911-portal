import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/api/client";
import {
  Cpu, RefreshCw, Search, Play, Pause, RotateCcw, Loader2,
  AlertTriangle, Plus, X, Pencil, Trash2, Link2, Unlink, CloudDownload, Info, Building2,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import SitePickerModal from "@/components/SitePickerModal";
import { useAuth } from "@/contexts/AuthContext";
import { config } from "@/config";
import { toast } from "sonner";

const STATUS_BADGE = {
  active:     "bg-emerald-50 text-emerald-700 border-emerald-200",
  inventory:  "bg-blue-50 text-blue-700 border-blue-200",
  assigned:   "bg-purple-50 text-purple-700 border-purple-200",
  suspended:  "bg-amber-50 text-amber-700 border-amber-200",
  deactivated:"bg-gray-100 text-gray-500 border-gray-200",
  terminated: "bg-red-50 text-red-700 border-red-200",
  error:      "bg-red-50 text-red-700 border-red-200",
};

const CARRIER_BADGE = {
  verizon:  "bg-red-50 text-red-700 border-red-200",
  tmobile:  "bg-pink-50 text-pink-700 border-pink-200",
  telnyx:   "bg-indigo-50 text-indigo-700 border-indigo-200",
  att:      "bg-blue-50 text-blue-700 border-blue-200",
  teal:     "bg-teal-50 text-teal-700 border-teal-200",
};

const CARRIER_OPTIONS = [
  { value: "verizon", label: "Verizon" },
  { value: "tmobile", label: "T-Mobile" },
  { value: "att", label: "AT&T" },
  { value: "telnyx", label: "Telnyx" },
  { value: "teal", label: "Teal" },
];

const STATUS_OPTIONS = ["inventory", "assigned", "active", "suspended", "deactivated", "error"];

const SIM_ACTIONS = {
  inventory: ["activate"],
  active: ["suspend"],
  suspended: ["activate", "resume"],
};

/* ── Add/Edit SIM Modal ── */
function SimFormModal({ onClose, onSaved, editSim }) {
  const isEdit = !!editSim;
  const [form, setForm] = useState({
    iccid: editSim?.iccid || "",
    imsi: editSim?.imsi || "",
    msisdn: editSim?.msisdn || "",
    carrier: editSim?.carrier || "verizon",
    plan: editSim?.plan || "",
    status: editSim?.status || "inventory",
    notes: editSim?.notes || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!form.iccid.trim()) {
      setError("ICCID is required.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        iccid: form.iccid.trim(),
        carrier: form.carrier,
        imsi: form.imsi.trim() || undefined,
        msisdn: form.msisdn.trim() || undefined,
        plan: form.plan.trim() || undefined,
        status: form.status,
        notes: form.notes.trim() || undefined,
      };

      if (isEdit) {
        await apiFetch(`/sims/${editSim.id}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        toast.success("SIM updated");
      } else {
        await apiFetch("/sims", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        toast.success("SIM added to inventory");
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err?.message || "Failed to save SIM");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-red-600" />
            <h3 className="text-base font-bold text-gray-900">{isEdit ? "Edit SIM" : "Add SIM"}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">ICCID *</label>
            <input
              value={form.iccid}
              onChange={set("iccid")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
              placeholder="89148000..."
              maxLength={22}
              required
              disabled={isEdit}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">IMSI</label>
              <input
                value={form.imsi}
                onChange={set("imsi")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
                placeholder="311480..."
                maxLength={15}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">MSISDN</label>
              <input
                value={form.msisdn}
                onChange={set("msisdn")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
                placeholder="+12145550201"
                maxLength={15}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Carrier *</label>
              <select
                value={form.carrier}
                onChange={set("carrier")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              >
                {CARRIER_OPTIONS.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Status</label>
              <select
                value={form.status}
                onChange={set("status")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              >
                {STATUS_OPTIONS.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Plan</label>
            <input
              value={form.plan}
              onChange={set("plan")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              placeholder="e.g. ThingSpace IoT 1GB"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Notes</label>
            <textarea
              value={form.notes}
              onChange={set("notes")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent resize-none"
              rows={2}
              placeholder="Optional notes..."
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">{error}</div>
          )}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
              {saving ? "Saving..." : isEdit ? "Save Changes" : "Add SIM"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Assign SIM Modal ── */
function AssignSimModal({ sim, onClose, onAssigned }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [assigning, setAssigning] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiFetch("/devices?limit=200");
        setDevices(data.filter(d => d.status !== "decommissioned"));
      } catch { setDevices([]); }
      setLoading(false);
    })();
  }, []);

  const handleAssign = async () => {
    if (!selectedDeviceId) return;
    setAssigning(true);
    try {
      await apiFetch(`/sims/${sim.id}/assign`, {
        method: "POST",
        body: JSON.stringify({ device_id: parseInt(selectedDeviceId), slot: 1 }),
      });
      toast.success(`SIM assigned to device`);
      onAssigned();
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to assign SIM");
      setAssigning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-4">
          <Link2 className="w-4 h-4 text-red-600" />
          <h3 className="text-base font-bold text-gray-900">Assign SIM to Device</h3>
        </div>
        <div className="text-xs text-gray-500 mb-3">
          SIM: <span className="font-mono font-semibold">{sim.iccid}</span>
          {sim.msisdn && <> | {sim.msisdn}</>}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-xs text-gray-400 py-4">
            <Loader2 className="w-3 h-3 animate-spin" /> Loading devices...
          </div>
        ) : devices.length === 0 ? (
          <div className="text-xs text-gray-400 py-4">No devices available.</div>
        ) : (
          <select
            value={selectedDeviceId}
            onChange={e => setSelectedDeviceId(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-4"
          >
            <option value="">-- Select device --</option>
            {devices.map(d => (
              <option key={d.id} value={d.id}>
                {d.device_id} ({d.device_type}{d.site_id ? ` @ ${d.site_id}` : ""})
              </option>
            ))}
          </select>
        )}

        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">
            Cancel
          </button>
          <button
            onClick={handleAssign}
            disabled={!selectedDeviceId || assigning}
            className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-semibold py-2.5 px-4 rounded-xl text-sm"
          >
            {assigning ? "Assigning..." : "Assign"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Delete confirm modal ── */
function DeleteSimModal({ sim, onClose, onDeleted }) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await apiFetch(`/sims/${sim.id}`, { method: "DELETE" });
      toast.success("SIM deactivated");
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to delete SIM");
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="text-center mb-4">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-red-100 rounded-full mb-3">
            <Trash2 className="w-6 h-6 text-red-600" />
          </div>
          <h3 className="text-lg font-bold text-gray-900">Deactivate SIM?</h3>
          <p className="text-sm text-gray-500 mt-1">
            SIM <span className="font-mono font-semibold">{sim.iccid}</span> will be marked as terminated.
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">
            Cancel
          </button>
          <button onClick={handleDelete} disabled={deleting} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
            {deleting ? "Deactivating..." : "Deactivate"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Main SIM Management Page ── */
export default function SimManagement() {
  const { can } = useAuth();
  const [sims, setSims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [carrierFilter, setCarrierFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [actionLoading, setActionLoading] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editSim, setEditSim] = useState(null);
  const [deleteSim, setDeleteSim] = useState(null);
  const [assignSim, setAssignSim] = useState(null);
  const [syncing, setSyncing] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [showSitePicker, setShowSitePicker] = useState(false);

  const carrierWriteEnabled = config.featureCarrierWriteOps;

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === filtered.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map(s => s.id)));
    }
  };

  const handleBulkAssignSite = async (siteId) => {
    try {
      const result = await apiFetch("/sims/bulk-assign-site", {
        method: "POST",
        body: JSON.stringify({ sim_ids: [...selected], site_id: siteId }),
      });
      toast.success(`${result.assigned} SIM(s) assigned to site`);
      setSelected(new Set());
      setShowSitePicker(false);
      fetchSims();
    } catch (err) {
      toast.error(err?.message || "Failed to assign SIMs to site");
    }
  };

  const handleSimAction = async (simId, action) => {
    if (!carrierWriteEnabled) {
      const confirmed = confirm(
        `Carrier API is not connected.\n\nThis will update the SIM status in the True911 database only. ` +
        `The actual SIM status on the carrier network will NOT change.\n\nProceed with local status update?`
      );
      if (!confirmed) return;
    }
    setActionLoading(`${simId}-${action}`);
    try {
      const result = await apiFetch(`/sims/${simId}/${action}`, { method: "POST" });
      toast.success(result?.message || `SIM ${action} completed`);
      fetchSims();
    } catch (err) {
      toast.error(err?.message || `Failed to ${action} SIM`);
    }
    setActionLoading(null);
  };

  const handleUnassign = async (simId) => {
    setActionLoading(`${simId}-unassign`);
    try {
      await apiFetch(`/sims/${simId}/unassign`, { method: "POST" });
      toast.success("SIM unassigned from device");
      fetchSims();
    } catch (err) {
      toast.error(err?.message || "Failed to unassign SIM");
    }
    setActionLoading(null);
  };

  const handleSync = async (carrier) => {
    setSyncing(carrier);
    try {
      if (carrier === "all") {
        const results = await apiFetch("/sims/sync-all", { method: "POST" });
        const summary = results.map(r =>
          `${r.carrier}: ${r.created} created, ${r.updated} updated${r.errors.length ? ` (${r.errors.length} errors)` : ""}`
        ).join("\n");
        toast.success(`Sync complete:\n${summary}`);
      } else {
        const result = await apiFetch(`/sims/sync/${carrier}`, { method: "POST" });
        toast.success(`${carrier} sync: ${result.created} created, ${result.updated} updated`);
      }
      fetchSims();
    } catch (err) {
      toast.error(err?.message || `Sync failed`);
    }
    setSyncing(null);
  };

  const fetchSims = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (carrierFilter) params.set("carrier", carrierFilter);
      if (statusFilter) params.set("status", statusFilter);
      params.set("limit", "500");
      const data = await apiFetch(`/sims?${params}`);
      setSims(data);
    } catch {
      toast.error("Failed to load SIMs");
    }
    setLoading(false);
  }, [carrierFilter, statusFilter]);

  useEffect(() => { fetchSims(); }, [fetchSims]);

  const filtered = sims.filter(s => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (s.iccid || "").toLowerCase().includes(q) ||
      (s.msisdn || "").toLowerCase().includes(q) ||
      (s.imsi || "").toLowerCase().includes(q) ||
      (s.carrier || "").toLowerCase().includes(q) ||
      (s.plan || "").toLowerCase().includes(q) ||
      (s.notes || "").toLowerCase().includes(q)
    );
  });

  const carriers = [...new Set(sims.map(s => s.carrier).filter(Boolean))].sort();

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Cpu className="w-6 h-6 text-red-600" />
              SIM Inventory
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">{sims.length} SIMs tracked</p>
          </div>
          <div className="flex items-center gap-2">
            {can("MANAGE_SIMS") && (
              <>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors"
                >
                  <Plus className="w-4 h-4" /> Add SIM
                </button>
                {/* Sync dropdown */}
                <div className="relative group">
                  <button
                    className="flex items-center gap-1.5 px-3 py-2 border border-gray-200 hover:bg-gray-50 rounded-lg text-sm font-medium text-gray-700 transition-colors"
                    disabled={!!syncing}
                  >
                    {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <CloudDownload className="w-4 h-4" />}
                    Sync
                  </button>
                  <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-10 min-w-[160px] hidden group-hover:block">
                    <button
                      onClick={() => handleSync("verizon")}
                      className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-700"
                      disabled={!!syncing}
                    >
                      Sync Verizon
                    </button>
                    <button
                      onClick={() => handleSync("tmobile")}
                      className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-700"
                      disabled={!!syncing}
                    >
                      Sync T-Mobile
                    </button>
                    <button
                      onClick={() => handleSync("att")}
                      className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-700"
                      disabled={!!syncing}
                    >
                      Sync AT&T
                    </button>
                    <hr className="my-1 border-gray-100" />
                    <button
                      onClick={() => handleSync("all")}
                      className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-700 font-medium"
                      disabled={!!syncing}
                    >
                      Sync All Providers
                    </button>
                  </div>
                </div>
              </>
            )}
            <button onClick={fetchSims} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search ICCID, MSISDN, IMSI, carrier, plan..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <select
            value={carrierFilter}
            onChange={e => setCarrierFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
          >
            <option value="">All Carriers</option>
            {carriers.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
          >
            <option value="">All Statuses</option>
            <option value="inventory">Inventory</option>
            <option value="active">Active</option>
            <option value="assigned">Assigned</option>
            <option value="suspended">Suspended</option>
            <option value="terminated">Terminated</option>
          </select>
        </div>

        {/* Carrier sync info banner */}
        {can("MANAGE_SIMS") && !carrierWriteEnabled && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-2.5 flex items-center gap-2">
            <Info className="w-4 h-4 text-blue-600 flex-shrink-0" />
            <div>
              <span className="text-blue-800 text-xs font-semibold">Carrier live sync is not configured.</span>
              <span className="text-blue-700 text-xs"> Manual SIM inventory and assignment are still available. Add SIMs manually or configure carrier API credentials to enable live sync.</span>
            </div>
          </div>
        )}

        {/* Bulk action bar */}
        {selected.size > 0 && can("MANAGE_SIMS") && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 flex items-center justify-between">
            <span className="text-red-800 text-xs font-semibold">{selected.size} SIM(s) selected</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowSitePicker(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold"
              >
                <Building2 className="w-3.5 h-3.5" /> Assign Selected to Site
              </button>
              <button
                onClick={() => setSelected(new Set())}
                className="px-3 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-lg hover:bg-white"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {can("MANAGE_SIMS") && (
                    <th className="px-3 py-2.5 w-8">
                      <input
                        type="checkbox"
                        checked={filtered.length > 0 && selected.size === filtered.length}
                        onChange={toggleSelectAll}
                        className="rounded border-gray-300 text-red-600 focus:ring-red-500"
                      />
                    </th>
                  )}
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">ICCID</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">MSISDN</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">IMSI</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Carrier</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Plan</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Created</th>
                  {can("MANAGE_SIMS") && (
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase w-36">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center">
                      <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto" />
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center">
                      {search || carrierFilter || statusFilter ? (
                        <span className="text-gray-400">No SIMs match your filters</span>
                      ) : (
                        <div className="space-y-3">
                          <p className="text-gray-400">No SIMs in inventory yet.</p>
                          {can("MANAGE_SIMS") && (
                            <button
                              onClick={() => setShowAddModal(true)}
                              className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold"
                            >
                              <Plus className="w-4 h-4" /> Add Your First SIM
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ) : (
                  filtered.map(s => (
                    <tr key={s.id} className={`hover:bg-gray-50 ${selected.has(s.id) ? "bg-red-50/50" : ""}`}>
                      {can("MANAGE_SIMS") && (
                        <td className="px-3 py-2.5">
                          <input
                            type="checkbox"
                            checked={selected.has(s.id)}
                            onChange={() => toggleSelect(s.id)}
                            className="rounded border-gray-300 text-red-600 focus:ring-red-500"
                          />
                        </td>
                      )}
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{s.iccid}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{s.msisdn || "\u2014"}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{s.imsi || "\u2014"}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${CARRIER_BADGE[s.carrier] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                          {s.carrier}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[s.status] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                          {s.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-gray-500 text-xs">{s.plan || "\u2014"}</td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs">
                        {s.created_at ? new Date(s.created_at).toLocaleDateString() : "\u2014"}
                      </td>
                      {can("MANAGE_SIMS") && (
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1">
                            {/* Lifecycle actions */}
                            {(SIM_ACTIONS[s.status] || []).map(action => {
                              const isLoading = actionLoading === `${s.id}-${action}`;
                              const icons = { activate: Play, suspend: Pause, resume: RotateCcw };
                              const Icon = icons[action] || Play;
                              return (
                                <button
                                  key={action}
                                  onClick={() => handleSimAction(s.id, action)}
                                  disabled={!!actionLoading}
                                  className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors"
                                  title={action.charAt(0).toUpperCase() + action.slice(1)}
                                >
                                  {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
                                </button>
                              );
                            })}
                            {/* Assign */}
                            {s.status !== "terminated" && (
                              <button
                                onClick={() => setAssignSim(s)}
                                className="p-1 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600 transition-colors"
                                title="Assign to device"
                              >
                                <Link2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {/* Unassign — shown when SIM has active device link */}
                            {s.status !== "terminated" && (
                              <button
                                onClick={() => handleUnassign(s.id)}
                                disabled={actionLoading === `${s.id}-unassign`}
                                className="p-1 rounded hover:bg-amber-50 text-gray-400 hover:text-amber-600 transition-colors"
                                title="Unassign from device"
                              >
                                {actionLoading === `${s.id}-unassign`
                                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  : <Unlink className="w-3.5 h-3.5" />}
                              </button>
                            )}
                            {/* Edit */}
                            <button
                              onClick={() => setEditSim(s)}
                              className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600 transition-colors"
                              title="Edit SIM"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            {/* Delete */}
                            {s.status !== "terminated" && (
                              <button
                                onClick={() => setDeleteSim(s)}
                                className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"
                                title="Deactivate SIM"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
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

      {/* Modals */}
      {showAddModal && (
        <SimFormModal
          onClose={() => setShowAddModal(false)}
          onSaved={fetchSims}
        />
      )}
      {editSim && (
        <SimFormModal
          editSim={editSim}
          onClose={() => setEditSim(null)}
          onSaved={fetchSims}
        />
      )}
      {deleteSim && (
        <DeleteSimModal
          sim={deleteSim}
          onClose={() => setDeleteSim(null)}
          onDeleted={fetchSims}
        />
      )}
      {assignSim && (
        <AssignSimModal
          sim={assignSim}
          onClose={() => setAssignSim(null)}
          onAssigned={fetchSims}
        />
      )}
      {showSitePicker && (
        <SitePickerModal
          title="Assign SIMs to Site"
          count={selected.size}
          entityLabel="SIM(s)"
          onClose={() => setShowSitePicker(false)}
          onConfirm={handleBulkAssignSite}
        />
      )}
    </PageWrapper>
  );
}
