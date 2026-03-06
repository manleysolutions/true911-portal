import { useState, useEffect, useCallback } from "react";
import { Site } from "@/api/entities";
import { apiFetch, setActAsTenant, getActAsTenant } from "@/api/client";
import { Settings, Search, Save, MapPin, Clock, ChevronDown, Loader2, Users, Shield, Plus, X, Eye, EyeOff, KeyRound, Trash2, Mail, Link, Copy, Check, RefreshCw, Building2, Pencil, Globe } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { updateE911, updateHeartbeat } from "@/components/actions";
import { toast } from "sonner";
import StatusBadge from "@/components/ui/StatusBadge";
import KitTypeBadge from "@/components/ui/KitTypeBadge";

const DEFAULT_HEARTBEAT = {
  FACP: "daily",
  Elevator: "weekly",
  "Emergency Call Box": "weekly",
  SCADA: "monthly",
  Fax: "monthly",
  Other: "monthly",
};

function HeartbeatPolicyCard() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
        <Clock className="w-4 h-4 text-red-600" />
        <h2 className="font-semibold text-gray-900 text-sm">Default Heartbeat Policies</h2>
      </div>
      <div className="p-5 space-y-3">
        {Object.entries(DEFAULT_HEARTBEAT).map(([kit, freq]) => (
          <div key={kit} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
            <div className="flex items-center gap-3">
              <KitTypeBadge type={kit} />
              <span className="text-sm text-gray-700">{kit}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-900 capitalize">{freq}</span>
              {freq === 'daily' && <span className="text-[10px] bg-red-50 text-red-600 border border-red-100 px-1.5 py-0.5 rounded font-medium uppercase">Strict</span>}
            </div>
          </div>
        ))}
      </div>
      <div className="px-5 pb-4">
        <p className="text-xs text-gray-500 leading-relaxed">
          <span className="font-semibold text-gray-700">Policy rationale:</span> Fire alarm panels (FACP) require daily check-ins per NFPA 72 monitoring requirements. Elevators follow weekly testing schedules per ASME A17.1. All other devices default to monthly.
        </p>
      </div>
    </div>
  );
}

function E911Editor({ site, onSaved }) {
  const { user } = useAuth();
  const [street, setStreet] = useState(site.e911_street || "");
  const [city, setCity] = useState(site.e911_city || "");
  const [state, setState] = useState(site.e911_state || "");
  const [zip, setZip] = useState(site.e911_zip || "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    const result = await updateE911(user, site, { street, city, state, zip });
    setSaving(false);
    if (result.success) {
      toast.success(`E911 address updated for ${site.site_name}`);
      onSaved?.();
    }
  };

  return (
    <div className="grid grid-cols-2 gap-3 mt-3">
      <div className="col-span-2">
        <label className="text-xs font-medium text-gray-600 mb-1 block">Street Address</label>
        <input value={street} onChange={e => setStreet(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
      </div>
      <div>
        <label className="text-xs font-medium text-gray-600 mb-1 block">City</label>
        <input value={city} onChange={e => setCity(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
      </div>
      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs font-medium text-gray-600 mb-1 block">State</label>
          <input value={state} onChange={e => setState(e.target.value)} maxLength={2} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500 uppercase" />
        </div>
        <div className="flex-1">
          <label className="text-xs font-medium text-gray-600 mb-1 block">ZIP</label>
          <input value={zip} onChange={e => setZip(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
        </div>
      </div>
      <div className="col-span-2">
        <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          {saving ? "Saving..." : "Save E911 Address"}
        </button>
      </div>
    </div>
  );
}

function HeartbeatEditor({ site, onSaved }) {
  const { user } = useAuth();
  const [freq, setFreq] = useState(site.heartbeat_frequency || DEFAULT_HEARTBEAT[site.kit_type] || "monthly");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    const result = await updateHeartbeat(user, site, freq);
    setSaving(false);
    if (result.success) {
      toast.success(result.message);
      onSaved?.();
    }
  };

  return (
    <div className="flex items-center gap-3 mt-3">
      <div className="relative">
        <select value={freq} onChange={e => setFreq(e.target.value)} className="appearance-none pl-3 pr-8 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
        <ChevronDown className="w-3.5 h-3.5 absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
      </div>
      <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-gray-900 hover:bg-gray-800 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
        {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
        {saving ? "Saving..." : "Update Policy"}
      </button>
      <span className="text-xs text-gray-400">Default for {site.kit_type}: <strong>{DEFAULT_HEARTBEAT[site.kit_type] || 'monthly'}</strong></span>
    </div>
  );
}

function SiteAdminRow({ site, onSaved }) {
  const [expanded, setExpanded] = useState(null); // 'e911' | 'heartbeat' | null
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!window.confirm(`Delete site "${site.site_name}" (${site.site_id})? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await Site.delete(site.id);
      toast.success(`Site "${site.site_name}" deleted`);
      onSaved?.();
    } catch (err) {
      toast.error(err?.message || "Failed to delete site");
    }
    setDeleting(false);
  };

  return (
    <div className="border border-gray-100 rounded-xl mb-3 overflow-hidden">
      <div className="flex items-center gap-3 p-4 bg-white">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 text-sm">{site.site_name}</span>
            <span className="text-xs text-gray-400 font-mono">{site.site_id}</span>
            <StatusBadge status={site.status} />
            <KitTypeBadge type={site.kit_type} />
          </div>
          <div className="text-xs text-gray-500 mt-0.5">{site.e911_street}, {site.e911_city}, {site.e911_state}</div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setExpanded(expanded === 'e911' ? null : 'e911')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-all ${expanded === 'e911' ? 'bg-red-50 border-red-300 text-red-700 font-medium' : 'border-gray-200 text-gray-600 hover:border-red-200'}`}
          >
            <MapPin className="w-3 h-3" /> E911
          </button>
          <button
            onClick={() => setExpanded(expanded === 'heartbeat' ? null : 'heartbeat')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-all ${expanded === 'heartbeat' ? 'bg-gray-900 border-gray-900 text-white font-medium' : 'border-gray-200 text-gray-600 hover:border-gray-400'}`}
          >
            <Clock className="w-3 h-3" /> Heartbeat
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            title="Delete site"
            className="flex items-center p-1.5 text-gray-400 border border-gray-200 rounded-lg hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors disabled:opacity-50"
          >
            {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
      {expanded === 'e911' && (
        <div className="px-4 pb-4 bg-red-50/30 border-t border-red-100">
          <div className="text-xs font-semibold text-red-700 pt-3 mb-1">Edit E911 Address</div>
          <E911Editor site={site} onSaved={() => { setExpanded(null); onSaved?.(); }} />
        </div>
      )}
      {expanded === 'heartbeat' && (
        <div className="px-4 pb-4 bg-gray-50/50 border-t border-gray-100">
          <div className="text-xs font-semibold text-gray-700 pt-3 mb-1">Override Heartbeat Policy</div>
          <HeartbeatEditor site={site} onSaved={() => { setExpanded(null); onSaved?.(); }} />
        </div>
      )}
    </div>
  );
}

/* ── Create User Modal ── */
function CreateUserModal({ open, onClose, onCreated, tenants, currentTenantId, isSuperAdmin }) {
  const [mode, setMode] = useState("invite"); // "invite" | "password"
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("User");
  const [tenantId, setTenantId] = useState(currentTenantId || "");
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [inviteUrl, setInviteUrl] = useState(null);
  const [copied, setCopied] = useState(false);

  // Reset tenant to current user's tenant when modal opens
  useEffect(() => {
    if (open && currentTenantId) setTenantId(currentTenantId);
  }, [open, currentTenantId]);

  const resetState = () => {
    setEmail(""); setName(""); setPassword(""); setRole("User");
    setTenantId(currentTenantId || "");
    setInviteUrl(null); setCopied(false); setMode("invite");
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const copyInviteUrl = () => {
    const fullUrl = `${window.location.origin}${inviteUrl}`;
    navigator.clipboard.writeText(fullUrl);
    setCopied(true);
    toast.success("Invite link copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSubmitInvite = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const data = await apiFetch("/admin/users/invite", {
        method: "POST",
        body: JSON.stringify({ email, name, role, tenant_id: tenantId || undefined }),
      });
      setInviteUrl(data.invite_url);
      toast.success("Invite created — copy the link to share");
      onCreated?.();
    } catch (err) {
      toast.error(err?.message || "Failed to create invite");
    }
    setSaving(false);
  };

  const handleSubmitPassword = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/admin/users", {
        method: "POST",
        body: JSON.stringify({ email, name, password, role, tenant_id: tenantId || undefined }),
      });
      toast.success("User created — they must change password on first login");
      resetState();
      onCreated?.();
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to create user");
    }
    setSaving(false);
  };

  if (!open) return null;

  // Show invite URL result
  if (inviteUrl) {
    const fullUrl = `${window.location.origin}${inviteUrl}`;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
        <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900 text-sm">Invite Link Ready</h3>
            <button onClick={handleClose} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>
          <div className="p-5 space-y-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <Check className="w-4 h-4 text-emerald-600" />
                <span className="text-sm font-medium text-emerald-800">Invite created for {email}</span>
              </div>
              <p className="text-xs text-emerald-600">Share this link with the user. It expires in 7 days.</p>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Invite URL</label>
              <div className="flex gap-2">
                <input type="text" readOnly value={fullUrl} className="flex-1 px-3 py-2 text-xs font-mono bg-gray-50 border border-gray-200 rounded-lg text-gray-700" />
                <button onClick={copyInviteUrl} className="flex items-center gap-1.5 px-3 py-2 bg-gray-900 hover:bg-gray-800 text-white text-xs font-medium rounded-lg transition-colors">
                  {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button onClick={handleClose} className="px-4 py-2 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">Done</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 text-sm">Create User</h3>
          <button onClick={handleClose} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* Mode toggle */}
        <div className="px-5 pt-4">
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            <button
              type="button"
              onClick={() => setMode("invite")}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-md transition-all ${mode === "invite" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              <Link className="w-3 h-3" /> Send invite link
            </button>
            <button
              type="button"
              onClick={() => setMode("password")}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-md transition-all ${mode === "password" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              <KeyRound className="w-3 h-3" /> Set password
            </button>
          </div>
        </div>

        <form onSubmit={mode === "invite" ? handleSubmitInvite : handleSubmitPassword} className="p-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Email</label>
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" placeholder="user@example.com" />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Full Name</label>
            <input type="text" required value={name} onChange={e => setName(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" placeholder="Jane Doe" />
          </div>

          {mode === "password" && (
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Temporary Password</label>
              <div className="relative">
                <input type={showPassword ? "text" : "password"} required value={password} onChange={e => setPassword(e.target.value)} className="w-full px-3 py-2 pr-10 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" placeholder="Min 12 chars, upper+lower+digit" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[10px] text-amber-600 mt-1">User will be required to change this password on first login.</p>
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Role</label>
            <select value={role} onChange={e => setRole(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500">
              <option value="User">User</option>
              <option value="Manager">Manager</option>
              <option value="Admin">Admin</option>
              {isSuperAdmin && <option value="SuperAdmin">SuperAdmin</option>}
            </select>
          </div>

          {((tenants && tenants.length > 1) || isSuperAdmin) && tenants && tenants.length > 0 && (
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Tenant</label>
              <select value={tenantId} onChange={e => setTenantId(e.target.value)} className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500">
                {tenants.map(t => (
                  <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
                ))}
              </select>
            </div>
          )}

          {mode === "invite" && (
            <div className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
              <p className="text-[10px] text-blue-700">An invite link will be generated. Share it with the user so they can set their own password. Link expires in 7 days.</p>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={handleClose} className="px-4 py-2 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">Cancel</button>
            <button type="submit" disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : mode === "invite" ? <Mail className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
              {saving ? "Creating..." : mode === "invite" ? "Create & Get Link" : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Reset Password Modal ── */
function ResetPasswordModal({ open, onClose, userId, userName }) {
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch(`/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ password }),
      });
      toast.success(`Password reset for ${userName}`);
      setPassword("");
      onClose();
    } catch (err) {
      toast.error(err?.message || "Failed to reset password");
    }
    setSaving(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 text-sm">Reset Password</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <p className="text-sm text-gray-600">Set a new password for <strong>{userName}</strong>.</p>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">New Password</label>
            <div className="relative">
              <input type={showPassword ? "text" : "password"} required value={password} onChange={e => setPassword(e.target.value)} className="w-full px-3 py-2 pr-10 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" placeholder="Min 12 chars, upper+lower+digit" />
              <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">Cancel</button>
            <button type="submit" disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <KeyRound className="w-3.5 h-3.5" />}
              {saving ? "Resetting..." : "Reset Password"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Invite URL Modal (for resend) ── */
function InviteUrlModal({ open, onClose, inviteUrl, email }) {
  const [copied, setCopied] = useState(false);
  if (!open) return null;

  const fullUrl = `${window.location.origin}${inviteUrl}`;
  const copyUrl = () => {
    navigator.clipboard.writeText(fullUrl);
    setCopied(true);
    toast.success("Invite link copied");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 text-sm">New Invite Link</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-gray-600">New invite link generated for <strong>{email}</strong>. Expires in 7 days.</p>
          <div className="flex gap-2">
            <input type="text" readOnly value={fullUrl} className="flex-1 px-3 py-2 text-xs font-mono bg-gray-50 border border-gray-200 rounded-lg text-gray-700" />
            <button onClick={copyUrl} className="flex items-center gap-1.5 px-3 py-2 bg-gray-900 hover:bg-gray-800 text-white text-xs font-medium rounded-lg transition-colors">
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <div className="flex justify-end">
            <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">Done</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Tenant Management Section ── */
function TenantManagement() {
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);

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

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
        <Building2 className="w-4 h-4 text-violet-600" />
        <h2 className="font-semibold text-gray-900 text-sm">Tenants</h2>
        <span className="text-xs text-gray-400 ml-auto mr-3">{tenants.length} tenants</span>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded-lg transition-colors"
        >
          <Plus className="w-3 h-3" /> Create Tenant
        </button>
      </div>

      {/* Inline create form */}
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
  );
}

/* ── User Management Section ── */
function UserManagement() {
  const { user: currentUser, isSuperAdmin } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [resetTarget, setResetTarget] = useState(null); // { id, name }
  const [resendResult, setResendResult] = useState(null); // { invite_url, email }
  const [tenants, setTenants] = useState([]);
  const [tenantFilter, setTenantFilter] = useState(""); // "" = all

  const fetchUsers = useCallback(async () => {
    try {
      const qs = isSuperAdmin && tenantFilter ? `?tenant_id=${tenantFilter}` : "";
      const fetches = [
        apiFetch(`/admin/users${qs}`),
      ];
      if (isSuperAdmin) {
        fetches.push(apiFetch("/admin/tenants").catch(() => []));
      }
      const [userData, tenantData] = await Promise.all(fetches);
      setUsers(userData);
      if (tenantData) setTenants(tenantData);
    } catch {
      // silently fail if endpoint not available
    }
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
    User: "bg-gray-100 text-gray-600 border-gray-200",
  };

  return (
    <>
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <Users className="w-4 h-4 text-indigo-600" />
          <h2 className="font-semibold text-gray-900 text-sm">User Management</h2>
          {isSuperAdmin && tenants.length > 0 && (
            <div className="relative ml-2">
              <select
                value={tenantFilter}
                onChange={e => setTenantFilter(e.target.value)}
                className="appearance-none pl-2 pr-6 py-1 text-xs font-medium border border-purple-200 bg-purple-50 text-purple-700 rounded-lg cursor-pointer focus:outline-none focus:ring-1 focus:ring-purple-400"
              >
                <option value="">All Tenants</option>
                {tenants.map(t => (
                  <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
                ))}
              </select>
              <ChevronDown className="w-3 h-3 absolute right-1.5 top-1/2 -translate-y-1/2 text-purple-400 pointer-events-none" />
            </div>
          )}
          <span className="text-xs text-gray-400 ml-auto mr-3">{users.length} users</span>
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

      <CreateUserModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={fetchUsers}
        tenants={tenants}
        currentTenantId={currentUser?.tenant_id}
        isSuperAdmin={isSuperAdmin}
      />

      {resetTarget && (
        <ResetPasswordModal
          open={true}
          onClose={() => setResetTarget(null)}
          userId={resetTarget.id}
          userName={resetTarget.name}
        />
      )}

      {resendResult && (
        <InviteUrlModal
          open={true}
          onClose={() => setResendResult(null)}
          inviteUrl={resendResult.invite_url}
          email={resendResult.email}
        />
      )}
    </>
  );
}

/* ── SuperAdmin Tenant Switcher Banner ── */
function TenantSwitcherBanner({ tenants, onRefresh }) {
  const [activeTenant, setActiveTenant] = useState(getActAsTenant() || "");

  const handleChange = (tenantId) => {
    setActiveTenant(tenantId);
    setActAsTenant(tenantId);
    onRefresh?.();
  };

  return (
    <div className="bg-purple-50 border border-purple-200 rounded-xl px-5 py-3 mb-6 flex items-center gap-3">
      <Globe className="w-4 h-4 text-purple-600 flex-shrink-0" />
      <span className="text-sm font-semibold text-purple-800">SuperAdmin</span>
      <span className="text-xs text-purple-600">Acting as:</span>
      <div className="relative">
        <select
          value={activeTenant}
          onChange={e => handleChange(e.target.value)}
          className="appearance-none pl-3 pr-7 py-1.5 text-xs font-medium border border-purple-300 bg-white text-purple-700 rounded-lg cursor-pointer focus:outline-none focus:ring-1 focus:ring-purple-400"
        >
          <option value="">All tenants (own context)</option>
          {tenants.map(t => (
            <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
          ))}
        </select>
        <ChevronDown className="w-3 h-3 absolute right-2 top-1/2 -translate-y-1/2 text-purple-400 pointer-events-none" />
      </div>
      {activeTenant && (
        <button
          onClick={() => handleChange("")}
          className="text-xs text-purple-600 hover:text-purple-800 underline ml-1"
        >
          Clear
        </button>
      )}
    </div>
  );
}

export default function Admin() {
  const { user, can, isSuperAdmin } = useAuth();
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState("sites"); // 'sites' | 'users' | 'tenants'
  const [saTenants, setSaTenants] = useState([]);

  const fetchData = useCallback(async () => {
    const data = await Site.list("-last_checkin", 100);
    setSites(data);
    setLoading(false);
  }, []);

  // Fetch tenants for the SuperAdmin switcher
  useEffect(() => {
    if (isSuperAdmin) {
      apiFetch("/admin/tenants").then(setSaTenants).catch(() => {});
    }
  }, [isSuperAdmin]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (!can('VIEW_ADMIN')) {
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

  const filtered = sites.filter(s => {
    if (!search) return true;
    const q = search.toLowerCase();
    return s.site_name?.toLowerCase().includes(q) || s.site_id?.toLowerCase().includes(q) || s.customer_name?.toLowerCase().includes(q);
  });

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto">
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${isSuperAdmin ? "bg-purple-100 text-purple-700 border-purple-200" : "bg-red-100 text-red-700 border-red-200"}`}>
              {isSuperAdmin ? "SuperAdmin" : "Admin Only"}
            </span>
          </div>
          <p className="text-sm text-gray-500">Manage site configuration, heartbeat policies, and user roles.</p>
        </div>

        {isSuperAdmin && saTenants.length > 0 && (
          <TenantSwitcherBanner tenants={saTenants} onRefresh={fetchData} />
        )}

        {/* Tab switcher */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab("sites")}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg border transition-all ${
              activeTab === "sites" ? "bg-gray-900 text-white border-gray-900" : "border-gray-200 text-gray-600 hover:border-gray-400"
            }`}
          >
            <Settings className="w-3.5 h-3.5" /> Site Config
          </button>
          <button
            onClick={() => setActiveTab("users")}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg border transition-all ${
              activeTab === "users" ? "bg-gray-900 text-white border-gray-900" : "border-gray-200 text-gray-600 hover:border-gray-400"
            }`}
          >
            <Shield className="w-3.5 h-3.5" /> Users & Roles
          </button>
          <button
            onClick={() => setActiveTab("tenants")}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg border transition-all ${
              activeTab === "tenants" ? "bg-gray-900 text-white border-gray-900" : "border-gray-200 text-gray-600 hover:border-gray-400"
            }`}
          >
            <Building2 className="w-3.5 h-3.5" /> Tenants
          </button>
        </div>

        {activeTab === "users" && <UserManagement />}
        {activeTab === "tenants" && <TenantManagement />}

        {activeTab === "sites" && (
          <>
            <HeartbeatPolicyCard />

            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-100">
                <Settings className="w-4 h-4 text-gray-400" />
                <h2 className="font-semibold text-gray-900 text-sm">Per-Site Configuration</h2>
              </div>
              <div className="px-5 py-4 border-b border-gray-100">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search sites..." className="w-full pl-8 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
                </div>
              </div>
              <div className="p-4">
                {loading ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  filtered.map(site => (
                    <SiteAdminRow key={site.id} site={site} onSaved={fetchData} />
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </PageWrapper>
  );
}
