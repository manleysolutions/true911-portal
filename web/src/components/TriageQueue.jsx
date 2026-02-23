import { useState, useEffect } from "react";
import { AlertTriangle, WifiOff, HelpCircle, ArrowRight, Signal, Radio, Clock } from "lucide-react";
import StatusBadge from "./ui/StatusBadge";

const TABS = [
  { key: "Attention Needed", label: "Attention Needed", icon: AlertTriangle, color: "text-amber-600", activeClass: "border-amber-500 text-amber-700 bg-amber-50" },
  { key: "Not Connected",    label: "Not Connected",    icon: WifiOff,       color: "text-red-600",   activeClass: "border-red-500 text-red-700 bg-red-50" },
  { key: "Unknown",          label: "Unknown",          icon: HelpCircle,    color: "text-gray-500",  activeClass: "border-gray-400 text-gray-700 bg-gray-100" },
];

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function recommendedAction(site) {
  const daysOld = site.last_checkin ? Math.floor((Date.now() - new Date(site.last_checkin)) / 86400000) : null;
  if (site.status === "Not Connected") {
    if (daysOld > 7) return "Dispatch field tech — offline >7 days, physical inspection required.";
    return "Ping device. If no response, initiate remote reboot or contact carrier.";
  }
  if (site.status === "Attention Needed") {
    if (site.signal_dbm && site.signal_dbm < -90) return "Signal critically weak. Check antenna, SIM card, or carrier outage.";
    return "Ping device to confirm connectivity. Review recent telemetry events.";
  }
  if (site.status === "Unknown") {
    if (daysOld > 30) return "Account review required — no contact in 30+ days. Contact site POC.";
    return "Contact lost. Attempt ping and review last known telemetry.";
  }
  return "Review and triage.";
}

function SignalBar({ dbm }) {
  if (!dbm) return <span className="text-gray-300 text-xs">—</span>;
  const color = dbm > -75 ? "text-emerald-600" : dbm > -85 ? "text-amber-500" : "text-red-500";
  return <span className={`text-xs font-medium ${color}`}>{dbm} dBm</span>;
}

export default function TriageQueue({ sites, onOpenSite, defaultTab }) {
  const [activeTab, setActiveTab] = useState(defaultTab || "Attention Needed");

  useEffect(() => {
    if (defaultTab) setActiveTab(defaultTab);
  }, [defaultTab]);

  const bySatus = (status) => sites.filter(s => s.status === status);
  const tabSites = bySatus(activeTab);

  return (
    <div className="bg-white rounded-xl border border-gray-200 flex flex-col">
      {/* Header */}
      <div className="px-5 pt-4 pb-0 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 text-red-600" />
          <h2 className="font-semibold text-gray-900 text-sm">Triage Queue</h2>
          <span className="ml-auto text-xs text-gray-400">
            {bySatus("Attention Needed").length + bySatus("Not Connected").length + bySatus("Unknown").length} sites need attention
          </span>
        </div>
        {/* Tabs */}
        <div className="flex gap-1">
          {TABS.map(tab => {
            const Icon = tab.icon;
            const count = bySatus(tab.key).length;
            const active = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg border-b-2 transition-all ${
                  active ? tab.activeClass + " border-b-2" : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${active ? "" : tab.color}`} />
                {tab.label}
                <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                  active ? "bg-white/60" : "bg-gray-100 text-gray-500"
                }`}>{count}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto flex-1">
        {tabSites.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <div className="text-2xl mb-2">✅</div>
            <div className="text-sm font-medium text-gray-700">No sites in this category</div>
            <div className="text-xs text-gray-400 mt-1">All clear for "{activeTab}"</div>
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left px-5 py-2.5 font-semibold text-gray-500 uppercase tracking-wide">Site</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-500 uppercase tracking-wide">Last Check-in</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-500 uppercase tracking-wide">Signal</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-500 uppercase tracking-wide">Carrier</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-500 uppercase tracking-wide">Type</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-500 uppercase tracking-wide">Recommended Action</th>
                <th className="px-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {tabSites.map(site => (
                <tr key={site.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-3">
                    <div className="font-semibold text-gray-900">{site.site_name}</div>
                    <div className="text-gray-400 mt-0.5">{site.customer_name} · <span className="font-mono">{site.site_id}</span></div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-1 text-gray-600">
                      <Clock className="w-3 h-3 text-gray-400" />
                      {timeSince(site.last_checkin)}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-1">
                      <Signal className="w-3 h-3 text-gray-400" />
                      <SignalBar dbm={site.signal_dbm} />
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-1 text-gray-600">
                      <Radio className="w-3 h-3 text-gray-400" />
                      {site.carrier || "—"}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-gray-600">{site.endpoint_type || site.kit_type || "—"}</td>
                  <td className="px-3 py-3 max-w-[220px]">
                    <span className="text-gray-600 leading-relaxed">{recommendedAction(site)}</span>
                  </td>
                  <td className="px-3 py-3">
                    <button
                      onClick={() => onOpenSite(site)}
                      className="flex items-center gap-1 px-3 py-1.5 bg-gray-900 text-white rounded-lg text-[11px] font-semibold hover:bg-gray-700 transition-colors whitespace-nowrap"
                    >
                      Open <ArrowRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}