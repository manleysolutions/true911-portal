import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetch, setActAsTenant, getActAsTenant } from "@/api/client";
import { Building2, Plus, Loader2, Pencil, ChevronDown, ArrowLeft, Globe, Shield, Wand2, Check, AlertTriangle } from "lucide-react";
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

  // Auto-provision state
  const [provisionPreview, setProvisionPreview] = useState(null);
  const [provisionLoading, setProvisionLoading] = useState(false);
  const [provisionCommitting, setProvisionCommitting] = useState(false);
  const [provisionResult, setProvisionResult] = useState(null);

  // Cleanup state
  const [cleanupPreview, setCleanupPreview] = useState(null);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [cleanupTarget, setCleanupTarget] = useState("");

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

  const handleProvisionPreview = async () => {
    setProvisionLoading(true);
    setProvisionResult(null);
    try {
      const data = await apiFetch("/admin/auto-provision/preview", { method: "POST" });
      setProvisionPreview(data);
    } catch (err) {
      toast.error(err?.message || "Failed to load preview");
    }
    setProvisionLoading(false);
  };

  const handleProvisionCommit = async () => {
    setProvisionCommitting(true);
    try {
      const data = await apiFetch("/admin/auto-provision/commit", {
        method: "POST",
        body: JSON.stringify({ commit: true }),
      });
      setProvisionResult(data);
      setProvisionPreview(null);
      toast.success(`Created ${data.tenants_created} tenants, reassigned ${data.sites_reassigned} sites`);
      fetchTenants();
    } catch (err) {
      toast.error(err?.message || "Failed to provision tenants");
    }
    setProvisionCommitting(false);
  };

  const handleCleanupPreview = async () => {
    if (!cleanupTarget) {
      toast.error("Select a target tenant first");
      return;
    }
    setCleanupLoading(true);
    try {
      const data = await apiFetch(`/admin/tenants/cleanup?target_tenant_id=${cleanupTarget}&dry_run=true`, { method: "POST" });
      setCleanupPreview(data);
    } catch (err) {
      toast.error(err?.message || "Failed to preview cleanup");
    }
    setCleanupLoading(false);
  };

  const handleCleanupCommit = async () => {
    setCleanupLoading(true);
    try {
      const data = await apiFetch(`/admin/tenants/cleanup?target_tenant_id=${cleanupTarget}&dry_run=false`, { method: "POST" });
      toast.success(`Deleted ${data.junk_tenant_count} junk tenants, moved ${data.sites_to_move} sites`);
      setCleanupPreview(null);
      fetchTenants();
    } catch (err) {
      toast.error(err?.message || "Failed to cleanup tenants");
    }
    setCleanupLoading(false);
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

        {/* Auto-Provision Section */}
        {isSuperAdmin && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
              <Wand2 className="w-4 h-4 text-amber-600" />
              <h2 className="font-semibold text-gray-900 text-sm">Auto-Provision Tenants from Sites</h2>
              <span className="text-xs text-gray-400 ml-auto mr-3">Group sites by customer name into tenants</span>
              {!provisionPreview && !provisionResult && (
                <button
                  onClick={handleProvisionPreview}
                  disabled={provisionLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-60 text-white text-xs font-medium rounded-lg transition-colors"
                >
                  {provisionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                  Preview
                </button>
              )}
            </div>

            {provisionPreview && (
              <div className="p-5">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                  <div className="bg-gray-50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-gray-900">{provisionPreview.total_sites}</div>
                    <div className="text-[11px] text-gray-500 uppercase font-medium">Total Sites</div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-gray-900">{provisionPreview.unique_customers}</div>
                    <div className="text-[11px] text-gray-500 uppercase font-medium">Unique Customers</div>
                  </div>
                  <div className="bg-emerald-50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-emerald-700">{provisionPreview.tenants_to_create}</div>
                    <div className="text-[11px] text-emerald-600 uppercase font-medium">Tenants to Create</div>
                  </div>
                  <div className="bg-blue-50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-blue-700">{provisionPreview.tenants_already_exist}</div>
                    <div className="text-[11px] text-blue-600 uppercase font-medium">Already Exist</div>
                  </div>
                </div>

                <div className="max-h-[400px] overflow-y-auto border border-gray-200 rounded-lg">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-gray-50">
                      <tr className="border-b border-gray-200">
                        <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500">Customer Name</th>
                        <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500">Tenant ID</th>
                        <th className="text-center px-4 py-2 text-xs font-semibold text-gray-500">Sites</th>
                        <th className="text-center px-4 py-2 text-xs font-semibold text-gray-500">Devices</th>
                        <th className="text-center px-4 py-2 text-xs font-semibold text-gray-500">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {provisionPreview.groups.map(g => (
                        <tr key={g.proposed_tenant_id} className="hover:bg-gray-50">
                          <td className="px-4 py-2 font-medium text-gray-900">{g.customer_name}</td>
                          <td className="px-4 py-2 font-mono text-xs text-gray-600">{g.proposed_tenant_id}</td>
                          <td className="px-4 py-2 text-center text-gray-700">{g.site_count}</td>
                          <td className="px-4 py-2 text-center text-gray-700">{g.device_count}</td>
                          <td className="px-4 py-2 text-center">
                            {g.existing_tenant ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full">
                                <Check className="w-3 h-3" /> Exists
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
                                <Plus className="w-3 h-3" /> New
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center gap-3 mt-4">
                  <button
                    onClick={handleProvisionCommit}
                    disabled={provisionCommitting}
                    className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    {provisionCommitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                    Create Tenants & Reassign Sites
                  </button>
                  <button
                    onClick={() => setProvisionPreview(null)}
                    className="px-4 py-2 text-sm font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    Cancel
                  </button>
                  <span className="text-xs text-gray-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-amber-500" />
                    This will create tenants and move sites + devices to them
                  </span>
                </div>
              </div>
            )}

            {provisionResult && (
              <div className="p-5">
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mb-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Check className="w-5 h-5 text-emerald-600" />
                    <span className="text-sm font-semibold text-emerald-800">Auto-Provisioning Complete</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                    <div>
                      <div className="text-xl font-bold text-emerald-700">{provisionResult.tenants_created}</div>
                      <div className="text-[11px] text-emerald-600">Tenants Created</div>
                    </div>
                    <div>
                      <div className="text-xl font-bold text-emerald-700">{provisionResult.sites_reassigned}</div>
                      <div className="text-[11px] text-emerald-600">Sites Moved</div>
                    </div>
                    <div>
                      <div className="text-xl font-bold text-emerald-700">{provisionResult.devices_reassigned}</div>
                      <div className="text-[11px] text-emerald-600">Devices Moved</div>
                    </div>
                    <div>
                      <div className="text-xl font-bold text-gray-500">{provisionResult.skipped_empty_name}</div>
                      <div className="text-[11px] text-gray-500">Skipped (no name)</div>
                    </div>
                  </div>
                </div>

                {provisionResult.details.length > 0 && (
                  <div className="max-h-[300px] overflow-y-auto border border-gray-200 rounded-lg">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-gray-50">
                        <tr className="border-b border-gray-200">
                          <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500">Customer</th>
                          <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500">Tenant ID</th>
                          <th className="text-center px-4 py-2 text-xs font-semibold text-gray-500">Sites</th>
                          <th className="text-center px-4 py-2 text-xs font-semibold text-gray-500">Devices Moved</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {provisionResult.details.map(d => (
                          <tr key={d.tenant_id} className="hover:bg-gray-50">
                            <td className="px-4 py-2 text-gray-900">{d.customer_name}</td>
                            <td className="px-4 py-2 font-mono text-xs text-gray-600">{d.tenant_id}</td>
                            <td className="px-4 py-2 text-center">{d.sites}</td>
                            <td className="px-4 py-2 text-center">{d.devices_moved}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <button
                  onClick={() => setProvisionResult(null)}
                  className="mt-3 px-3 py-1.5 text-xs font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  Dismiss
                </button>
              </div>
            )}
          </div>
        )}

        {/* Cleanup Junk Tenants */}
        {isSuperAdmin && tenants.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <h2 className="font-semibold text-gray-900 text-sm">Cleanup Junk Tenants</h2>
              <span className="text-xs text-gray-400 ml-auto mr-3">Remove numeric/device-name tenants and move sites back</span>
            </div>
            <div className="px-5 py-4 flex items-end gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Move orphaned sites to:</label>
                <select
                  value={cleanupTarget}
                  onChange={e => setCleanupTarget(e.target.value)}
                  className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
                >
                  <option value="">Select target tenant...</option>
                  {tenants.map(t => (
                    <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleCleanupPreview}
                disabled={cleanupLoading || !cleanupTarget}
                className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-xs font-medium rounded-lg transition-colors"
              >
                {cleanupLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <AlertTriangle className="w-3 h-3" />}
                Preview Cleanup
              </button>
            </div>
            {cleanupPreview && (
              <div className="px-5 pb-5">
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-3">
                  <p className="text-sm text-red-800 font-medium mb-2">
                    Found {cleanupPreview.junk_tenant_count} junk tenants with {cleanupPreview.sites_to_move} sites and {cleanupPreview.devices_to_move} devices to move.
                  </p>
                  <div className="max-h-[200px] overflow-y-auto text-xs text-red-700 space-y-0.5">
                    {cleanupPreview.junk_tenants.map(jt => (
                      <div key={jt.tenant_id} className="font-mono">
                        {jt.tenant_id} — {jt.name}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleCleanupCommit}
                    disabled={cleanupLoading}
                    className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    {cleanupLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                    Delete Junk Tenants & Move Sites
                  </button>
                  <button
                    onClick={() => setCleanupPreview(null)}
                    className="px-4 py-2 text-sm font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
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
