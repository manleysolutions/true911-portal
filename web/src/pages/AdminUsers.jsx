import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "@/api/client";
import {
  Users, Plus, Loader2, ChevronDown, ArrowLeft, Shield, KeyRound,
  Trash2, RefreshCw, Eye, EyeOff, X, Copy, Check, Mail, Link as LinkIcon,
  Pencil, Save,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { createPageUrl } from "@/utils";

export default function AdminUsers() {
  const { can, user: currentUser, isSuperAdmin } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [resetTarget, setResetTarget] = useState(null);
  const [resendResult, setResendResult] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [tenantFilter, setTenantFilter] = useState("");

  const fetchUsers = useCallback(async () => {
    try {
      const qs = isSuperAdmin && tenantFilter ? `?tenant_id=${tenantFilter}` : "";
      const fetches = [apiFetch(`/admin/users${qs}`)];
      if (isSuperAdmin) fetches.push(apiFetch("/admin/tenants").catch(() => []));
      const [userData, tenantData] = await Promise.all(fetches);
      setUsers(userData);
      if (tenantData) setTenants(tenantData);
    } catch { /* silently fail */ }
    setLoading(false);
  }, [isSuperAdmin, tenantFilter]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleRoleChange = async (userId, newRole) => {
    setUpdatingId(userId);
    try {
      await apiFetch(`/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole }),
      });
      toast.success("User role updated");
      fetchUsers();
    } catch (err) {
      toast.error(err?.message || "Failed to update role");
    }
    setUpdatingId(null);
  };

  const handleToggleActive = async (userId, currentlyActive) => {
    setUpdatingId(userId);
    try {
      await apiFetch(`/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !currentlyActive }),
      });
      toast.success(currentlyActive ? "User disabled" : "User enabled");
      fetchUsers();
    } catch (err) {
      toast.error(err?.message || "Failed to update user status");
    }
    setUpdatingId(null);
  };

  const handleDeleteUser = async (userId, userName) => {
    if (!window.confirm(`Delete user "${userName}"? This action cannot be undone.`)) return;
    setUpdatingId(userId);
    try {
      await apiFetch(`/admin/users/${userId}`, { method: "DELETE" });
      toast.success(`User "${userName}" deleted`);
      fetchUsers();
    } catch (err) {
      toast.error(err?.message || "Failed to delete user");
    }
    setUpdatingId(null);
  };

  const handleResendInvite = async (userId) => {
    setUpdatingId(userId);
    try {
      const data = await apiFetch(`/admin/users/${userId}/resend-invite`, { method: "POST" });
      setResendResult({ invite_url: data.invite_url, email: data.email });
      fetchUsers();
    } catch (err) {
      toast.error(err?.message || "Failed to resend invite");
    }
    setUpdatingId(null);
  };

  const ROLE_BADGE = {
    SuperAdmin: "bg-purple-50 text-purple-700 border-purple-200",
    Admin: "bg-red-50 text-red-700 border-red-200",
    Manager: "bg-blue-50 text-blue-700 border-blue-200",
    DataEntry: "bg-amber-50 text-amber-700 border-amber-200",
    User: "bg-gray-100 text-gray-600 border-gray-200",
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
          <Users className="w-5 h-5 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
          {isSuperAdmin && (
            <span className="text-xs font-bold px-2 py-0.5 rounded-full border bg-purple-100 text-purple-700 border-purple-200">
              SuperAdmin
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 mb-6">Create users, manage roles, and send invitations.</p>

        {/* Tenant Filter */}
        {isSuperAdmin && tenants.length > 0 && (
          <div className="bg-purple-50 border border-purple-200 rounded-xl p-4 mb-4 flex items-center gap-3">
            <Shield className="w-4 h-4 text-purple-600 flex-shrink-0" />
            <span className="text-sm font-medium text-purple-800">Tenant Filter</span>
            <div className="relative">
              <select
                value={tenantFilter}
                onChange={e => setTenantFilter(e.target.value)}
                className="appearance-none pl-3 pr-7 py-1.5 text-xs font-medium border border-purple-300 bg-white text-purple-800 rounded-lg cursor-pointer focus:outline-none focus:ring-1 focus:ring-purple-400"
              >
                <option value="">All Tenants</option>
                {tenants.map(t => (
                  <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
                ))}
              </select>
              <ChevronDown className="w-3 h-3 absolute right-2 top-1/2 -translate-y-1/2 text-purple-400 pointer-events-none" />
            </div>
            {tenantFilter && (
              <button onClick={() => setTenantFilter("")} className="text-xs text-purple-600 hover:text-purple-800 underline">
                Clear
              </button>
            )}
          </div>
        )}

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
          <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
            <Users className="w-4 h-4 text-indigo-600" />
            <h2 className="font-semibold text-gray-900 text-sm">Users</h2>
            <span className="text-xs text-gray-400 ml-auto mr-3">{users.length} users{tenantFilter ? ` in ${tenantFilter}` : ""}</span>
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded-lg transition-colors"
            >
              <Plus className="w-3 h-3" /> Create User
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Name</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Email</th>
                  {isSuperAdmin && <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Tenant</th>}
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Role</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Joined</th>
                  <th className="text-right px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map(u => (
                  <tr key={u.id} className={`hover:bg-gray-50 ${!u.is_active ? "opacity-50" : ""}`}>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-[11px] font-bold text-gray-600">
                          {u.name?.charAt(0)?.toUpperCase() || "?"}
                        </div>
                        <span className="font-medium text-gray-900">{u.name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-gray-600 text-xs font-mono">{u.email}</td>
                    {isSuperAdmin && (
                      <td className="px-5 py-3 text-xs text-gray-500 font-mono">{u.tenant_id}</td>
                    )}
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <select
                          value={u.role}
                          onChange={e => handleRoleChange(u.id, e.target.value)}
                          disabled={updatingId === u.id}
                          className={`appearance-none pl-2 pr-6 py-1 text-xs font-bold rounded-full border cursor-pointer ${ROLE_BADGE[u.role] || ROLE_BADGE.User}`}
                        >
                          {isSuperAdmin && <option value="SuperAdmin">SuperAdmin</option>}
                          <option value="Admin">Admin</option>
                          <option value="Manager">Manager</option>
                          <option value="DataEntry">Data Entry / Import Operator</option>
                          <option value="User">User</option>
                        </select>
                        {updatingId === u.id && <Loader2 className="w-3 h-3 animate-spin text-gray-400" />}
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1.5">
                        {u.invite_status === "pending" ? (
                          <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase rounded-full border bg-amber-50 text-amber-700 border-amber-200">
                            Invite Pending
                          </span>
                        ) : u.invite_status === "expired" ? (
                          <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase rounded-full border bg-red-50 text-red-600 border-red-200">
                            Invite Expired
                          </span>
                        ) : (
                          <button
                            onClick={() => handleToggleActive(u.id, u.is_active)}
                            disabled={updatingId === u.id || u.id === currentUser?.id}
                            title={u.id === currentUser?.id ? "Cannot disable yourself" : (u.is_active ? "Click to disable" : "Click to enable")}
                            className={`inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase rounded-full border transition-colors ${
                              u.is_active
                                ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                                : "bg-gray-100 text-gray-500 border-gray-200 hover:bg-gray-200"
                            } ${(u.id === currentUser?.id) ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                          >
                            {u.is_active ? "Active" : "Disabled"}
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-400">
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : "\u2014"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setEditTarget(u)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 transition-colors"
                        >
                          <Pencil className="w-3 h-3" /> Edit
                        </button>
                        {u.invite_status ? (
                          <button
                            onClick={() => handleResendInvite(u.id)}
                            disabled={updatingId === u.id}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors disabled:opacity-50"
                          >
                            {updatingId === u.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                            Resend Invite
                          </button>
                        ) : (
                          <button
                            onClick={() => setResetTarget({ id: u.id, name: u.name })}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-gray-300 transition-colors"
                          >
                            <KeyRound className="w-3 h-3" /> Reset Password
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteUser(u.id, u.name)}
                          disabled={updatingId === u.id || u.id === currentUser?.id}
                          title={u.id === currentUser?.id ? "Cannot delete yourself" : "Delete user"}
                          className={`inline-flex items-center p-1.5 text-gray-400 border border-gray-200 rounded-lg hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors ${u.id === currentUser?.id ? "cursor-not-allowed opacity-40" : ""}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Create User Modal */}
        {showCreateModal && (
          <CreateUserModal
            onClose={() => setShowCreateModal(false)}
            onCreated={fetchUsers}
            tenants={tenants}
            currentTenantId={currentUser?.tenant_id}
            isSuperAdmin={isSuperAdmin}
          />
        )}

        {/* Edit User Modal */}
        {editTarget && (
          <EditUserModal
            user={editTarget}
            onClose={() => setEditTarget(null)}
            onSaved={fetchUsers}
            tenants={tenants}
            isSuperAdmin={isSuperAdmin}
          />
        )}

        {/* Reset Password Modal */}
        {resetTarget && (
          <ResetPasswordModal
            onClose={() => setResetTarget(null)}
            userId={resetTarget.id}
            userName={resetTarget.name}
          />
        )}

        {/* Invite URL Modal */}
        {resendResult && (
          <InviteUrlModal
            onClose={() => setResendResult(null)}
            inviteUrl={resendResult.invite_url}
            email={resendResult.email}
          />
        )}
      </div>
    </PageWrapper>
  );
}


/* ── Edit User Modal ── */
function EditUserModal({ user: target, onClose, onSaved, tenants, isSuperAdmin }) {
  const [name, setName] = useState(target.name || "");
  const [email, setEmail] = useState(target.email || "");
  const [role, setRole] = useState(target.role || "User");
  const [tenantId, setTenantId] = useState(target.tenant_id || "");
  const [isActive, setIsActive] = useState(target.is_active !== false);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { name, email, role, is_active: isActive };
      if (isSuperAdmin) body.tenant_id = tenantId;
      await apiFetch(`/admin/users/${target.id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      toast.success(`User "${name}" updated`);
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to update user");
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Edit User</h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Name</label>
            <input type="text" required value={name} onChange={e => setName(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Email</label>
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs font-medium text-gray-600 mb-1 block">Role</label>
              <select value={role} onChange={e => setRole(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500">
                {isSuperAdmin && <option value="SuperAdmin">SuperAdmin</option>}
                <option value="Admin">Admin</option>
                <option value="Manager">Manager</option>
                <option value="DataEntry">Data Entry / Import Operator</option>
                <option value="User">User</option>
              </select>
            </div>
            {isSuperAdmin && tenants.length > 0 && (
              <div className="flex-1">
                <label className="text-xs font-medium text-gray-600 mb-1 block">Tenant</label>
                <select value={tenantId} onChange={e => setTenantId(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500">
                  {tenants.map(t => <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>)}
                </select>
              </div>
            )}
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Status</label>
            <div className="flex gap-2">
              <button type="button" onClick={() => setIsActive(true)} className={`flex-1 px-3 py-2 text-xs font-medium rounded-lg border ${isActive ? "bg-emerald-50 border-emerald-300 text-emerald-700" : "border-gray-200 text-gray-600 hover:bg-gray-50"}`}>
                Active
              </button>
              <button type="button" onClick={() => setIsActive(false)} className={`flex-1 px-3 py-2 text-xs font-medium rounded-lg border ${!isActive ? "bg-red-50 border-red-300 text-red-700" : "border-gray-200 text-gray-600 hover:bg-gray-50"}`}>
                Disabled
              </button>
            </div>
          </div>
          <button type="submit" disabled={saving} className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Changes
          </button>
        </form>
      </div>
    </div>
  );
}


/* ── Create User Modal ── */
function CreateUserModal({ onClose, onCreated, tenants, currentTenantId, isSuperAdmin }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("User");
  const [tenantId, setTenantId] = useState(currentTenantId || "");
  const [mode, setMode] = useState("invite");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [inviteResult, setInviteResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { name, email, role };
      if (isSuperAdmin && tenantId) body.tenant_id = tenantId;
      if (mode === "password") {
        body.password = password;
      }
      const data = await apiFetch(mode === "invite" ? "/admin/users/invite" : "/admin/users", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (mode === "invite" && data.invite_url) {
        setInviteResult({ invite_url: data.invite_url, email });
      } else {
        toast.success(`User "${name}" created`);
        onCreated();
        onClose();
      }
    } catch (err) {
      toast.error(err?.message || "Failed to create user");
    }
    setSaving(false);
  };

  if (inviteResult) {
    return (
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
        <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
          <InviteUrlContent inviteUrl={inviteResult.invite_url} email={inviteResult.email} onClose={() => { onCreated(); onClose(); }} />
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Create User</h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Name</label>
            <input type="text" required value={name} onChange={e => setName(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Email</label>
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs font-medium text-gray-600 mb-1 block">Role</label>
              <select value={role} onChange={e => setRole(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500">
                {isSuperAdmin && <option value="SuperAdmin">SuperAdmin</option>}
                <option value="Admin">Admin</option>
                <option value="Manager">Manager</option>
                <option value="DataEntry">Data Entry / Import Operator</option>
                <option value="User">User</option>
              </select>
            </div>
            {isSuperAdmin && tenants.length > 0 && (
              <div className="flex-1">
                <label className="text-xs font-medium text-gray-600 mb-1 block">Tenant</label>
                <select value={tenantId} onChange={e => setTenantId(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500">
                  {tenants.map(t => <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>)}
                </select>
              </div>
            )}
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Creation Mode</label>
            <div className="flex gap-2">
              <button type="button" onClick={() => setMode("invite")} className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border ${mode === "invite" ? "bg-blue-50 border-blue-300 text-blue-700" : "border-gray-200 text-gray-600 hover:bg-gray-50"}`}>
                <Mail className="w-3 h-3" /> Invite Link
              </button>
              <button type="button" onClick={() => setMode("password")} className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border ${mode === "password" ? "bg-blue-50 border-blue-300 text-blue-700" : "border-gray-200 text-gray-600 hover:bg-gray-50"}`}>
                <KeyRound className="w-3 h-3" /> Set Password
              </button>
            </div>
          </div>
          {mode === "password" && (
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Password</label>
              <div className="relative">
                <input type={showPwd ? "text" : "password"} required value={password} onChange={e => setPassword(e.target.value)} className="w-full px-3 py-2 pr-8 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" minLength={12} />
                <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400">
                  {showPwd ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
          )}
          <button type="submit" disabled={saving} className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {mode === "invite" ? "Send Invite" : "Create User"}
          </button>
        </form>
      </div>
    </div>
  );
}


/* ── Reset Password Modal ── */
function ResetPasswordModal({ onClose, userId, userName }) {
  const [newPwd, setNewPwd] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleReset = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch(`/admin/users/${userId}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ new_password: newPwd }),
      });
      toast.success(`Password reset for ${userName}`);
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to reset password");
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Reset Password</h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-sm text-gray-500 mb-4">Set a new password for <strong>{userName}</strong>.</p>
        <form onSubmit={handleReset} className="space-y-4">
          <div className="relative">
            <input type={showPwd ? "text" : "password"} required value={newPwd} onChange={e => setNewPwd(e.target.value)} className="w-full px-3 py-2 pr-8 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" minLength={12} placeholder="New password (12+ chars)" />
            <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400">
              {showPwd ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          </div>
          <button type="submit" disabled={saving} className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
            Reset Password
          </button>
        </form>
      </div>
    </div>
  );
}


/* ── Invite URL Content ── */
function InviteUrlContent({ inviteUrl, email, onClose }) {
  const [copied, setCopied] = useState(false);
  const fullUrl = `${window.location.origin}${inviteUrl}`;

  return (
    <>
      <div className="flex items-center gap-2 mb-4">
        <LinkIcon className="w-5 h-5 text-blue-600" />
        <h3 className="text-lg font-semibold text-gray-900">Invite Created</h3>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Share this link with <strong>{email}</strong> to complete registration:
      </p>
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 flex items-center gap-2">
        <code className="flex-1 text-xs text-gray-700 break-all">{fullUrl}</code>
        <button
          onClick={() => { navigator.clipboard.writeText(fullUrl); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
          className="flex-shrink-0 p-1.5 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-200"
        >
          {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>
      <button onClick={onClose} className="w-full mt-4 px-4 py-2.5 bg-gray-900 hover:bg-gray-800 text-white text-sm font-medium rounded-lg">
        Done
      </button>
    </>
  );
}


/* ── Invite URL Modal ── */
function InviteUrlModal({ onClose, inviteUrl, email }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
        <InviteUrlContent inviteUrl={inviteUrl} email={email} onClose={onClose} />
      </div>
    </div>
  );
}
