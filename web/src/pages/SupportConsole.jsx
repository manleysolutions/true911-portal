/**
 * Support Console — internal admin-only page for reviewing AI support sessions.
 *
 * Three-column layout:
 *   LEFT:   Session queue with filters
 *   CENTER: Transcript + AI summary
 *   RIGHT:  Diagnostics / context panel
 *
 * Accessible to Admin and SuperAdmin roles only.
 */

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import { HelpCircle, ShieldAlert } from "lucide-react";

import SupportFiltersBar from "@/components/support/SupportFiltersBar";
import SupportSessionQueue from "@/components/support/SupportSessionQueue";
import SupportTranscriptPanel from "@/components/support/SupportTranscriptPanel";
import SupportSummaryPanel from "@/components/support/SupportSummaryPanel";
import SupportDiagnosticsPanel from "@/components/support/SupportDiagnosticsPanel";
import SupportActionsBar from "@/components/support/SupportActionsBar";

export default function SupportConsole() {
  const { user, can } = useAuth();

  // ── State ──
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [filters, setFilters] = useState({ status: "", escalated: "", search: "" });

  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);      // { session, messages, diagnostics }
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // ── Access check ──
  const isAdmin = user?.role === "Admin" || user?.role === "SuperAdmin";
  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <ShieldAlert className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-gray-800">Access Restricted</h2>
          <p className="text-sm text-gray-500 mt-1">The Support Console is available to Admin and SuperAdmin users only.</p>
        </div>
      </div>
    );
  }

  // ── Fetch sessions ──
  const fetchSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.status) params.set("status", filters.status);
      if (filters.escalated === "true") params.set("escalated", "true");
      params.set("limit", "100");
      const qs = params.toString() ? `?${params}` : "";
      const data = await apiFetch(`/support/sessions${qs}`);
      let filtered = data;
      // Client-side search filter (backend doesn't have full-text search)
      if (filters.search) {
        const q = filters.search.toLowerCase();
        filtered = data.filter((s) =>
          s.tenant_id?.toLowerCase().includes(q) ||
          s.issue_category?.toLowerCase().includes(q) ||
          String(s.site_id).includes(q) ||
          String(s.device_id).includes(q)
        );
      }
      setSessions(filtered);
    } catch (err) {
      toast.error("Failed to load support sessions");
    }
    setSessionsLoading(false);
  }, [filters.status, filters.escalated, filters.search]);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  // Auto-refresh every 30s
  useEffect(() => {
    const iv = setInterval(fetchSessions, 30000);
    return () => clearInterval(iv);
  }, [fetchSessions]);

  // ── Fetch detail ──
  const fetchDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return; }
    setDetailLoading(true);
    try {
      const data = await apiFetch(`/support/sessions/${id}`);
      setDetail(data);
    } catch (err) {
      toast.error("Failed to load session detail");
      setDetail(null);
    }
    setDetailLoading(false);
  }, []);

  useEffect(() => { fetchDetail(selectedId); }, [selectedId, fetchDetail]);

  // ── Actions ──
  const handleRunDiagnostics = async () => {
    if (!selectedId) return;
    setActionLoading(true);
    try {
      await apiFetch("/support/diagnostics/run", {
        method: "POST",
        body: JSON.stringify({ session_id: selectedId }),
      });
      toast.success("Diagnostics complete");
      await fetchDetail(selectedId);
    } catch (err) {
      toast.error(err?.message || "Failed to run diagnostics");
    }
    setActionLoading(false);
  };

  const handleEscalate = async (reason) => {
    if (!selectedId) return;
    setActionLoading(true);
    try {
      await apiFetch("/support/escalate", {
        method: "POST",
        body: JSON.stringify({ session_id: selectedId, reason }),
      });
      toast.success("Session escalated");
      await fetchDetail(selectedId);
      await fetchSessions();
    } catch (err) {
      toast.error(err?.message || "Escalation failed");
    }
    setActionLoading(false);
  };

  const handleMarkResolved = async () => {
    if (!selectedId) return;
    setActionLoading(true);
    try {
      await apiFetch(`/support/sessions/${selectedId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "resolved" }),
      });
      toast.success("Session marked as resolved");
      await fetchDetail(selectedId);
      await fetchSessions();
    } catch (err) {
      toast.error(err?.message || "Failed to update session");
    }
    setActionLoading(false);
  };

  const handleRefresh = async () => {
    await fetchSessions();
    if (selectedId) await fetchDetail(selectedId);
    toast.success("Refreshed");
  };

  // ── Render ──
  const session = detail?.session;
  const messages = detail?.messages || [];
  const diagnostics = detail?.diagnostics || [];
  const escalations = detail?.escalations || [];

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 bg-white flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-red-50 rounded-lg flex items-center justify-center">
            <HelpCircle className="w-4.5 h-4.5 text-red-600" />
          </div>
          <div>
            <h1 className="text-base font-bold text-gray-900">Support Console</h1>
            <p className="text-[11px] text-gray-500">AI support sessions &middot; Internal only</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{sessions.length} session{sessions.length !== 1 ? "s" : ""}</span>
          {sessions.filter((s) => s.escalated).length > 0 && (
            <span className="text-red-600 font-medium">
              {sessions.filter((s) => s.escalated).length} escalated
            </span>
          )}
        </div>
      </div>

      {/* Three-column layout */}
      <div className="flex-1 flex min-h-0">
        {/* LEFT: Session Queue */}
        <div className="w-[280px] flex-shrink-0 border-r border-gray-200 bg-white flex flex-col">
          <SupportFiltersBar filters={filters} onChange={setFilters} />
          <div className="flex-1 overflow-y-auto">
            <SupportSessionQueue
              sessions={sessions}
              selectedId={selectedId}
              onSelect={setSelectedId}
              loading={sessionsLoading}
            />
          </div>
        </div>

        {/* CENTER: Transcript + Summary */}
        <div className="flex-1 flex flex-col min-w-0 bg-white">
          {!selectedId ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <HelpCircle className="w-10 h-10 text-gray-200 mx-auto mb-3" />
                <p className="text-sm text-gray-400">Select a session to view details</p>
              </div>
            </div>
          ) : detailLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-gray-300 border-t-red-600 rounded-full animate-spin" />
            </div>
          ) : (
            <>
              {/* AI Summary card at top */}
              <div className="border-b border-gray-200 bg-gray-50/50 flex-shrink-0">
                <SupportSummaryPanel session={session} messages={messages} escalations={escalations} />
              </div>

              {/* Transcript */}
              <SupportTranscriptPanel messages={messages} />

              {/* Actions */}
              <SupportActionsBar
                session={session}
                onRunDiagnostics={handleRunDiagnostics}
                onRefresh={handleRefresh}
                onEscalate={handleEscalate}
                onMarkResolved={handleMarkResolved}
                loading={actionLoading}
              />
            </>
          )}
        </div>

        {/* RIGHT: Diagnostics / Context */}
        <div className="w-[280px] flex-shrink-0 border-l border-gray-200 bg-white overflow-y-auto">
          {selectedId ? (
            <SupportDiagnosticsPanel diagnostics={diagnostics} />
          ) : (
            <div className="p-4 text-center text-sm text-gray-400 mt-8">
              Diagnostics will appear here when a session is selected.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
