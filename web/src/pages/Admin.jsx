import { useState, useEffect, useCallback } from "react";
import { Site } from "@/api/entities";
import { apiFetch } from "@/api/client";
import { Settings, Search, Save, MapPin, Clock, ChevronDown, Loader2, Users, Shield } from "lucide-react";
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

/* ── User Management Section ── */
function UserManagement() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);

  const fetchUsers = useCallback(async () => {
    try {
      const data = await apiFetch("/admin/users");
      setUsers(data);
    } catch {
      // silently fail if endpoint not available
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleRoleChange = async (userId, newRole) => {
    setUpdatingId(userId);
    try {
      await apiFetch(`/admin/users/${userId}/role`, {
        method: "PUT",
        body: JSON.stringify({ role: newRole }),
      });
      toast.success("User role updated");
      fetchUsers();
    } catch (err) {
      toast.error(err?.message || "Failed to update role");
    }
    setUpdatingId(null);
  };

  const ROLE_BADGE = {
    Admin: "bg-red-50 text-red-700 border-red-200",
    Manager: "bg-blue-50 text-blue-700 border-blue-200",
    User: "bg-gray-100 text-gray-600 border-gray-200",
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
        <Users className="w-4 h-4 text-indigo-600" />
        <h2 className="font-semibold text-gray-900 text-sm">User Management</h2>
        <span className="text-xs text-gray-400 ml-auto">{users.length} users</span>
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
              <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Role</th>
              <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase">Joined</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-[11px] font-bold text-gray-600">
                      {u.name?.charAt(0)?.toUpperCase() || "?"}
                    </div>
                    <span className="font-medium text-gray-900">{u.name}</span>
                  </div>
                </td>
                <td className="px-5 py-3 text-gray-600 text-xs font-mono">{u.email}</td>
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <select
                      value={u.role}
                      onChange={e => handleRoleChange(u.id, e.target.value)}
                      disabled={updatingId === u.id}
                      className={`appearance-none pl-2 pr-6 py-1 text-xs font-bold rounded-full border cursor-pointer ${ROLE_BADGE[u.role] || ROLE_BADGE.User}`}
                    >
                      <option value="Admin">Admin</option>
                      <option value="Manager">Manager</option>
                      <option value="User">User</option>
                    </select>
                    {updatingId === u.id && <Loader2 className="w-3 h-3 animate-spin text-gray-400" />}
                  </div>
                </td>
                <td className="px-5 py-3 text-xs text-gray-400">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : "\u2014"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Admin() {
  const { user, can } = useAuth();
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState("sites"); // 'sites' | 'users'

  const fetchData = useCallback(async () => {
    const data = await Site.list("-last_checkin", 100);
    setSites(data);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (!can('VIEW_ADMIN')) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-4xl mb-3">&#128274;</div>
            <div className="text-lg font-semibold text-gray-800">Admin Access Required</div>
            <div className="text-sm text-gray-500 mt-1">This section is only accessible to Admin users.</div>
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
            <span className="bg-red-100 text-red-700 text-xs font-bold px-2 py-0.5 rounded-full border border-red-200">Admin Only</span>
          </div>
          <p className="text-sm text-gray-500">Manage site configuration, heartbeat policies, and user roles.</p>
        </div>

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
        </div>

        {activeTab === "users" && <UserManagement />}

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
