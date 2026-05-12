/**
 * Onboarding Review queue (Phase A).
 *
 * Triage surface owned by the Data Steward role.  Reads gated by
 * VIEW_ONBOARDING_REVIEW; writes by MANAGE_ONBOARDING_REVIEW.  The page
 * is intentionally simple — list, filter, add note, change status,
 * assign, link out to the underlying record, export CSV.  No bulk
 * actions, no destructive operations.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  ClipboardList, Search, RefreshCw, Loader2, Plus, Download,
  AlertCircle, Building2, Cpu, FileSpreadsheet, ExternalLink, X,
} from "lucide-react";
import { toast } from "sonner";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { OnboardingReviewAPI } from "@/api/onboardingReview";

// ── Static option sets — mirror api/app/schemas/onboarding_review.py.

const ENTITY_TYPES = ["customer", "site", "device", "line", "import_row", "other"];

const ISSUE_TYPES = [
  "missing_address",
  "missing_identifier",
  "duplicate_candidate",
  "e911_needs_review",
  "customer_site_mismatch",
  "napco_manual_verification",
  "other",
];

const STATUSES = [
  "pending_review",
  "waiting_on_stuart",
  "ready_to_import",
  "imported",
  "hold",
  "resolved",
  "rejected",
];

const PRIORITIES = ["low", "normal", "high"];

const STATUS_TONE = {
  pending_review: "bg-amber-50 text-amber-700 border-amber-200",
  waiting_on_stuart: "bg-violet-50 text-violet-700 border-violet-200",
  ready_to_import: "bg-cyan-50 text-cyan-700 border-cyan-200",
  imported: "bg-emerald-50 text-emerald-700 border-emerald-200",
  hold: "bg-slate-100 text-slate-600 border-slate-200",
  resolved: "bg-emerald-100 text-emerald-800 border-emerald-300",
  rejected: "bg-red-50 text-red-700 border-red-200",
};

const PRIORITY_TONE = {
  low: "bg-slate-50 text-slate-500 border-slate-200",
  normal: "bg-slate-100 text-slate-700 border-slate-200",
  high: "bg-red-50 text-red-700 border-red-200",
};

const ENTITY_ICON = {
  customer: Building2,
  site: Building2,
  device: Cpu,
  line: FileSpreadsheet,
  import_row: FileSpreadsheet,
  other: ClipboardList,
};


function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.pending_review;
  return (
    <span className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full border ${tone}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function PriorityBadge({ priority }) {
  const tone = PRIORITY_TONE[priority] || PRIORITY_TONE.normal;
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded border ${tone}`}>
      {priority}
    </span>
  );
}

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleString(); } catch { return s; }
}

function linkFor(item) {
  if (!item.entity_id) return null;
  switch (item.entity_type) {
    case "customer": return createPageUrl(`Customers`);
    case "site": return createPageUrl(`SiteDetail?id=${encodeURIComponent(item.entity_id)}`);
    case "device": return createPageUrl(`Devices`);
    case "line": return createPageUrl(`Lines`);
    case "import_row": return createPageUrl(`ImportVerification`);
    default: return null;
  }
}


// ───────────────────────────────────────────────────────────────────
// New item modal
// ───────────────────────────────────────────────────────────────────

function NewReviewModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    entity_type: "site",
    entity_id: "",
    external_ref: "",
    issue_type: "missing_address",
    priority: "normal",
    assigned_to: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);

  if (!open) return null;

  const update = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { ...form };
      // Drop blank optional strings so the server sees null/missing.
      ["entity_id", "external_ref", "assigned_to", "notes"].forEach(k => {
        if (!body[k]) delete body[k];
      });
      const created = await OnboardingReviewAPI.create(body);
      toast.success(`Created ${created.review_id}`);
      onCreated?.(created);
      onClose();
    } catch (err) {
      toast.error(`Create failed: ${err.message || err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-900">New review item</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-500">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-gray-600">
              Entity type
              <select value={form.entity_type} onChange={update("entity_type")} className="mt-1 w-full text-sm border-gray-300 rounded">
                {ENTITY_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="text-xs text-gray-600">
              Issue type
              <select value={form.issue_type} onChange={update("issue_type")} className="mt-1 w-full text-sm border-gray-300 rounded">
                {ISSUE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-gray-600">
              Entity ID <span className="text-gray-400">(optional)</span>
              <input value={form.entity_id} onChange={update("entity_id")} className="mt-1 w-full text-sm border-gray-300 rounded" />
            </label>
            <label className="text-xs text-gray-600">
              External ref <span className="text-gray-400">(optional)</span>
              <input value={form.external_ref} onChange={update("external_ref")} className="mt-1 w-full text-sm border-gray-300 rounded" />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-gray-600">
              Priority
              <select value={form.priority} onChange={update("priority")} className="mt-1 w-full text-sm border-gray-300 rounded">
                {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label className="text-xs text-gray-600">
              Assigned to <span className="text-gray-400">(email)</span>
              <input value={form.assigned_to} onChange={update("assigned_to")} className="mt-1 w-full text-sm border-gray-300 rounded" placeholder="name@manleysolutions.com" />
            </label>
          </div>

          <label className="block text-xs text-gray-600">
            Notes
            <textarea value={form.notes} onChange={update("notes")} rows={3} className="mt-1 w-full text-sm border-gray-300 rounded" />
          </label>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="text-sm px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={saving} className="text-sm px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50">
              {saving ? "Saving..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


// ───────────────────────────────────────────────────────────────────
// Row detail drawer
// ───────────────────────────────────────────────────────────────────

function RowDrawer({ item, onClose, onSaved, canManage }) {
  const [form, setForm] = useState({
    status: item.status,
    priority: item.priority,
    assigned_to: item.assigned_to || "",
    notes: item.notes || "",
    resolution_notes: item.resolution_notes || "",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm({
      status: item.status,
      priority: item.priority,
      assigned_to: item.assigned_to || "",
      notes: item.notes || "",
      resolution_notes: item.resolution_notes || "",
    });
  }, [item.review_id]);

  const update = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...form };
      // Coerce empty strings to null so the server clears them.
      ["assigned_to", "notes", "resolution_notes"].forEach(k => {
        if (body[k] === "") body[k] = null;
      });
      const updated = await OnboardingReviewAPI.update(item.review_id, body);
      toast.success(`Saved ${updated.review_id}`);
      onSaved?.(updated);
    } catch (err) {
      toast.error(`Save failed: ${err.message || err}`);
    } finally {
      setSaving(false);
    }
  };

  const link = linkFor(item);
  const Icon = ENTITY_ICON[item.entity_type] || ClipboardList;

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="w-[460px] bg-white shadow-xl overflow-y-auto">
        <div className="p-5 border-b">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-[11px] text-gray-500 uppercase tracking-wide">
                <Icon className="w-3.5 h-3.5" />
                {item.entity_type} · {item.issue_type.replace(/_/g, " ")}
              </div>
              <div className="mt-0.5 text-base font-semibold text-gray-900">{item.review_id}</div>
              {(item.entity_id || item.external_ref) && (
                <div className="mt-1 text-xs text-gray-600 break-all">
                  {item.entity_id && <span>id: {item.entity_id}</span>}
                  {item.entity_id && item.external_ref && <span> · </span>}
                  {item.external_ref && <span>ref: {item.external_ref}</span>}
                </div>
              )}
            </div>
            <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-500">
              <X className="w-4 h-4" />
            </button>
          </div>

          {link && (
            <Link to={link} className="inline-flex items-center gap-1.5 mt-3 text-xs font-medium text-blue-600 hover:text-blue-800">
              Open related record <ExternalLink className="w-3 h-3" />
            </Link>
          )}
        </div>

        <div className="p-5 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-gray-600">
              Status
              <select value={form.status} onChange={update("status")} disabled={!canManage} className="mt-1 w-full text-sm border-gray-300 rounded disabled:bg-gray-50">
                {STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </label>
            <label className="text-xs text-gray-600">
              Priority
              <select value={form.priority} onChange={update("priority")} disabled={!canManage} className="mt-1 w-full text-sm border-gray-300 rounded disabled:bg-gray-50">
                {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>

          <label className="block text-xs text-gray-600">
            Assigned to
            <input value={form.assigned_to} onChange={update("assigned_to")} disabled={!canManage} className="mt-1 w-full text-sm border-gray-300 rounded disabled:bg-gray-50" placeholder="email@example.com" />
          </label>

          <label className="block text-xs text-gray-600">
            Notes
            <textarea value={form.notes} onChange={update("notes")} disabled={!canManage} rows={4} className="mt-1 w-full text-sm border-gray-300 rounded disabled:bg-gray-50" />
          </label>

          <label className="block text-xs text-gray-600">
            Resolution notes
            <textarea value={form.resolution_notes} onChange={update("resolution_notes")} disabled={!canManage} rows={3} className="mt-1 w-full text-sm border-gray-300 rounded disabled:bg-gray-50" />
          </label>

          <div className="grid grid-cols-2 gap-3 pt-2 text-[11px] text-gray-500">
            <div>Created: <span className="text-gray-700">{fmtDate(item.created_at)}</span></div>
            <div>Updated: <span className="text-gray-700">{fmtDate(item.updated_at)}</span></div>
            {item.created_by && <div>By: <span className="text-gray-700">{item.created_by}</span></div>}
            {item.resolved_at && <div>Resolved: <span className="text-gray-700">{fmtDate(item.resolved_at)}</span></div>}
          </div>

          {canManage && (
            <div className="pt-3 flex items-center justify-end gap-2">
              <button onClick={save} disabled={saving} className="text-sm px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50">
                {saving ? "Saving..." : "Save changes"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ───────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────

export default function OnboardingReview() {
  const { can } = useAuth();
  const canView = can("VIEW_ONBOARDING_REVIEW");
  const canManage = can("MANAGE_ONBOARDING_REVIEW");

  const [filters, setFilters] = useState({
    status: "",
    issue_type: "",
    entity_type: "",
    priority: "",
    assigned_to: "",
    search: "",
  });
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    if (!canView) return;
    setLoading(true);
    setError(null);
    try {
      const res = await OnboardingReviewAPI.list({ ...filters, limit: 200 });
      setItems(res.items || []);
      setTotal(res.total ?? (res.items?.length ?? 0));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }, [filters, canView]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (k) => (e) => setFilters(f => ({ ...f, [k]: e.target.value }));

  const onSaved = (updated) => {
    setItems(arr => arr.map(it => it.review_id === updated.review_id ? updated : it));
    setSelected(updated);
  };

  const onCreated = (created) => {
    setItems(arr => [created, ...arr]);
    setTotal(t => t + 1);
  };

  const onExport = async () => {
    try {
      await OnboardingReviewAPI.exportCsv(filters);
    } catch (err) {
      toast.error(`Export failed: ${err.message || err}`);
    }
  };

  const visibleCount = items.length;

  return (
    <PageWrapper>
      <div className="p-4 max-w-7xl mx-auto">
        <header className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2 text-gray-900">
              <ClipboardList className="w-5 h-5 text-slate-700" />
              <h1 className="text-lg font-semibold">Onboarding Review</h1>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Triage queue for records that need a steward's attention. {total > 0 && (
                <span className="font-medium text-gray-700">Showing {visibleCount} of {total}.</span>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={load} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded border border-gray-300 hover:bg-gray-50 text-gray-700">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
            <button onClick={onExport} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded border border-gray-300 hover:bg-gray-50 text-gray-700">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            {canManage && (
              <button onClick={() => setShowNew(true)} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800">
                <Plus className="w-3.5 h-3.5" /> New item
              </button>
            )}
          </div>
        </header>

        {/* Filter bar */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-3">
          <div className="relative col-span-2">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input value={filters.search} onChange={setFilter("search")} placeholder="Search review id, entity id, ref, notes" className="w-full pl-7 text-sm border-gray-300 rounded" />
          </div>
          <select value={filters.status} onChange={setFilter("status")} className="text-sm border-gray-300 rounded">
            <option value="">Any status</option>
            {STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
          <select value={filters.issue_type} onChange={setFilter("issue_type")} className="text-sm border-gray-300 rounded">
            <option value="">Any issue</option>
            {ISSUE_TYPES.map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
          <select value={filters.entity_type} onChange={setFilter("entity_type")} className="text-sm border-gray-300 rounded">
            <option value="">Any entity</option>
            {ENTITY_TYPES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filters.priority} onChange={setFilter("priority")} className="text-sm border-gray-300 rounded">
            <option value="">Any priority</option>
            {PRIORITIES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {/* Table */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading...
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-12 text-red-600 text-sm">
              <AlertCircle className="w-4 h-4 mr-2" /> {error}
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-gray-500">
              <ClipboardList className="w-8 h-8 text-gray-300 mb-2" />
              <div className="text-sm">No review items match these filters.</div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-[11px] uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="text-left px-3 py-2 font-semibold">Review</th>
                  <th className="text-left px-3 py-2 font-semibold">Entity</th>
                  <th className="text-left px-3 py-2 font-semibold">Issue</th>
                  <th className="text-left px-3 py-2 font-semibold">Status</th>
                  <th className="text-left px-3 py-2 font-semibold">Priority</th>
                  <th className="text-left px-3 py-2 font-semibold">Assigned</th>
                  <th className="text-left px-3 py-2 font-semibold">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map(item => {
                  const Icon = ENTITY_ICON[item.entity_type] || ClipboardList;
                  return (
                    <tr key={item.review_id} onClick={() => setSelected(item)} className="cursor-pointer hover:bg-slate-50">
                      <td className="px-3 py-2 font-mono text-[11px] text-gray-700">{item.review_id}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1.5 text-gray-700">
                          <Icon className="w-3.5 h-3.5 text-gray-400" />
                          <span>{item.entity_type}</span>
                          {item.entity_id && <span className="text-[11px] text-gray-500">· {item.entity_id}</span>}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-gray-700">{item.issue_type.replace(/_/g, " ")}</td>
                      <td className="px-3 py-2"><StatusBadge status={item.status} /></td>
                      <td className="px-3 py-2"><PriorityBadge priority={item.priority} /></td>
                      <td className="px-3 py-2 text-gray-700 text-xs">{item.assigned_to || "—"}</td>
                      <td className="px-3 py-2 text-gray-500 text-xs">{fmtDate(item.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {selected && (
        <RowDrawer
          item={selected}
          onClose={() => setSelected(null)}
          onSaved={onSaved}
          canManage={canManage}
        />
      )}
      <NewReviewModal
        open={showNew}
        onClose={() => setShowNew(false)}
        onCreated={onCreated}
      />
    </PageWrapper>
  );
}
