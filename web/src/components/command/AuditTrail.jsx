import { useState, useEffect } from "react";
import { ScrollText, Download, Loader2, Filter } from "lucide-react";
import { apiFetch, getAccessToken } from "@/api/client";
import { config } from "@/config";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const CATEGORY_STYLE = {
  device: "bg-blue-100 text-blue-700",
  firmware: "bg-indigo-100 text-indigo-700",
  verification: "bg-purple-100 text-purple-700",
  incident: "bg-red-100 text-red-700",
  config: "bg-gray-100 text-gray-700",
  network: "bg-amber-100 text-amber-700",
};

const CATEGORIES = ["all", "device", "firmware", "verification", "incident", "config", "network"];

export default function AuditTrail({ siteId }) {
  const { can } = useAuth();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("all");

  useEffect(() => {
    let url = "/command/audit-log?limit=50";
    if (category !== "all") url += `&category=${category}`;
    if (siteId) url += `&site_id=${siteId}`;

    apiFetch(url)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [category, siteId]);

  const handleExport = async () => {
    try {
      const res = await fetch(
        `${config.apiUrl}/command/audit-log/export${category !== "all" ? `?category=${category}` : ""}`,
        { headers: { Authorization: `Bearer ${getAccessToken()}` } }
      );
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_log_${category}_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Audit log exported");
    } catch {
      toast.error("Export failed");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-2">
        <ScrollText className="w-4 h-4 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-900">Audit Trail</h3>
        {can("COMMAND_EXPORT_AUDIT") && (
          <button onClick={handleExport} className="ml-auto flex items-center gap-1 text-[10px] font-medium text-gray-500 hover:text-gray-700">
            <Download className="w-3 h-3" /> Export CSV
          </button>
        )}
      </div>

      <div className="flex gap-1 flex-wrap">
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => { setCategory(cat); setLoading(true); }}
            className={`px-2 py-0.5 text-[10px] font-medium rounded-full border transition-colors ${
              category === cat
                ? "bg-gray-900 text-white border-gray-900"
                : "bg-white text-gray-600 border-gray-200 hover:border-gray-300"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      ) : entries.length === 0 ? (
        <p className="text-xs text-gray-500 text-center py-4">No audit entries found.</p>
      ) : (
        <div className="space-y-1 max-h-[400px] overflow-y-auto">
          {entries.map(entry => (
            <div key={entry.id} className="flex items-start gap-2 p-2 border-b border-gray-50">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full mt-0.5 ${CATEGORY_STYLE[entry.category] || "bg-gray-100 text-gray-600"}`}>
                {entry.category}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-900">{entry.summary}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-gray-500">{entry.action.replace(/_/g, " ")}</span>
                  {entry.actor && <span className="text-[10px] text-gray-400">• {entry.actor}</span>}
                  <span className="text-[10px] text-gray-400">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
