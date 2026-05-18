import { ArrowRight, Lightbulb } from "lucide-react";

export default function CustomerNextStepCard({ actions, onSendMessage }) {
  if (!actions || actions.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 bg-blue-50 rounded-lg flex items-center justify-center flex-shrink-0">
            <Lightbulb className="w-5 h-5 text-blue-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Need Help?</h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              Use the chat to ask a question, run a system test, or let us know what's going on.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb className="w-4 h-4 text-blue-600" />
        <h3 className="text-sm font-semibold text-slate-800">Suggested Next Steps</h3>
      </div>
      <div className="space-y-1.5">
        {actions.slice(0, 4).map((action, i) => (
          <button
            key={i}
            onClick={() => onSendMessage(`Help me with: ${action}`)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs text-slate-700 bg-slate-50 hover:bg-slate-100 rounded-lg transition-colors text-left group"
          >
            <span>{action}</span>
            <ArrowRight className="w-3 h-3 text-slate-300 group-hover:text-slate-500 flex-shrink-0" />
          </button>
        ))}
      </div>
    </div>
  );
}
