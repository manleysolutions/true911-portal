import { useState, useEffect } from "react";
import { Building2, CheckCircle2, Loader2 } from "lucide-react";
import { apiFetch } from "@/api/client";

const BUILDING_ICONS = {
  retail: "🏪",
  commercial_office: "🏢",
  hospital: "🏥",
  airport: "✈️",
  data_center: "🖥️",
  elevator_bank: "🛗",
};

export default function TemplateSelector({ selected, onSelect }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/command/templates")
      .then(setTemplates)
      .catch(() => setTemplates([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">
        Select a template to auto-configure verification tasks and monitoring rules.
      </p>

      {/* No template option */}
      <button
        onClick={() => onSelect(null)}
        className={`w-full text-left p-3 rounded-xl border transition-all ${
          !selected ? "border-red-300 bg-red-50 ring-2 ring-red-100" : "border-gray-200 hover:border-gray-300"
        }`}
      >
        <div className="flex items-center gap-2">
          {!selected && <CheckCircle2 className="w-4 h-4 text-red-600" />}
          <span className="text-sm font-medium text-gray-900">No Template (Manual Setup)</span>
        </div>
        <p className="text-xs text-gray-500 mt-1">Configure verification tasks and rules manually after site creation.</p>
      </button>

      <div className="grid grid-cols-2 gap-2">
        {templates.map(tmpl => {
          const isSelected = selected?.id === tmpl.id;
          const icon = BUILDING_ICONS[tmpl.building_type] || "🏗️";
          let systemCount = 0;
          let taskCount = 0;
          try { systemCount = JSON.parse(tmpl.systems_json || "[]").length; } catch {}
          try { taskCount = JSON.parse(tmpl.verification_tasks_json || "[]").length; } catch {}

          return (
            <button
              key={tmpl.id}
              onClick={() => onSelect(tmpl)}
              className={`text-left p-3 rounded-xl border transition-all ${
                isSelected ? "border-red-300 bg-red-50 ring-2 ring-red-100" : "border-gray-200 hover:border-gray-300"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">{icon}</span>
                <span className="text-sm font-semibold text-gray-900">{tmpl.name}</span>
                {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-red-600 ml-auto" />}
              </div>
              {tmpl.description && (
                <p className="text-xs text-gray-500 line-clamp-2">{tmpl.description}</p>
              )}
              <div className="flex items-center gap-2 mt-1.5">
                {systemCount > 0 && (
                  <span className="text-[10px] text-gray-400">{systemCount} system{systemCount !== 1 ? "s" : ""}</span>
                )}
                {taskCount > 0 && (
                  <span className="text-[10px] text-gray-400">{taskCount} task{taskCount !== 1 ? "s" : ""}</span>
                )}
                {tmpl.is_global && (
                  <span className="text-[10px] text-blue-500 font-semibold">BUILT-IN</span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
