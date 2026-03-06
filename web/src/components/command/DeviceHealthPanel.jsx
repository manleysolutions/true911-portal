import { Cpu, Signal, Battery, Thermometer, AlertTriangle } from "lucide-react";

function HealthBar({ value, max, color, label, unit }) {
  if (value == null) return null;
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-slate-500 w-16 flex-shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-400 w-14 text-right">{value}{unit}</span>
    </div>
  );
}

function formatUptime(seconds) {
  if (!seconds) return "0s";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  if (d > 0) return `${d}d ${h}h`;
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function signalColor(dbm) {
  if (dbm == null) return "bg-slate-500";
  if (dbm > -50) return "bg-emerald-500";
  if (dbm > -70) return "bg-green-500";
  if (dbm > -85) return "bg-amber-500";
  return "bg-red-500";
}

function batteryColor(pct) {
  if (pct == null) return "bg-slate-500";
  if (pct > 50) return "bg-emerald-500";
  if (pct > 20) return "bg-amber-500";
  return "bg-red-500";
}

function tempColor(c) {
  if (c == null) return "bg-slate-500";
  if (c < 40) return "bg-emerald-500";
  if (c < 60) return "bg-amber-500";
  return "bg-red-500";
}

export default function DeviceHealthPanel({ telemetry = [] }) {
  if (telemetry.length === 0) return null;

  // Group by device_id, take latest per device
  const byDevice = {};
  for (const t of telemetry) {
    if (!byDevice[t.device_id] || new Date(t.recorded_at) > new Date(byDevice[t.device_id].recorded_at)) {
      byDevice[t.device_id] = t;
    }
  }
  const devices = Object.values(byDevice);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-700/50">
        <Cpu className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Device Health</h3>
        <span className="text-xs text-slate-600 ml-auto">{devices.length} device(s)</span>
      </div>

      <div className="divide-y divide-slate-800/50 max-h-[400px] overflow-y-auto">
        {devices.map((t) => {
          const hasWarning = (t.battery_pct != null && t.battery_pct < 20) ||
            (t.signal_strength != null && t.signal_strength < -85) ||
            (t.error_count != null && t.error_count > 5) ||
            (t.temperature_c != null && t.temperature_c > 60);

          return (
            <div key={t.device_id} className="px-5 py-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm text-slate-200 font-medium">{t.device_id}</span>
                {hasWarning && <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
                <span className="text-[10px] text-slate-600 ml-auto">
                  Uptime: {formatUptime(t.uptime_seconds)}
                </span>
              </div>
              <div className="space-y-1.5">
                <HealthBar value={t.signal_strength} max={0} color={signalColor(t.signal_strength)} label="Signal" unit=" dBm" />
                <HealthBar value={t.battery_pct} max={100} color={batteryColor(t.battery_pct)} label="Battery" unit="%" />
                <HealthBar value={t.temperature_c} max={100} color={tempColor(t.temperature_c)} label="Temp" unit="C" />
                {t.error_count > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 w-16">Errors</span>
                    <span className={`text-[10px] font-bold ${t.error_count > 10 ? "text-red-400" : "text-amber-400"}`}>
                      {t.error_count}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
