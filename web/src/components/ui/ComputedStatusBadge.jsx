const COMPUTED_COLORS = {
  Online: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", dot: "bg-emerald-500" },
  Offline: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200", dot: "bg-red-500" },
  Provisioning: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", dot: "bg-blue-400" },
};

export default function ComputedStatusBadge({ status }) {
  if (!status) return null;
  const c = COMPUTED_COLORS[status] || COMPUTED_COLORS.Provisioning;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border font-medium px-2 py-0.5 text-[10px] ${c.bg} ${c.text} ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot} flex-shrink-0`} />
      {status}
    </span>
  );
}
