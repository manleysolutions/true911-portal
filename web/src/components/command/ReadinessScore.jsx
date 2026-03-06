import { ShieldCheck, ShieldAlert, ShieldX, TrendingDown } from "lucide-react";

const RISK_CONFIG = {
  Operational:      { icon: ShieldCheck, color: "text-emerald-400", ring: "border-emerald-500", bg: "bg-emerald-500/10", barColor: "bg-emerald-500" },
  "Attention Needed": { icon: ShieldAlert, color: "text-amber-400", ring: "border-amber-500", bg: "bg-amber-500/10", barColor: "bg-amber-500" },
  "At Risk":        { icon: ShieldX, color: "text-red-400", ring: "border-red-500", bg: "bg-red-500/10", barColor: "bg-red-500" },
};

export default function ReadinessScore({ readiness = {} }) {
  const { score = 0, risk_label = "Operational", factors = [] } = readiness;
  const cfg = RISK_CONFIG[risk_label] || RISK_CONFIG.Operational;
  const Icon = cfg.icon;

  // SVG circle gauge
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/50">
        <h3 className="text-sm font-semibold text-white">Emergency Readiness</h3>
      </div>

      <div className="p-5">
        {/* Gauge */}
        <div className="flex items-center justify-center mb-4">
          <div className="relative">
            <svg width="140" height="140" viewBox="0 0 140 140">
              <circle
                cx="70" cy="70" r={radius}
                fill="none"
                stroke="rgba(51,65,85,0.5)"
                strokeWidth="10"
              />
              <circle
                cx="70" cy="70" r={radius}
                fill="none"
                stroke={score >= 85 ? "#10b981" : score >= 60 ? "#f59e0b" : "#ef4444"}
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                transform="rotate(-90 70 70)"
                className="transition-all duration-1000"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={`text-3xl font-bold ${cfg.color}`}>{score}</span>
              <span className="text-xs text-slate-500">/ 100</span>
            </div>
          </div>
        </div>

        {/* Risk label */}
        <div className="flex items-center justify-center gap-2 mb-5">
          <div className={`w-8 h-8 rounded-lg border-2 ${cfg.ring} ${cfg.bg} flex items-center justify-center`}>
            <Icon className={`w-4 h-4 ${cfg.color}`} />
          </div>
          <span className={`text-sm font-bold ${cfg.color}`}>{risk_label}</span>
        </div>

        {/* Factors */}
        {factors.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 mb-2">
              <TrendingDown className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-xs text-slate-500 font-medium">Score Factors</span>
            </div>
            {factors.map((f, i) => (
              <div key={i} className="bg-slate-800/50 rounded-lg px-3 py-2.5">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs text-slate-300 font-medium">{f.label}</span>
                  <span className="text-xs font-bold text-red-400">{f.impact}</span>
                </div>
                <p className="text-[11px] text-slate-500">{f.detail}</p>
              </div>
            ))}
          </div>
        )}

        {factors.length === 0 && (
          <p className="text-center text-xs text-slate-500">All systems nominal</p>
        )}
      </div>
    </div>
  );
}
