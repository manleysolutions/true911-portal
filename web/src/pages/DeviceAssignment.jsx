import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Upload, FileSpreadsheet, CheckCircle2, AlertTriangle, XCircle,
  Download, ArrowLeft, Loader2, Cpu, Building2, RefreshCw,
  ChevronDown, ChevronUp, Info, LinkIcon,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

import { config } from "@/config";
import { getAccessToken } from "@/api/client";
const API_URL = config.apiUrl;
const authHeaders = () => ({
  Authorization: `Bearer ${getAccessToken()}`,
});

export default function DeviceAssignment() {
  const { can } = useAuth();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [commitResult, setCommitResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [showRows, setShowRows] = useState(false);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer?.files?.[0];
    if (f && f.name.endsWith(".csv")) { setFile(f); setPreview(null); setCommitResult(null); }
    else toast.error("Please drop a .csv file");
  }, []);

  const handleFileSelect = useCallback((e) => {
    const f = e.target.files?.[0];
    if (f) { setFile(f); setPreview(null); setCommitResult(null); }
  }, []);

  const handlePreview = async () => {
    if (!file) return;
    setLoading(true);
    setPreview(null);
    setCommitResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/command/device-assignment/preview`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Preview failed (${res.status})`);
      }
      const data = await res.json();
      setPreview(data);
      if (data.has_errors) toast.error("Some rows have issues — review before committing");
      else toast.success("Preview ready — review matches and confirm");
    } catch (err) {
      toast.error(err.message || "Preview failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!file) return;
    setCommitting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/command/device-assignment/commit`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Assignment failed (${res.status})`);
      }
      const data = await res.json();
      setCommitResult(data);
      setPreview(null);
      toast.success(`Assignment complete: ${data.assigned} assigned, ${data.reassigned} reassigned`);
    } catch (err) {
      toast.error(err.message || "Assignment failed");
    } finally {
      setCommitting(false);
    }
  };

  const downloadTemplate = async () => {
    try {
      const res = await fetch(`${API_URL}/command/device-assignment/template-csv`, {
        headers: authHeaders(),
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "device_assignment_template.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to download template");
    }
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setCommitResult(null);
    setShowRows(false);
  };

  if (!can("MANAGE_DEVICES")) {
    return (
      <PageWrapper>
        <div className="p-6 text-center text-gray-500">You do not have permission to access this page.</div>
      </PageWrapper>
    );
  }

  const errorRows = preview?.rows?.filter(r => r.errors?.length > 0) || [];
  const warnRows = preview?.rows?.filter(r => (r.warnings?.length > 0) && !(r.errors?.length > 0)) || [];
  const canCommit = preview && !preview.has_errors && (preview.will_assign > 0 || preview.will_reassign > 0);

  return (
    <PageWrapper>
      <div className="p-6 max-w-4xl mx-auto">
        <Link to={createPageUrl("AdminImports")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 mb-4">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Imports
        </Link>

        <div className="flex items-center gap-2 mb-2">
          <LinkIcon className="w-5 h-5 text-red-600" />
          <h1 className="text-2xl font-bold text-gray-900">Bulk Device Assignment</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">
          Assign Verizon-synced devices to the correct customer sites using a CSV worksheet.
          Match devices by ICCID, IMEI, or MSISDN to sites by name and customer.
        </p>

        {/* How it works */}
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-6">
          <p className="text-xs font-semibold text-gray-700 mb-2">How it works</p>
          <ol className="text-xs text-gray-600 space-y-1 list-decimal list-inside">
            <li>Download the template CSV and fill in your device-to-site mapping</li>
            <li>Each row maps a device (by ICCID/IMEI/MSISDN) to a site (by site_name + customer_name)</li>
            <li>Upload and preview to see matches, conflicts, and reassignments</li>
            <li>Confirm to apply all assignments in bulk</li>
          </ol>
        </div>

        {/* Template download */}
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-blue-900">Download Assignment Template</p>
              <p className="text-xs text-blue-700 mt-0.5">
                Columns: iccid, imei, msisdn, customer_name, site_name, site_id, notes
              </p>
            </div>
            <button onClick={downloadTemplate} className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium">
              <Download className="w-3.5 h-3.5" /> Download
            </button>
          </div>
        </div>

        {/* Upload zone */}
        {!commitResult && (
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
                <button onClick={reset} className="text-xs text-red-500 hover:text-red-700 mt-2">Remove</button>
              </div>
            ) : (
              <div>
                <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                <p className="text-sm text-gray-600">Drag & drop your assignment CSV here, or</p>
                <label className="inline-flex items-center gap-1.5 px-4 py-2 mt-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 cursor-pointer">
                  <FileSpreadsheet className="w-4 h-4" /> Browse Files
                  <input type="file" accept=".csv" onChange={handleFileSelect} className="hidden" />
                </label>
              </div>
            )}
          </div>
        )}

        {/* Preview button */}
        {file && !preview && !commitResult && (
          <button
            onClick={handlePreview}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-xl text-sm font-semibold mb-6"
          >
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing matches...</> : <><FileSpreadsheet className="w-4 h-4" /> Preview Assignments</>}
          </button>
        )}

        {/* Preview Results */}
        {preview && (
          <div className="space-y-4 mb-6">
            {/* Summary cards */}
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Assignment Preview</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                <SummaryCard label="Total Rows" value={preview.total_rows} color="gray" />
                <SummaryCard label="Will Assign" value={preview.will_assign} color="emerald" />
                <SummaryCard label="Will Reassign" value={preview.will_reassign} color="amber" />
                <SummaryCard label="Already Correct" value={preview.already_assigned} color="blue" />
                <SummaryCard label="Unmatched" value={preview.unmatched} color="red" />
                <SummaryCard label="Conflicts" value={preview.conflicts} color="red" />
              </div>
            </div>

            {/* Errors */}
            {errorRows.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <p className="text-sm font-semibold text-red-800 mb-2 flex items-center gap-1.5">
                  <XCircle className="w-4 h-4" /> {errorRows.length} Row{errorRows.length > 1 ? "s" : ""} with Errors
                </p>
                <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                  {errorRows.map((r) => (
                    <div key={r.row} className="text-xs text-red-700">
                      <span className="font-medium">Row {r.row}</span>
                      {r.iccid ? ` (${r.iccid})` : r.imei ? ` (IMEI ${r.imei})` : ""}
                      : {r.errors.join("; ")}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Warnings (reassignments) */}
            {warnRows.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <p className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4" /> {warnRows.length} Reassignment{warnRows.length > 1 ? "s" : ""}
                </p>
                <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                  {warnRows.map((r) => (
                    <div key={r.row} className="text-xs text-amber-700">
                      <span className="font-medium">Row {r.row}</span>
                      {` (${r.device_id})`}: {r.warnings.join("; ")}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Row detail toggle */}
            <button
              onClick={() => setShowRows(!showRows)}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700"
            >
              {showRows ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              {showRows ? "Hide" : "Show"} all {preview.total_rows} rows
            </button>

            {showRows && (
              <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Row</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Device</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">ICCID</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Target Site</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Customer</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Action</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {preview.rows.map((r) => (
                        <tr key={r.row} className={r.errors?.length > 0 ? "bg-red-50" : r.warnings?.length > 0 ? "bg-amber-50" : ""}>
                          <td className="px-3 py-2 text-gray-500">{r.row}</td>
                          <td className="px-3 py-2 font-mono text-gray-700">{r.device_id || "\u2014"}</td>
                          <td className="px-3 py-2 font-mono text-gray-500 max-w-[140px] truncate">{r.iccid || "\u2014"}</td>
                          <td className="px-3 py-2 text-gray-700 max-w-[160px] truncate">{r.target_site_name || r.site_name || "\u2014"}</td>
                          <td className="px-3 py-2 text-gray-600 max-w-[140px] truncate">{r.target_customer || r.customer_name || "\u2014"}</td>
                          <td className="px-3 py-2">
                            <ActionBadge action={r.action} />
                          </td>
                          <td className="px-3 py-2">
                            {r.errors?.length > 0 && <span className="text-red-600 font-medium">{r.errors.length} error{r.errors.length > 1 ? "s" : ""}</span>}
                            {!(r.errors?.length > 0) && r.warnings?.length > 0 && <span className="text-amber-600">{r.warnings.length} warn</span>}
                            {!(r.errors?.length > 0) && !(r.warnings?.length > 0) && <span className="text-emerald-600">OK</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Confirm / Cancel */}
            <div className="flex gap-3">
              <button
                onClick={reset}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleCommit}
                disabled={committing || !canCommit}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white rounded-xl text-sm font-semibold"
                title={
                  preview.has_errors
                    ? "Fix all errors before committing"
                    : !canCommit
                    ? "No assignments to make"
                    : ""
                }
              >
                {committing ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Assigning...</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4" /> Confirm Assignment ({preview.will_assign + preview.will_reassign})</>
                )}
              </button>
            </div>

            {preview.has_errors && (
              <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                Fix all errors in your CSV and re-upload. Rows with errors will be skipped on commit.
              </div>
            )}

            {preview.will_reassign > 0 && !preview.has_errors && (
              <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                {preview.will_reassign} device{preview.will_reassign > 1 ? "s" : ""} will be reassigned from their current site. Review the warnings above.
              </div>
            )}
          </div>
        )}

        {/* Commit Results */}
        {commitResult && (
          <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" /> Assignment Complete
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <ResultCard label="Assigned" value={commitResult.assigned} color="emerald" />
                <ResultCard label="Reassigned" value={commitResult.reassigned} color="amber" />
                <ResultCard label="Already Correct" value={commitResult.already_assigned} color="blue" />
                <ResultCard label="Skipped" value={commitResult.skipped} color="gray" />
              </div>
            </div>
            {commitResult.errors?.length > 0 && (
              <div className="p-4">
                <p className="text-xs font-semibold text-gray-600 uppercase mb-2">Issues</p>
                <div className="space-y-1 max-h-[200px] overflow-y-auto">
                  {commitResult.errors.map((err, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-amber-700">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span>{err}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="p-4 flex gap-3">
              <button onClick={reset} className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50">
                Assign More
              </button>
              <Link to={createPageUrl("Devices")} className="flex-1 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium text-center flex items-center justify-center gap-1">
                <Cpu className="w-4 h-4" /> View Devices
              </Link>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}

function SummaryCard({ label, value, color }) {
  const colorMap = {
    emerald: "bg-emerald-50 text-emerald-700",
    blue: "bg-blue-50 text-blue-700",
    amber: "bg-amber-50 text-amber-700",
    red: "bg-red-50 text-red-700",
    gray: "bg-gray-50 text-gray-700",
  };
  return (
    <div className={`rounded-lg p-3 text-center ${colorMap[color] || colorMap.gray}`}>
      <p className="text-xl font-bold">{value}</p>
      <p className="text-[10px] uppercase tracking-wide opacity-70">{label}</p>
    </div>
  );
}

function ResultCard({ label, value, color }) {
  const colorMap = {
    emerald: "bg-emerald-50",
    blue: "bg-blue-50",
    amber: "bg-amber-50",
    gray: "bg-gray-50",
    red: "bg-red-50",
  };
  const textMap = {
    emerald: "text-emerald-600",
    blue: "text-blue-600",
    amber: "text-amber-600",
    gray: "text-gray-900",
    red: "text-red-600",
  };
  return (
    <div className={`text-center p-3 rounded-lg ${colorMap[color] || colorMap.gray}`}>
      <p className={`text-2xl font-bold ${textMap[color] || textMap.gray}`}>{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  );
}

function ActionBadge({ action }) {
  const styles = {
    assign: "bg-emerald-100 text-emerald-700",
    reassign: "bg-amber-100 text-amber-700",
    already_assigned: "bg-blue-100 text-blue-700",
    unmatched: "bg-red-100 text-red-700",
    conflict: "bg-red-100 text-red-700",
    error: "bg-red-100 text-red-700",
  };
  const labels = {
    assign: "Assign",
    reassign: "Reassign",
    already_assigned: "Already OK",
    unmatched: "Not Found",
    conflict: "Conflict",
    error: "Error",
  };
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${styles[action] || styles.error}`}>
      {labels[action] || action}
    </span>
  );
}
