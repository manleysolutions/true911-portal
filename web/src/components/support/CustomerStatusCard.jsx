import { CheckCircle, AlertCircle, XCircle } from "lucide-react";

const STATUS_INFO = {
  operational: {
    icon: CheckCircle,
    title: "All Systems Operational",
    desc: "Your devices are reporting in and services are running normally.",
    color: "text-emerald-600",
    iconBg: "bg-emerald-50",
  },
  attention: {
    icon: AlertCircle,
    title: "Attention Needed",
    desc: "We've noticed something that may need a look. Your service may still be working normally.",
    color: "text-amber-600",
    iconBg: "bg-amber-50",
  },
  impacted: {
    icon: XCircle,
    title: "Service May Be Impacted",
    desc: "We're seeing an issue that could affect your service. Our team is aware and monitoring.",
    color: "text-red-600",
    iconBg: "bg-red-50",
  },
};

export default function CustomerStatusCard({ status }) {
  const s = STATUS_INFO[status] || STATUS_INFO.operational;
  const Icon = s.icon;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-start gap-3">
        <div className={`w-9 h-9 ${s.iconBg} rounded-lg flex items-center justify-center flex-shrink-0`}>
          <Icon className={`w-5 h-5 ${s.color}`} />
        </div>
        <div>
          <h3 className={`text-sm font-semibold ${s.color}`}>{s.title}</h3>
          <p className="text-xs text-gray-500 mt-1 leading-relaxed">{s.desc}</p>
        </div>
      </div>
    </div>
  );
}
