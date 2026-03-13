import { useState, useEffect } from "react";
import { apiFetch } from "@/api/client";
import { Building2, Search, X, Loader2, AlertTriangle } from "lucide-react";

export default function SitePickerModal({ title, count, entityLabel, onClose, onConfirm }) {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [assigning, setAssigning] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiFetch("/sites?limit=200");
        setSites(data);
      } catch { setSites([]); }
      setLoading(false);
    })();
  }, []);

  const filtered = sites.filter(s => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (s.site_name || "").toLowerCase().includes(q) ||
      (s.site_id || "").toLowerCase().includes(q) ||
      (s.customer_name || "").toLowerCase().includes(q) ||
      (s.e911_city || "").toLowerCase().includes(q)
    );
  });

  const selectedSite = sites.find(s => s.site_id === selectedSiteId);
  const hasE911 = selectedSite && selectedSite.e911_street && selectedSite.e911_city;

  const handleConfirm = async () => {
    if (!selectedSiteId) return;
    setAssigning(true);
    await onConfirm(selectedSiteId);
    setAssigning(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-red-600" />
            <h3 className="text-base font-bold text-gray-900">{title || "Assign to Site"}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-3">
          <div className="bg-gray-50 rounded-lg px-3 py-2 text-xs text-gray-600 mb-3">
            {count} {entityLabel} selected for assignment
          </div>

          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search sites..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm"
              autoFocus
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 min-h-0">
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-gray-400 py-6 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading sites...
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-xs text-gray-400 py-6 text-center">No sites found.</div>
          ) : (
            <div className="space-y-1 pb-2">
              {filtered.map(s => (
                <button
                  key={s.site_id}
                  onClick={() => setSelectedSiteId(s.site_id)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                    selectedSiteId === s.site_id
                      ? "bg-red-50 border-red-200 border"
                      : "hover:bg-gray-50 border border-transparent"
                  }`}
                >
                  <div className="text-sm font-medium text-gray-900">{s.site_name}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    {s.customer_name} | {s.site_id}
                    {s.e911_city && ` | ${s.e911_city}, ${s.e911_state}`}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* E911 warning */}
        {selectedSite && !hasE911 && (
          <div className="px-6 py-2">
            <div className="flex items-center gap-1.5 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
              <span className="text-[10px] text-amber-700">This site has no E911 address. You can assign now and update E911 later.</span>
            </div>
          </div>
        )}

        <div className="flex gap-3 px-6 py-4 border-t border-gray-100">
          <button onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!selectedSiteId || assigning}
            className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-semibold py-2.5 px-4 rounded-xl text-sm"
          >
            {assigning ? "Assigning..." : "Assign to Site"}
          </button>
        </div>
      </div>
    </div>
  );
}
