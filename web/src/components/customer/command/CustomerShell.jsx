import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Eye, XCircle, ChevronDown, KeyRound, LogOut, HelpCircle, LayoutDashboard, Inbox, Building2 } from "lucide-react";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

// ════════════════════════════════════════════════════════════════════
// CustomerShell — the CUSTOMER_* roles' application frame (internal roles keep
// the existing sidebar).  ONE navigation system: a top application bar on
// desktop, a bottom bar on mobile.  Navigation items are REGISTERED by the page
// for the workspace views that actually exist (Overview / Action Center /
// Locations, switched with ?view=), so there is never a dead, "coming soon" or
// fake destination.
// ════════════════════════════════════════════════════════════════════

const NavCtx = createContext({ items: [], setItems: () => {} });
// Production brand assets (web/public/brand) — never the reference concept boards.
export const BEACON_REVERSED = "/brand/true911-beacon-reversed.svg";
const APP_TITLE = "True911 — Life-Safety Command Center";
const NAV_ICON = { overview: LayoutDashboard, actions: Inbox, locations: Building2 };

// Page-side hook: declare the real sections this page renders.
// Each item: { id, label, icon, href, current, onSelect }.
export function useCustomerNav(items) {
  const { setItems } = useContext(NavCtx);
  const key = items.map((i) => `${i.id}:${i.current ? 1 : 0}`).join("|");
  useEffect(() => {
    setItems(items);
    return () => setItems([]);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
}

function select(e, item) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;   // let new-tab work
  e.preventDefault();
  item.onSelect?.();
}

export default function CustomerShell({ user, impersonation, onExitImpersonation, onChangePassword, onLogout, children }) {
  const [items, setItemsState] = useState([]);
  const setItems = useCallback((v) => setItemsState(v), []);
  const ctx = useMemo(() => ({ items, setItems }), [items, setItems]);
  // the customer application's tab title; the general brand title is restored on exit
  useEffect(() => {
    const prev = document.title;
    document.title = APP_TITLE;
    return () => { document.title = prev; };
  }, []);

  return (
    <NavCtx.Provider value={ctx}>
      <div className="t911-customer min-h-screen bg-slate-100/70">
        <a href="#cc-main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[2000] focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:shadow">Skip to content</a>

        {impersonation && (
          <div className="bg-purple-700 text-white px-4 py-2 flex items-center justify-between text-sm">
            <span className="flex items-center gap-2"><Eye className="w-4 h-4" aria-hidden="true" />Viewing as {impersonation.role} in {impersonation.tenantName || impersonation.tenantId}<span className="text-purple-200 text-xs">| Read-only mode</span></span>
            <button onClick={onExitImpersonation} className="cc-focus flex items-center gap-1.5 px-3 py-1 bg-white/20 hover:bg-white/30 rounded-lg text-xs font-semibold"><XCircle className="w-3.5 h-3.5" aria-hidden="true" />Exit</button>
          </div>
        )}

        <header className="sticky top-0 z-40 bg-slate-950 text-white shadow-[0_1px_0_rgba(255,255,255,0.04)]">
          <div className="mx-auto max-w-[1440px] h-14 px-4 sm:px-6 flex items-center gap-4">
            <div className="flex items-center gap-2.5 min-w-0">
              {/* Beacon mark — decorative here: the wordmark beside it carries the name */}
              <img src={BEACON_REVERSED} alt="" aria-hidden="true" width="34" height="34" className="w-[34px] h-[34px] flex-shrink-0" />
              <span className="leading-none min-w-0">
                <span className="block text-[17px] font-bold tracking-tight">True<span className="text-[#60A9FF]">911</span></span>
                <span className="block text-[10.5px] font-medium uppercase tracking-[0.14em] text-slate-300 mt-1 truncate">Life-Safety Command Center</span>
              </span>
            </div>

            {items.length > 1 && (
              <nav aria-label="Primary" className="hidden md:flex items-center gap-1 ml-4">
                {items.map((i) => (
                  <a key={i.id} href={i.href} onClick={(e) => select(e, i)}
                    aria-current={i.current ? "page" : undefined}
                    className={`cc-focus-dark px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors ${i.current ? "bg-white/10 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}>
                    {i.label}
                  </a>
                ))}
              </nav>
            )}

            <div className="ml-auto">
              <DropdownMenu>
                <DropdownMenuTrigger className="cc-focus-dark flex items-center gap-2 rounded-lg px-2 py-1.5 min-h-[40px] hover:bg-white/5">
                  <span className="inline-flex w-7 h-7 items-center justify-center rounded-full bg-white/10 text-[12px] font-semibold">{user?.name?.charAt(0)?.toUpperCase() || "?"}</span>
                  <span className="hidden sm:block text-[12.5px] text-slate-300 max-w-[160px] truncate">{user?.name}</span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                  <span className="sr-only">Account menu</span>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  <DropdownMenuLabel className="font-normal">
                    <p className="text-[13px] font-medium text-slate-900 truncate">{user?.name}</p>
                    <p className="text-[11.5px] text-slate-500 truncate">{user?.email}</p>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={onChangePassword}><KeyRound className="w-4 h-4 mr-2" aria-hidden="true" />Change password</DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <a href="mailto:support@manleysolutions.com"><HelpCircle className="w-4 h-4 mr-2" aria-hidden="true" />Help — support@manleysolutions.com</a>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={onLogout}><LogOut className="w-4 h-4 mr-2" aria-hidden="true" />Sign out</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <main id="cc-main" tabIndex={-1} className="outline-none pb-20 md:pb-0">{children}</main>

        {items.length > 1 && (
          <nav aria-label="Primary" className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white/95 backdrop-blur border-t border-slate-200 pb-[env(safe-area-inset-bottom)]">
            <ul className="flex">
              {items.map((i) => {
                const Icon = NAV_ICON[i.icon] || LayoutDashboard;
                const on = Boolean(i.current);
                return (
                  <li key={i.id} className="flex-1">
                    <a href={i.href} onClick={(e) => select(e, i)} aria-current={on ? "page" : undefined}
                      className={`cc-focus flex flex-col items-center justify-center gap-0.5 min-h-[56px] text-[11px] font-medium ${on ? "text-slate-900" : "text-slate-500"}`}>
                      <Icon className="w-5 h-5" aria-hidden="true" />{i.label}
                      {i.badge ? <span className="sr-only">, {i.badge} waiting</span> : null}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}
      </div>
    </NavCtx.Provider>
  );
}
