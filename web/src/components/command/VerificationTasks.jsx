import { useState } from "react";
import { ClipboardCheck, Clock, AlertTriangle, CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";

const PRIORITY_STYLE = {
  high: "border-red-700/40 bg-red-900/20",
  medium: "border-amber-700/40 bg-amber-900/20",
  low: "border-slate-700/40 bg-slate-800/40",
};

const STATUS_BADGE = {
  pending: { label: "Pending", cls: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  in_progress: { label: "In Progress", cls: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  completed: { label: "Completed", cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
};

function timeSince(iso) {
  if (!iso) return "--";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDate(iso) {
  if (!iso) return "--";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function VerificationTasks({ tasks = [], summary = {}, onComplete, onRefresh }) {
  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState("all");

  const filtered = filter === "all" ? tasks
    : filter === "overdue" ? tasks.filter(t => t.is_overdue)
    : tasks.filter(t => t.status === filter);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center justify-between w-full px-5 py-4 border-b border-slate-700/50"
      >
        <div className="flex items-center gap-2">
          <ClipboardCheck className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm font-semibold text-white">Verification Tasks</h3>
          {summary.overdue > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">
              {summary.overdue} overdue
            </span>
          )}
          <span className="text-xs text-slate-500">
            {summary.completed || 0}/{summary.total || 0} complete ({summary.completion_pct || 0}%)
          </span>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
      </button>

      {expanded && (
        <>
          {/* Progress bar */}
          <div className="px-5 pt-3">
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all"
                style={{ width: `${summary.completion_pct || 0}%` }}
              />
            </div>
            <div className="flex items-center gap-3 mt-2">
              {[
                ["all", "All"],
                ["pending", "Pending"],
                ["in_progress", "In Progress"],
                ["completed", "Done"],
                ["overdue", "Overdue"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={`text-[11px] font-medium px-2 py-0.5 rounded transition-colors ${
                    filter === key
                      ? "bg-slate-700 text-white"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="divide-y divide-slate-800/50 max-h-[400px] overflow-y-auto">
            {filtered.length === 0 && (
              <div className="px-5 py-6 text-center text-sm text-slate-600">
                {filter === "all" ? "No verification tasks" : `No ${filter} tasks`}
              </div>
            )}
            {filtered.map((task) => {
              const badge = STATUS_BADGE[task.status] || STATUS_BADGE.pending;
              return (
                <div key={task.id} className={`px-5 py-3 ${task.is_overdue ? "bg-red-900/10" : ""}`}>
                  <div className="flex items-center gap-2 mb-1">
                    {task.is_overdue && <AlertTriangle className="w-3 h-3 text-red-400" />}
                    <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold border ${badge.cls}`}>
                      {badge.label}
                    </span>
                    <span className="text-[10px] text-slate-600 uppercase font-semibold">{task.priority}</span>
                    {task.result && (
                      <span className={`inline-flex items-center gap-0.5 text-[10px] font-bold ${
                        task.result === "pass" ? "text-emerald-400" : "text-red-400"
                      }`}>
                        {task.result === "pass" ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                        {task.result}
                      </span>
                    )}
                    {task.due_date && (
                      <span className={`text-[10px] ml-auto ${task.is_overdue ? "text-red-400 font-bold" : "text-slate-600"}`}>
                        <Clock className="w-3 h-3 inline mr-0.5" />
                        {formatDate(task.due_date)}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-300">{task.title}</p>
                  {task.description && (
                    <p className="text-xs text-slate-500 mt-0.5">{task.description}</p>
                  )}
                  {task.assigned_to && (
                    <p className="text-xs text-slate-600 mt-1">Assigned: {task.assigned_to}</p>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
