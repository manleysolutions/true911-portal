import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, Building2, Cpu, RefreshCw, ChevronRight,
  Clock, Wifi, WifiOff, MapPin, AlertTriangle,
  CheckCircle2, Search, ChevronDown, ChevronUp,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import {
  statusLabel,
  statusColor,
  toCanonical,
  getAttentionCounts,
  getAttentionFeed,
  customerSitePresentation,
  getCustomerCounts,
  toCustomerStatus,
  isCustomerRole,
  CUSTOMER_STATUS,
} from "@/lib/attention";

// ═══════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// UserDashboard is a customer-facing surface (the role landing target
// for `User`).  The portal is positioned as a deployment / inventory
// management platform, NOT a NOC — so we use the customer-facing
// presentation layer (inventory / reporting language).  Internal
// roles never reach this page, but the role guard is kept defensively.
function friendlyStatus(site, role) {
  const pres = customerSitePresentation(site, role);
  if (pres) return pres.label;
  return statusLabel(toCanonical(site), "user");
}

function siteColor(site, role) {
  const pres = customerSitePresentation(site, role);
  if (pres) return pres;
  return statusColor(toCanonical(site));
}


// ═══════════════════════════════════════════════════════════════════
// STATUS CARD (large, simple)
// ═══════════════════════════════════════════════════════════════════

function StatusCard({ label, value, icon: Icon, color = "text-gray-400", bgColor = "bg-white", borderColor }) {
  return (
    <div className={`${bgColor} rounded-xl border ${borderColor || "border-gray-200"} p-5 text-center`}>
      <Icon className={`w-5 h-5 ${color} mx-auto mb-2`} />
      <p className="text-3xl font-bold text-gray-900 tabular-nums">{value ?? "—"}</p>
      <p className="text-xs text-gray-500 mt-1 font-medium">{label}</p>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// CUSTOMER SYSTEM BANNER
//
// Uses inventory + telemetry language, never monitoring language.
// Five buckets feed this banner:
//   reporting           — device IS sending live telemetry
//   inventory           — registered location, no telemetry yet
//                         (neutral; reporting begins after the
//                          carrier/API integration is established)
//   attention_needed    — specific actionable signal
//   not_reporting       — was reporting, has stopped, OR open
//                         critical incident.  Amber, NOT red:
//                         telemetry absence ≠ confirmed outage.
//   integration_pending — explicit "awaiting carrier/API integration"
//
// Internal roles see the existing SystemStatusBanner below, unchanged.
// ═══════════════════════════════════════════════════════════════════

function CustomerSystemBanner({ counts }) {
  const {
    total,
    reporting,
    inventory,
    attention_needed: attentionNeeded,
    not_reporting: notReporting,
  } = counts;

  const inventoryFragment = (() => {
    const parts = [];
    if (reporting > 0) {
      parts.push(`${reporting} reporting`);
    }
    if (inventory > 0) {
      parts.push(`${inventory} registered, awaiting integration`);
    }
    return parts.length ? parts.join(" · ") + "." : "";
  })();

  if (notReporting > 0) {
    // Amber, NOT red.  Absence of telemetry alone is not an outage —
    // the device may still be operational in the field.  Real outages
    // surface separately through the incident feed.
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
            <WifiOff className="w-5 h-5 text-amber-500" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-amber-800">
              {notReporting} location{notReporting > 1 ? "s" : ""}
              {" "}not currently reporting
            </p>
            <p className="text-[13px] text-amber-700 mt-0.5">
              {inventoryFragment || `Out of ${total} total location${total !== 1 ? "s" : ""}.`}
              {" "}A device may still be operational on site even when telemetry is absent.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (attentionNeeded > 0) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-amber-800">
              {attentionNeeded} location{attentionNeeded > 1 ? "s" : ""}
              {" "}need{attentionNeeded === 1 ? "s" : ""} attention
            </p>
            <p className="text-[13px] text-amber-600 mt-0.5">
              {inventoryFragment || "All other locations are in their expected state."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (inventory > 0 && reporting > 0) {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-emerald-800">
              {reporting} location{reporting > 1 ? "s are" : " is"} reporting telemetry
            </p>
            <p className="text-[13px] text-emerald-700 mt-0.5">
              {inventory} additional location{inventory > 1 ? "s are" : " is"} registered, awaiting carrier or API integration before reporting begins.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (inventory > 0) {
    // No reporting devices yet — every location is still an inventory
    // record.  Neutral slate.  Not an alarm.
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
            <Clock className="w-5 h-5 text-slate-500" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-slate-800">
              {inventory} location{inventory > 1 ? "s" : ""}
              {" "}registered
            </p>
            <p className="text-[13px] text-slate-600 mt-0.5">
              Reporting will begin once carrier or API integration is established for each device.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (reporting > 0) {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-emerald-800">
              All {reporting} location{reporting > 1 ? "s are" : " is"} reporting telemetry
            </p>
            <p className="text-[13px] text-emerald-600 mt-0.5">
              True911 is receiving live telemetry from every device.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
          <MapPin className="w-5 h-5 text-slate-400" />
        </div>
        <div>
          <p className="text-[15px] font-semibold text-slate-700">No locations registered yet</p>
          <p className="text-[13px] text-slate-500 mt-0.5">
            Your registered locations and devices will appear here once added.
          </p>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// SYSTEM STATUS BANNER  (legacy / internal fallback — unchanged)
// ═══════════════════════════════════════════════════════════════════

function SystemStatusBanner({ counts }) {
  const attentionCount = (counts.attention || 0) + (counts.offline || 0);
  const offlineCount = counts.offline || 0;
  const total = counts.total || 0;

  if (offlineCount > 0) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
            <WifiOff className="w-5 h-5 text-red-500" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-red-800">
              {offlineCount} site{offlineCount > 1 ? "s" : ""} offline
            </p>
            <p className="text-[13px] text-red-600 mt-0.5">
              {attentionCount > offlineCount
                ? `${attentionCount - offlineCount} additional site${attentionCount - offlineCount > 1 ? "s" : ""} need attention. ${total - attentionCount} site${total - attentionCount !== 1 ? "s" : ""} working normally.`
                : `${total - offlineCount} of ${total} site${total !== 1 ? "s" : ""} working normally.`
              }
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (attentionCount > 0) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-amber-800">
              {attentionCount} site{attentionCount > 1 ? "s" : ""} need{attentionCount === 1 ? "s" : ""} attention
            </p>
            <p className="text-[13px] text-amber-600 mt-0.5">
              {total - attentionCount} of {total} site{total !== 1 ? "s" : ""} working normally. No sites are fully offline.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
          <CheckCircle2 className="w-5 h-5 text-emerald-500" />
        </div>
        <div>
          <p className="text-[15px] font-semibold text-emerald-800">All systems working</p>
          <p className="text-[13px] text-emerald-600 mt-0.5">
            {total > 0 ? `${total} site${total !== 1 ? "s" : ""} connected and reporting normally.` : "No sites deployed yet."}
          </p>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// ISSUES LIST (simplified, no actions)
// ═══════════════════════════════════════════════════════════════════

function IssuesList({ siteSummaries = [], incidents = [], role }) {
  const customerView = isCustomerRole(role);

  const items = useMemo(() => {
    const list = [];

    // Active incidents — always shown to anyone reading this surface.
    incidents.filter(i => !["resolved", "dismissed", "closed"].includes(i.status)).forEach(inc => {
      list.push({
        id: `inc-${inc.incident_id || inc.id}`,
        severity: inc.severity === "critical" ? "critical" : "warning",
        title: inc.summary,
        site: inc.site_name || inc.site_id,
        siteId: inc.site_id,
        time: inc.opened_at,
      });
    });

    // Sites needing attention (not already covered by an incident).
    //
    // Customer view: skip Inventory sites — a registered location
    // that hasn't reported yet is neither good nor bad, it's just an
    // inventory record.  Only Not Reporting + Attention Needed
    // surface here, and Not Reporting is "warning" (not "critical")
    // because telemetry absence alone is not a confirmed outage.
    //
    // Internal view: keep the existing behavior so admins still see
    // every needs_attention row.
    const incSiteIds = new Set(
      incidents
        .filter(i => !["resolved", "dismissed", "closed"].includes(i.status))
        .map(i => i.site_id)
    );

    siteSummaries
      .filter(s => s.needs_attention && !incSiteIds.has(s.site_id))
      .forEach(s => {
        let title;
        let severity;

        if (customerView) {
          const key = toCustomerStatus(s);
          if (key === CUSTOMER_STATUS.INVENTORY) {
            // Inventory record — never goes in the issues list.
            return;
          }
          if (key === CUSTOMER_STATUS.NOT_REPORTING) {
            title = "Device stopped reporting telemetry";
            severity = "warning";
          } else if (s.stale_devices > 0) {
            title = "A device has stopped reporting";
            severity = "warning";
          } else if (s.overdue_tasks > 0) {
            title = "Maintenance scheduled";
            severity = "warning";
          } else {
            title = "Attention needed";
            severity = "warning";
          }
        } else {
          if (s.status === "Not Connected") {
            title = "Site offline";
            severity = "critical";
          } else if (s.stale_devices > 0) {
            title = "Device not reporting";
            severity = "warning";
          } else if (s.overdue_tasks > 0) {
            title = "Maintenance overdue";
            severity = "warning";
          } else {
            title = "Needs attention";
            severity = "warning";
          }
        }

        list.push({
          id: `site-${s.site_id}`,
          severity,
          title,
          site: s.site_name,
          siteId: s.site_id,
          time: s.last_checkin,
        });
      });

    list.sort((a, b) => {
      const so = { critical: 0, warning: 1 };
      return (so[a.severity] ?? 2) - (so[b.severity] ?? 2);
    });
    return list;
  }, [siteSummaries, incidents, customerView]);

  if (items.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900">Issues Requiring Attention</h2>
      </div>
      <div className="divide-y divide-gray-50 max-h-[360px] overflow-y-auto">
        {items.slice(0, 8).map(item => (
          <Link
            key={item.id}
            to={createPageUrl("SiteDetail") + `?site=${item.siteId}`}
            className="flex items-center gap-3 px-5 py-3.5 hover:bg-gray-50 transition-colors"
          >
            <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
              item.severity === "critical" ? "bg-red-500" : "bg-amber-500"
            }`} />
            <div className="flex-1 min-w-0">
              <p className="text-[13px] text-gray-900 font-medium">{item.title}</p>
              <p className="text-[11px] text-gray-400 mt-0.5">{item.site}</p>
            </div>
            {item.time && <span className="text-[11px] text-gray-400 flex-shrink-0">{timeSince(item.time)}</span>}
            <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />
          </Link>
        ))}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// MAP PREVIEW
// ═══════════════════════════════════════════════════════════════════

// Map marker color by customer-status key — no red on this surface.
// Inventory sites are slate (neutral), not-reporting sites are amber
// (informative, not alarming).  Real outages surface separately
// through the incident feed, not as a baked-in marker color.
const _MAP_DOT_COLOR = {
  reporting:           "bg-emerald-500",
  inventory:           "bg-slate-400",
  attention_needed:    "bg-amber-500",
  not_reporting:       "bg-amber-500",
  integration_pending: "bg-blue-500",
};

function MapPreview({ siteSummaries = [], role }) {
  const customerView = isCustomerRole(role);
  const total = siteSummaries.length;

  // Customer-bucketed counts for the legend row underneath the map.
  const counts = useMemo(() => getCustomerCounts(siteSummaries), [siteSummaries]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900">Site Locations</h2>
        <Link to={createPageUrl("DeploymentMap")} className="text-[11px] text-red-600 hover:text-red-700 font-medium flex items-center gap-0.5">
          Full Map <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
      <div className="p-5">
        <div className="relative h-40 bg-gray-50 rounded-lg overflow-hidden mb-4 border border-gray-100">
          <div className="absolute inset-0 opacity-10">
            <svg width="100%" height="100%" className="text-gray-300">
              {[...Array(8)].map((_, i) => (
                <line key={`h${i}`} x1="0" y1={`${(i+1)*12.5}%`} x2="100%" y2={`${(i+1)*12.5}%`} stroke="currentColor" strokeWidth="0.5" />
              ))}
              {[...Array(12)].map((_, i) => (
                <line key={`v${i}`} x1={`${(i+1)*8.33}%`} y1="0" x2={`${(i+1)*8.33}%`} y2="100%" stroke="currentColor" strokeWidth="0.5" />
              ))}
            </svg>
          </div>
          {siteSummaries.slice(0, 25).map((site, i) => {
            // Customer view uses the disambiguated bucket so imported
            // sites stop showing as alarming red.  Internal view keeps
            // the existing simple Working/Attention/Offline split.
            let dotClass;
            let pulse;
            if (customerView) {
              const key = toCustomerStatus(site);
              dotClass = _MAP_DOT_COLOR[key] || "bg-slate-400";
              // No pulse animation on customer surfaces — pulsing
              // implies an alarming live signal and conflicts with
              // the inventory model.  Real outages animate via the
              // incident feed instead.
              pulse = false;
            } else {
              const isOffline = site.status === "Not Connected" || site.critical_incidents > 0;
              const isWarn = site.needs_attention && !isOffline;
              dotClass = isOffline ? "bg-red-500" : isWarn ? "bg-amber-500" : "bg-emerald-500";
              pulse = isOffline;
            }
            const x = 6 + ((i * 37 + 13) % 88);
            const y = 8 + ((i * 53 + 7) % 84);
            return (
              <div key={site.site_id}
                className={`absolute w-3 h-3 rounded-full ${dotClass} border-2 border-white shadow-sm ${pulse ? "animate-pulse" : ""}`}
                style={{ left: `${x}%`, top: `${y}%` }} title={site.site_name} />
            );
          })}
          {total === 0 && <div className="absolute inset-0 flex items-center justify-center"><p className="text-[11px] text-gray-400">No sites yet</p></div>}
        </div>
        {customerView ? (
          <div className="flex items-center flex-wrap gap-x-4 gap-y-1 text-[11px]">
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-emerald-500" /><span className="text-gray-600">{counts.reporting} Reporting</span></div>
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-slate-400" /><span className="text-gray-600">{counts.inventory} Inventory</span></div>
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-amber-500" /><span className="text-gray-600">{counts.attention_needed} Attention</span></div>
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-amber-500" /><span className="text-gray-600">{counts.not_reporting} Not Reporting</span></div>
          </div>
        ) : (
          (() => {
            const offline = siteSummaries.filter(s => s.status === "Not Connected" || s.critical_incidents > 0).length;
            const attention = siteSummaries.filter(s => s.needs_attention && s.status !== "Not Connected" && !s.critical_incidents).length;
            const working = total - offline - attention;
            return (
              <div className="flex items-center gap-5 text-[11px]">
                <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-emerald-500" /><span className="text-gray-600">{working} Working</span></div>
                <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-amber-500" /><span className="text-gray-600">{attention} Attention</span></div>
                <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-red-500" /><span className="text-gray-600">{offline} Offline</span></div>
              </div>
            );
          })()
        )}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// SITE LIST (simplified, read-only)
// ═══════════════════════════════════════════════════════════════════

function SiteList({ siteSummaries = [], role }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = useMemo(() => {
    let list = [...siteSummaries];
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(s => (s.site_name || "").toLowerCase().includes(q));
    }
    if (statusFilter === "working") list = list.filter(s => toCanonical(s) === "connected");
    else if (statusFilter === "attention") list = list.filter(s => toCanonical(s) === "attention" || s.needs_attention);
    else if (statusFilter === "offline") list = list.filter(s => toCanonical(s) === "offline");

    // Attention first, then alphabetical
    list.sort((a, b) => {
      const aa = a.needs_attention ? 1 : 0;
      const bb = b.needs_attention ? 1 : 0;
      if (aa !== bb) return bb - aa;
      return (a.site_name || "").localeCompare(b.site_name || "");
    });
    return list;
  }, [siteSummaries, search, statusFilter]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-900">Your Sites</h2>
          <span className="text-[11px] text-gray-400">{filtered.length} site{filtered.length !== 1 ? "s" : ""}</span>
        </div>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-gray-400" />
            <input type="text" placeholder="Search sites..." value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500" />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20">
            <option value="all">All</option>
            <option value="working">Working</option>
            <option value="attention">Needs Attention</option>
            <option value="offline">Offline</option>
          </select>
        </div>
      </div>
      <div className="divide-y divide-gray-50 max-h-[500px] overflow-y-auto">
        {filtered.length === 0 && (
          <div className="px-5 py-8 text-center text-xs text-gray-400">No sites match your search.</div>
        )}
        {filtered.map(site => {
          const sc = siteColor(site, role);
          return (
            <Link
              key={site.site_id}
              to={createPageUrl("SiteDetail") + `?site=${site.site_id}`}
              className="flex items-center gap-3 px-5 py-3.5 hover:bg-gray-50 transition-colors"
            >
              <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${sc.dot}`} />
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-gray-900 truncate">{site.site_name}</p>
                <div className="flex items-center gap-3 mt-0.5 text-[11px] text-gray-400">
                  <span className={`font-medium ${sc.text}`}>{friendlyStatus(site, role)}</span>
                  <span>{site.total_devices || 0} device{(site.total_devices || 0) !== 1 ? "s" : ""}</span>
                  {site.last_checkin && <span>{timeSince(site.last_checkin)}</span>}
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />
            </Link>
          );
        })}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// MAIN USER DASHBOARD
// ═══════════════════════════════════════════════════════════════════

export default function UserDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  const fetchData = useCallback(async () => {
    try {
      const result = await apiFetch("/command/summary");
      setData(result);
      setLastRefresh(new Date());
    } catch (err) {
      console.error("Dashboard fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000); // refresh every 60s for User
    return () => clearInterval(interval);
  }, [fetchData]);

  // Derived values that include hooks (useMemo) MUST be computed
  // before any early return.  Rules of Hooks require every hook to
  // be called on every render in the same order.  Each helper is
  // null-safe so the "still loading" render path is fine.
  const siteSummaries = data?.site_summaries || [];
  const incidents = data?.incident_feed || [];
  const counts = getAttentionCounts(data);
  const customerView = isCustomerRole(user?.role);
  const customerCounts = useMemo(
    () => (customerView ? getCustomerCounts(siteSummaries) : null),
    [customerView, siteSummaries],
  );

  if (loading) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-xs text-gray-400">Loading...</p>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const totalSites = counts.total;
  const connectedSites = counts.connected;
  const attentionSites = counts.attention;
  const offlineSites = counts.offline;

  return (
    <PageWrapper>
      <div className="min-h-screen bg-gray-50">
        <div className="p-5 lg:p-6 max-w-[1200px] mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-red-600 rounded-xl flex items-center justify-center shadow-sm">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900">System Status</h1>
                <p className="text-[11px] text-gray-400">Welcome, {user?.name}</p>
              </div>
            </div>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-100 text-gray-400 transition-colors">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* System Status Banner */}
          {customerView && customerCounts
            ? <CustomerSystemBanner counts={customerCounts} />
            : <SystemStatusBanner counts={counts} />
          }

          {/* Status Cards */}
          {customerView && customerCounts ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              <StatusCard
                label="Registered Locations" value={customerCounts.total}
                icon={Building2}
              />
              <StatusCard
                label="Reporting" value={customerCounts.reporting}
                icon={Wifi} color="text-emerald-500"
                bgColor={customerCounts.reporting === customerCounts.total && customerCounts.total > 0 ? "bg-emerald-50/50" : "bg-white"}
                borderColor={customerCounts.reporting === customerCounts.total && customerCounts.total > 0 ? "border-emerald-200" : undefined}
              />
              <StatusCard
                label="Inventory Record" value={customerCounts.inventory}
                icon={Clock}
                color={customerCounts.inventory > 0 ? "text-slate-500" : "text-gray-300"}
                bgColor={customerCounts.inventory > 0 ? "bg-slate-50" : "bg-white"}
                borderColor={customerCounts.inventory > 0 ? "border-slate-200" : undefined}
              />
              <StatusCard
                label="Attention Needed" value={customerCounts.attention_needed}
                icon={AlertTriangle}
                color={customerCounts.attention_needed > 0 ? "text-amber-500" : "text-gray-300"}
                bgColor={customerCounts.attention_needed > 0 ? "bg-amber-50/50" : "bg-white"}
                borderColor={customerCounts.attention_needed > 0 ? "border-amber-200" : undefined}
              />
              <StatusCard
                label="Not Reporting" value={customerCounts.not_reporting}
                icon={WifiOff}
                color={customerCounts.not_reporting > 0 ? "text-amber-500" : "text-gray-300"}
                bgColor={customerCounts.not_reporting > 0 ? "bg-amber-50/50" : "bg-white"}
                borderColor={customerCounts.not_reporting > 0 ? "border-amber-200" : undefined}
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatusCard label="Total Sites" value={totalSites} icon={Building2} />
              <StatusCard
                label="Working" value={connectedSites}
                icon={Wifi} color="text-emerald-500"
                bgColor={connectedSites === totalSites && totalSites > 0 ? "bg-emerald-50/50" : "bg-white"}
                borderColor={connectedSites === totalSites && totalSites > 0 ? "border-emerald-200" : undefined}
              />
              <StatusCard
                label="Needs Attention" value={attentionSites}
                icon={AlertTriangle}
                color={attentionSites > 0 ? "text-amber-500" : "text-gray-300"}
                bgColor={attentionSites > 0 ? "bg-amber-50/50" : "bg-white"}
                borderColor={attentionSites > 0 ? "border-amber-200" : undefined}
              />
              <StatusCard
                label="Offline" value={offlineSites}
                icon={WifiOff}
                color={offlineSites > 0 ? "text-red-500" : "text-gray-300"}
                bgColor={offlineSites > 0 ? "bg-red-50/50" : "bg-white"}
                borderColor={offlineSites > 0 ? "border-red-200" : undefined}
              />
            </div>
          )}

          {/* Main Content */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Left */}
            <div className="lg:col-span-7 space-y-5">
              <IssuesList siteSummaries={siteSummaries} incidents={incidents} role={user?.role} />
              <SiteList siteSummaries={siteSummaries} role={user?.role} />
            </div>
            {/* Right */}
            <div className="lg:col-span-5">
              <MapPreview siteSummaries={siteSummaries} role={user?.role} />
            </div>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
