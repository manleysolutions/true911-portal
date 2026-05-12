import { useState, useEffect, useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, LayoutDashboard, Map, Building2, FileText, Settings, Menu, X, LogOut,
  AlertOctagon, Bell, Cpu, Phone, Disc3, Activity, MapPin, Sparkles, Rocket, Plug,
  ArrowDownUp, ShieldCheck, FileSpreadsheet, Globe, Radio, Bot, Upload, Users,
  KeyRound, Eye, EyeOff, AlertTriangle, CheckCircle, Loader2, HelpCircle,
  UserCog, XCircle, Zap, ChevronRight, Gauge, Package, Wrench, MonitorCog,
  Layers, SlidersHorizontal, ClipboardList,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import { config } from "@/config";

// ── Role hierarchy ──────────────────────────────────────────────
const ROLE_LEVEL = { User: 1, DataEntry: 1.5, DataSteward: 1.7, Manager: 2, Admin: 3, SuperAdmin: 4 };
function roleLevel(role) { return ROLE_LEVEL[role] || 0; }

const ROLE_BADGE = {
  SuperAdmin: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  Admin: "bg-red-500/20 text-red-300 border-red-500/30",
  Manager: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  DataSteward: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  DataEntry: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  User: "bg-gray-500/20 text-gray-400 border-gray-500/30",
};

const FEATURE_FLAGS = {
  samantha: config.featureSamantha,
};

// ═══════════════════════════════════════════════════════════════════
// NAVIGATION CONFIG
// ═══════════════════════════════════════════════════════════════════
//
// Structure:
//   Top-level items:   { name, page, icon, minRole?, featureFlag? }
//   Collapsible group: { group, label, icon, minRole?, children: [...items] }
//
// minRole defaults to "User" (everyone).  "Admin" hides from Manager/User.
// "SuperAdmin" hides from Admin/Manager/User.
//
// ── NOC / Admin portal ──────────────────────────────────────────

const NOC_NAV = [
  // ── Primary ──
  { name: "Command Center",  page: "Command",         icon: ShieldCheck },
  // ``permission`` items disappear from the nav when can() returns
  // false — Registrations is internal-only, so this hides it during
  // SuperAdmin impersonation of a customer tenant.
  { name: "Registrations",   page: "Registrations",   icon: ClipboardList, permission: "VIEW_REGISTRATIONS" },
  { name: "Onboarding Review", page: "OnboardingReview", icon: ClipboardList, permission: "VIEW_ONBOARDING_REVIEW" },
  { name: "Customers",       page: "Customers",       icon: Users },
  { name: "Sites",           page: "Sites",           icon: Building2 },
  { name: "Devices",         page: "Devices",         icon: Cpu },
  { name: "Incidents",       page: "Incidents",       icon: AlertOctagon },
  { name: "Map",             page: "DeploymentMap",   icon: Map },

  // ── Support Console ──
  { name: "Support Console",  page: "SupportConsole",       icon: HelpCircle, minRole: "Admin" },
  { name: "Self-Healing",     page: "SelfHealingConsole",   icon: Wrench,     minRole: "Admin" },

  // ── Monitoring ──
  {
    group: "monitoring", label: "Monitoring", icon: Activity, minRole: "Manager",
    children: [
      { name: "Alerts",          page: "Notifications",     icon: Bell },
      { name: "Events",          page: "Events",            icon: Activity },
      { name: "Network Health",  page: "NetworkDashboard",  icon: Radio },
      { name: "Recordings",      page: "Recordings",        icon: Disc3 },
      { name: "Reports",         page: "Reports",           icon: FileText },
      { name: "Automation",      page: "AutomationDashboard", icon: Zap },
    ],
  },

  // ── Network ──
  {
    group: "network", label: "Network", icon: Layers,
    children: [
      { name: "Lines",   page: "Lines",          icon: Phone },
      { name: "SIMs",    page: "SimManagement",  icon: Disc3 },
      { name: "E911",    page: "E911",           icon: MapPin },
    ],
  },

  // ── Deployment ──
  {
    group: "deployment", label: "Deployment", icon: Rocket, minRole: "Admin",
    children: [
      { name: "New Installation",           page: "Install",            icon: Zap },
      { name: "Onboard Site",              page: "OnboardSite",        icon: Building2 },
      { name: "Lines & Devices Import",    page: "SubscriberImport",   icon: FileSpreadsheet },
      { name: "Site Import",               page: "SiteImport",         icon: Upload },
      { name: "Import Verification",       page: "ImportVerification", icon: CheckCircle },
      { name: "Unassigned Devices & SIMs", page: "ProvisioningQueue",  icon: Package },
    ],
  },

  // ── Device Control (Advanced) ──
  {
    group: "device_control", label: "Device Control", icon: Wrench, minRole: "Admin",
    children: [
      { name: "VOLA Integration",   page: "VolaIntegration",     icon: Radio },
      { name: "PR12 Device Actions", page: "Pr12QuickDeploy",    icon: Rocket },
    ],
  },

  // ── Administration ──
  {
    group: "admin", label: "Administration", icon: Settings, minRole: "Admin",
    children: [
      { name: "Providers",      page: "Providers",         icon: Plug },
      { name: "Integrations",   page: "IntegrationSync",   icon: ArrowDownUp },
      { name: "Organization",   page: "OrgSettings",       icon: Globe },
      { name: "Tenants",        page: "AdminTenants",      icon: Building2,  minRole: "SuperAdmin" },
      { name: "Users & Roles",  page: "AdminUsers",        icon: Shield,     minRole: "SuperAdmin" },
      { name: "Data Imports",   page: "AdminImports",      icon: Upload,     minRole: "SuperAdmin" },
      { name: "System",         page: "Admin",             icon: MonitorCog, minRole: "SuperAdmin" },
    ],
  },
];

// ── Admin / customer admin portal ────────────────────────────────

const ADMIN_NAV = [
  { name: "Dashboard",     page: "AdminDashboard",  icon: LayoutDashboard },
  { name: "Support",       page: "Support",          icon: HelpCircle },
  // Internal-only: hidden during impersonation and for Admins whose
  // home tenant is not in INTERNAL_TENANT_IDS.
  { name: "Registrations", page: "Registrations",   icon: ClipboardList, permission: "VIEW_REGISTRATIONS" },
  { name: "Onboarding Review", page: "OnboardingReview", icon: ClipboardList, permission: "VIEW_ONBOARDING_REVIEW" },
  { name: "Sites",         page: "Sites",           icon: Building2 },
  { name: "Devices",       page: "Devices",         icon: Cpu },
  { name: "Incidents",     page: "Incidents",       icon: AlertOctagon },
  { name: "Map",           page: "DeploymentMap",   icon: Map },

  {
    group: "monitoring", label: "Monitoring", icon: Activity,
    children: [
      { name: "Alerts",     page: "Notifications",       icon: Bell },
      { name: "Events",     page: "Events",              icon: Activity },
      { name: "Network",    page: "NetworkDashboard",    icon: Radio },
      { name: "Recordings", page: "Recordings",          icon: Disc3 },
      { name: "Reports",    page: "Reports",             icon: FileText },
      { name: "Automation", page: "AutomationDashboard", icon: Zap },
    ],
  },

  {
    group: "deployment", label: "Deployment", icon: Rocket,
    children: [
      { name: "New Installation",        page: "Install",          icon: Zap },
      { name: "Onboard Site",           page: "OnboardSite",      icon: Building2 },
      { name: "Lines & Devices Import", page: "SubscriberImport", icon: FileSpreadsheet },
      { name: "Site Import",            page: "SiteImport",       icon: Upload },
    ],
  },

  {
    group: "network", label: "Network", icon: Layers,
    children: [
      { name: "Lines",   page: "Lines",  icon: Phone },
      { name: "E911",    page: "E911",   icon: MapPin },
    ],
  },

  {
    group: "settings", label: "Settings", icon: Settings,
    children: [
      { name: "Organization", page: "OrgSettings", icon: Globe },
    ],
  },
];

// ── Manager portal ────────────────────────────────────────────────

const MANAGER_NAV = [
  { name: "Dashboard",   page: "ManagerDashboard", icon: LayoutDashboard },
  { name: "Support",     page: "Support",           icon: HelpCircle },
  { name: "My Sites",    page: "Sites",            icon: Building2 },
  { name: "My Devices",  page: "Devices",          icon: Cpu },
  { name: "Incidents",   page: "Incidents",        icon: AlertOctagon },
  { name: "Map",         page: "DeploymentMap",    icon: Map },
  {
    group: "monitoring", label: "Monitoring", icon: Activity,
    children: [
      { name: "Lines",        page: "Lines",             icon: Phone },
      { name: "Events",       page: "Events",            icon: Activity },
      { name: "Network",      page: "NetworkDashboard",  icon: Radio },
      { name: "Recordings",   page: "Recordings",        icon: Disc3 },
      { name: "Reports",      page: "Reports",           icon: FileText },
    ],
  },
];

// ── User (view-only) portal ──────────────────────────────────────

const USER_NAV = [
  { name: "Status",   page: "UserDashboard",  icon: ShieldCheck },
  { name: "Support",  page: "Support",         icon: HelpCircle },
  { name: "Sites",    page: "Sites",           icon: Building2 },
  { name: "Map",      page: "DeploymentMap",   icon: Map },
];


// ── Data Entry / Import Operator portal ──────────────────────────
const DATAENTRY_NAV = [
  // Internal-only: hidden during impersonation and for DataEntry users
  // whose home tenant is not in INTERNAL_TENANT_IDS.
  { name: "Registrations", page: "Registrations", icon: ClipboardList, permission: "VIEW_REGISTRATIONS" },
  { name: "Customers",     page: "Customers",     icon: Users },
  { name: "Sites",         page: "Sites",         icon: Building2 },
  { name: "Devices",       page: "Devices",       icon: Cpu },

  {
    group: "deployment", label: "Deployment", icon: Rocket,
    children: [
      { name: "Site Import",               page: "SiteImport",         icon: Upload },
      { name: "Lines & Devices Import",    page: "SubscriberImport",   icon: FileSpreadsheet },
      { name: "Import Verification",       page: "ImportVerification", icon: CheckCircle },
      { name: "Unassigned Devices & SIMs", page: "ProvisioningQueue",  icon: Package },
    ],
  },
];


// ── Data Steward portal ──────────────────────────────────────────
// Superset of the DataEntry nav with the new triage queue surfaced
// at the top.  Hidden ``permission`` filter ensures the queue still
// disappears for users that lack VIEW_ONBOARDING_REVIEW.
const DATASTEWARD_NAV = [
  { name: "Onboarding Review", page: "OnboardingReview", icon: ClipboardList, permission: "VIEW_ONBOARDING_REVIEW" },
  { name: "Registrations",     page: "Registrations",    icon: ClipboardList, permission: "VIEW_REGISTRATIONS" },
  { name: "Customers",         page: "Customers",        icon: Users },
  { name: "Sites",             page: "Sites",            icon: Building2 },
  { name: "Devices",           page: "Devices",          icon: Cpu },

  {
    group: "deployment", label: "Deployment", icon: Rocket,
    children: [
      { name: "Site Import",               page: "SiteImport",         icon: Upload },
      { name: "Lines & Devices Import",    page: "SubscriberImport",   icon: FileSpreadsheet },
      { name: "Import Verification",       page: "ImportVerification", icon: CheckCircle },
      { name: "Unassigned Devices & SIMs", page: "ProvisioningQueue",  icon: Package },
    ],
  },
];


// ═══════════════════════════════════════════════════════════════════
// NAV FILTERING UTILITIES
// ═══════════════════════════════════════════════════════════════════

function isItemVisible(item, level, can) {
  if (item.featureFlag && !FEATURE_FLAGS[item.featureFlag]) return false;
  if (item.minRole && level < ROLE_LEVEL[item.minRole]) return false;
  // ``permission`` is the internal-only escape hatch — items marked
  // with a permission disappear from the nav when can() returns
  // false.  This hides Registrations during SuperAdmin impersonation
  // and from customer-tenant Admin/DataEntry users without changing
  // the role-based grants in permissions.json.
  if (item.permission && !can(item.permission)) return false;
  return true;
}

function filterNav(nav, level, can) {
  return nav
    .filter(item => isItemVisible(item, level, can))
    .map(item => {
      if (item.group && item.children) {
        const kids = item.children.filter(c => isItemVisible(c, level, can));
        if (kids.length === 0) return null;
        return { ...item, children: kids };
      }
      return item;
    })
    .filter(Boolean);
}

function getChildPages(item) {
  if (item.children) return item.children.map(c => c.page);
  return [];
}


// ═══════════════════════════════════════════════════════════════════
// SIDEBAR COMPONENT
// ═══════════════════════════════════════════════════════════════════

function Sidebar({ currentPageName, onClose, onChangePassword, onViewAs }) {
  const { user, logout, impersonation, stopImpersonation, isRealSuperAdmin, can } = useAuth();

  const userRole = user?.role || "User";
  const level = roleLevel(userRole);
  const isSuperAdmin = level >= ROLE_LEVEL.SuperAdmin;
  const isAdmin = level >= ROLE_LEVEL.Admin;
  const isManager = level >= ROLE_LEVEL.Manager;
  const isNOC = isSuperAdmin;

  const isDataEntry = userRole === "DataEntry";
  const isDataSteward = userRole === "DataSteward";
  const navSource = isSuperAdmin
    ? NOC_NAV
    : isAdmin
    ? ADMIN_NAV
    : isManager
    ? MANAGER_NAV
    : isDataSteward
    ? DATASTEWARD_NAV
    : isDataEntry
    ? DATAENTRY_NAV
    : USER_NAV;
  const visibleNav = useMemo(() => filterNav(navSource, level, can), [navSource, level, can]);

  // Track which groups are expanded — auto-expand the one containing the active page
  const [expanded, setExpanded] = useState(() => {
    const open = {};
    navSource.forEach(item => {
      if (item.group && item.children?.some(c => c.page === currentPageName)) {
        open[item.group] = true;
      }
    });
    return open;
  });

  // Keep the active group expanded when route changes
  useEffect(() => {
    navSource.forEach(item => {
      if (item.group && item.children?.some(c => c.page === currentPageName)) {
        setExpanded(prev => ({ ...prev, [item.group]: true }));
      }
    });
  }, [currentPageName, navSource]);

  const toggleGroup = (group) => {
    setExpanded(prev => ({ ...prev, [group]: !prev[group] }));
  };

  const accentColor = isNOC ? "red" : "slate";

  return (
    <aside className="flex flex-col h-full bg-gray-950 text-gray-300 w-[248px]">
      {/* ── Branding ── */}
      <div className="px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isNOC ? "bg-red-600" : "bg-slate-700"}`}>
            <Shield className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-[15px] font-bold text-white leading-none tracking-tight">
              True911<span className={isNOC ? "text-red-500" : "text-slate-500"}>+</span>
            </div>
            <div className="text-[9px] text-gray-500 tracking-[0.18em] uppercase mt-0.5">
              {isSuperAdmin ? "NOC Operations" : isAdmin ? "Admin Portal" : isDataSteward ? "Steward Portal" : isDataEntry ? "Import Portal" : "Customer Portal"}
            </div>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-800 text-gray-500 lg:hidden">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ── User card ── */}
      {user && (
        <div className="mx-3 mb-3 px-3 py-2.5 rounded-lg bg-gray-900/70 border border-gray-800/60">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-full bg-gray-800 flex items-center justify-center text-xs font-semibold text-gray-400">
              {user.name?.charAt(0)?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-gray-200 truncate">{user.name}</div>
              <div className="text-[10px] text-gray-500 truncate">{user.email}</div>
            </div>
            <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${ROLE_BADGE[userRole] || ROLE_BADGE.User}`}>
              {userRole}
            </span>
          </div>
        </div>
      )}

      {/* ── Navigation ── */}
      <nav className="flex-1 px-3 pb-3 overflow-y-auto space-y-0.5 scrollbar-thin">
        {visibleNav.map((item, idx) => {
          // ── Top-level link ──
          if (!item.group) {
            return (
              <NavLink
                key={item.page}
                item={item}
                active={currentPageName === item.page}
                accent={accentColor}
                onClick={onClose}
              />
            );
          }

          // ── Collapsible group ──
          const isOpen = !!expanded[item.group];
          const hasActiveChild = item.children.some(c => c.page === currentPageName);

          return (
            <div key={item.group} className="mt-1.5">
              <button
                onClick={() => toggleGroup(item.group)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-colors ${
                  hasActiveChild
                    ? "text-gray-200 bg-gray-800/50"
                    : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/30"
                }`}
              >
                <item.icon className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                <span className="flex-1 text-left">{item.label}</span>
                <ChevronRight
                  className={`w-3 h-3 transition-transform duration-200 ${isOpen ? "rotate-90" : ""}`}
                />
              </button>

              {/* Children */}
              <div
                className={`overflow-hidden transition-all duration-200 ease-in-out ${
                  isOpen ? "max-h-[500px] opacity-100" : "max-h-0 opacity-0"
                }`}
              >
                <div className="ml-3 pl-3 border-l border-gray-800/60 mt-0.5 space-y-0.5">
                  {item.children.map(child => (
                    <NavLink
                      key={child.page}
                      item={child}
                      active={currentPageName === child.page}
                      accent={accentColor}
                      onClick={onClose}
                      nested
                    />
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </nav>

      {/* ── Footer ── */}
      <div className="px-3 py-3 border-t border-gray-800/60">
        {user && (
          <div className="space-y-0.5">
            {isRealSuperAdmin && !impersonation && (
              <FooterButton onClick={onViewAs} icon={UserCog} label="View As..." color="purple" />
            )}
            {impersonation && (
              <FooterButton
                onClick={() => { stopImpersonation(); window.location.reload(); }}
                icon={XCircle} label="Exit Impersonation" color="red"
              />
            )}
            <FooterButton onClick={onChangePassword} icon={KeyRound} label="Change Password" />
            <FooterButton onClick={logout} icon={LogOut} label="Sign Out" />
          </div>
        )}
        <div className="mt-3 flex items-center gap-1.5 justify-center">
          <span className="text-[9px] text-blue-400 font-bold tracking-wide">Made in USA</span>
          <span className="text-gray-700 text-[9px]">·</span>
          <span className="text-[9px] text-gray-600">NDAA-TAA</span>
        </div>
        <div className="text-[9px] text-gray-600 text-center mt-0.5">© 2026 Manley Solutions</div>
      </div>
    </aside>
  );
}


// ── NavLink (reusable for top-level and nested items) ───────────

function NavLink({ item, active, accent, onClick, nested = false }) {
  const Icon = item.icon;
  const activeClasses = accent === "red"
    ? "bg-red-600/15 text-red-400 font-semibold"
    : "bg-slate-700/40 text-slate-200 font-semibold";

  return (
    <Link
      to={createPageUrl(item.page)}
      onClick={onClick}
      className={`group flex items-center gap-2.5 rounded-lg transition-all duration-150 ${
        nested ? "px-2.5 py-1.5 text-[12.5px]" : "px-3 py-2 text-[13px]"
      } ${
        active
          ? activeClasses
          : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
      }`}
    >
      <Icon className={`flex-shrink-0 ${nested ? "w-3.5 h-3.5" : "w-4 h-4"} ${
        active
          ? accent === "red" ? "text-red-400" : "text-slate-300"
          : "text-gray-500 group-hover:text-gray-400"
      }`} />
      <span className="truncate">{item.name}</span>
      {active && (
        <div className={`ml-auto w-1.5 h-1.5 rounded-full flex-shrink-0 ${
          accent === "red" ? "bg-red-500" : "bg-slate-400"
        }`} />
      )}
    </Link>
  );
}


// ── Footer button ───────────────────────────────────────────────

function FooterButton({ onClick, icon: Icon, label, color }) {
  const colorStyles = {
    purple: "text-purple-400 hover:text-purple-300 hover:bg-purple-500/10",
    red: "text-red-400 hover:text-red-300 hover:bg-red-500/10",
  };
  const baseStyle = colorStyles[color] || "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50";

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg transition-colors ${baseStyle}`}
    >
      <Icon className="w-3.5 h-3.5" /> {label}
    </button>
  );
}


// ═══════════════════════════════════════════════════════════════════
// CHANGE PASSWORD MODAL
// ═══════════════════════════════════════════════════════════════════

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
    if (newPwd !== confirmPwd) { setError("Passwords do not match."); return; }
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


// ═══════════════════════════════════════════════════════════════════
// VIEW AS MODAL (SuperAdmin)
// ═══════════════════════════════════════════════════════════════════

function ViewAsModal({ onClose }) {
  const { startImpersonation } = useAuth();
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState("");
  const [selectedRole, setSelectedRole] = useState("Admin");
  const [search, setSearch] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const data = await apiFetch("/admin/tenants");
        setTenants(data);
      } catch { setTenants([]); }
      setLoading(false);
    })();
  }, []);

  const filtered = tenants.filter(t => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (t.name || "").toLowerCase().includes(q) || (t.tenant_id || "").toLowerCase().includes(q);
  });

  const handleStart = () => {
    if (!selectedTenant) return;
    const t = tenants.find(x => x.tenant_id === selectedTenant);
    startImpersonation(selectedTenant, t?.name || selectedTenant, selectedRole);
    toast.success(`Now viewing as ${selectedRole} in ${t?.name || selectedTenant}`);
    onClose();
    window.location.reload();
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-[80] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <UserCog className="w-5 h-5 text-purple-600" /> View As
          </h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-xs text-gray-500 mb-4">
          Temporarily view the portal as another role and tenant. Actions are read-only while impersonating.
        </p>
        <div className="mb-3">
          <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Tenant / Account</label>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search tenants..."
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <div className="max-h-40 overflow-y-auto border border-gray-200 rounded-lg">
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-gray-400 py-4 justify-center"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</div>
            ) : filtered.length === 0 ? (
              <div className="text-xs text-gray-400 text-center py-4">No tenants found.</div>
            ) : filtered.map(t => (
              <button
                key={t.tenant_id}
                onClick={() => setSelectedTenant(t.tenant_id)}
                className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                  selectedTenant === t.tenant_id ? "bg-purple-50 text-purple-700 font-medium" : "hover:bg-gray-50 text-gray-700"
                }`}
              >
                {t.name} <span className="text-[10px] text-gray-400">({t.tenant_id})</span>
              </button>
            ))}
          </div>
        </div>
        <div className="mb-4">
          <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">View as Role</label>
          <div className="flex gap-2">
            {["Admin", "Manager", "DataEntry", "User"].map(r => (
              <button
                key={r} onClick={() => setSelectedRole(r)}
                className={`flex-1 py-2 rounded-lg text-xs font-semibold border transition-colors ${
                  selectedRole === r
                    ? "bg-purple-600 text-white border-purple-600"
                    : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
                }`}
              >{r}</button>
            ))}
          </div>
        </div>
        <button
          onClick={handleStart} disabled={!selectedTenant}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-40 text-white text-sm font-medium rounded-lg"
        >
          <Eye className="w-4 h-4" /> Start Impersonation
        </button>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// APP LAYOUT
// ═══════════════════════════════════════════════════════════════════

const PUBLIC_PAGES = ["AuthGate"];

function AppLayout({ children, currentPageName }) {
  const { user, ready, impersonation, stopImpersonation, isRealSuperAdmin } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showChangePwd, setShowChangePwd] = useState(false);
  const [showViewAs, setShowViewAs] = useState(false);

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
    window.location.href = "/login";
    return null;
  }

  const isNOC = roleLevel(user.role) >= ROLE_LEVEL.Admin;

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Desktop sidebar */}
      <div className="hidden lg:flex flex-col fixed inset-y-0 left-0 w-[248px] z-30">
        <Sidebar
          currentPageName={currentPageName}
          onChangePassword={() => setShowChangePwd(true)}
          onViewAs={() => setShowViewAs(true)}
        />
      </div>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <>
          <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={() => setMobileOpen(false)} />
          <div className="fixed inset-y-0 left-0 w-[248px] z-40 flex flex-col lg:hidden shadow-2xl">
            <Sidebar
              currentPageName={currentPageName}
              onClose={() => setMobileOpen(false)}
              onChangePassword={() => { setShowChangePwd(true); setMobileOpen(false); }}
              onViewAs={() => { setShowViewAs(true); setMobileOpen(false); }}
            />
          </div>
        </>
      )}

      {showChangePwd && <ChangePasswordModal onClose={() => setShowChangePwd(false)} />}
      {showViewAs && <ViewAsModal onClose={() => setShowViewAs(false)} />}

      <div className="flex-1 lg:ml-[248px] flex flex-col min-h-screen">
        {/* Mobile header */}
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

        {/* Impersonation banner */}
        {impersonation && (
          <div className="bg-purple-600 text-white px-4 py-2 flex items-center justify-between text-sm sticky top-0 z-20">
            <div className="flex items-center gap-2">
              <Eye className="w-4 h-4" />
              <span className="font-medium">
                Viewing as {impersonation.role} in {impersonation.tenantName || impersonation.tenantId}
              </span>
              <span className="text-purple-200 text-xs">| Read-only mode</span>
            </div>
            <button
              onClick={() => { stopImpersonation(); window.location.reload(); }}
              className="flex items-center gap-1.5 px-3 py-1 bg-white/20 hover:bg-white/30 rounded-lg text-xs font-semibold transition-colors"
            >
              <XCircle className="w-3.5 h-3.5" /> Exit
            </button>
          </div>
        )}

        <main className="flex-1">{children}</main>
      </div>

      <Toaster position="top-right" />

      <style>{`
        :root { --font-sans: 'Inter', system-ui, -apple-system, sans-serif; }
        body { font-family: var(--font-sans); }
        * { box-sizing: border-box; }
        .scrollbar-thin::-webkit-scrollbar { width: 4px; }
        .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 4px; }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
      `}</style>
    </div>
  );
}

export default function Layout({ children, currentPageName }) {
  return <AppLayout children={children} currentPageName={currentPageName} />;
}
