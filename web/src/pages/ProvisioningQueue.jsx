import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/api/client";
import {
  Cpu, Disc3, Phone, RefreshCw, Search, CheckCircle2, AlertTriangle, XCircle,
  Loader2, Building2, MapPin, Link2, Eye, HelpCircle, Zap, ChevronDown,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import SitePickerModal from "@/components/SitePickerModal";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const TYPE_CONFIG = {
  sim: { icon: Disc3, label: "SIM", color: "text-indigo-600", bg: "bg-indigo-50", border: "border-indigo-200" },
  device: { icon: Cpu, label: "Device", color: "text-blue-600", bg: "bg-blue-50", border: "border-blue-200" },
  line: { icon: Phone, label: "Line", color: "text-emerald-600", bg: "bg-emerald-50", border: "border-emerald-200" },
};

const STATUS_CONFIG = {
  new: { label: "New", cls: "bg-blue-50 text-blue-700 border-blue-200" },
  suggested: { label: "Suggested", cls: "bg-purple-50 text-purple-700 border-purple-200" },
  needs_review: { label: "Needs Review", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  approved: { label: "Approved", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  linked: { label: "Linked", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  ignored: { label: "Ignored", cls: "bg-gray-100 text-gray-500 border-gray-200" },
};

function ConfidenceBar({ value }) {
  if (value == null) return <span className="text-[10px] text-gray-400">No suggestion</span>;
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-bold text-gray-500 w-8">{pct}%</span>
    </div>
  );
}


export default function ProvisioningQueue() {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [linkTarget, setLinkTarget] = useState(null); // item to link via site picker
  const [actionLoading, setActionLoading] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (typeFilter) params.set("item_type", typeFilter);
      if (statusFilter) params.set("status", statusFilter);
      params.set("limit", "200");

      const [itemsData, summaryData] = await Promise.all([
        apiFetch(`/provisioning?${params}`),
        apiFetch("/provisioning/summary"),
      ]);
      setItems(itemsData);
      setSummary(summaryData);
    } catch {
      toast.error("Failed to load provisioning queue");
    }
    setLoading(false);
  }, [typeFilter, statusFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const result = await apiFetch("/provisioning/scan", { method: "POST" });
      toast.success(`Scan complete: ${result.created} new items, ${result.skipped} already queued`);
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Scan failed");
    }
    setScanning(false);
  };

  const handleApprove = async (item) => {
    if (!item.suggested_site_id) {
      setLinkTarget(item);
      return;
    }
    setActionLoading(item.id);
    try {
      await apiFetch(`/provisioning/${item.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ site_id: item.suggested_site_id }),
      });
      toast.success(`${item.item_type} linked to ${item.suggested_site_name || item.suggested_site_id}`);
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to approve");
    }
    setActionLoading(null);
  };

  const handleLink = async (siteId) => {
    if (!linkTarget) return;
    setActionLoading(linkTarget.id);
    try {
      await apiFetch(`/provisioning/${linkTarget.id}/link`, {
        method: "POST",
        body: JSON.stringify({ site_id: siteId }),
      });
      toast.success(`${linkTarget.item_type} linked to site`);
      setLinkTarget(null);
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to link");
    }
    setActionLoading(null);
  };

  const handleIgnore = async (item) => {
    setActionLoading(item.id);
    try {
      await apiFetch(`/provisioning/${item.id}/ignore`, { method: "POST" });
      toast.success("Item ignored");
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to ignore");
    }
    setActionLoading(null);
  };

  const filtered = items.filter(i => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (i.external_ref || "").toLowerCase().includes(q) ||
           (i.suggested_site_name || "").toLowerCase().includes(q) ||
           (i.source_provider || "").toLowerCase().includes(q) ||
           (i.suggestion_reason || "").toLowerCase().includes(q);
  });

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto space-y-5">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Zap className="w-6 h-6 text-purple-600" />
              Provisioning Queue
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {summary ? `${summary.actionable} items need attention` : "Loading..."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleScan}
              disabled={scanning}
              className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
            >
              {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              Scan Inventory
            </button>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-400">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Summary cards */}
        {summary && (
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: "SIMs", count: summary.by_type?.sim || 0, icon: Disc3, color: "text-indigo-600" },
              { label: "Devices", count: summary.by_type?.device || 0, icon: Cpu, color: "text-blue-600" },
              { label: "Lines", count: summary.by_type?.line || 0, icon: Phone, color: "text-emerald-600" },
              { label: "Actionable", count: summary.actionable, icon: AlertTriangle, color: "text-amber-600" },
            ].map(c => (
              <div key={c.label} className="bg-white rounded-xl border border-gray-200 p-4 text-center">
                <c.icon className={`w-5 h-5 ${c.color} mx-auto mb-1`} />
                <div className="text-2xl font-bold text-gray-900">{c.count}</div>
                <div className="text-[10px] text-gray-500 uppercase font-semibold">{c.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search ICCID, device, DID, site..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">All Types</option>
            <option value="sim">SIMs</option>
            <option value="device">Devices</option>
            <option value="line">Lines</option>
          </select>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">Actionable</option>
            <option value="new">New</option>
            <option value="suggested">Suggested</option>
            <option value="needs_review">Needs Review</option>
            <option value="linked">Linked</option>
            <option value="ignored">Ignored</option>
          </select>
        </div>

        {/* Queue items */}
        <div className="space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-purple-600 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
              <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
              <p className="text-sm text-gray-500">
                {items.length === 0 ? "No items in queue. Click \"Scan Inventory\" to detect unlinked infrastructure." : "No items match your filters."}
              </p>
            </div>
          ) : filtered.map(item => {
            const tc = TYPE_CONFIG[item.item_type] || TYPE_CONFIG.sim;
            const sc = STATUS_CONFIG[item.status] || STATUS_CONFIG.new;
            const TypeIcon = tc.icon;
            const isActionable = ["new", "suggested", "needs_review"].includes(item.status);

            return (
              <div key={item.id} className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-start gap-4">
                  {/* Type badge */}
                  <div className={`w-10 h-10 rounded-lg ${tc.bg} ${tc.border} border flex items-center justify-center flex-shrink-0`}>
                    <TypeIcon className={`w-5 h-5 ${tc.color}`} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-bold text-gray-900 font-mono">{item.external_ref}</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${sc.cls}`}>{sc.label}</span>
                      {item.source_provider && item.source_provider !== "manual" && (
                        <span className="text-[10px] bg-indigo-50 text-indigo-600 border border-indigo-200 px-1.5 py-0.5 rounded-full font-bold">{item.source_provider}</span>
                      )}
                    </div>

                    {/* Suggestion */}
                    {item.suggested_site_name && (
                      <div className="flex items-center gap-2 mb-2">
                        <Building2 className="w-3.5 h-3.5 text-purple-500" />
                        <span className="text-xs text-gray-700">
                          Suggested: <span className="font-semibold">{item.suggested_site_name}</span>
                        </span>
                      </div>
                    )}
                    {item.suggestion_reason && (
                      <p className="text-[10px] text-gray-500 mb-2">{item.suggestion_reason}</p>
                    )}

                    {/* Confidence */}
                    {item.suggestion_confidence != null && (
                      <div className="w-40 mb-2">
                        <ConfidenceBar value={item.suggestion_confidence} />
                      </div>
                    )}

                    {/* Warning badges */}
                    <div className="flex flex-wrap gap-1.5">
                      {item.missing_site && (
                        <span className="flex items-center gap-1 text-[10px] text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full">
                          <Building2 className="w-2.5 h-2.5" /> No site
                        </span>
                      )}
                      {item.missing_e911 && (
                        <span className="flex items-center gap-1 text-[10px] text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded-full">
                          <MapPin className="w-2.5 h-2.5" /> No E911
                        </span>
                      )}
                      {item.needs_compliance_review && (
                        <span className="flex items-center gap-1 text-[10px] text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded-full">
                          <HelpCircle className="w-2.5 h-2.5" /> Compliance review
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  {isActionable && (
                    <div className="flex flex-col gap-1.5 flex-shrink-0">
                      {item.suggested_site_id && (
                        <button
                          onClick={() => handleApprove(item)}
                          disabled={actionLoading === item.id}
                          className="flex items-center gap-1 px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-[11px] font-semibold rounded-lg"
                        >
                          {actionLoading === item.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                          Approve
                        </button>
                      )}
                      <button
                        onClick={() => setLinkTarget(item)}
                        className="flex items-center gap-1 px-2.5 py-1.5 border border-gray-200 hover:bg-gray-50 text-gray-700 text-[11px] font-medium rounded-lg"
                      >
                        <Link2 className="w-3 h-3" /> Link to Site
                      </button>
                      <button
                        onClick={() => handleIgnore(item)}
                        disabled={actionLoading === item.id}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 text-[11px] rounded-lg"
                      >
                        <XCircle className="w-3 h-3" /> Ignore
                      </button>
                    </div>
                  )}

                  {/* Resolved state */}
                  {item.status === "linked" && item.resolved_site_id && (
                    <div className="flex items-center gap-1.5 text-xs text-emerald-700">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Linked to {item.resolved_site_id}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Site picker for manual linking */}
      {linkTarget && (
        <SitePickerModal
          title={`Link ${linkTarget.item_type} to Site`}
          count={1}
          entityLabel={linkTarget.external_ref || linkTarget.item_type}
          onClose={() => setLinkTarget(null)}
          onConfirm={handleLink}
        />
      )}
    </PageWrapper>
  );
}
