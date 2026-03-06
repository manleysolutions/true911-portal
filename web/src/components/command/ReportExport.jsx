import { useState } from "react";
import { Download, FileSpreadsheet } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const API_BASE = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "";

export default function ReportExport({ siteId }) {
  const { can } = useAuth();
  const [exporting, setExporting] = useState(false);

  if (!can("COMMAND_EXPORT_REPORTS")) return null;

  async function handleExport() {
    setExporting(true);
    try {
      const token = localStorage.getItem("access_token");
      const url = siteId
        ? `${API_BASE}/api/command/reports/site/${siteId}`
        : `${API_BASE}/api/command/reports/portfolio`;

      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`Export failed: ${resp.status}`);

      const blob = await resp.blob();
      const disposition = resp.headers.get("Content-Disposition") || "";
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
      const filename = filenameMatch ? filenameMatch[1] : `true911_report.csv`;

      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);

      toast.success("Report downloaded");
    } catch (err) {
      toast.error(err.message || "Export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={exporting}
      className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-sm transition-colors disabled:opacity-50"
    >
      {exporting ? (
        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : (
        <FileSpreadsheet className="w-4 h-4 text-emerald-500" />
      )}
      {siteId ? "Export Site Report" : "Export Portfolio CSV"}
    </button>
  );
}
