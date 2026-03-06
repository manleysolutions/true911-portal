import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetch, setActAsTenant, getActAsTenant } from "@/api/client";
import { Building2, Plus, Loader2, Pencil, ChevronDown, ArrowLeft, Globe, Shield } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { createPageUrl } from "@/utils";

export default function AdminTenants() {
  const { can, isSuperAdmin } = useAuth();
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);

  // Tenant switcher state
  const [activeTenant, setActiveTenant] = useState(getActAsTenant() || "");

  const fetchTenants = useCallback(async () => {
    try {
      const data = await apiFetch("/admin/tenants");
      setTenants(data);
    } catch { /* silently fail */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchTenants(); }, [fetchTenants]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/admin/tenants", {
        method: "POST",
        body: JSON.stringify({ tenant_id: newId, name: newName }),
      });
      toast.success(`Tenant "${newId}" created`);
      setNewId(""); setNewName(""); setShowCreate(false);
      fetchTenants();
    } catch (err) {
      toast.error(err?.message || "Failed to create tenant");
    }
    setSaving(false);
  };

  const handleSaveEdit = async (tenantId) => {
    setSaving(true);
    try {
      await apiFetch(`/admin/tenants/${tenantId}`, {
        method: "PATCH",
        body: JSON.stringify({ name: editName }),
      });
      toast.success("Tenant updated");
      setEditingId(null);
      fetchTenants();
    } catch (err) {
      toast.error(err?.message || "Failed to update tenant");
    }
    setSaving(false);
  };

  const handleTenantSwitch = (tenantId) => {
    setActiveTenant(tenantId);
    setActAsTenant(tenantId || null);
    toast.success(tenantId ? `Acting as tenant: ${tenantId}` : "Switched back to own tenant");
  };

  if (!can("VIEW_ADMIN")) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-4xl mb-3">&#128274;</div>
            <div className="text-lg font-semibold text-gray-800">Admin Access Required</div>
            <div className="text-sm text-gray-500 mt-1">This section is only accessible to Admin and SuperAdmin users.</div>
          </div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto">
        <Link to={createPageUrl("Admin")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 mb-4">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Admin
        </Link>

        <div className="flex items-center gap-2 mb-1">
          <Building2 className="w-5 h-5 text-violet-600" />
          <h1 className="text-2xl font-bold text-gray-900">Tenant Management</h1>
          {isSuperAdmin && (
            <span className="text-xs font-bold px-2 py-0.5 rounded-full border bg-purple-100 text-purple-700 border-purple-200">
              SuperAdmin
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 mb-6">Create and manage organization tenants.</p>

        {/* SuperAdmin tenant switcher */}
        {isSuperAdmin && tenants.length > 0 && (
          <div className="bg-purple-50 border border-purple-200 rounded-xl p-4 mb-6">
            <div className="flex items-center gap-3">
              <Shield className="w-4 h-4 text-purple-600" />
              <span className="text-sm font-medium text-purple-800">Act as Tenant:</span>
              <div className="relative">
                <select
                  value={activeTenant}
                  onChange={e => handleTenantSwitch(e.target.value)}
                  className="appearance-none pl-3 pr-7 py-1.5 text-xs font-medium border border-purple-300 bg-white text-purple-800 rounded-lg cursor-pointer focus:outline-none focus:ring-1 focus:ring-purple-400"
                >
                  <option value="">My Tenant (default)</option>
                  {tenants.map(t => (
                    <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
                  ))}
                </select>
                <ChevronDown className="w-3 h-3 absolute right-2 top-1/2 -translate-y-1/2 text-purple-400 pointer-events-none" />
              </div>
            </div>
          </div>
        )}

        {/* Tenant list */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
            <Globe className="w-4 h-4 text-violet-600" />
            <h2 className="font-semibold text-gray-900 text-sm">Tenants</h2>
            <span className="text-xs text-gray-400 ml-auto mr-3">{tenants.length} tenants</span>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded-lg transition-colors"
            >
              <Plus className="w-3 h-3" /> Create Tenant
            </button>
          </div>

          {showCreate && (
            <form onSubmit={handleCreate} className="px-5 py-4 bg-gray-50 border-b border-gray-200 flex items-end gap-3">
              <div className="flex-1">
                <label className="text-xs font-medium text-gray-600 mb-1 block">Tenant ID (slug)</label>
                <input
                  type="text"
                  required
                  value={newId}
                  onChange={e => setNewId(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500 font-mono"
                  placeholder="e.g. acme-corp"
                />
              </div>
              <div className="flex-1">
                <label className="text-xs font-medium text-gray-600 mb-1 block">Display Name</label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
                  placeholder="e.g. Acme Corporation"
                />
              </div>
              <button type="submit" disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-xs font-medium rounded-lg transition-colors whitespace-nowrap">
                {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                Create
              </button>
              <button type="button" onClick={() => { setShowCreate(false); setNewId(""); setNewName(""); }} className="px-3 py-2 text-xs font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors">
                Cancel
              </button>
            </form>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Tenant ID</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Name</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Type</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Created</th>
                  <th className="text-right px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {tenants.map(t => (
                  <tr key={t.tenant_id} className="hover:bg-gray-50">
                    <td className="px-5 py-3 font-mono text-xs text-gray-700">{t.tenant_id}</td>
                    <td className="px-5 py-3">
                      {editingId === t.tenant_id ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={editName}
                            onChange={e => setEditName(e.target.value)}
                            className="px-2 py-1 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
                            autoFocus
                          />
                          <button onClick={() => handleSaveEdit(t.tenant_id)} disabled={saving} className="px-2 py-1 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700 disabled:opacity-60">
                            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : "Save"}
                          </button>
                          <button onClick={() => setEditingId(null)} className="px-2 py-1 text-xs text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100">Cancel</button>
                        </div>
                      ) : (
                        <span className="text-gray-900">{t.name}</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-500">{t.org_type || "customer"}</td>
                    <td className="px-5 py-3 text-xs text-gray-400">
                      {t.created_at ? new Date(t.created_at).toLocaleDateString() : "\u2014"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {editingId !== t.tenant_id && (
                        <button
                          onClick={() => { setEditingId(t.tenant_id); setEditName(t.name); }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-gray-300 transition-colors"
                        >
                          <Pencil className="w-3 h-3" /> Edit
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}
