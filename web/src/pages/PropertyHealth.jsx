/**
 * PropertyHealth — customer-facing, hardware-agnostic device health.
 *
 * Property managers should understand this without knowing Vola, TAAP, SIP,
 * TR-069, or any API detail. It shows, per property:
 *   Service Unit (Elevator / Fire Alarm / Line) · Device · Carrier ·
 *   Voice Path · Status · Last Check-In · Last Call · Recommended Action
 *
 * Data comes ONLY from the sanitized /api/device-health/property/{site_id}
 * endpoint (no raw vendor/API fields are sent to the customer). Every call is
 * tenant-scoped server-side, so a customer only ever sees their own properties.
 *
 * Hardware-agnostic: nothing here is Vola- or Integrity-specific. Any property
 * with active devices renders; pending/test placeholder sites (no live devices)
 * are listed separately as "being set up" and never shown as live deployments.
 *
 * Gated by config.featureDeviceHealth (mirrors backend FEATURE_DEVICE_HEALTH).
 */

import { useEffect, useState } from "react";
import {
  Activity, Building2, RefreshCw, CheckCircle2, AlertTriangle,
  WifiOff, HelpCircle, Clock, Cpu, Radio, Wrench,
} from "lucide-react";

import { config } from "@/config";
import { useAuth } from "@/contexts/AuthContext";
import { Site } from "@/api/entities";
import { getPropertyHealth } from "@/api/deviceHealth";

// ── Presentation helpers ────────────────────────────────────────────
const STATUS_STYLES = {
  "Online": { cls: "bg-emerald-50 text-emerald-700 border-emerald-200", Icon: CheckCircle2 },
  "Attention Needed": { cls: "bg-amber-50 text-amber-700 border-amber-200", Icon: AlertTriangle },
  "Offline": { cls: "bg-red-50 text-red-700 border-red-200", Icon: WifiOff },
  "Unknown": { cls: "bg-slate-50 text-slate-600 border-slate-200", Icon: HelpCircle },
};

function StatusPill({ status }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES["Unknown"];
  const Icon = s.Icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${s.cls}`}>
      <Icon className="w-3.5 h-3.5" /> {status}
    </span>
  );
}

const CARRIER_LABELS = { tmobile: "T-Mobile", verizon: "Verizon", att: "AT&T" };
function carrierLabel(c) {
  if (!c || c === "—") return "—";
  return CARRIER_LABELS[c.toLowerCase()] || c;
}

function timeAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "Just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleDateString();
}

// ── Property card ───────────────────────────────────────────────────
function PropertyCard({ data }) {
  const units = data.units || [];
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 flex items-center gap-3 border-b border-slate-100">
        <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center">
          <Building2 className="w-[18px] h-[18px] text-slate-600" />
        </div>
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-slate-900 truncate">{data.property}</h3>
          <p className="text-[11px] text-slate-400">{units.length} service unit{units.length === 1 ? "" : "s"}</p>
        </div>
        <div className="ml-auto"><StatusPill status={data.status} /></div>
      </div>

      {units.length === 0 ? (
        <div className="px-5 py-6 text-sm text-slate-500 flex items-center gap-2">
          <Wrench className="w-4 h-4 text-slate-400" /> This property is being set up — no devices reporting yet.
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10.5px] uppercase tracking-wide text-slate-400 border-b border-slate-100">
                  <th className="text-left font-semibold px-5 py-2.5">Service Unit</th>
                  <th className="text-left font-semibold px-3 py-2.5">Device</th>
                  <th className="text-left font-semibold px-3 py-2.5">Device Type</th>
                  <th className="text-left font-semibold px-3 py-2.5">Carrier</th>
                  <th className="text-left font-semibold px-3 py-2.5">Voice Path</th>
                  <th className="text-left font-semibold px-3 py-2.5">Status</th>
                  <th className="text-left font-semibold px-3 py-2.5">Last Check-In</th>
                  <th className="text-left font-semibold px-3 py-2.5">Last Heartbeat</th>
                  <th className="text-left font-semibold px-3 py-2.5">Firmware</th>
                  <th className="text-left font-semibold px-5 py-2.5">Recommended Action</th>
                </tr>
              </thead>
              <tbody>
                {units.map((u, i) => (
                  <tr key={i} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
                    <td className="px-5 py-3 font-medium text-slate-800 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-slate-400" />{u.unit || "—"}</span>
                    </td>
                    <td className="px-3 py-3 text-slate-600 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5"><Cpu className="w-3.5 h-3.5 text-slate-400" />{u.device || "—"}</span>
                    </td>
                    <td className="px-3 py-3 text-slate-600 whitespace-nowrap">{u.device_type || "—"}</td>
                    <td className="px-3 py-3 text-slate-600 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5"><Radio className="w-3.5 h-3.5 text-slate-400" />{carrierLabel(u.carrier)}</span>
                    </td>
                    <td className="px-3 py-3 text-slate-600 whitespace-nowrap">{u.voice_path || "—"}</td>
                    <td className="px-3 py-3"><StatusPill status={u.status} /></td>
                    <td className="px-3 py-3 text-slate-500 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-slate-300" />{timeAgo(u.last_check_in)}</span>
                    </td>
                    <td className="px-3 py-3 text-slate-500 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-slate-300" />{timeAgo(u.last_heartbeat)}</span>
                    </td>
                    <td className="px-3 py-3 text-slate-500 whitespace-nowrap">{u.firmware || "—"}</td>
                    <td className="px-5 py-3 text-slate-500 max-w-[280px]">{u.recommended_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden divide-y divide-slate-100">
            {units.map((u, i) => (
              <div key={i} className="px-5 py-3.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-800">{u.unit || "—"}</span>
                  <StatusPill status={u.status} />
                </div>
                <div className="text-[12px] text-slate-500">{u.device} · {u.device_type} · {carrierLabel(u.carrier)} · {u.voice_path}</div>
                <div className="text-[12px] text-slate-500 flex flex-wrap gap-x-4">
                  <span><Clock className="inline w-3 h-3 mr-1 text-slate-300" />Check-in {timeAgo(u.last_check_in)}</span>
                  <span><Clock className="inline w-3 h-3 mr-1 text-slate-300" />Heartbeat {timeAgo(u.last_heartbeat)}</span>
                  {u.firmware && u.firmware !== "—" && <span>fw {u.firmware}</span>}
                </div>
                <div className="text-[12px] text-slate-500">{u.recommended_action}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────
export default function PropertyHealth() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [properties, setProperties] = useState([]);
  const [pending, setPending] = useState([]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const sites = await Site.list();
      const list = Array.isArray(sites) ? sites : [];
      const active = list.filter((s) => (s.status || "").toLowerCase() === "active");
      const placeholders = list.filter((s) => (s.status || "").toLowerCase() !== "active");

      const results = [];
      for (const s of active) {
        try {
          results.push(await getPropertyHealth(s.site_id));
        } catch (e) {
          if (e?.status === 404) {
            // Active site with no devices reporting yet — show as "being set up".
            results.push({ property: s.site_name, site_id: s.site_id, status: "Unknown", units: [] });
          } else {
            throw e;
          }
        }
      }
      setProperties(results);
      setPending(placeholders);
    } catch (e) {
      setError(e?.message || "Unable to load property health.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!config.featureDeviceHealth) {
      setLoading(false);
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Feature off — friendly, non-alarming empty state.
  if (!config.featureDeviceHealth) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <Header />
        <div className="mt-6 bg-white rounded-xl border border-slate-200 p-8 text-center">
          <Activity className="w-8 h-8 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-600 font-medium">Property Health is being prepared for your account.</p>
          <p className="text-slate-400 text-sm mt-1">Check back soon, or contact your True911 support team.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <Header onRefresh={load} loading={loading} subtitle={user?.tenant_id ? null : undefined} />

      {loading && (
        <div className="mt-8 flex items-center gap-2 text-slate-500 text-sm">
          <RefreshCw className="w-4 h-4 animate-spin" /> Loading your properties…
        </div>
      )}

      {error && !loading && (
        <div className="mt-6 flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-700 text-sm px-4 py-3 rounded-xl">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" /> {error}
        </div>
      )}

      {!loading && !error && properties.length === 0 && pending.length === 0 && (
        <div className="mt-6 bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500">
          No properties found for your account yet.
        </div>
      )}

      <div className="mt-6 space-y-5">
        {properties.map((p) => (
          <PropertyCard key={p.site_id} data={p} />
        ))}
      </div>

      {pending.length > 0 && (
        <div className="mt-8">
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 mb-2">
            Properties being set up
          </h2>
          <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100">
            {pending.map((s) => (
              <div key={s.site_id} className="px-5 py-3 flex items-center gap-3">
                <Building2 className="w-4 h-4 text-slate-300" />
                <span className="text-sm text-slate-600">{s.site_name}</span>
                <span className="ml-auto text-[10.5px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 border border-slate-200 uppercase tracking-wide">
                  Pending
                </span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-slate-400 mt-2">
            These locations are not live yet and are not monitored as active deployments.
          </p>
        </div>
      )}
    </div>
  );
}

function Header({ onRefresh, loading }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center">
        <Activity className="w-5 h-5 text-white" />
      </div>
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Property Health</h1>
        <p className="text-sm text-slate-500">Live status of your devices, by property.</p>
      </div>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={loading}
          className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      )}
    </div>
  );
}
