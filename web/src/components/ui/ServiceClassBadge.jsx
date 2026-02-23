const SC_COLORS = {
  'Life Safety': { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
  'Operations':  { bg: 'bg-teal-50', text: 'text-teal-700', border: 'border-teal-200' },
  'Convenience': { bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200' },
};

export default function ServiceClassBadge({ serviceClass }) {
  const c = SC_COLORS[serviceClass] || SC_COLORS['Convenience'];
  return (
    <span className={`inline-flex items-center rounded-full border font-medium px-2 py-0.5 text-xs ${c.bg} ${c.text} ${c.border}`}>
      {serviceClass || 'Convenience'}
    </span>
  );
}