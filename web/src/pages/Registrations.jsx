/**
 * Internal registration review queue (Phase R3).
 *
 * Authenticated page gated by VIEW_REGISTRATIONS.  Lists all
 * registrations across the "ops" tenant — the staging side of the
 * customer onboarding workflow.  Row actions take the reviewer to
 * RegistrationDetail for the actual approve / request-info / cancel
 * operations.
 *
 * Conversion into production rows is NOT exposed on this page yet;
 * it lands in Phase R4.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  ClipboardList, Search, Filter, RefreshCw, Loader2, ChevronRight,
  AlertCircle, Building2, Phone,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { RegistrationAdminAPI } from "@/api/registrations";

// ── Status presentation ─────────────────────────────────────────────

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-600 border-slate-200",
  submitted: "bg-blue-50 text-blue-700 border-blue-200",
  internal_review: "bg-indigo-50 text-indigo-700 border-indigo-200",
  pending_customer_info: "bg-amber-50 text-amber-700 border-amber-200",
  pending_equipment_assignment: "bg-violet-50 text-violet-700 border-violet-200",
  pending_sim_assignment: "bg-violet-50 text-violet-700 border-violet-200",
  pending_installer_schedule: "bg-violet-50 text-violet-700 border-violet-200",
  scheduled: "bg-cyan-50 text-cyan-700 border-cyan-200",
  installed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  qa_review: "bg-emerald-50 text-emerald-700 border-emerald-200",
  ready_for_activation: "bg-emerald-50 text-emerald-700 border-emerald-200",
  active: "bg-emerald-100 text-emerald-800 border-emerald-300",
  cancelled: "bg-red-50 text-red-700 border-red-200",
};

const STATUS_LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  internal_review: "In Review",
  pending_customer_info: "Awaiting Customer",
  pending_equipment_assignment: "Equipment",
  pending_sim_assignment: "SIM",
  pending_installer_schedule: "Scheduling",
  scheduled: "Scheduled",
  installed: "Installed",
  qa_review: "QA",
  ready_for_activation: "Ready",
  active: "Active",
  cancelled: "Cancelled",
};

const FILTER_TABS = [
  { value: "", label: "All" },
  { value: "submitted", label: "New" },
  { value: "internal_review", label: "In Review" },
  { value: "pending_customer_info", label: "Awaiting Customer" },
  { value: "pending_equipment_assignment", label: "Equipment" },
  { value: "pending_sim_assignment", label: "SIM" },
  { value: "pending_installer_schedule", label: "Scheduling" },
  { value: "scheduled", label: "Scheduled" },
  { value: "installed", label: "Installed" },
  { value: "active", label: "Active" },
  { value: "cancelled", label: "Cancelled" },
];

function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.draft;
  const label = STATUS_LABELS[status] || status;
  return (
    <span className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full border ${tone}`}>
      {label}
    </span>
  );
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return "—";
  }
}


// ── Page ────────────────────────────────────────────────────────────

export default function Registrations() {
  const { can } = useAuth();
  const canView = can("VIEW_REGISTRATIONS");

  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({ total: 0, by_status: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, c] = await Promise.all([
        RegistrationAdminAPI.list({ status: statusFilter || undefined, search: search || undefined, limit: 300 }),
        RegistrationAdminAPI.count(),
      ]);
      setRows(Array.isArray(list) ? list : []);
      setCounts(c || { total: 0, by_status: {} });
    } catch (err) {
      setError(err?.message || "Failed to load registrations.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search]);

  useEffect(() => {
    if (canView) reload();
  }, [reload, canView]);

  // Debounce the free-text search so we don't fire on every keystroke.
  // 300ms feels responsive without thrashing the API.
  const [searchInput, setSearchInput] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  if (!canView) {
    return (
      <PageWrapper>
        <div className="p-6 text-sm text-gray-500">
          You do not have permission to view registrations.
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-7xl mx-auto p-6 space-y-5">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                <ClipboardList className="w-5 h-5 text-red-600" />
                Registrations
              </h1>
              <p className="text-xs text-gray-500 mt-1">
                Customer onboarding submissions awaiting review.
              </p>
            </div>
            <button
              onClick={reload}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-60"
            >
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
              Refresh
            </button>
          </div>

          {/* Filter chips + count */}
          <div className="bg-white rounded-xl border border-gray-200 p-3">
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              <Filter className="w-3.5 h-3.5 text-gray-400 mr-1" />
              {FILTER_TABS.map((tab) => {
                const count = tab.value === ""
                  ? counts.total
                  : counts.by_status?.[tab.value] || 0;
                const active = statusFilter === tab.value;
                return (
                  <button
                    key={tab.value || "all"}
                    onClick={() => setStatusFilter(tab.value)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                      active
                        ? "bg-red-600 text-white border-red-600"
                        : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    {tab.label}
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${active ? "bg-red-700/40" : "bg-gray-100 text-gray-500"}`}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search by reference number, company, or submitter email…"
                className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500"
              />
            </div>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Table */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <Th>Reference</Th>
                    <Th>Customer</Th>
                    <Th>Contact</Th>
                    <Th>Status</Th>
                    <Th className="text-center">Locations</Th>
                    <Th className="text-center">Phones</Th>
                    <Th>Hardware / Carrier</Th>
                    <Th>Submitted</Th>
                    <Th className="text-right pr-4">Action</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {loading && rows.length === 0 && (
                    <tr><td colSpan={9} className="py-10 text-center text-gray-400">
                      <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> Loading…
                    </td></tr>
                  )}
                  {!loading && rows.length === 0 && (
                    <tr><td colSpan={9} className="py-10 text-center text-gray-400">
                      No registrations match your filters yet.
                    </td></tr>
                  )}
                  {rows.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{r.registration_id}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-start gap-2">
                          <Building2 className="w-3.5 h-3.5 text-gray-400 mt-0.5" />
                          <div>
                            <div className="text-gray-900 font-medium">{r.customer_name || <span className="italic text-gray-400">—</span>}</div>
                            <div className="text-[11px] text-gray-500">{r.submitter_email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-gray-900">{r.poc_name || <span className="italic text-gray-400">—</span>}</div>
                        <div className="text-[11px] text-gray-500 flex items-center gap-2">
                          {r.poc_phone && <span className="inline-flex items-center gap-1"><Phone className="w-3 h-3" />{r.poc_phone}</span>}
                          {r.poc_email && <span className="truncate max-w-[14ch]" title={r.poc_email}>{r.poc_email}</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                      <td className="px-4 py-3 text-center text-gray-700">{r.locations_count}</td>
                      <td className="px-4 py-3 text-center text-gray-700">{r.service_units_count}</td>
                      <td className="px-4 py-3 text-xs text-gray-600">
                        {(r.hardware_summary || r.carrier_summary) ? (
                          <span>
                            {r.hardware_summary || <span className="text-gray-300">—</span>}
                            <span className="text-gray-300 mx-1">·</span>
                            {r.carrier_summary || <span className="text-gray-300">—</span>}
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-600 whitespace-nowrap">
                        {formatDate(r.submitted_at || r.created_at)}
                      </td>
                      <td className="px-4 py-3 text-right pr-4">
                        <Link
                          to={`${createPageUrl("RegistrationDetail")}?id=${encodeURIComponent(r.registration_id)}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-red-600 hover:text-red-700"
                        >
                          View <ChevronRight className="w-3 h-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}

function Th({ children, className = "" }) {
  return (
    <th className={`px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-gray-500 ${className}`}>
      {children}
    </th>
  );
}
