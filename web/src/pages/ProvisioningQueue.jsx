import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/api/client";
import {
  Cpu, Disc3, Phone, RefreshCw, Search, CheckCircle2, AlertTriangle, XCircle,
  Loader2, Building2, MapPin, Link2, HelpCircle, Zap,
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
  linked: { label: "Linked", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  ignored: { label: "Ignored", cls: "bg-gray-100 text-gray-500 border-gray-200" },
};


export default function ProvisioningQueue() {
  const { can } = useAuth();
  const canManage = can("MANAGE_PROVISIONING");
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [linkMode, setLinkMode] = useState(null); // "single" item or "bulk"
  const [linkTarget, setLinkTarget] = useState(null); // single item for site picker
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (typeFilter) params.set("item_type", typeFilter);
      if (statusFilter) params.set("status", statusFilter);
      params.set("limit", "300");
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

  // ── Single item: link to site ──
  const handleLinkSingle = (item) => {
    setLinkTarget(item);
    setLinkMode("single");
  };

  // ── Bulk: link selected to site ──
  const handleBulkLink = () => {
    setLinkMode("bulk");
  };

  // ── Site picker confirm ──
  const handleSiteConfirm = async (siteId) => {
    setActionLoading(true);
    try {
      if (linkMode === "single" && linkTarget) {
        await apiFetch(`/provisioning/${linkTarget.id}/link`, {
          method: "POST",
          body: JSON.stringify({ site_id: siteId }),
        });
        toast.success(`Linked to site`);
      } else if (linkMode === "bulk") {
        const result = await apiFetch("/provisioning/bulk-link", {
          method: "POST",
          body: JSON.stringify({ item_ids: [...selected], site_id: siteId }),
        });
        toast.success(`${result.linked} item(s) linked to site`);
        setSelected(new Set());
      }
      setLinkMode(null);
      setLinkTarget(null);
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to link");
    }
    setActionLoading(false);
  };

  // ── Single ignore ──
  const handleIgnore = async (item) => {
    try {
      await apiFetch(`/provisioning/${item.id}/ignore`, { method: "POST" });
      toast.success("Ignored");
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to ignore");
    }
  };

  // ── Bulk ignore ──
  const handleBulkIgnore = async () => {
    try {
      const result = await apiFetch("/provisioning/bulk-ignore", {
        method: "POST",
        body: JSON.stringify({ item_ids: [...selected] }),
      });
      toast.success(`${result.ignored} item(s) ignored`);
      setSelected(new Set());
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to ignore");
    }
  };

  // ── Selection ──
  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const filtered = items.filter(i => {
    if (!search) return true;
    const q = search.toLowerCase();
    const label = i.meta?.carrier_label || "";
    return (i.external_ref || "").toLowerCase().includes(q) ||
           label.toLowerCase().includes(q) ||
           (i.meta?.iccid || "").toLowerCase().includes(q) ||
           (i.suggested_site_name || "").toLowerCase().includes(q) ||
           (i.source_provider || "").toLowerCase().includes(q) ||
           (i.suggestion_reason || "").toLowerCase().includes(q) ||
           (i.tenant_id || "").toLowerCase().includes(q);
  });

  const isActionable = (item) => ["new", "suggested", "needs_review"].includes(item.status);

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto space-y-5">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Zap className="w-6 h-6 text-purple-600" />
              Unassigned Devices & SIMs
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {summary ? `${summary.actionable} items need attention` : "Loading..."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canManage && (
              <button onClick={handleScan} disabled={scanning}
                className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold">
                {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                Scan Inventory
              </button>
            )}
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

        {/* Bulk action bar */}
        {canManage && selected.size > 0 && (
          <div className="bg-purple-50 border border-purple-200 rounded-xl px-4 py-2.5 flex items-center justify-between">
            <span className="text-purple-800 text-xs font-semibold">{selected.size} item(s) selected</span>
            <div className="flex items-center gap-2">
              <button onClick={handleBulkLink}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-semibold">
                <Building2 className="w-3.5 h-3.5" /> Assign to Site
              </button>
              <button onClick={handleBulkIgnore}
                className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 hover:bg-white text-gray-600 rounded-lg text-xs font-medium">
                <XCircle className="w-3.5 h-3.5" /> Ignore Selected
              </button>
              <button onClick={() => setSelected(new Set())}
                className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700">
                Clear
              </button>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search ICCID, device, DID, site, tenant..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
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
        <div className="space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-purple-600 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
              <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
              <p className="text-sm text-gray-500">
                {items.length === 0 ? 'No items in queue. Click "Scan Inventory" to detect unlinked infrastructure.' : "No items match your filters."}
              </p>
            </div>
          ) : (
            <>
            {/* Select all */}
            {canManage && (
              <div className="flex items-center gap-2 px-1">
                <input type="checkbox"
                  checked={filtered.length > 0 && selected.size === filtered.filter(isActionable).length}
                  onChange={() => {
                    const actionableIds = filtered.filter(isActionable).map(i => i.id);
                    if (selected.size === actionableIds.length) setSelected(new Set());
                    else setSelected(new Set(actionableIds));
                  }}
                  className="rounded border-gray-300 text-purple-600 focus:ring-purple-500" />
                <span className="text-xs text-gray-500">Select all actionable ({filtered.filter(isActionable).length})</span>
              </div>
            )}

            {filtered.map(item => {
              const tc = TYPE_CONFIG[item.item_type] || TYPE_CONFIG.sim;
              const sc = STATUS_CONFIG[item.status] || STATUS_CONFIG.new;
              const TypeIcon = tc.icon;
              const actionable = isActionable(item);

              return (
                <div key={item.id} className={`bg-white rounded-xl border border-gray-200 px-4 py-3 flex items-center gap-3 ${selected.has(item.id) ? "ring-2 ring-purple-200 bg-purple-50/30" : ""}`}>
                  {/* Checkbox */}
                  {canManage && actionable && (
                    <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggleSelect(item.id)}
                      className="rounded border-gray-300 text-purple-600 focus:ring-purple-500 flex-shrink-0" />
                  )}
                  {(!canManage || !actionable) && <div className="w-4" />}

                  {/* Type icon */}
                  <div className={`w-8 h-8 rounded-lg ${tc.bg} ${tc.border} border flex items-center justify-center flex-shrink-0`}>
                    <TypeIcon className={`w-4 h-4 ${tc.color}`} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold text-gray-900 font-mono">{item.external_ref}</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${sc.cls}`}>{sc.label}</span>
                      {item.source_provider && item.source_provider !== "manual" && (
                        <span className="text-[10px] bg-indigo-50 text-indigo-600 border border-indigo-200 px-1.5 py-0.5 rounded-full font-bold">{item.source_provider}</span>
                      )}
                      <span className="text-[10px] text-gray-400">{item.tenant_id}</span>
                    </div>
                    {/* Carrier label — the user-defined name from Verizon/ThingSpace */}
                    {item.meta?.carrier_label && (
                      <div className="text-xs text-purple-700 font-medium mt-0.5">
                        {item.meta.carrier_label}
                      </div>
                    )}
                    {/* ICCID subtitle for SIMs (since external_ref is now MSISDN) */}
                    {item.item_type === "sim" && item.meta?.iccid && (
                      <div className="text-[10px] text-gray-400 font-mono">{item.meta.iccid}</div>
                    )}
                    {/* Suggestion or reason */}
                    {item.suggested_site_name ? (
                      <div className="text-xs text-gray-600 mt-0.5">
                        Suggested: <span className="font-semibold">{item.suggested_site_name}</span>
                        {item.suggestion_confidence != null && <span className="text-gray-400 ml-1">({Math.round(item.suggestion_confidence * 100)}%)</span>}
                      </div>
                    ) : item.suggestion_reason ? (
                      <div className="text-[11px] text-gray-500 mt-0.5">{item.suggestion_reason}</div>
                    ) : null}
                    {/* Warning badges */}
                    <div className="flex flex-wrap gap-1 mt-1">
                      {item.missing_site && (
                        <span className="text-[9px] text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full">No site</span>
                      )}
                      {item.missing_e911 && (
                        <span className="text-[9px] text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded-full">No E911</span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  {canManage && actionable && (
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button onClick={() => handleLinkSingle(item)}
                        className="flex items-center gap-1 px-2.5 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-[11px] font-semibold rounded-lg">
                        <Building2 className="w-3 h-3" /> Assign Site
                      </button>
                      <button onClick={() => handleIgnore(item)}
                        className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded-lg" title="Ignore">
                        <XCircle className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  {/* Resolved */}
                  {item.status === "linked" && item.resolved_site_id && (
                    <div className="flex items-center gap-1.5 text-xs text-emerald-700 flex-shrink-0">
                      <CheckCircle2 className="w-4 h-4" /> {item.resolved_site_id}
                    </div>
                  )}
                </div>
              );
            })}
            </>
          )}
        </div>
      </div>

      {/* Site picker */}
      {linkMode && (
        <SitePickerModal
          title={linkMode === "bulk" ? `Assign ${selected.size} Item(s) to Site` : `Assign ${linkTarget?.item_type || "item"} to Site`}
          count={linkMode === "bulk" ? selected.size : 1}
          entityLabel={linkMode === "bulk" ? "item(s)" : (linkTarget?.external_ref || "item")}
          onClose={() => { setLinkMode(null); setLinkTarget(null); }}
          onConfirm={handleSiteConfirm}
        />
      )}
    </PageWrapper>
  );
}
