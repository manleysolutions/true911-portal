import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Upload, FileSpreadsheet, CheckCircle2, AlertTriangle,
  Download, ArrowLeft, Loader2, Building2,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";

export default function BulkDeploy() {
  const { can } = useAuth();
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer?.files?.[0];
    if (f && f.name.endsWith(".csv")) setFile(f);
    else toast.error("Please drop a .csv file");
  }, []);

  const handleFileSelect = useCallback((e) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(
        `${import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL}/command/bulk-import`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
          body: formData,
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Upload failed (${res.status})`);
      }
      const data = await res.json();
      setResult(data);
      if (data.created > 0) toast.success(`${data.created} sites imported`);
    } catch (err) {
      toast.error(err.message || "Import failed");
    } finally {
      setLoading(false);
    }
  };

  const downloadTemplate = async () => {
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL}/command/bulk-import/template-csv`,
        { headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` } }
      );
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "bulk_import_template.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to download template");
    }
  };

  if (!can("COMMAND_BULK_IMPORT")) {
    return (
      <PageWrapper>
        <div className="p-6 text-center text-gray-500">You do not have permission to access this page.</div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-2xl mx-auto">
        <Link to={createPageUrl("Command")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 mb-4">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Command
        </Link>

        <div className="flex items-center gap-2 mb-2">
          <FileSpreadsheet className="w-5 h-5 text-red-600" />
          <h1 className="text-2xl font-bold text-gray-900">Bulk Site Import</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">
          Import multiple sites at once from a CSV file. Sites can be linked to templates for automatic verification task setup.
        </p>

        {/* Template download */}
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-blue-900">Download CSV Template</p>
              <p className="text-xs text-blue-700 mt-0.5">
                Use this template to format your site data correctly.
              </p>
            </div>
            <button onClick={downloadTemplate} className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium">
              <Download className="w-3.5 h-3.5" /> Download
            </button>
          </div>
        </div>

        {/* Upload zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors mb-6 ${
            dragOver ? "border-red-400 bg-red-50" : file ? "border-emerald-400 bg-emerald-50" : "border-gray-300 bg-gray-50"
          }`}
        >
          {file ? (
            <div>
              <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
              <p className="text-sm font-semibold text-gray-900">{file.name}</p>
              <p className="text-xs text-gray-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
              <button onClick={() => setFile(null)} className="text-xs text-red-500 hover:text-red-700 mt-2">Remove</button>
            </div>
          ) : (
            <div>
              <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
              <p className="text-sm text-gray-600">Drag & drop a CSV file here, or</p>
              <label className="inline-flex items-center gap-1.5 px-4 py-2 mt-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 cursor-pointer">
                <FileSpreadsheet className="w-4 h-4" /> Browse Files
                <input type="file" accept=".csv" onChange={handleFileSelect} className="hidden" />
              </label>
            </div>
          )}
        </div>

        {/* Upload button */}
        {file && !result && (
          <button
            onClick={handleUpload}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white rounded-xl text-sm font-semibold"
          >
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Importing...</> : <><Upload className="w-4 h-4" /> Import Sites</>}
          </button>
        )}

        {/* Results */}
        {result && (
          <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 mt-6">
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Import Results</h3>
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900">{result.total_rows}</p>
                  <p className="text-xs text-gray-500">Total Rows</p>
                </div>
                <div className="text-center p-3 bg-emerald-50 rounded-lg">
                  <p className="text-2xl font-bold text-emerald-600">{result.created}</p>
                  <p className="text-xs text-gray-500">Created</p>
                </div>
                <div className="text-center p-3 bg-amber-50 rounded-lg">
                  <p className="text-2xl font-bold text-amber-600">{result.skipped}</p>
                  <p className="text-xs text-gray-500">Skipped</p>
                </div>
              </div>
            </div>
            {result.errors?.length > 0 && (
              <div className="p-4">
                <p className="text-xs font-semibold text-gray-600 uppercase mb-2">Issues</p>
                <div className="space-y-1 max-h-[200px] overflow-y-auto">
                  {result.errors.map((err, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-amber-700">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span>{err}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="p-4">
              <div className="flex gap-3">
                <button onClick={() => { setFile(null); setResult(null); }} className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50">
                  Import More
                </button>
                <Link to={createPageUrl("OperatorView")} className="flex-1 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium text-center flex items-center justify-center gap-1">
                  <Building2 className="w-4 h-4" /> View Sites
                </Link>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
