import { useState, useEffect, useCallback } from "react";
import { Line, Site } from "@/api/entities";
import { MapPin, Search, RefreshCw, CheckCircle2, AlertTriangle, Clock, XCircle } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const E911_BADGE = {
  validated: { cls: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: CheckCircle2, iconCls: "text-emerald-500" },
  pending: { cls: "bg-amber-50 text-amber-700 border-amber-200", icon: Clock, iconCls: "text-amber-500" },
  failed: { cls: "bg-red-50 text-red-700 border-red-200", icon: XCircle, iconCls: "text-red-500" },
  none: { cls: "bg-gray-100 text-gray-500 border-gray-200", icon: MapPin, iconCls: "text-gray-400" },
};

function E911Row({ line, siteName, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [street, setStreet] = useState(line.e911_street || "");
  const [city, setCity] = useState(line.e911_city || "");
  const [state, setState] = useState(line.e911_state || "");
  const [zip, setZip] = useState(line.e911_zip || "");
  const [saving, setSaving] = useState(false);

  const badge = E911_BADGE[line.e911_status] || E911_BADGE.none;
  const BadgeIcon = badge.icon;

  const handleSave = async () => {
    setSaving(true);
    try {
      await Line.update(line.id, {
        e911_street: street, e911_city: city, e911_state: state, e911_zip: zip,
        e911_status: "pending",
      });
      toast.success(`E911 address updated for ${line.line_id}`);
      setEditing(false);
      onSaved();
    } catch {
      toast.error("Failed to update E911 address");
    }
    setSaving(false);
  };

  return (
    <div className="border border-gray-100 rounded-xl mb-3 overflow-hidden">
      <div className="flex items-center gap-3 p-4 bg-white">
        <BadgeIcon className={`w-5 h-5 ${badge.iconCls} flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 text-sm">{line.did || line.line_id}</span>
            <span className="text-xs text-gray-400 font-mono">{line.line_id}</span>
            <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${badge.cls}`}>
              {line.e911_status}
            </span>
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {siteName || line.site_id || "No site"} · {line.provider} · {line.protocol}
          </div>
          {(line.e911_street || line.e911_city) && !editing && (
            <div className="text-xs text-gray-600 mt-1">
              {[line.e911_street, line.e911_city, line.e911_state, line.e911_zip].filter(Boolean).join(", ")}
            </div>
          )}
        </div>
        <button
          onClick={() => setEditing(!editing)}
          className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
            editing ? "bg-gray-100 border-gray-300 text-gray-700" : "border-gray-200 text-gray-600 hover:border-red-200"
          }`}
        >
          {editing ? "Cancel" : "Edit E911"}
        </button>
      </div>

      {editing && (
        <div className="px-4 pb-4 bg-red-50/30 border-t border-red-100">
          <div className="text-xs font-semibold text-red-700 pt-3 mb-2">E911 Address</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <input value={street} onChange={e => setStreet(e.target.value)} placeholder="Street Address"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
            </div>
            <input value={city} onChange={e => setCity(e.target.value)} placeholder="City"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
            <div className="flex gap-2">
              <input value={state} onChange={e => setState(e.target.value)} placeholder="ST" maxLength={2}
                className="w-16 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500 uppercase" />
              <input value={zip} onChange={e => setZip(e.target.value)} placeholder="ZIP"
                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
            </div>
            <div className="col-span-2">
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
                {saving ? "Saving..." : "Save E911 Address"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function E911() {
  const { can } = useAuth();
  const [lines, setLines] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const fetchData = useCallback(async () => {
    const [lineData, siteData] = await Promise.all([
      Line.list("-created_at", 200),
      Site.list("-last_checkin", 200),
    ]);
    setLines(lineData);
    setSites(siteData);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (!can('VIEW_ADMIN')) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <MapPin className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <div className="text-lg font-semibold text-gray-800">Admin Access Required</div>
            <div className="text-sm text-gray-500 mt-1">E911 address management requires Admin access.</div>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const siteMap = Object.fromEntries(sites.map(s => [s.site_id, s]));

  const filtered = lines.filter(l => {
    if (statusFilter && l.e911_status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      const site = siteMap[l.site_id];
      return (
        (l.did || "").toLowerCase().includes(q) ||
        (l.line_id || "").toLowerCase().includes(q) ||
        (l.e911_street || "").toLowerCase().includes(q) ||
        (l.e911_city || "").toLowerCase().includes(q) ||
        (site?.site_name || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Summary counts
  const counts = { validated: 0, pending: 0, failed: 0, none: 0 };
  lines.forEach(l => { counts[l.e911_status] = (counts[l.e911_status] || 0) + 1; });

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">E911 Address Management</h1>
            <p className="text-sm text-gray-500 mt-0.5">Manage E911 addresses for all voice lines</p>
          </div>
          <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Validated", count: counts.validated, cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
            { label: "Pending", count: counts.pending, cls: "text-amber-700 bg-amber-50 border-amber-200" },
            { label: "Failed", count: counts.failed, cls: "text-red-700 bg-red-50 border-red-200" },
            { label: "None", count: counts.none, cls: "text-gray-600 bg-gray-50 border-gray-200" },
          ].map(c => (
            <div key={c.label} className={`rounded-xl border p-3 text-center ${c.cls}`}>
              <div className="text-2xl font-bold">{c.count}</div>
              <div className="text-xs font-semibold uppercase tracking-wide">{c.label}</div>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search by DID, line, address, site..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">All E911 Status</option>
            <option value="validated">Validated</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
            <option value="none">None</option>
          </select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-gray-300 py-16 text-center">
            <MapPin className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <div className="text-sm font-semibold text-gray-500">
              {lines.length === 0 ? "No lines to manage" : "No lines match your filters"}
            </div>
            <div className="text-xs text-gray-400 mt-1">
              {lines.length === 0
                ? "Add voice lines first, then configure E911 addresses here."
                : "Try adjusting your search or filter."}
            </div>
          </div>
        ) : (
          <div>
            {filtered.map(l => (
              <E911Row key={l.id} line={l} siteName={siteMap[l.site_id]?.site_name} onSaved={fetchData} />
            ))}
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
