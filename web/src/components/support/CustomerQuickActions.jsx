import { Activity, MessageSquare, Wrench, Phone, MapPin } from "lucide-react";

const ACTIONS = [
  { id: "status", icon: Activity, label: "Check Status", message: "What's the current status of my system?" },
  { id: "test", icon: Wrench, label: "Run System Test", message: null },
  { id: "troubleshoot", icon: MessageSquare, label: "Help Me Troubleshoot", message: "I need help troubleshooting an issue with my system." },
  { id: "human", icon: Phone, label: "Request Human Help", message: null },
  { id: "e911", icon: MapPin, label: "E911 Help", message: "I have a question about E911 compliance for my site." },
];

export default function CustomerQuickActions({ onSendMessage, onRunTest, onRequestHelp }) {
  const handleClick = (action) => {
    if (action.id === "test") {
      onRunTest();
    } else if (action.id === "human") {
      onRequestHelp();
    } else if (action.message) {
      onSendMessage(action.message);
    }
  };

  return (
    <div className="flex flex-wrap gap-1.5 px-4 py-2.5 border-t border-slate-100 bg-slate-50/60">
      {ACTIONS.map((a) => (
        <button
          key={a.id}
          onClick={() => handleClick(a)}
          className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600 bg-white border border-slate-200 rounded-full px-3 py-1.5 hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900 transition-colors"
        >
          <a.icon className="w-3 h-3" />
          {a.label}
        </button>
      ))}
    </div>
  );
}
