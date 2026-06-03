/**
 * Four assurance summary cards for the current tenant:
 * Protected · Attention Needed · Critical · Pending Install.
 * Counts come from the aggregated portfolio (summarizePortfolio).
 */
const CARDS = [
  { key: "protected", label: "Protected Sites", cls: "bg-green-50 border-green-200", num: "text-green-700", sub: "text-green-600" },
  { key: "attention", label: "Attention Needed", cls: "bg-amber-50 border-amber-200", num: "text-amber-700", sub: "text-amber-600" },
  { key: "critical", label: "Critical Sites", cls: "bg-red-50 border-red-200", num: "text-red-700", sub: "text-red-600" },
  { key: "pending", label: "Pending Install", cls: "bg-blue-50 border-blue-200", num: "text-blue-700", sub: "text-blue-600" },
];

export default function AssuranceSummaryCards({ counts }) {
  const c = counts || {};
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {CARDS.map((card) => (
        <div key={card.key} className={`rounded-xl border p-4 ${card.cls}`}>
          <div className={`text-3xl font-semibold ${card.num}`}>{c[card.key] ?? 0}</div>
          <div className={`text-sm font-medium mt-1 ${card.sub}`}>{card.label}</div>
        </div>
      ))}
    </div>
  );
}
