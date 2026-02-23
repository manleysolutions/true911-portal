const KIT_COLORS = {
  Elevator: { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200' },
  FACP: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
  Fax: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  SCADA: { bg: 'bg-teal-50', text: 'text-teal-700', border: 'border-teal-200' },
  'Emergency Call Box': { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
  Other: { bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200' },
};

export default function KitTypeBadge({ type }) {
  const c = KIT_COLORS[type] || KIT_COLORS.Other;
  return (
    <span className={`inline-flex items-center rounded-full border font-medium px-2 py-0.5 text-xs ${c.bg} ${c.text} ${c.border}`}>
      {type}
    </span>
  );
}