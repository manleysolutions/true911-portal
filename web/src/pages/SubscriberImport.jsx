import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Upload, FileSpreadsheet, CheckCircle2, AlertTriangle, XCircle,
  Download, ArrowLeft, Loader2, Building2, Cpu, Phone, Sim,
  ChevronDown, ChevronUp, Info, Users, ArrowRight, Search,
  Filter, FileDown,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const API_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL;
const authHeaders = () => ({
  Authorization: `Bearer ${localStorage.getItem("access_token")}`,
});

const STEPS = [
  { id: "upload", label: "Upload CSV" },
  { id: "preview", label: "Review Preview" },
  { id: "commit", label: "Confirm Import" },
  { id: "result", label: "Results" },
];

export default function SubscriberImport() {
  const { can } = useAuth();
  const [step, setStep] = useState("upload");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [commitResult, setCommitResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [showRows, setShowRows] = useState(false);
  const [filterStatus, setFilterStatus] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer?.files?.[0];
    if (f && f.name.endsWith(".csv")) {
      setFile(f);
      setPreview(null);
      setCommitResult(null);
      setStep("upload");
    } else {
      toast.error("Please drop a .csv file");
    }
  }, []);

  const handleFileSelect = useCallback((e) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setPreview(null);
      setCommitResult(null);
      setStep("upload");
    }
  }, []);

  const handlePreview = async () => {
    if (!file) return;
    setLoading(true);
    setPreview(null);
    setCommitResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/command/subscriber-import/preview`, {
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
      setStep("preview");
      if (data.has_errors) toast.error("CSV has validation errors — review before importing");
      else toast.success(`Preview ready — ${data.total_rows} rows analyzed`);
    } catch (err) {
      toast.error(err.message || "Preview failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!file) return;
    setCommitting(true);
    setStep("commit");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/command/subscriber-import/commit`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Import failed (${res.status})`);
      }
      const data = await res.json();
      setCommitResult(data);
      setPreview(null);
      setStep("result");
      toast.success(
        `Import complete: ${data.summary.lines_created} lines, ` +
        `${data.summary.devices_created} devices, ` +
        `${data.summary.sites_created} sites created`
      );
    } catch (err) {
      toast.error(err.message || "Import failed");
      setStep("preview");
    } finally {
      setCommitting(false);
    }
  };

  const downloadTemplate = async () => {
    try {
      const res = await fetch(`${API_URL}/command/subscriber-import/template-csv`, {
        headers: authHeaders(),
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "subscriber_import_template.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to download template");
    }
  };

  const exportProblems = () => {
    if (!preview) return;
    const problems = preview.rows.filter(r => r.errors.length > 0 || r.warnings.length > 0);
    const csv = "row,customer,site,device,msisdn,status,errors,warnings\n" +
      problems.map(r =>
        `${r.row},"${r.customer_name || ""}","${r.site_name || ""}","${r.device_id || ""}","${r.msisdn || ""}",${r.status},"${r.errors.join("; ")}","${r.warnings.join("; ")}"`
      ).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "import_problems.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setCommitResult(null);
    setShowRows(false);
    setStep("upload");
    setFilterStatus("all");
    setSearchTerm("");
  };

  if (!can("SUBSCRIBER_IMPORT")) {
    return (
      <PageWrapper>
        <div className="p-6 text-center text-gray-500">You do not have permission to access this page.</div>
      </PageWrapper>
    );
  }

  const filteredRows = preview?.rows?.filter(r => {
    if (filterStatus !== "all" && r.status !== filterStatus) return false;
    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      return (
        (r.customer_name || "").toLowerCase().includes(s) ||
        (r.site_name || "").toLowerCase().includes(s) ||
        (r.device_id || "").toLowerCase().includes(s) ||
        (r.msisdn || "").toLowerCase().includes(s) ||
        (r.sim_iccid || "").toLowerCase().includes(s)
      );
    }
    return true;
  }) || [];

  const summary = preview?.summary || {};

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto">
        <Link to={createPageUrl("Command")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 mb-4">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Command
        </Link>

        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-red-600" />
            <h1 className="text-2xl font-bold text-gray-900">Subscriber Import</h1>
          </div>
          <Link
            to={createPageUrl("ImportVerification")}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200"
          >
            Verification Dashboard <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        <p className="text-sm text-gray-500 mb-4">
          Import service lines from an audited spreadsheet. Each row = one line/subscription.
          Customer, site, and device fields may repeat across rows.
        </p>

        {/* Step indicator */}
        <div className="flex items-center gap-1 mb-6">
          {STEPS.map((s, idx) => (
            <div key={s.id} className="flex items-center gap-1">
              <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                step === s.id ? "bg-red-600 text-white" :
                STEPS.findIndex(x => x.id === step) > idx ? "bg-emerald-100 text-emerald-700" :
                "bg-gray-100 text-gray-400"
              }`}>
                {STEPS.findIndex(x => x.id === step) > idx && <CheckCircle2 className="w-3 h-3" />}
                {s.label}
              </div>
              {idx < STEPS.length - 1 && <ArrowRight className="w-3 h-3 text-gray-300" />}
            </div>
          ))}
        </div>

        {/* Help box + template */}
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-blue-900">Import Template & Instructions</p>
            <button onClick={downloadTemplate} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium">
              <Download className="w-3.5 h-3.5" /> Download Template
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-blue-800">
            <div className="flex items-start gap-1.5">
              <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span><strong>1 row = 1 line</strong> (service record / subscription)</span>
            </div>
            <div className="flex items-start gap-1.5">
              <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>Sites and devices may repeat across rows</span>
            </div>
            <div className="flex items-start gap-1.5">
              <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>Do not merge different devices into one row</span>
            </div>
            <div className="flex items-start gap-1.5">
              <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>Use consistent site naming for correct matching</span>
            </div>
          </div>
        </div>

        {/* Upload zone */}
        {(step === "upload") && (
          <>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors mb-4 ${
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
                  <p className="text-sm text-gray-600">Drag & drop your audited CSV file here, or</p>
                  <label className="inline-flex items-center gap-1.5 px-4 py-2 mt-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 cursor-pointer">
                    <FileSpreadsheet className="w-4 h-4" /> Browse Files
                    <input type="file" accept=".csv" onChange={handleFileSelect} className="hidden" />
                  </label>
                </div>
              )}
            </div>

            {file && (
              <button
                onClick={handlePreview}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white rounded-xl text-sm font-semibold"
              >
                {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing CSV...</> : <><FileSpreadsheet className="w-4 h-4" /> Preview Import</>}
              </button>
            )}
          </>
        )}

        {/* Preview Results */}
        {step === "preview" && preview && (
          <div className="space-y-4 mb-6">
            {/* Summary cards */}
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Import Preview Summary</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <SummaryCard icon={Users} label="New Customers" value={summary.new_tenants || 0} sub={`${summary.matched_tenants || 0} matched`} color="emerald" />
                <SummaryCard icon={Building2} label="New Sites" value={summary.new_sites || 0} sub={`${summary.matched_sites || 0} matched`} color="blue" />
                <SummaryCard icon={Cpu} label="New Devices" value={summary.new_devices || 0} sub={`${summary.matched_devices || 0} matched`} color="violet" />
                <SummaryCard icon={Phone} label="New Lines" value={summary.new_lines || 0} sub={`${summary.updated_lines || 0} updated`} color="amber" />
              </div>
              <div className="grid grid-cols-3 gap-3 mt-3">
                <MiniCard label="Total Rows" value={preview.total_rows} />
                <MiniCard label="Errors" value={summary.error_rows || 0} color={summary.error_rows > 0 ? "red" : "gray"} />
                <MiniCard label="Warnings" value={summary.warning_rows || 0} color={summary.warning_rows > 0 ? "amber" : "gray"} />
              </div>
            </div>

            {/* Error summary */}
            {(summary.error_rows || 0) > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <p className="text-sm font-semibold text-red-800 mb-2 flex items-center gap-1.5">
                  <XCircle className="w-4 h-4" /> {summary.error_rows} Row{summary.error_rows > 1 ? "s" : ""} with Errors
                </p>
                <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                  {preview.rows.filter(r => r.errors.length > 0).map(r => (
                    <div key={r.row} className="text-xs text-red-700">
                      <span className="font-medium">Row {r.row}</span>
                      {r.customer_name ? ` (${r.customer_name})` : ""}: {r.errors.join("; ")}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Warning summary */}
            {(summary.warning_rows || 0) > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <p className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4" /> {summary.warning_rows} Warning{summary.warning_rows > 1 ? "s" : ""}
                </p>
                <div className="space-y-1.5 max-h-[150px] overflow-y-auto">
                  {preview.rows.filter(r => r.warnings.length > 0 && r.errors.length === 0).slice(0, 20).map(r => (
                    <div key={r.row} className="text-xs text-amber-700">
                      <span className="font-medium">Row {r.row}</span>: {r.warnings.join("; ")}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Row detail */}
            <div className="flex items-center justify-between">
              <button
                onClick={() => setShowRows(!showRows)}
                className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700"
              >
                {showRows ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                {showRows ? "Hide" : "Show"} all {preview.total_rows} rows
              </button>
              {preview.rows.some(r => r.errors.length > 0 || r.warnings.length > 0) && (
                <button onClick={exportProblems} className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700">
                  <FileDown className="w-3 h-3" /> Export Problems
                </button>
              )}
            </div>

            {showRows && (
              <>
                {/* Filters */}
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search customer, site, device, MSISDN..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg"
                    />
                  </div>
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className="px-2 py-1.5 text-xs border border-gray-200 rounded-lg"
                  >
                    <option value="all">All Rows</option>
                    <option value="ok">OK</option>
                    <option value="warning">Warnings</option>
                    <option value="error">Errors</option>
                  </select>
                </div>

                <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Row</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Customer</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Site</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Device</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">MSISDN</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">SIM ICCID</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Customer</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Site</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Device</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Line</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {filteredRows.map(r => (
                          <tr key={r.row} className={r.errors.length > 0 ? "bg-red-50" : r.warnings.length > 0 ? "bg-amber-50" : ""}>
                            <td className="px-3 py-2 text-gray-500">{r.row}</td>
                            <td className="px-3 py-2 font-medium text-gray-900 max-w-[120px] truncate">{r.customer_name || "—"}</td>
                            <td className="px-3 py-2 text-gray-600 max-w-[120px] truncate">{r.site_name || "—"}</td>
                            <td className="px-3 py-2 text-gray-600 max-w-[100px] truncate">{r.device_id || "—"}</td>
                            <td className="px-3 py-2 text-gray-600">{r.msisdn || "—"}</td>
                            <td className="px-3 py-2 text-gray-600 max-w-[100px] truncate">{r.sim_iccid || "—"}</td>
                            <td className="px-3 py-2"><ActionBadge action={r.tenant_action} /></td>
                            <td className="px-3 py-2"><ActionBadge action={r.site_action} /></td>
                            <td className="px-3 py-2"><ActionBadge action={r.device_action} /></td>
                            <td className="px-3 py-2"><ActionBadge action={r.line_action} /></td>
                            <td className="px-3 py-2">
                              <StatusBadge status={r.status} errorCount={r.errors.length} warnCount={r.warnings.length} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {filteredRows.length === 0 && (
                    <p className="text-xs text-gray-400 text-center py-4">No rows match your filter</p>
                  )}
                </div>
              </>
            )}

            {/* Confirm / Cancel */}
            <div className="flex gap-3">
              <button
                onClick={reset}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel & Start Over
              </button>
              <button
                onClick={handleCommit}
                disabled={committing || preview.has_errors}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white rounded-xl text-sm font-semibold"
                title={preview.has_errors ? "Fix validation errors before importing" : ""}
              >
                {committing ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Importing...</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4" /> Confirm & Import</>
                )}
              </button>
            </div>

            {preview.has_errors && (
              <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                Fix all validation errors in your CSV and re-upload to continue.
              </div>
            )}
          </div>
        )}

        {/* Committing spinner */}
        {step === "commit" && committing && (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 text-red-600 animate-spin mx-auto mb-3" />
            <p className="text-sm font-medium text-gray-700">Importing subscriber data...</p>
            <p className="text-xs text-gray-400 mt-1">Creating customers, sites, devices, and lines</p>
          </div>
        )}

        {/* Commit Results */}
        {step === "result" && commitResult && (
          <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-900 mb-1 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" /> Import Complete
              </h3>
              <p className="text-xs text-gray-500 mb-3">Batch ID: {commitResult.batch_id}</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <ResultCard label="Customers Created" value={commitResult.summary.tenants_created} color="emerald" />
                <ResultCard label="Sites Created" value={commitResult.summary.sites_created} color="blue" />
                <ResultCard label="Devices Created" value={commitResult.summary.devices_created} color="violet" />
                <ResultCard label="Lines Created" value={commitResult.summary.lines_created} color="amber" />
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                <ResultCard label="Lines Updated" value={commitResult.summary.lines_updated} color="blue" />
                <ResultCard label="Rows Matched" value={commitResult.summary.rows_matched} color="gray" />
                <ResultCard label="Total Rows" value={commitResult.total_rows} color="gray" />
                <ResultCard label="Failed" value={commitResult.summary.rows_failed} color={commitResult.summary.rows_failed > 0 ? "red" : "gray"} />
              </div>
            </div>
            {commitResult.errors.length > 0 && (
              <div className="p-4">
                <p className="text-xs font-semibold text-gray-600 uppercase mb-2">Row Errors</p>
                <div className="space-y-1 max-h-[200px] overflow-y-auto">
                  {commitResult.errors.map((err, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-red-700">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span>{err}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="p-4 flex gap-3">
              <button onClick={reset} className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50">
                Import More
              </button>
              <Link
                to={createPageUrl("ImportVerification")}
                className="flex-1 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium text-center flex items-center justify-center gap-1"
              >
                <CheckCircle2 className="w-4 h-4" /> Verify Import
              </Link>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}

function SummaryCard({ icon: Icon, label, value, sub, color }) {
  const colorMap = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    violet: "bg-violet-50 text-violet-700 border-violet-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    gray: "bg-gray-50 text-gray-700 border-gray-200",
  };
  return (
    <div className={`rounded-lg p-3 text-center border ${colorMap[color] || colorMap.gray}`}>
      <Icon className="w-4 h-4 mx-auto mb-1 opacity-60" />
      <p className="text-xl font-bold">{value}</p>
      <p className="text-[10px] uppercase tracking-wide opacity-70">{label}</p>
      {sub && <p className="text-[10px] opacity-50 mt-0.5">{sub}</p>}
    </div>
  );
}

function MiniCard({ label, value, color = "gray" }) {
  const colors = {
    gray: "bg-gray-50 text-gray-700",
    red: "bg-red-50 text-red-700",
    amber: "bg-amber-50 text-amber-700",
  };
  return (
    <div className={`rounded-lg p-2 text-center ${colors[color] || colors.gray}`}>
      <p className="text-lg font-bold">{value}</p>
      <p className="text-[10px] uppercase tracking-wide opacity-60">{label}</p>
    </div>
  );
}

function ResultCard({ label, value, color }) {
  const colorMap = {
    emerald: "bg-emerald-50 text-emerald-600",
    blue: "bg-blue-50 text-blue-600",
    violet: "bg-violet-50 text-violet-600",
    amber: "bg-amber-50 text-amber-600",
    gray: "bg-gray-50 text-gray-900",
    red: "bg-red-50 text-red-600",
  };
  return (
    <div className={`text-center p-3 rounded-lg ${colorMap[color] || colorMap.gray}`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  );
}

function ActionBadge({ action }) {
  const styles = {
    create: "bg-emerald-100 text-emerald-700",
    match: "bg-blue-100 text-blue-700",
    update: "bg-amber-100 text-amber-700",
    duplicate: "bg-red-100 text-red-700",
    skip: "bg-gray-100 text-gray-500",
  };
  const labels = {
    create: "Create",
    match: "Match",
    update: "Update",
    duplicate: "Dup",
    skip: "—",
  };
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${styles[action] || styles.skip}`}>
      {labels[action] || action || "—"}
    </span>
  );
}

function StatusBadge({ status, errorCount, warnCount }) {
  if (status === "error") return <span className="text-red-600 font-medium text-[10px]">{errorCount} error{errorCount > 1 ? "s" : ""}</span>;
  if (status === "warning") return <span className="text-amber-600 text-[10px]">{warnCount} warn</span>;
  return <span className="text-emerald-600 text-[10px]">OK</span>;
}
