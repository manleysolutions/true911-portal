import { Wifi, WifiOff, AlertTriangle } from "lucide-react";

export default function StalenessIndicator({ staleness = {} }) {
  const { total_devices = 0, stale_count = 0, stale_devices = [], has_stale_critical = false } = staleness;

  if (total_devices === 0) return null;

  const healthyCount = total_devices - stale_count;
  const healthPct = Math.round((healthyCount / total_devices) * 100);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-700/50">
        {stale_count > 0 ? (
          <WifiOff className="w-4 h-4 text-red-400" />
        ) : (
          <Wifi className="w-4 h-4 text-emerald-400" />
        )}
        <h3 className="text-sm font-semibold text-white">Device Connectivity</h3>
        {has_stale_critical && (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">
            STALE ACTIVE
          </span>
        )}
      </div>
      <div className="p-5">
        {/* Health bar */}
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500">{healthyCount}/{total_devices} reporting</span>
          <span className={`text-xs font-bold ${healthPct >= 90 ? "text-emerald-400" : healthPct >= 70 ? "text-amber-400" : "text-red-400"}`}>
            {healthPct}%
          </span>
        </div>
        <div className="h-2 bg-slate-800 rounded-full overflow-hidden mb-3">
          <div
            className={`h-full rounded-full transition-all ${
              healthPct >= 90 ? "bg-emerald-500" : healthPct >= 70 ? "bg-amber-500" : "bg-red-500"
            }`}
            style={{ width: `${healthPct}%` }}
          />
        </div>

        {/* Stale device list */}
        {stale_devices.length > 0 && (
          <div className="space-y-2 mt-3">
            <p className="text-[11px] text-slate-500 font-semibold uppercase">Stale Devices</p>
            {stale_devices.slice(0, 5).map((d, i) => (
              <div key={i} className="flex items-center justify-between bg-slate-800/50 rounded-lg px-3 py-2 border border-slate-700/30">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-3 h-3 text-amber-400" />
                  <span className="text-xs text-slate-300 font-mono">{d.device_id}</span>
                </div>
                <span className="text-[10px] text-slate-500">
                  {d.reason === "never_seen" ? "Never seen" : `${d.minutes_since}m since last`}
                </span>
              </div>
            ))}
            {stale_devices.length > 5 && (
              <p className="text-[10px] text-slate-600 text-center">
                +{stale_devices.length - 5} more
              </p>
            )}
          </div>
        )}

        {stale_count === 0 && (
          <div className="text-center py-2">
            <p className="text-xs text-emerald-400">All devices reporting normally</p>
          </div>
        )}
      </div>
    </div>
  );
}
