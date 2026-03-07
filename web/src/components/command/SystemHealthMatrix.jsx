import { Flame, Phone, Radio, PhoneCall, Zap, Server, Shield } from "lucide-react";

const ICONS = {
  fire_alarm: Flame,
  elevator_phone: Phone,
  das_radio: Radio,
  call_station: PhoneCall,
  backup_power: Zap,
  emergency_device: Shield,
  other: Server,
};

const STATUS_RING = {
  healthy:  "border-emerald-500/60",
  warning:  "border-amber-500/60",
  critical: "border-red-500/60",
};

const STATUS_BG = {
  healthy:  "bg-emerald-500/10",
  warning:  "bg-amber-500/10",
  critical: "bg-red-500/10",
};

const STATUS_TEXT = {
  healthy:  "text-emerald-400",
  warning:  "text-amber-400",
  critical: "text-red-400",
};

const STATUS_LABEL = {
  healthy:  "Healthy",
  warning:  "Warning",
  critical: "Critical",
};

export default function SystemHealthMatrix({ systems = [] }) {
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/50">
        <h3 className="text-sm font-semibold text-white">System Health Matrix</h3>
        <p className="text-xs text-slate-500 mt-0.5">Life-safety system status across portfolio</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-0 divide-y sm:divide-y-0">
        {systems.length === 0 && (
          <div className="px-5 py-8 text-center col-span-full">
            <Server className="w-6 h-6 text-slate-600 mx-auto mb-2" />
            <p className="text-sm text-slate-500">No system categories detected yet</p>
            <p className="text-xs text-slate-600 mt-1">Categories appear automatically based on registered devices</p>
          </div>
        )}
        {systems.map((sys) => {
          const Icon = ICONS[sys.key] || Server;
          const ring = STATUS_RING[sys.status] || STATUS_RING.healthy;
          const bg = STATUS_BG[sys.status] || STATUS_BG.healthy;
          const textColor = STATUS_TEXT[sys.status] || STATUS_TEXT.healthy;
          const label = STATUS_LABEL[sys.status] || "Unknown";

          return (
            <div key={sys.key} className="px-5 py-4 border-b border-slate-800/50 last:border-b-0 sm:border-r sm:border-slate-800/50 sm:last:border-r-0">
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-10 h-10 rounded-lg border-2 ${ring} ${bg} flex items-center justify-center`}>
                  <Icon className={`w-5 h-5 ${textColor}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-200 truncate">{sys.label}</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${sys.status === "healthy" ? "bg-emerald-500" : sys.status === "warning" ? "bg-amber-500" : "bg-red-500"}`} />
                    <span className={`text-xs font-semibold ${textColor}`}>{label}</span>
                  </div>
                </div>
              </div>

              {/* Health bar */}
              <div className="mb-2">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-500">Health</span>
                  <span className={`font-bold ${textColor}`}>{sys.health_pct}%</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full transition-all ${
                      sys.status === "healthy" ? "bg-emerald-500" :
                      sys.status === "warning" ? "bg-amber-500" : "bg-red-500"
                    }`}
                    style={{ width: `${sys.health_pct}%` }}
                  />
                </div>
              </div>

              {/* Breakdown */}
              <div className="flex items-center gap-3 text-xs">
                <span className="text-emerald-400">{sys.healthy} ok</span>
                {sys.warning > 0 && <span className="text-amber-400">{sys.warning} warn</span>}
                {sys.critical > 0 && <span className="text-red-400">{sys.critical} crit</span>}
                <span className="text-slate-600 ml-auto">{sys.total} total</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
