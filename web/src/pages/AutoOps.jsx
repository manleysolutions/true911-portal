import { useState, useEffect, useCallback } from "react";
import {
  Bot, Play, Loader2, RefreshCw, Zap,
  Shield, Wrench, ArrowUpCircle, Calendar,
  CheckCircle2, FileBarChart, Heart,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import AutonomousLog from "@/components/command/AutonomousLog";
import DigestPanel from "@/components/command/DigestPanel";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";

function StatCard({ label, value, icon: Icon, color, sub }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-[10px] text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function AutoOps() {
  const { can } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [healing, setHealing] = useState(false);
  const [generating, setGenerating] = useState(false);

  const fetchSummary = useCallback(() => {
    setLoading(true);
    apiFetch("/command/autonomous/summary")
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(fetchSummary, [fetchSummary]);

  const runEngine = async () => {
    setRunning(true);
    try {
      const result = await apiFetch("/command/autonomous/run", { method: "POST" });
      toast.success(
        `Engine cycle complete: ${result.incidents_created} incidents, ` +
        `${result.diagnostics_run} diagnostics, ${result.escalations_processed} escalations`
      );
      fetchSummary();
    } catch (err) {
      toast.error(err.message || "Engine run failed");
    } finally {
      setRunning(false);
    }
  };

  const runSelfHeal = async () => {
    setHealing(true);
    try {
      const result = await apiFetch("/command/autonomous/self-heal", { method: "POST" });
      toast.success(`Self-heal: ${result.attempted} attempted, ${result.resolved} resolved`);
      fetchSummary();
    } catch (err) {
      toast.error(err.message || "Self-heal failed");
    } finally {
      setHealing(false);
    }
  };

  const generateDigest = async (type) => {
    setGenerating(true);
    try {
      await apiFetch("/command/digests/generate", {
        method: "POST",
        body: JSON.stringify({ digest_type: type }),
      });
      toast.success(`${type} digest generated`);
    } catch (err) {
      toast.error(err.message || "Digest generation failed");
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-indigo-600" />
            <h1 className="text-2xl font-bold text-gray-900">Autonomous Operations</h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={fetchSummary}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
            {can("COMMAND_RUN_ENGINE") && (
              <button onClick={runEngine} disabled={running}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg">
                {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Run Engine
              </button>
            )}
          </div>
        </div>

        {/* Stats */}
        {summary && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Actions (24h)" value={summary.total_actions_24h}
              icon={Zap} color="text-indigo-600" sub="autonomous actions" />
            <StatCard label="Auto Incidents" value={summary.incidents_auto_created}
              icon={Zap} color="text-red-600" sub="created by engine" />
            <StatCard label="Self-Healed" value={summary.self_heals_resolved}
              icon={Heart} color="text-emerald-600"
              sub={`${summary.self_heals_attempted} attempted`} />
            <StatCard label="Escalations" value={summary.escalations_triggered}
              icon={ArrowUpCircle} color="text-amber-600" sub="auto-escalated" />
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          {can("COMMAND_MANAGE_AUTO_OPS") && (
            <button onClick={runSelfHeal} disabled={healing}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100 disabled:opacity-50">
              {healing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Shield className="w-3.5 h-3.5" />}
              Run Self-Heal
            </button>
          )}
          {can("COMMAND_GENERATE_DIGEST") && (
            <>
              <button onClick={() => generateDigest("daily")} disabled={generating}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 disabled:opacity-50">
                {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileBarChart className="w-3.5 h-3.5" />}
                Daily Digest
              </button>
              <button onClick={() => generateDigest("weekly")} disabled={generating}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-teal-700 bg-teal-50 border border-teal-200 rounded-lg hover:bg-teal-100 disabled:opacity-50">
                {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileBarChart className="w-3.5 h-3.5" />}
                Weekly Digest
              </button>
            </>
          )}
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Autonomous Action Log */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <AutonomousLog limit={30} />
          </div>

          {/* Operational Digests */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <DigestPanel />
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
