import { useState, useEffect, useCallback } from "react";
import { Provider } from "@/api/entities";
import { useAuth } from "@/contexts/AuthContext";
import { Plug, Search, RefreshCw, Plus, X, Pencil, Trash2 } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { toast } from "sonner";

const TYPE_OPTIONS = ["telnyx", "bandwidth", "tmobile", "vola", "other"];

const ENABLED_BADGE = {
  true: "bg-emerald-50 text-emerald-700 border-emerald-200",
  false: "bg-gray-100 text-gray-500 border-gray-200",
};

function timeSince(iso) {
  if (!iso) return "\u2014";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/* ── Create / Edit modal ── */
function ProviderFormModal({ provider, onClose, onSaved }) {
  const isEdit = !!provider;
  const [form, setForm] = useState({
    provider_id: provider?.provider_id || "",
    provider_type: provider?.provider_type || "telnyx",
    display_name: provider?.display_name || "",
    api_key_ref: provider?.api_key_ref || "",
    enabled: provider?.enabled ?? false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (field) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm(f => ({ ...f, [field]: val }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      if (isEdit) {
        await Provider.update(provider.id, {
          provider_type: form.provider_type,
          display_name: form.display_name,
          api_key_ref: form.api_key_ref || undefined,
          enabled: form.enabled,
        });
        toast.success("Provider updated.");
      } else {
        await Provider.create({
          provider_id: form.provider_id,
          provider_type: form.provider_type,
          display_name: form.display_name,
          api_key_ref: form.api_key_ref || undefined,
          enabled: form.enabled,
        });
        toast.success("Provider created.");
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err?.message || `Failed to ${isEdit ? "update" : "create"} provider.`);
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Plug className="w-4 h-4 text-red-600" />
            <h3 className="text-base font-bold text-gray-900">{isEdit ? "Edit Provider" : "Add Provider"}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Provider ID *</label>
              <input
                value={form.provider_id}
                onChange={set("provider_id")}
                required
                disabled={isEdit}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
                placeholder="e.g. telnyx-prod"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Type *</label>
              <select
                value={form.provider_type}
                onChange={set("provider_type")}
                required
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              >
                {TYPE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Display Name *</label>
            <input
              value={form.display_name}
              onChange={set("display_name")}
              required
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              placeholder="e.g. Telnyx (Production)"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">API Key Reference</label>
            <input
              value={form.api_key_ref}
              onChange={set("api_key_ref")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              placeholder="Vault path or env-var name"
            />
          </div>

          <div className="flex items-center gap-2.5">
            <input
              type="checkbox"
              id="provider-enabled"
              checked={form.enabled}
              onChange={set("enabled")}
              className="w-4 h-4 rounded border-gray-300 text-red-600 focus:ring-red-500"
            />
            <label htmlFor="provider-enabled" className="text-sm text-gray-700 font-medium">Enabled</label>
          </div>

          {error && <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">{error}</div>}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">Cancel</button>
            <button type="submit" disabled={saving} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
              {saving ? "Saving..." : isEdit ? "Update" : "Add Provider"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Delete confirmation modal ── */
function DeleteConfirmModal({ provider, onClose, onDeleted }) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await Provider.delete(provider.id);
      toast.success("Provider deleted.");
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to delete provider.");
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <h3 className="text-base font-bold text-gray-900 mb-2">Delete Provider</h3>
        <p className="text-sm text-gray-600 mb-5">
          Are you sure you want to delete <span className="font-semibold">{provider.display_name}</span>? This cannot be undone.
        </p>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">Cancel</button>
          <button onClick={handleDelete} disabled={deleting} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
            {deleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Main Providers page ── */
export default function Providers() {
  const { can } = useAuth();
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const fetchData = useCallback(async () => {
    const data = await Provider.list("-created_at", 200);
    setProviders(data);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const filtered = providers.filter(p => {
    if (typeFilter && p.provider_type !== typeFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        p.provider_id.toLowerCase().includes(q) ||
        p.display_name.toLowerCase().includes(q) ||
        p.provider_type.toLowerCase().includes(q) ||
        (p.api_key_ref || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  const uniqueTypes = [...new Set(providers.map(p => p.provider_type))].sort();

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
            <h1 className="text-2xl font-bold text-gray-900">Providers</h1>
            <p className="text-sm text-gray-500 mt-0.5">{providers.length} provider integration{providers.length !== 1 ? "s" : ""}</p>
          </div>
          <div className="flex items-center gap-2">
            {can("MANAGE_PROVIDERS") && (
              <button
                onClick={() => { setEditing(null); setShowForm(true); }}
                className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors"
              >
                <Plus className="w-4 h-4" /> Add Provider
              </button>
            )}
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search providers..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          {uniqueTypes.length > 1 && (
            <select
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
            >
              <option value="">All Types</option>
              {uniqueTypes.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Plug className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <div className="text-sm font-semibold text-gray-500">
                {providers.length === 0 ? "No providers yet" : "No providers match your filters"}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {providers.length === 0 ? "Click \"Add Provider\" to connect your first integration." : "Try adjusting your search or filter."}
              </div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Provider ID</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Name</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Type</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">API Key Ref</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Enabled</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Created</th>
                  {can("MANAGE_PROVIDERS") && (
                    <th className="text-right px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase w-24">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(p => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{p.provider_id}</td>
                    <td className="px-4 py-2.5 text-gray-800 font-medium">{p.display_name}</td>
                    <td className="px-4 py-2.5 text-gray-600 capitalize">{p.provider_type}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{p.api_key_ref || "\u2014"}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${ENABLED_BADGE[p.enabled]}`}>
                        {p.enabled ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">{timeSince(p.created_at)}</td>
                    {can("MANAGE_PROVIDERS") && (
                      <td className="px-4 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => { setEditing(p); setShowForm(true); }}
                            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                            title="Edit"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => setDeleting(p)}
                            className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showForm && (
        <ProviderFormModal
          provider={editing}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={fetchData}
        />
      )}

      {deleting && (
        <DeleteConfirmModal
          provider={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={fetchData}
        />
      )}
    </PageWrapper>
  );
}
