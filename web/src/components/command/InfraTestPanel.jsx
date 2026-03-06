import { useState, useEffect } from "react";
import { FlaskConical, Play, CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";

const STATUS_STYLE = {
  pass: { icon: CheckCircle2, color: "text-emerald-600", bg: "bg-emerald-50" },
  fail: { icon: XCircle, color: "text-red-600", bg: "bg-red-50" },
  error: { icon: XCircle, color: "text-amber-600", bg: "bg-amber-50" },
  running: { icon: Loader2, color: "text-blue-600", bg: "bg-blue-50" },
};

const TYPE_LABELS = {
  voice_path: "Voice Path",
  emergency_call: "Emergency Call",
  heartbeat_verify: "Heartbeat",
  radio_coverage: "Radio Coverage",
  connectivity: "Connectivity",
};

export default function InfraTestPanel({ siteId }) {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);

  const fetchTests = () => {
    apiFetch(`/command/infra-tests?site_id=${siteId}`)
      .then(setTests)
      .catch(() => setTests([]))
      .finally(() => setLoading(false));
  };

  useEffect(fetchTests, [siteId]);

  const runTest = async (testId) => {
    setRunning(testId);
    try {
      const result = await apiFetch(`/command/infra-tests/${testId}/run`, {
        method: "POST",
        body: JSON.stringify({ triggered_by: "manual" }),
      });
      toast.success(`Test completed: ${result.status}`);
      fetchTests();
    } catch (err) {
      toast.error(err.message || "Test execution failed");
    } finally {
      setRunning(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-2">
        <FlaskConical className="w-4 h-4 text-purple-600" />
        <h3 className="text-sm font-semibold text-gray-900">Infrastructure Tests</h3>
        <span className="text-[10px] text-gray-400 ml-auto">{tests.length} configured</span>
      </div>

      {tests.length === 0 ? (
        <p className="text-xs text-gray-500 text-center py-4">No infrastructure tests configured for this site.</p>
      ) : (
        <div className="space-y-1.5">
          {tests.map(test => {
            const st = STATUS_STYLE[test.last_result] || STATUS_STYLE.error;
            const StatusIcon = st.icon;
            const isRunning = running === test.id;

            return (
              <div key={test.id} className="flex items-center gap-2 p-2.5 bg-gray-50 rounded-lg">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${st.bg}`}>
                  {test.last_result ? (
                    <StatusIcon className={`w-3.5 h-3.5 ${st.color} ${test.last_result === "running" ? "animate-spin" : ""}`} />
                  ) : (
                    <Clock className="w-3.5 h-3.5 text-gray-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-gray-900 truncate">{test.name}</div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] text-gray-500">{TYPE_LABELS[test.test_type] || test.test_type}</span>
                    {test.schedule_cron && (
                      <span className="text-[10px] text-gray-400">• Scheduled</span>
                    )}
                    {test.last_run_at && (
                      <span className="text-[10px] text-gray-400">
                        • Last: {new Date(test.last_run_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => runTest(test.id)}
                  disabled={isRunning || !test.enabled}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg"
                >
                  {isRunning ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Play className="w-3 h-3" />
                  )}
                  Run
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
