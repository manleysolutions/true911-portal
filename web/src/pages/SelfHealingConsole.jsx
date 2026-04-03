/**
 * Self-Healing Console — internal admin-only dashboard for remediation visibility.
 *
 * Answers: What did the system try? Did it work? Why did it stop?
 * Is a device noisy? Is a human handling this? Is life-safety at risk?
 *
 * Admin/SuperAdmin only.
 */

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import { ShieldAlert, Wrench, Activity, Cpu, Shield } from "lucide-react";

import SelfHealingKpiStrip from "@/components/support/SelfHealingKpiStrip";
import RemediationFiltersBar from "@/components/support/RemediationFiltersBar";
import RemediationActivityTable from "@/components/support/RemediationActivityTable";
import RemediationDetailPanel from "@/components/support/RemediationDetailPanel";
import DeviceRecoveryTable from "@/components/support/DeviceRecoveryTable";
import LifeSafetyRecoveryPanel from "@/components/support/LifeSafetyRecoveryPanel";

const TABS = [
  { id: "activity", label: "Activity", icon: Activity },
  { id: "devices", label: "Devices", icon: Cpu },
  { id: "life-safety", label: "Life-Safety", icon: Shield },
];

export default function SelfHealingConsole() {
  const { user } = useAuth();

  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({});
  const [selectedId, setSelectedId] = useState(null);
  const [activeTab, setActiveTab] = useState("activity");

  const isAdmin = user?.role === "Admin" || user?.role === "SuperAdmin";

  // Access check
  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <ShieldAlert className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-gray-800">Access Restricted</h2>
          <p className="text-sm text-gray-500 mt-1">The Self-Healing Console is available to Admin and SuperAdmin users only.</p>
        </div>
      </div>
    );
  }

  // Fetch records
  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.status) params.set("status", filters.status);
      if (filters.action_type) params.set("action_type", filters.action_type);
      if (filters.verification_status) params.set("verification_status", filters.verification_status);
      params.set("limit", "200");
      const qs = params.toString() ? `?${params}` : "";
      const data = await apiFetch(`/support/remediation${qs}`);

      // Client-side filtering for fields the backend doesn't filter
      let filtered = data;
      if (filters.search) {
        const q = filters.search.toLowerCase();
        filtered = filtered.filter((r) =>
          String(r.site_id).includes(q) ||
          String(r.device_id).includes(q) ||
          r.tenant_id?.toLowerCase().includes(q) ||
          r.issue_category?.toLowerCase().includes(q) ||
          r.action_type?.toLowerCase().includes(q) ||
          String(r.session_id || "").toLowerCase().includes(q) ||
          String(r.escalation_id || "").toLowerCase().includes(q)
        );
      }
      if (filters.escalated_only) {
        filtered = filtered.filter((r) => r.escalation_id != null);
      }
      if (filters.blocked_only) {
        filtered = filtered.filter((r) => r.status === "blocked" || r.status === "cooldown");
      }

      setRecords(filtered);
    } catch (err) {
      toast.error("Failed to load remediation data");
    }
    setLoading(false);
  }, [filters.status, filters.action_type, filters.verification_status, filters.search, filters.escalated_only, filters.blocked_only]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  // Auto-refresh every 30s
  useEffect(() => {
    const iv = setInterval(fetchRecords, 30000);
    return () => clearInterval(iv);
  }, [fetchRecords]);

  const selectedRecord = records.find((r) => r.id === selectedId) || null;

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 bg-white flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-amber-50 rounded-lg flex items-center justify-center">
            <Wrench className="w-4.5 h-4.5 text-amber-600" />
          </div>
          <div>
            <h1 className="text-base font-bold text-gray-900">Self-Healing Console</h1>
            <p className="text-[11px] text-gray-500">Remediation activity &middot; Internal only</p>
          </div>
        </div>
        <div className="text-xs text-gray-500">
          {records.length} record{records.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* KPI Strip */}
      <div className="px-5 py-3 border-b border-gray-200 bg-gray-50/50 flex-shrink-0">
        <SelfHealingKpiStrip records={records} />
      </div>

      {/* Tabs */}
      <div className="px-5 pt-2 border-b border-gray-200 bg-white flex-shrink-0">
        <div className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-red-600 text-red-600 bg-red-50/30"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50"
              }`}
            >
              <tab.icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 flex min-h-0">
        {activeTab === "activity" && (
          <>
            {/* Left: Filters + Table */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
              <div className="px-4 py-2 flex-shrink-0">
                <RemediationFiltersBar filters={filters} onChange={setFilters} />
              </div>
              <div className="flex-1 overflow-y-auto px-4 pb-4">
                <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                  <RemediationActivityTable
                    records={records}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    loading={loading}
                  />
                </div>
              </div>
            </div>

            {/* Right: Detail Panel */}
            <div className="w-[300px] flex-shrink-0 border-l border-gray-200 bg-white overflow-y-auto">
              <RemediationDetailPanel record={selectedRecord} />
            </div>
          </>
        )}

        {activeTab === "devices" && (
          <div className="flex-1 overflow-y-auto p-4">
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <DeviceRecoveryTable records={records} />
            </div>
          </div>
        )}

        {activeTab === "life-safety" && (
          <div className="flex-1 overflow-y-auto p-4">
            <div className="max-w-3xl">
              <LifeSafetyRecoveryPanel records={records} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
