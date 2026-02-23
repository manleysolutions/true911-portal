import { useState } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { Shield, LayoutDashboard, Map, Building2, RefreshCw, FileText, Settings, Menu, X, LogOut, Box, AlertOctagon, Bell } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";

const NAV_ITEMS = [
  { name: "Overview", page: "Overview", icon: LayoutDashboard },
  { name: "Deployment Map", page: "DeploymentMap", icon: Map },
  { name: "Sites", page: "Sites", icon: Building2 },
  { name: "Containers (CSAS)", page: "Containers", icon: Box },
  { name: "Incidents", page: "Incidents", icon: AlertOctagon },
  { name: "Sync Status", page: "SyncStatus", icon: RefreshCw },
  { name: "Reports", page: "Reports", icon: FileText },
  { name: "Notifications", page: "Notifications", icon: Bell, adminOnly: true },
  { name: "Admin", page: "Admin", icon: Settings, adminOnly: true },
];

const ROLE_BADGE = {
  Admin: "bg-red-100 text-red-700 border-red-200",
  Manager: "bg-blue-100 text-blue-700 border-blue-200",
  User: "bg-gray-100 text-gray-600 border-gray-200",
};

function Sidebar({ currentPageName, onClose }) {
  const { user, logout, can } = useAuth();
  const visibleNav = NAV_ITEMS.filter(item => !item.adminOnly || can('VIEW_ADMIN'));

  return (
    <aside className="flex flex-col h-full bg-white border-r border-gray-200 w-60">
      <div className="px-5 py-5 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-red-600 rounded-lg flex items-center justify-center">
            <Shield className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-base font-bold text-gray-900 leading-none">True911<span className="text-red-600">+</span></div>
            <div className="text-[10px] text-gray-400 tracking-widest uppercase mt-0.5">NOC Portal</div>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400 lg:hidden">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

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
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${ROLE_BADGE[user.role] || ROLE_BADGE.User}`}>
              {user.role}
            </span>
          </div>
        </div>
      )}

      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        {visibleNav.map(({ name, page, icon: Icon }) => {
          const active = currentPageName === page;
          return (
            <Link
              key={page}
              to={createPageUrl(page)}
              onClick={onClose}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all ${
                active
                  ? 'bg-red-50 text-red-700 font-semibold'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {name}
              {active && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-red-600" />}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-4 border-t border-gray-100">
        {user && (
          <button
            onClick={logout}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign Out
          </button>
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

const PUBLIC_PAGES = ["AuthGate"];

function AppLayout({ children, currentPageName }) {
  const { user, ready } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

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

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <div className="hidden lg:flex flex-col fixed inset-y-0 left-0 w-60 z-30">
        <Sidebar currentPageName={currentPageName} />
      </div>

      {mobileOpen && (
        <>
          <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setMobileOpen(false)} />
          <div className="fixed inset-y-0 left-0 w-60 z-40 flex flex-col lg:hidden shadow-xl">
            <Sidebar currentPageName={currentPageName} onClose={() => setMobileOpen(false)} />
          </div>
        </>
      )}

      <div className="flex-1 lg:ml-60 flex flex-col min-h-screen">
        <div className="lg:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200 sticky top-0 z-20">
          <button onClick={() => setMobileOpen(true)} className="p-2 rounded-lg hover:bg-gray-100">
            <Menu className="w-5 h-5 text-gray-700" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-red-600 rounded flex items-center justify-center">
              <Shield className="w-3 h-3 text-white" />
            </div>
            <span className="font-bold text-gray-900">True911<span className="text-red-600">+</span></span>
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
