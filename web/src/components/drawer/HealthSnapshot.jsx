import { Wifi, Signal, Radio, Globe, Calendar, Server } from "lucide-react";

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function SignalQuality({ dbm }) {
  if (!dbm) return <span className="text-gray-400">No data</span>;
  const quality = dbm > -70 ? { label: "Excellent", color: "text-emerald-600" }
    : dbm > -80 ? { label: "Good", color: "text-green-600" }
    : dbm > -90 ? { label: "Fair", color: "text-amber-600" }
    : { label: "Poor", color: "text-red-600" };
  return (
    <span>
      <span className="font-semibold text-gray-800">{dbm} dBm</span>
      <span className={`ml-1.5 text-[10px] font-semibold ${quality.color}`}>{quality.label}</span>
    </span>
  );
}

function Row({ icon: Icon, label, children }) {
  return (
    <div className="flex items-start gap-2.5 py-2 border-b border-gray-50 last:border-0">
      <Icon className="w-3.5 h-3.5 text-gray-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1">
        <div className="text-[10px] text-gray-400 font-medium uppercase tracking-wide">{label}</div>
        <div className="text-xs text-gray-700 mt-0.5">{children}</div>
      </div>
    </div>
  );
}

export default function HealthSnapshot({ site }) {
  const nextDue = site.heartbeat_next_due
    ? new Date(site.heartbeat_next_due) > new Date()
      ? `in ${Math.ceil((new Date(site.heartbeat_next_due) - Date.now()) / 86400000)}d`
      : `overdue by ${Math.floor((Date.now() - new Date(site.heartbeat_next_due)) / 86400000)}d`
    : "—";

  const nextDueColor = site.heartbeat_next_due && new Date(site.heartbeat_next_due) < new Date()
    ? "text-red-600 font-semibold"
    : "text-gray-700";

  return (
    <div className="mb-5">
      <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Health Snapshot</div>
      <div className="bg-gray-50 rounded-lg px-3 py-1">
        <Row icon={Wifi} label="Internet Path">
          {site.network_tech || "—"}
          {site.static_ip && <span className="ml-2 font-mono text-gray-500 text-[10px]">· {site.static_ip}</span>}
        </Row>
        <Row icon={Signal} label="Signal Strength">
          <SignalQuality dbm={site.signal_dbm} />
        </Row>
        <Row icon={Radio} label="Carrier & Network">
          {site.carrier || "—"} {site.network_tech ? `(${site.network_tech})` : ""}
        </Row>
        <Row icon={Server} label="Device Heartbeat">
          {timeSince(site.last_device_heartbeat || site.last_checkin)}
          <span className="text-gray-400 ml-1">· Portal: {timeSince(site.last_portal_sync || site.last_checkin)}</span>
        </Row>
        <Row icon={Calendar} label="Heartbeat Policy">
          <span className="capitalize">{site.heartbeat_frequency || "weekly"}</span>
          {" · "}
          <span className={nextDueColor}>Next {nextDue}</span>
        </Row>
      </div>
    </div>
  );
}