import { useState, useEffect, useCallback } from "react";
import { Line, Site } from "@/api/entities";
import { Phone, Search, RefreshCw, Plus, X, Pencil, Trash2 } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { toast } from "sonner";

const STATUS_BADGE = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  provisioning: "bg-blue-50 text-blue-700 border-blue-200",
  suspended: "bg-amber-50 text-amber-700 border-amber-200",
  disconnected: "bg-red-50 text-red-700 border-red-200",
};

const E911_BADGE = {
  validated: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  none: "bg-gray-100 text-gray-500 border-gray-200",
};

/* ── Line form modal (create or edit) ── */
function LineFormModal({ onClose, onSaved, sites, editLine }) {
  const isEdit = !!editLine;
  const [form, setForm] = useState({
    line_id: editLine?.line_id || "",
    provider: editLine?.provider || "telnyx",
    did: editLine?.did || "",
    sip_uri: editLine?.sip_uri || "",
    protocol: editLine?.protocol || "SIP",
    site_id: editLine?.site_id || "",
    device_id: editLine?.device_id || "",
    status: editLine?.status || "provisioning",
    e911_status: editLine?.e911_status || "none",
    e911_street: editLine?.e911_street || "",
    e911_city: editLine?.e911_city || "",
    e911_state: editLine?.e911_state || "",
    e911_zip: editLine?.e911_zip || "",
    notes: editLine?.notes || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      if (isEdit) {
        await Line.update(editLine.id, {
          provider: form.provider,
          did: form.did || undefined,
          sip_uri: form.sip_uri || undefined,
          protocol: form.protocol,
          site_id: form.site_id || undefined,
          device_id: form.device_id || undefined,
          status: form.status,
          e911_status: form.e911_status,
          e911_street: form.e911_street || undefined,
          e911_city: form.e911_city || undefined,
          e911_state: form.e911_state || undefined,
          e911_zip: form.e911_zip || undefined,
          notes: form.notes || undefined,
        });
        toast.success(`Line ${form.line_id} updated`);
        onSaved();
        onClose();
      } else {
        await Line.create({
          ...form,
          sip_uri: form.sip_uri || undefined,
          site_id: form.site_id || undefined,
          device_id: form.device_id || undefined,
          e911_street: form.e911_street || undefined,
          e911_city: form.e911_city || undefined,
          e911_state: form.e911_state || undefined,
          e911_zip: form.e911_zip || undefined,
          notes: form.notes || undefined,
        });
        toast.success("Line created");
        onSaved();
        onClose();
      }
    } catch (err) {
      setError(err?.message || "Failed to save line.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Phone className="w-4 h-4 text-red-600" />
            <h3 className="text-base font-bold text-gray-900">{isEdit ? "Edit Voice Line" : "Add Voice Line"}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Line ID *</label>
              <input value={form.line_id} onChange={set("line_id")} required disabled={isEdit}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent disabled:bg-gray-50"
                placeholder="e.g. LINE-001" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">DID / Phone *</label>
              <input value={form.did} onChange={set("did")} required
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="+12145550101" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Provider</label>
              <select value={form.provider} onChange={set("provider")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                <option value="telnyx">Telnyx</option>
                <option value="tmobile">T-Mobile</option>
                <option value="bandwidth">Bandwidth</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Protocol</label>
              <select value={form.protocol} onChange={set("protocol")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                <option value="SIP">SIP</option>
                <option value="POTS">POTS</option>
                <option value="cellular">Cellular</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Site</label>
              <select value={form.site_id} onChange={set("site_id")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                <option value="">-- None --</option>
                {sites.map(s => <option key={s.site_id} value={s.site_id}>{s.site_name}</option>)}
              </select>
            </div>
          </div>

          {isEdit && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Status</label>
                <select value={form.status} onChange={set("status")}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                  <option value="provisioning">Provisioning</option>
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                  <option value="disconnected">Disconnected</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">E911 Status</label>
                <select value={form.e911_status} onChange={set("e911_status")}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                  <option value="none">None</option>
                  <option value="pending">Pending</option>
                  <option value="validated">Validated</option>
                  <option value="failed">Failed</option>
                </select>
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">SIP URI</label>
            <input value={form.sip_uri} onChange={set("sip_uri")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              placeholder="sip:2145550101@sip.telnyx.com" />
          </div>

          <div className="border-t border-gray-100 pt-4">
            <div className="text-xs font-semibold text-gray-600 mb-2 uppercase tracking-wide">E911 Address</div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <input value={form.e911_street} onChange={set("e911_street")} placeholder="Street"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent" />
              </div>
              <input value={form.e911_city} onChange={set("e911_city")} placeholder="City"
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent" />
              <div className="flex gap-2">
                <input value={form.e911_state} onChange={set("e911_state")} placeholder="ST" maxLength={2}
                  className="w-20 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent uppercase" />
                <input value={form.e911_zip} onChange={set("e911_zip")} placeholder="ZIP"
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent" />
              </div>
            </div>
          </div>

          {error && <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">{error}</div>}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">Cancel</button>
            <button type="submit" disabled={saving} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
              {saving ? "Saving..." : isEdit ? "Save Changes" : "Add Line"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Confirm delete modal ── */
function ConfirmDeleteLineModal({ line, onClose, onConfirm }) {
  const [deleting, setDeleting] = useState(false);
  const handleConfirm = async () => {
    setDeleting(true);
    await onConfirm();
  };
  return (
    <div className="fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="text-center mb-4">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-red-100 rounded-full mb-3">
            <Trash2 className="w-6 h-6 text-red-600" />
          </div>
          <h3 className="text-lg font-bold text-gray-900">Delete Line?</h3>
          <p className="text-sm text-gray-500 mt-1">
            Line <span className="font-mono font-semibold">{line.line_id}</span> ({line.did || "no DID"}) will be permanently deleted.
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">Cancel</button>
          <button onClick={handleConfirm} disabled={deleting} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
            {deleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Lines() {
  const [lines, setLines] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [editLine, setEditLine] = useState(null);
  const [deleteLine, setDeleteLine] = useState(null);

  const fetchData = useCallback(async () => {
    const [lineData, siteData] = await Promise.all([
      Line.list("-created_at", 200),
      Site.list("-last_checkin", 200),
    ]);
    setLines(lineData);
    setSites(siteData);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const siteMap = Object.fromEntries(sites.map(s => [s.site_id, s]));

  const handleDelete = async (line) => {
    try {
      await Line.delete(line.id);
      toast.success(`Line ${line.line_id} deleted`);
      setDeleteLine(null);
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to delete line.");
      setDeleteLine(null);
    }
  };

  const filtered = lines.filter(l => {
    if (statusFilter && l.status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      const site = siteMap[l.site_id];
      return (
        l.line_id.toLowerCase().includes(q) ||
        (l.did || "").toLowerCase().includes(q) ||
        (l.provider || "").toLowerCase().includes(q) ||
        (site?.site_name || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Lines</h1>
            <p className="text-sm text-gray-500 mt-0.5">{lines.length} voice lines / DIDs</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowAdd(true)}
              className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors">
              <Plus className="w-4 h-4" /> Add Line
            </button>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search lines, DID, provider, site..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="provisioning">Provisioning</option>
            <option value="suspended">Suspended</option>
            <option value="disconnected">Disconnected</option>
          </select>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Phone className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <div className="text-sm font-semibold text-gray-500">
                {lines.length === 0 ? "No voice lines yet" : "No lines match your filters"}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {lines.length === 0 ? "Click \"Add Line\" to provision your first voice line." : "Try adjusting your search or filter."}
              </div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Line ID</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">DID</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Site</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Provider</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Protocol</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">E911</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase w-20">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(l => {
                  const site = siteMap[l.site_id];
                  return (
                    <tr key={l.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{l.line_id}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-800 font-semibold">{l.did || "---"}</td>
                      <td className="px-4 py-2.5 text-gray-800">{site?.site_name || l.site_id || "---"}</td>
                      <td className="px-4 py-2.5 text-gray-600 capitalize">{l.provider}</td>
                      <td className="px-4 py-2.5 text-gray-600">{l.protocol}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[l.status] || STATUS_BADGE.disconnected}`}>
                          {l.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${E911_BADGE[l.e911_status] || E911_BADGE.none}`}>
                          {l.e911_status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => setEditLine(l)}
                            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600"
                            title="Edit line"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => setDeleteLine(l)}
                            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-red-600"
                            title="Delete line"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showAdd && (
        <LineFormModal
          sites={sites}
          onClose={() => setShowAdd(false)}
          onSaved={fetchData}
        />
      )}

      {editLine && (
        <LineFormModal
          sites={sites}
          editLine={editLine}
          onClose={() => setEditLine(null)}
          onSaved={fetchData}
        />
      )}

      {deleteLine && (
        <ConfirmDeleteLineModal
          line={deleteLine}
          onClose={() => setDeleteLine(null)}
          onConfirm={() => handleDelete(deleteLine)}
        />
      )}
    </PageWrapper>
  );
}
