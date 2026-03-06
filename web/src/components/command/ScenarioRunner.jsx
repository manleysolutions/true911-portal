import { useState, useRef, useCallback } from "react";
import { Play, Square, Clock, CheckCircle2, AlertTriangle, User, Wrench, RotateCcw, Database } from "lucide-react";
import { apiFetch } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const SCENARIO_STEPS = [
  {
    time: 0,
    title: "Issue Detected",
    detail: "Elevator Emergency Phone Verification Failed",
    site: "Boston Medical Research Tower",
    location: "Floor 18 — Elevator Bank C",
    severity: "critical",
    type: "detection",
  },
  {
    time: 8000,
    title: "Site Status Updated",
    detail: "Boston Medical Research Tower status changed to Attention Needed",
    severity: "warning",
    type: "status_change",
  },
  {
    time: 15000,
    title: "Readiness Score Impact",
    detail: "Portfolio readiness score dropped from 94% to 79% — risk level: Attention Needed",
    severity: "warning",
    type: "score_change",
    scoreBefore: 94,
    scoreAfter: 79,
  },
  {
    time: 22000,
    title: "Incident Feed Updated",
    detail: "New critical incident added: ELP-VER-FAIL-018. Awaiting acknowledgment.",
    severity: "critical",
    type: "feed_update",
  },
  {
    time: 30000,
    title: "Recommended Actions Generated",
    detail: "System generated response plan:",
    severity: "info",
    type: "actions",
    actions: [
      "Notify integrator (Schindler Elevator Corp)",
      "Dispatch certified technician",
      "Hold final verification for Floor 18",
      "Update readiness checklist — elevator systems",
    ],
  },
  {
    time: 40000,
    title: "Technician Assigned",
    detail: "Field technician Mike Torres dispatched. ETA: 45 minutes.",
    severity: "info",
    type: "assignment",
  },
  {
    time: 48000,
    title: "Retest Scheduled",
    detail: "Automated retest scheduled for elevator phone line — Floor 18, Bank C.",
    severity: "info",
    type: "retest",
  },
  {
    time: 55000,
    title: "Incident Resolving",
    detail: "Technician on-site. Line test passed. Incident status: In Progress -> Resolved. Readiness score recovering to 92%.",
    severity: "success",
    type: "resolution",
    scoreAfter: 92,
  },
];

const SEV_STYLE = {
  critical: { bg: "bg-red-900/30", border: "border-red-700/40", text: "text-red-400", dot: "bg-red-500" },
  warning:  { bg: "bg-amber-900/30", border: "border-amber-700/40", text: "text-amber-400", dot: "bg-amber-500" },
  info:     { bg: "bg-blue-900/30", border: "border-blue-700/40", text: "text-blue-400", dot: "bg-blue-500" },
  success:  { bg: "bg-emerald-900/30", border: "border-emerald-700/40", text: "text-emerald-400", dot: "bg-emerald-500" },
};

export default function ScenarioRunner({ onRefresh }) {
  const { can } = useAuth();
  const [running, setRunning] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [visibleSteps, setVisibleSteps] = useState([]);
  const [persistMode, setPersistMode] = useState(false);
  const [persisted, setPersisted] = useState(false);
  const timersRef = useRef([]);

  const startScenario = useCallback(() => {
    setRunning(true);
    setCompleted(false);
    setVisibleSteps([]);
    setPersisted(false);

    const timers = SCENARIO_STEPS.map((step, idx) =>
      setTimeout(() => {
        setVisibleSteps(prev => [...prev, { ...step, idx }]);
        if (idx === SCENARIO_STEPS.length - 1) {
          setRunning(false);
          setCompleted(true);
        }
      }, step.time)
    );
    timersRef.current = timers;
  }, []);

  const stopScenario = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    setRunning(false);
  }, []);

  const resetScenario = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    setRunning(false);
    setCompleted(false);
    setVisibleSteps([]);
    setPersisted(false);
  }, []);

  const persistToBackend = useCallback(async () => {
    try {
      // Pick a real site_id from the first available site, fallback to SITE-001
      const siteId = "SITE-001";
      await apiFetch("/command/incidents", {
        method: "POST",
        body: JSON.stringify({
          site_id: siteId,
          summary: "Elevator Emergency Phone Verification Failed — Floor 18, Elevator Bank C",
          severity: "critical",
          incident_type: "elevator_phone_fail",
          source: "scenario_simulation",
          description: "Simulated incident from scenario runner. Elevator emergency phone line test failed during scheduled verification.",
          location_detail: "Floor 18 — Elevator Bank C",
          recommended_actions_json: JSON.stringify([
            "Notify integrator (Schindler Elevator Corp)",
            "Dispatch certified technician",
            "Hold final verification for Floor 18",
            "Update readiness checklist",
          ]),
        }),
      });
      setPersisted(true);
      toast.success("Scenario incident persisted to backend");
      onRefresh?.();
    } catch (err) {
      toast.error(err.message || "Failed to persist incident");
    }
  }, [onRefresh]);

  const canCreate = can("COMMAND_CREATE_INCIDENT");

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/50">
        <div>
          <h3 className="text-sm font-semibold text-white">Incident Scenario Simulation</h3>
          <p className="text-xs text-slate-500 mt-0.5">60-second end-to-end incident response demo</p>
        </div>
        <div className="flex items-center gap-2">
          {!running && !completed && (
            <button
              onClick={startScenario}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold transition-colors"
            >
              <Play className="w-3.5 h-3.5" />
              Run Scenario
            </button>
          )}
          {running && (
            <button
              onClick={stopScenario}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-semibold transition-colors"
            >
              <Square className="w-3.5 h-3.5" />
              Stop
            </button>
          )}
          {completed && (
            <>
              {canCreate && !persisted && (
                <button
                  onClick={persistToBackend}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold transition-colors"
                >
                  <Database className="w-3.5 h-3.5" />
                  Save to Backend
                </button>
              )}
              <button
                onClick={resetScenario}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-semibold transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset
              </button>
            </>
          )}
        </div>
      </div>

      {running && (
        <div className="h-1 bg-slate-800">
          <div
            className="h-1 bg-red-500 transition-all duration-1000"
            style={{ width: `${(visibleSteps.length / SCENARIO_STEPS.length) * 100}%` }}
          />
        </div>
      )}

      <div className="p-5 max-h-[500px] overflow-y-auto">
        {visibleSteps.length === 0 && !running && (
          <div className="text-center py-8">
            <AlertTriangle className="w-10 h-10 text-slate-700 mx-auto mb-3" />
            <p className="text-sm text-slate-500">Run the scenario to simulate a real incident response workflow.</p>
            <p className="text-xs text-slate-600 mt-1">Elevator phone verification failure at a medical research tower.</p>
          </div>
        )}

        <div className="space-y-0">
          {visibleSteps.map((step, i) => {
            const sev = SEV_STYLE[step.severity] || SEV_STYLE.info;
            return (
              <div key={i} className="flex gap-3 animate-fadeIn">
                <div className="flex flex-col items-center">
                  <div className={`w-3 h-3 rounded-full ${sev.dot} flex-shrink-0 mt-1.5`} />
                  {i < visibleSteps.length - 1 && (
                    <div className="w-px flex-1 bg-slate-700/50 my-1" />
                  )}
                </div>

                <div className={`flex-1 mb-4 rounded-lg border ${sev.border} ${sev.bg} px-4 py-3`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-bold ${sev.text}`}>{step.title}</span>
                    <span className="text-[10px] text-slate-600 ml-auto">
                      {Math.round(step.time / 1000)}s
                    </span>
                  </div>
                  <p className="text-sm text-slate-300">{step.detail}</p>

                  {step.site && (
                    <p className="text-xs text-slate-500 mt-1">
                      {step.site} — {step.location}
                    </p>
                  )}

                  {step.actions && (
                    <ul className="mt-2 space-y-1">
                      {step.actions.map((a, j) => (
                        <li key={j} className="flex items-center gap-2 text-xs text-slate-400">
                          <Wrench className="w-3 h-3 text-slate-600 flex-shrink-0" />
                          {a}
                        </li>
                      ))}
                    </ul>
                  )}

                  {step.scoreAfter && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-1.5 flex-1 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className={`h-1.5 rounded-full transition-all duration-700 ${
                            step.scoreAfter >= 85 ? "bg-emerald-500" : step.scoreAfter >= 60 ? "bg-amber-500" : "bg-red-500"
                          }`}
                          style={{ width: `${step.scoreAfter}%` }}
                        />
                      </div>
                      <span className={`text-xs font-bold ${
                        step.scoreAfter >= 85 ? "text-emerald-400" : step.scoreAfter >= 60 ? "text-amber-400" : "text-red-400"
                      }`}>{step.scoreAfter}%</span>
                    </div>
                  )}

                  {step.type === "assignment" && (
                    <div className="flex items-center gap-1.5 mt-2 text-xs text-slate-400">
                      <User className="w-3.5 h-3.5" />
                      Mike Torres — Field Technician
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {running && (
            <div className="flex items-center gap-2 pl-6 pt-2">
              <div className="w-4 h-4 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-slate-500">Scenario in progress...</span>
            </div>
          )}

          {completed && (
            <div className="flex items-center gap-2 pl-6 pt-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              <span className="text-xs text-emerald-400 font-medium">
                Scenario complete — incident resolved
                {persisted && " (saved to backend)"}
              </span>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn { animation: fadeIn 0.4s ease-out; }
      `}</style>
    </div>
  );
}
