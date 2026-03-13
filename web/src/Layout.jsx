import { useState } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, LayoutDashboard, Map, Building2, FileText, Settings, Menu, X, LogOut,
  AlertOctagon, Bell, Cpu, Phone, Disc3, Activity, MapPin, Sparkles, Rocket, Plug,
  ArrowDownUp, ShieldCheck, FileSpreadsheet, Globe, Radio, Bot, Upload, Users,
  KeyRound, Eye, EyeOff, AlertTriangle, CheckCircle, Loader2, HelpCircle, Home,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import { config } from "@/config";

// ── Role hierarchy ──────────────────────────────────────────────
// Higher number = more access.  SuperAdmin sees everything.
const ROLE_LEVEL = { User: 1, Manager: 2, Admin: 3, SuperAdmin: 4 };

function roleLevel(role) {
  return ROLE_LEVEL[role] || 0;
}

// ── Navigation definitions ──────────────────────────────────────
// minRole: minimum role to see this item (default: visible to all)
// portal:  "customer" = customer-facing, "noc" = NOC/admin, "both" = always shown

const CUSTOMER_NAV = [
  { section: "label", label: "MY PORTAL" },
  { name: "My Sites",     page: "Sites",            icon: Building2 },
  { name: "My Devices",   page: "Devices",           icon: Cpu },
  { name: "Lines",        page: "Lines",             icon: Phone },
  { name: "Incidents",    page: "Incidents",         icon: AlertOctagon },
  { name: "Reports",      page: "Reports",           icon: FileText },
  { section: "separator" },
  { name: "Events",       page: "Events",            icon: Activity,       minRole: "Manager" },
  { name: "Recordings",   page: "Recordings",        icon: Disc3,          minRole: "Manager" },
  { name: "Network",      page: "NetworkDashboard",  icon: Radio,          minRole: "Manager" },
  { name: "Map",          page: "DeploymentMap",      icon: Map,            minRole: "Manager" },
];

const NOC_NAV = [
  { section: "label", label: "OPERATIONS" },
  { name: "Command",      page: "Command",           icon: ShieldCheck },
  { name: "Operator View", page: "OperatorView",     icon: Building2 },
  { name: "Overview",     page: "Overview",           icon: LayoutDashboard },
  { section: "separator" },
  { section: "label", label: "FLEET" },
  { name: "Customers",    page: "Customers",          icon: Users },
  { name: "Sites",        page: "Sites",              icon: Building2 },
  { name: "Devices",      page: "Devices",            icon: Cpu },
  { name: "SIMs",         page: "SimManagement",      icon: Disc3 },
  { name: "Lines",        page: "Lines",              icon: Phone },
  { name: "E911",         page: "E911",               icon: MapPin },
  { section: "separator" },
  { section: "label", label: "MONITORING" },
  { name: "Alerts",       page: "Notifications",      icon: Bell },
  { name: "Events",       page: "Events",             icon: Activity },
  { name: "Incidents",    page: "Incidents",           icon: AlertOctagon },
  { name: "Network",      page: "NetworkDashboard",   icon: Radio },
  { name: "Recordings",   page: "Recordings",         icon: Disc3 },
  { name: "Reports",      page: "Reports",            icon: FileText },
  { name: "Map",          page: "DeploymentMap",       icon: Map },
  { section: "separator" },
  { section: "label", label: "PLATFORM" },
  { name: "Auto Ops",     page: "AutoOps",            icon: Bot },
  { name: "Providers",    page: "Providers",           icon: Plug },
  { name: "Integrations", page: "IntegrationSync",    icon: ArrowDownUp },
  { name: "Site Onboard",  page: "SiteOnboarding",     icon: Building2 },
  { name: "Device Setup", page: "OnboardingWizard",   icon: Rocket },
  { name: "Organization", page: "OrgSettings",        icon: Globe },
  { name: "AI / Samantha", page: "Samantha",          icon: Sparkles,       featureFlag: "samantha" },
  { section: "separator" },
  { section: "label", label: "SYSTEM ADMIN", minRole: "SuperAdmin" },
  { name: "Admin",        page: "Admin",              icon: Settings,       minRole: "SuperAdmin" },
  { name: "Tenants",      page: "AdminTenants",       icon: Building2,      minRole: "SuperAdmin" },
  { name: "Users",        page: "AdminUsers",         icon: Shield,         minRole: "SuperAdmin" },
  { name: "Imports",      page: "AdminImports",       icon: Upload,         minRole: "SuperAdmin" },
];

const ROLE_BADGE = {
  SuperAdmin: "bg-purple-100 text-purple-700 border-purple-200",
  Admin: "bg-red-100 text-red-700 border-red-200",
  Manager: "bg-blue-100 text-blue-700 border-blue-200",
  User: "bg-gray-100 text-gray-600 border-gray-200",
};

const FEATURE_FLAGS = {
  samantha: config.featureSamantha,
};


// ── Change Password Modal ───────────────────────────────────────
function ChangePasswordModal({ onClose }) {
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (newPwd !== confirmPwd) {
      setError("Passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPwd, new_password: newPwd }),
      });
      setSuccess(true);
      toast.success("Password changed successfully");
      setTimeout(onClose, 1500);
    } catch (err) {
      setError(err?.message || "Failed to change password");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-red-600" /> Change Password
          </h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>

        {success ? (
          <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs px-4 py-3 rounded-xl">
            <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
            Password changed successfully.
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Current Password</label>
              <input type={showPwd ? "text" : "password"} value={currentPwd} onChange={e => setCurrentPwd(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500" required autoComplete="current-password" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">New Password</label>
              <input type={showPwd ? "text" : "password"} value={newPwd} onChange={e => setNewPwd(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500" placeholder="Min 12 chars" required autoComplete="new-password" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Confirm New Password</label>
              <input type={showPwd ? "text" : "password"} value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500" required autoComplete="new-password" />
            </div>
            <button type="button" onClick={() => setShowPwd(!showPwd)} className="text-[10px] text-gray-500 hover:text-gray-700 flex items-center gap-1">
              {showPwd ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              {showPwd ? "Hide passwords" : "Show passwords"}
            </button>
            {error && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-100 text-red-600 text-xs px-3 py-2.5 rounded-lg">
                <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />{error}
              </div>
            )}
            <button type="submit" disabled={saving}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
              Change Password
            </button>
          </form>
        )}
      </div>
    </div>
  );
}


// ── Sidebar ─────────────────────────────────────────────────────
function Sidebar({ currentPageName, onClose, onChangePassword }) {
  const { user, logout, can, isSuperAdmin } = useAuth();

  const userRole = user?.role || "User";
  const level = roleLevel(userRole);
  const isNOC = level >= ROLE_LEVEL.Admin; // Admin + SuperAdmin see NOC nav

  const navItems = isNOC ? NOC_NAV : CUSTOMER_NAV;
  const portalLabel = isNOC ? "NOC Portal" : "Customer Portal";

  const visibleNav = navItems.filter(item => {
    // Sections: show label/separator if user meets minRole (or no minRole set)
    if (item.section) {
      if (item.minRole && level < ROLE_LEVEL[item.minRole]) return false;
      return true;
    }
    // Feature flags
    if (item.featureFlag && !FEATURE_FLAGS[item.featureFlag]) return false;
    // Min role check
    if (item.minRole && level < ROLE_LEVEL[item.minRole]) return false;
    return true;
  });

  return (
    <aside className="flex flex-col h-full bg-white border-r border-gray-200 w-60">
      {/* Branding */}
      <div className="px-5 py-5 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isNOC ? "bg-red-600" : "bg-slate-800"}`}>
            <Shield className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-base font-bold text-gray-900 leading-none">True911<span className={isNOC ? "text-red-600" : "text-slate-600"}>+</span></div>
            <div className="text-[10px] text-gray-400 tracking-widest uppercase mt-0.5">{portalLabel}</div>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400 lg:hidden">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* User info */}
      {user && (
        <div className="px-4 py-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-xs font-semibold text-gray-600">
              {user.name?.charAt(0)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-gray-900 truncate">{user.name}</div>
              <div className="text-[10px] text-gray-500 truncate">{user.email}</div>
            </div>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${ROLE_BADGE[userRole] || ROLE_BADGE.User}`}>
              {userRole}
            </span>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        {visibleNav.map((item, idx) => {
          if (item.section === "separator") {
            return <div key={`sep-${idx}`} className="my-2 border-t border-gray-100" />;
          }
          if (item.section === "label") {
            return <div key={`lbl-${idx}`} className="px-3 pt-3 pb-1 text-[10px] font-bold text-gray-400 uppercase tracking-widest">{item.label}</div>;
          }
          const { name, page, icon: Icon } = item;
          const active = currentPageName === page;
          return (
            <Link
              key={page}
              to={createPageUrl(page)}
              onClick={onClose}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all ${
                active
                  ? isNOC ? 'bg-red-50 text-red-700 font-semibold' : 'bg-slate-100 text-slate-900 font-semibold'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {name}
              {active && <div className={`ml-auto w-1.5 h-1.5 rounded-full ${isNOC ? "bg-red-600" : "bg-slate-700"}`} />}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-gray-100">
        {user && (
          <div className="space-y-0.5">
            <button onClick={onChangePassword}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors">
              <KeyRound className="w-3.5 h-3.5" /> Change Password
            </button>
            <button onClick={logout}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors">
              <LogOut className="w-3.5 h-3.5" /> Sign Out
            </button>
          </div>
        )}
        <div className="mt-3 flex items-center gap-1.5 justify-center">
          <span className="text-[10px] text-blue-800 font-bold">Made in USA</span>
          <span className="text-gray-300 text-[10px]">·</span>
          <span className="text-[10px] text-gray-400">NDAA-TAA</span>
        </div>
        <div className="text-[10px] text-gray-400 text-center">© 2026 Manley Solutions</div>
      </div>
    </aside>
  );
}


// ── App Layout ──────────────────────────────────────────────────
const PUBLIC_PAGES = ["AuthGate"];

function AppLayout({ children, currentPageName }) {
  const { user, ready } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showChangePwd, setShowChangePwd] = useState(false);

  if (PUBLIC_PAGES.includes(currentPageName)) {
    return (
      <div className="min-h-screen bg-gray-50">
        {children}
        <Toaster position="top-right" />
      </div>
    );
  }

  if (!ready) return null;

  if (!user) {
    window.location.href = "/AuthGate";
    return null;
  }

  const isNOC = roleLevel(user.role) >= ROLE_LEVEL.Admin;

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <div className="hidden lg:flex flex-col fixed inset-y-0 left-0 w-60 z-30">
        <Sidebar currentPageName={currentPageName} onChangePassword={() => setShowChangePwd(true)} />
      </div>

      {mobileOpen && (
        <>
          <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setMobileOpen(false)} />
          <div className="fixed inset-y-0 left-0 w-60 z-40 flex flex-col lg:hidden shadow-xl">
            <Sidebar currentPageName={currentPageName} onClose={() => setMobileOpen(false)} onChangePassword={() => { setShowChangePwd(true); setMobileOpen(false); }} />
          </div>
        </>
      )}

      {showChangePwd && <ChangePasswordModal onClose={() => setShowChangePwd(false)} />}

      <div className="flex-1 lg:ml-60 flex flex-col min-h-screen">
        <div className="lg:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200 sticky top-0 z-20">
          <button onClick={() => setMobileOpen(true)} className="p-2 rounded-lg hover:bg-gray-100">
            <Menu className="w-5 h-5 text-gray-700" />
          </button>
          <div className="flex items-center gap-2">
            <div className={`w-6 h-6 rounded flex items-center justify-center ${isNOC ? "bg-red-600" : "bg-slate-800"}`}>
              <Shield className="w-3 h-3 text-white" />
            </div>
            <span className="font-bold text-gray-900">True911<span className={isNOC ? "text-red-600" : "text-slate-600"}>+</span></span>
          </div>
          <div className="w-9" />
        </div>

        <main className="flex-1">
          {children}
        </main>
      </div>

      <Toaster position="top-right" />

      <style>{`
        :root {
          --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
        }
        body { font-family: var(--font-sans); }
        * { box-sizing: border-box; }
      `}</style>
    </div>
  );
}

export default function Layout({ children, currentPageName }) {
  return <AppLayout children={children} currentPageName={currentPageName} />;
}
