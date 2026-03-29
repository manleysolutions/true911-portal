import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, Building2, AlertOctagon, Cpu, RefreshCw, ChevronRight, Zap,
  Eye, Activity, Radio, Clock, ShieldCheck, ShieldAlert, ShieldX,
  TrendingDown, Flame, Phone, PhoneCall, Server, MapPin, Wifi, WifiOff,
  ArrowUpRight, ArrowDownRight, Minus, AlertTriangle, CheckCircle2,
  Play, Target, ArrowRight, FileSpreadsheet,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import NotificationCenter from "@/components/command/NotificationCenter";
import ReportExport from "@/components/command/ReportExport";
import EscalationBadge from "@/components/command/EscalationBadge";

// ═══════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════

function timeSince(iso) {
  if (!iso) return "--";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function pct(a, b) {
  if (!b) return 0;
  return Math.round((a / b) * 100);
}

// ═══════════════════════════════════════════════════════════════════
// AI OPERATIONAL INTELLIGENCE BANNER
// ═══════════════════════════════════════════════════════════════════

function IntelligenceBanner({ data }) {
  const intel = data?.intelligence?.operational_summary;
  const p = data?.portfolio || {};
  const siteSummaries = data?.site_summaries || [];

  // Build the summary sentence that sits below the header
  const summaryLine = useMemo(() => {
    if (intel?.headline && intel?.subheadline) {
      // Combine backend headline + subheadline into one flowing statement
      return `${intel.headline}. ${intel.subheadline}.`;
    }
    // Client-side fallback
    const activeInc = data?.active_incidents || 0;
    const attentionCount = siteSummaries.filter(s => s.needs_attention).length;
    const stale = p.stale_devices || 0;
    const overdue = p.overdue_tasks || 0;
    const totalSites = p.total_sites || 0;
    const connected = p.connected_sites || 0;
    const healthyPct = totalSites > 0 ? pct(connected, totalSites) : 100;

    const parts = [];
    if (attentionCount > 0) {
      parts.push(`${attentionCount} site${attentionCount > 1 ? "s" : ""} need${attentionCount === 1 ? "s" : ""} attention`);
    }
    if (activeInc === 0) {
      parts.push("No active incidents");
    } else {
      parts.push(`${activeInc} active incident${activeInc > 1 ? "s" : ""}`);
    }
    const issues = [];
    if (stale > 0) issues.push("overdue heartbeat reporting");
    if (overdue > 0) issues.push(`${overdue} overdue verification task${overdue > 1 ? "s" : ""}`);
    if (issues.length > 0 && activeInc === 0) {
      parts.push(`but ${issues.join(" and ")} require follow-up`);
    }
    if (attentionCount === 0 && activeInc === 0 && issues.length === 0) {
      return `System stable across ${healthyPct}% of monitored infrastructure. All sites reporting normally.`;
    }
    return parts.join(". ") + ".";
  }, [data, intel, p, siteSummaries]);

  // Bullet highlights
  const highlights = useMemo(() => {
    if (intel?.highlights?.length) {
      return intel.highlights.slice(0, 4).map(h => ({
        severity: h.toLowerCase().includes("offline") || h.toLowerCase().includes("critical") ? "critical"
          : h.toLowerCase().includes("degraded") || h.toLowerCase().includes("overdue") ? "warning"
          : "info",
        text: h,
      }));
    }
    // Fallback highlights from incident feed
    const incidents = data?.incident_feed || [];
    const lines = [];
    incidents.filter(i => i.severity === "critical" && !["resolved", "dismissed", "closed"].includes(i.status)).slice(0, 2).forEach(inc => {
      lines.push({ severity: "critical", text: `${inc.summary} — ${inc.site_name || inc.site_id} — ${timeSince(inc.opened_at)}` });
    });
    incidents.filter(i => i.severity === "warning" && !["resolved", "dismissed", "closed"].includes(i.status)).slice(0, 2).forEach(inc => {
      if (lines.length < 3) lines.push({ severity: "warning", text: `${inc.summary} — ${inc.site_name || inc.site_id}` });
    });
    const stale = p.stale_devices || 0;
    if (stale > 0 && lines.length < 4) lines.push({ severity: "warning", text: `${stale} device${stale > 1 ? "s" : ""} with overdue heartbeat reporting` });
    const overdue = p.overdue_tasks || 0;
    if (overdue > 0 && lines.length < 4) lines.push({ severity: "info", text: `${overdue} verification task${overdue > 1 ? "s" : ""} overdue — compliance risk` });
    return lines;
  }, [data, intel, p]);

  const hasCritical = highlights.some(i => i.severity === "critical");
  const hasWarning = highlights.some(i => i.severity === "warning");
  const hasAnyIssue = highlights.length > 0;
  const borderColor = hasCritical ? "border-red-500/30" : hasWarning ? "border-amber-500/20" : hasAnyIssue ? "border-blue-500/15" : "border-emerald-500/20";
  const glowColor = hasCritical ? "bg-red-500/5" : hasWarning ? "bg-amber-500/5" : hasAnyIssue ? "bg-blue-500/5" : "bg-emerald-500/5";

  const sevIcon = {
    critical: <AlertOctagon className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />,
    warning: <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />,
    info: <Activity className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />,
    ok: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />,
  };

  return (
    <div className={`rounded-xl border ${borderColor} ${glowColor} p-5`}>
      <div className="flex items-center gap-2 mb-2">
        <Target className="w-4 h-4 text-blue-400" />
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Operational Intelligence</span>
        <span className="text-[10px] text-slate-600 ml-auto">Auto-refresh 30s</span>
      </div>
      {/* Summary sentence */}
      <p className="text-[14px] text-slate-200 leading-relaxed mb-3">{summaryLine}</p>
      {/* Bullet highlights */}
      {highlights.length > 0 && (
        <div className="space-y-1.5 border-t border-slate-800/40 pt-3">
          {highlights.map((h, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <div className="mt-0.5">{sevIcon[h.severity]}</div>
              <p className={`text-[12.5px] leading-snug ${
                h.severity === "critical" ? "text-red-300" :
                h.severity === "warning" ? "text-amber-200/80" :
                "text-slate-400"
              }`}>{h.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// EXECUTIVE METRIC CARD
// ═══════════════════════════════════════════════════════════════════

function MetricCard({ label, value, sub, icon: Icon, iconBg, iconColor, border, trend }) {
  return (
    <div className={`bg-slate-900/80 rounded-xl border ${border || "border-slate-800/60"} p-4 hover:border-slate-700/60 transition-colors`}>
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.08em]">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${iconBg}`}>
          <Icon className={`w-4 h-4 ${iconColor}`} />
        </div>
      </div>
      <div className="flex items-end gap-2">
        <span className="text-[28px] font-bold text-white leading-none tabular-nums">{value ?? "--"}</span>
        {trend && (
          <span className={`flex items-center gap-0.5 text-[10px] font-semibold mb-1 ${
            trend === "up" ? "text-emerald-400" : trend === "down" ? "text-red-400" : "text-slate-500"
          }`}>
            {trend === "up" ? <ArrowUpRight className="w-3 h-3" /> : trend === "down" ? <ArrowDownRight className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
          </span>
        )}
      </div>
      {sub && <p className="text-[11px] text-slate-500 mt-1.5 leading-snug">{sub}</p>}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// INCIDENT PRIORITY STACK
// ═══════════════════════════════════════════════════════════════════

const SEV_CONFIG = {
  critical: { bg: "bg-red-500/10", border: "border-red-500/20", text: "text-red-400", dot: "bg-red-500", icon: AlertOctagon, label: "CRITICAL" },
  warning:  { bg: "bg-amber-500/8", border: "border-amber-500/15", text: "text-amber-400", dot: "bg-amber-500", icon: AlertTriangle, label: "WARNING" },
  info:     { bg: "bg-blue-500/8", border: "border-blue-500/15", text: "text-blue-400", dot: "bg-blue-500", icon: Activity, label: "NOTICE" },
};

const STATUS_BADGE = {
  new:          { label: "New",        cls: "bg-red-500/15 text-red-400 border-red-500/25" },
  open:         { label: "Open",       cls: "bg-red-500/15 text-red-400 border-red-500/25" },
  acknowledged: { label: "Ack'd",      cls: "bg-amber-500/15 text-amber-400 border-amber-500/25" },
  in_progress:  { label: "Working",    cls: "bg-blue-500/15 text-blue-400 border-blue-500/25" },
  resolved:     { label: "Resolved",   cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" },
  dismissed:    { label: "Dismissed",  cls: "bg-slate-500/15 text-slate-400 border-slate-500/25" },
  closed:       { label: "Closed",     cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" },
};

const TRANSITIONS = {
  new:          [{ target: "acknowledged", label: "Ack", perm: "COMMAND_ACK", icon: Eye }],
  open:         [{ target: "acknowledged", label: "Ack", perm: "COMMAND_ACK", icon: Eye }],
  acknowledged: [{ target: "in_progress", label: "Start", perm: "COMMAND_ASSIGN", icon: Play }],
  in_progress:  [{ target: "resolved", label: "Resolve", perm: "COMMAND_RESOLVE", icon: CheckCircle2 }],
};

function IncidentStack({ incidents = [], onRefresh, portfolio = {}, siteSummaries = [] }) {
  const { can } = useAuth();
  const [acting, setActing] = useState(null);

  const active = incidents.filter(i => !["resolved", "dismissed", "closed"].includes(i.status));
  const sorted = [...active].sort((a, b) => {
    const sevOrder = { critical: 0, warning: 1, info: 2 };
    return (sevOrder[a.severity] ?? 3) - (sevOrder[b.severity] ?? 3);
  });

  async function handleTransition(inc, target) {
    const key = `${inc.id}-${target}`;
    setActing(key);
    try {
      await apiFetch(`/command/incidents/${inc.id}/transition/${target}`, { method: "POST", body: JSON.stringify({}) });
      toast.success(`Incident ${target}`);
      onRefresh?.();
    } catch (err) {
      toast.error(err.message || "Action failed");
    } finally {
      setActing(null);
    }
  }

  return (
    <div className="bg-slate-900/80 rounded-xl border border-slate-800/60 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800/40">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          <h3 className="text-sm font-semibold text-white">Priority Incidents</h3>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-500 tabular-nums">{active.length} active</span>
          <Link to={createPageUrl("Incidents")} className="text-[11px] text-red-400 hover:text-red-300 font-medium flex items-center gap-0.5">
            All <ChevronRight className="w-3 h-3" />
          </Link>
        </div>
      </div>

      <div className="divide-y divide-slate-800/40 max-h-[520px] overflow-y-auto">
        {sorted.length === 0 && (() => {
          const attentionCount = siteSummaries.filter(s => s.needs_attention).length;
          const stale = portfolio.stale_devices || 0;
          const overdue = portfolio.overdue_tasks || 0;
          const hasIssues = attentionCount > 0 || stale > 0 || overdue > 0;
          const parts = [];
          if (attentionCount > 0) parts.push(`monitoring ${attentionCount} site${attentionCount > 1 ? "s" : ""} needing attention`);
          if (stale > 0) parts.push(`${stale} device${stale > 1 ? "s" : ""} with overdue heartbeat`);
          if (overdue > 0) parts.push(`${overdue} overdue verification task${overdue > 1 ? "s" : ""}`);
          return (
            <div className="px-5 py-8 text-center">
              <CheckCircle2 className={`w-7 h-7 mx-auto mb-2 ${hasIssues ? "text-amber-500/50" : "text-emerald-500/50"}`} />
              <p className={`text-sm font-medium ${hasIssues ? "text-slate-300" : "text-emerald-400/70"}`}>No active incidents</p>
              <p className="text-[11px] text-slate-500 mt-1.5 max-w-xs mx-auto leading-relaxed">
                {hasIssues
                  ? `No open incidents, but ${parts.join(" and ")} require follow-up.`
                  : "All systems reporting normally. No issues detected."}
              </p>
              {hasIssues && (
                <div className="flex items-center justify-center gap-3 mt-3">
                  <Link to={createPageUrl("OperatorView")} className="text-[11px] text-amber-400 hover:text-amber-300 font-medium flex items-center gap-0.5">
                    View Sites <ChevronRight className="w-3 h-3" />
                  </Link>
                </div>
              )}
            </div>
          );
        })()}
        {sorted.slice(0, 12).map(inc => {
          const sev = SEV_CONFIG[inc.severity] || SEV_CONFIG.info;
          const sts = STATUS_BADGE[inc.status] || STATUS_BADGE.open;
          const SIcon = sev.icon;
          const actions = (TRANSITIONS[inc.status] || []).filter(t => can(t.perm));

          return (
            <div key={inc.incident_id || inc.id} className="px-5 py-3.5 hover:bg-slate-800/30 transition-colors">
              <div className="flex items-start gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${sev.bg} ${sev.border}`}>
                  <SIcon className={`w-4 h-4 ${sev.text}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                    <span className={`text-[9px] font-bold tracking-wider ${sev.text}`}>{sev.label}</span>
                    <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-semibold border ${sts.cls}`}>{sts.label}</span>
                    <EscalationBadge incident={inc} />
                  </div>
                  <Link
                    to={createPageUrl("CommandSite") + `?site=${inc.site_id}`}
                    className="text-[13px] text-slate-200 leading-snug hover:text-white transition-colors"
                  >
                    {inc.summary}
                  </Link>
                  <div className="flex items-center gap-2 mt-1.5 text-[11px] text-slate-500">
                    <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{inc.site_name || inc.site_id}</span>
                    <span className="text-slate-700">·</span>
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{timeSince(inc.opened_at)}</span>
                  </div>
                  {actions.length > 0 && (
                    <div className="flex items-center gap-1.5 mt-2">
                      {actions.map(action => {
                        const AIcon = action.icon;
                        const isActing = acting === `${inc.id}-${action.target}`;
                        return (
                          <button
                            key={action.target}
                            onClick={() => handleTransition(inc, action.target)}
                            disabled={isActing}
                            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium border transition-colors
                              ${action.target === "resolved" ? "border-emerald-700/40 text-emerald-400 hover:bg-emerald-900/20" : "border-slate-700/50 text-slate-400 hover:bg-slate-800 hover:text-slate-300"}
                              ${isActing ? "opacity-50" : ""}
                            `}
                          >
                            {isActing ? <div className="w-2.5 h-2.5 border border-current border-t-transparent rounded-full animate-spin" /> : <AIcon className="w-2.5 h-2.5" />}
                            {action.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// READINESS SCORE
// ═══════════════════════════════════════════════════════════════════

const RISK_CFG = {
  Operational:        { icon: ShieldCheck, color: "text-emerald-400", stroke: "#10b981", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  "Attention Needed": { icon: ShieldAlert, color: "text-amber-400", stroke: "#f59e0b", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  "At Risk":          { icon: ShieldX, color: "text-red-400", stroke: "#ef4444", bg: "bg-red-500/10", border: "border-red-500/20" },
};

function ReadinessPanel({ readiness = {}, portfolio = {} }) {
  const { score = 0, risk_label = "Operational", factors = [] } = readiness;
  const cfg = RISK_CFG[risk_label] || RISK_CFG.Operational;
  const RIcon = cfg.icon;
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  // Build plain-English summary from portfolio data
  const plainSummary = useMemo(() => {
    const parts = [];
    const td = portfolio.total_devices || 0;
    const ad = portfolio.active_devices || 0;
    const ts = portfolio.total_sites || 0;
    const cs = portfolio.connected_sites || 0;
    if (td > 0) parts.push(`${ad} of ${td} device${td > 1 ? "s" : ""} active`);
    if (ts > 0) parts.push(`${cs} of ${ts} site${ts > 1 ? "s" : ""} fully connected`);
    const stale = portfolio.stale_devices || 0;
    if (stale > 0) parts.push(`${stale} with overdue heartbeat`);
    const overdue = portfolio.overdue_tasks || 0;
    if (overdue > 0) parts.push(`${overdue} overdue verification task${overdue > 1 ? "s" : ""}`);
    return parts.join(". ") + (parts.length > 0 ? "." : "");
  }, [portfolio]);

  return (
    <div className={`bg-slate-900/80 rounded-xl border ${cfg.border} overflow-hidden`}>
      <div className="px-5 py-4 border-b border-slate-800/40">
        <h3 className="text-sm font-semibold text-white">Emergency Readiness</h3>
      </div>
      <div className="p-5">
        <div className="flex items-center gap-5 mb-4">
          <div className="relative flex-shrink-0">
            <svg width="120" height="120" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(51,65,85,0.3)" strokeWidth="8" />
              <circle
                cx="60" cy="60" r={radius} fill="none"
                stroke={cfg.stroke} strokeWidth="8" strokeLinecap="round"
                strokeDasharray={circumference} strokeDashoffset={offset}
                transform="rotate(-90 60 60)"
                className="transition-all duration-1000"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={`text-3xl font-bold ${cfg.color}`}>{score}</span>
              <span className="text-[10px] text-slate-600">/100</span>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <div className={`w-7 h-7 rounded-lg border ${cfg.border} ${cfg.bg} flex items-center justify-center`}>
                <RIcon className={`w-3.5 h-3.5 ${cfg.color}`} />
              </div>
              <span className={`text-sm font-bold ${cfg.color}`}>{risk_label}</span>
            </div>
            {/* Plain-English summary */}
            <p className="text-[11px] text-slate-400 leading-relaxed">
              {plainSummary || (score >= 85 ? "All readiness factors within normal parameters." : "Readiness reflects current deployment and monitoring status.")}
            </p>
          </div>
        </div>

        {factors.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 mb-1">
              <TrendingDown className="w-3 h-3 text-slate-600" />
              <span className="text-[10px] text-slate-600 font-medium uppercase tracking-wider">What is affecting the score</span>
            </div>
            {factors.map((f, i) => (
              <div key={i} className="flex items-center gap-2.5 px-3 py-2 bg-slate-800/30 rounded-lg">
                <span className="text-[11px] text-slate-400 flex-1">{f.detail || f.label}</span>
                <span className="text-[11px] font-bold text-red-400">{f.impact}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// SYSTEM HEALTH MATRIX (compact)
// ═══════════════════════════════════════════════════════════════════

const SYS_ICONS = {
  fire_alarm: Flame, elevator_phone: Phone, das_radio: Radio,
  call_station: PhoneCall, backup_power: Zap, emergency_device: Shield, other: Server,
};

function SystemHealthCompact({ systems = [] }) {
  if (systems.length === 0) return null;
  return (
    <div className="bg-slate-900/80 rounded-xl border border-slate-800/60 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-800/40">
        <h3 className="text-sm font-semibold text-white">System Health</h3>
        <p className="text-[11px] text-slate-500 mt-0.5">Life-safety infrastructure by category</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3">
        {systems.map(sys => {
          const SIcon = SYS_ICONS[sys.key] || Server;
          const statusColor = sys.status === "healthy" ? "text-emerald-400" : sys.status === "warning" ? "text-amber-400" : "text-red-400";
          const barColor = sys.status === "healthy" ? "bg-emerald-500" : sys.status === "warning" ? "bg-amber-500" : "bg-red-500";
          return (
            <div key={sys.key} className="px-4 py-3.5 border-b border-r border-slate-800/30 last:border-r-0">
              <div className="flex items-center gap-2 mb-2">
                <SIcon className={`w-4 h-4 ${statusColor}`} />
                <span className="text-[12px] text-slate-300 font-medium truncate">{sys.label}</span>
              </div>
              <div className="flex items-end justify-between mb-1.5">
                <span className={`text-lg font-bold ${statusColor}`}>{sys.health_pct}%</span>
                <span className="text-[10px] text-slate-600">{sys.total} total</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-1">
                <div className={`h-1 rounded-full transition-all ${barColor}`} style={{ width: `${sys.health_pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// MAP PREVIEW
// ═══════════════════════════════════════════════════════════════════

function MapPreview({ siteSummaries = [] }) {
  const total = siteSummaries.length;
  const critical = siteSummaries.filter(s => s.critical_incidents > 0).length;
  const warning = siteSummaries.filter(s => s.needs_attention && !s.critical_incidents).length;
  const healthy = total - critical - warning;

  return (
    <div className="bg-slate-900/80 rounded-xl border border-slate-800/60 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800/40">
        <h3 className="text-sm font-semibold text-white">Site Status Map</h3>
        <Link to={createPageUrl("DeploymentMap")} className="text-[11px] text-blue-400 hover:text-blue-300 font-medium flex items-center gap-0.5">
          Full Map <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
      <div className="p-5">
        <div className="relative h-36 bg-slate-800/30 rounded-lg overflow-hidden mb-4">
          <div className="absolute inset-0 opacity-20">
            <svg width="100%" height="100%" className="text-slate-700">
              {[...Array(8)].map((_, i) => (
                <line key={`h${i}`} x1="0" y1={`${(i + 1) * 12.5}%`} x2="100%" y2={`${(i + 1) * 12.5}%`} stroke="currentColor" strokeWidth="0.5" />
              ))}
              {[...Array(12)].map((_, i) => (
                <line key={`v${i}`} x1={`${(i + 1) * 8.33}%`} y1="0" x2={`${(i + 1) * 8.33}%`} y2="100%" stroke="currentColor" strokeWidth="0.5" />
              ))}
            </svg>
          </div>
          {siteSummaries.slice(0, 20).map((site, i) => {
            const isCrit = site.critical_incidents > 0;
            const isWarn = site.needs_attention && !isCrit;
            const color = isCrit ? "bg-red-500" : isWarn ? "bg-amber-500" : "bg-emerald-500";
            const x = 8 + ((i * 37 + 13) % 84);
            const y = 10 + ((i * 53 + 7) % 80);
            return (
              <div
                key={site.site_id}
                className={`absolute w-2.5 h-2.5 rounded-full ${color} ${isCrit ? "animate-pulse shadow-lg shadow-red-500/40" : ""}`}
                style={{ left: `${x}%`, top: `${y}%` }}
                title={`${site.site_name}: ${isCrit ? "Critical" : isWarn ? "Warning" : "Healthy"}`}
              />
            );
          })}
          {total === 0 && (
            <div className="absolute inset-0 flex items-center justify-center">
              <p className="text-[11px] text-slate-600">No sites deployed</p>
            </div>
          )}
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-[11px] text-slate-400">{healthy} Healthy</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-[11px] text-slate-400">{warning} Warning</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-[11px] text-slate-400">{critical} Critical</span>
            </div>
          </div>
          <span className="text-[10px] text-slate-600 tabular-nums">{total} sites</span>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// ACTIVITY TIMELINE
// ═══════════════════════════════════════════════════════════════════

const ACT_ICONS = {
  incident_created: { icon: AlertOctagon, color: "text-red-400", dot: "bg-red-500" },
  incident_acknowledged: { icon: Eye, color: "text-amber-400", dot: "bg-amber-400" },
  incident_in_progress: { icon: Play, color: "text-blue-400", dot: "bg-blue-400" },
  incident_resolved: { icon: CheckCircle2, color: "text-emerald-400", dot: "bg-emerald-400" },
  incident_dismissed: { icon: Activity, color: "text-slate-400", dot: "bg-slate-500" },
  incident_assigned: { icon: Target, color: "text-blue-400", dot: "bg-blue-400" },
  site_import: { icon: ArrowRight, color: "text-cyan-400", dot: "bg-cyan-400" },
  subscriber_import: { icon: ArrowRight, color: "text-cyan-400", dot: "bg-cyan-400" },
  bulk_import: { icon: ArrowRight, color: "text-cyan-400", dot: "bg-cyan-400" },
  readiness_recalculated: { icon: RefreshCw, color: "text-purple-400", dot: "bg-purple-400" },
  verification_scheduled: { icon: Clock, color: "text-cyan-400", dot: "bg-cyan-400" },
};

function TimelinePanel({ activities = [] }) {
  const items = activities.slice(0, 12);
  return (
    <div className="bg-slate-900/80 rounded-xl border border-slate-800/60 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-800/40">
        <Activity className="w-4 h-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-white">Activity</h3>
        <span className="text-[10px] text-slate-600 ml-auto">{items.length} recent</span>
      </div>
      <div className="p-4 max-h-[420px] overflow-y-auto">
        {items.length === 0 ? (
          <p className="text-[12px] text-slate-600 text-center py-6">No recent activity</p>
        ) : (
          <div className="space-y-0">
            {items.map((act, i) => {
              const acfg = ACT_ICONS[act.activity_type] || { icon: Activity, color: "text-slate-400", dot: "bg-slate-600" };
              const AIcon = acfg.icon;
              return (
                <div key={act.id || i} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <div className={`w-2 h-2 rounded-full ${acfg.dot} flex-shrink-0 mt-2`} />
                    {i < items.length - 1 && <div className="w-px flex-1 bg-slate-800/80 my-1" />}
                  </div>
                  <div className="flex-1 pb-3 min-w-0">
                    <div className="flex items-start gap-2">
                      <AIcon className={`w-3.5 h-3.5 ${acfg.color} flex-shrink-0 mt-0.5`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-[12px] text-slate-300 leading-snug">{act.summary}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          {act.actor && act.actor !== "system" && <span className="text-[10px] text-slate-500">{act.actor}</span>}
                          <span className="text-[10px] text-slate-600 ml-auto">{timeSince(act.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// ACTION CENTER
// ═══════════════════════════════════════════════════════════════════

function ActionCenter() {
  const { can } = useAuth();

  const actions = [
    { label: "View Incidents",     icon: AlertOctagon,    page: "Incidents",          color: "text-red-400" },
    { label: "Deployment Map",     icon: MapPin,          page: "DeploymentMap",      color: "text-blue-400" },
    { label: "Network Status",     icon: Radio,           page: "NetworkDashboard",   color: "text-cyan-400" },
    { label: "Export Report",      custom: true },
    { label: "Provisioning",       icon: Zap,             page: "ProvisioningQueue",  color: "text-amber-400",   perm: "COMMAND_BULK_IMPORT" },
    { label: "Subscriber Import",  icon: FileSpreadsheet, page: "SubscriberImport",   color: "text-emerald-400", perm: "SUBSCRIBER_IMPORT" },
  ];

  const visible = actions.filter(a => !a.perm || can(a.perm));

  return (
    <div className="bg-slate-900/80 rounded-xl border border-slate-800/60 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-800/40">
        <h3 className="text-sm font-semibold text-white">Quick Actions</h3>
      </div>
      <div className="p-3 space-y-1">
        {visible.map((action, i) => {
          if (action.custom) return <ReportExport key={i} />;
          const AIcon = action.icon;
          return (
            <Link
              key={i}
              to={createPageUrl(action.page)}
              className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg hover:bg-slate-800/60 text-slate-400 hover:text-slate-200 text-[12.5px] transition-colors"
            >
              <AIcon className={`w-4 h-4 ${action.color}`} />
              {action.label}
              <ChevronRight className="w-3 h-3 ml-auto text-slate-700" />
            </Link>
          );
        })}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// RECOMMENDED ACTIONS
// ═══════════════════════════════════════════════════════════════════

function RecommendationsPanel({ data }) {
  const backendRecs = data?.intelligence?.recommended_actions;

  const recs = useMemo(() => {
    // Use backend recommendations when available
    if (backendRecs?.length) {
      return backendRecs.map(r => ({
        severity: r.priority === "high" ? "critical" : r.priority === "medium" ? "warning" : "info",
        action: r.title,
        detail: r.reason,
        page: r.route?.startsWith("/") ? r.route.split("?")[0].replace("/", "") : null,
        query: r.route?.includes("?") ? "?" + r.route.split("?")[1] : "",
      }));
    }

    // Fallback: client-side derivation
    const incidents = data?.incident_feed || [];
    const siteSummaries = data?.site_summaries || [];
    const list = [];

    incidents
      .filter(i => i.severity === "critical" && ["new", "open"].includes(i.status))
      .slice(0, 2)
      .forEach(inc => {
        list.push({
          severity: "critical",
          action: `Investigate ${inc.summary}`,
          detail: `${inc.site_name || inc.site_id} — open ${timeSince(inc.opened_at)}`,
          page: "CommandSite",
          query: `?site=${inc.site_id}`,
        });
      });

    const staleSites = siteSummaries.filter(s => s.stale_devices > 0);
    if (staleSites.length > 0 && list.length < 4) {
      const s = staleSites[0];
      list.push({
        severity: "warning",
        action: `Check ${s.stale_devices} stale device${s.stale_devices > 1 ? "s" : ""} at ${s.site_name}`,
        detail: "Device heartbeat overdue — possible connectivity issue",
        page: "CommandSite",
        query: `?site=${s.site_id}`,
      });
    }

    const overdueSites = (data?.site_summaries || []).filter(s => s.overdue_tasks > 0);
    if (overdueSites.length > 0 && list.length < 4) {
      const s = overdueSites[0];
      list.push({
        severity: "info",
        action: `${s.overdue_tasks} overdue verification task${s.overdue_tasks > 1 ? "s" : ""} at ${s.site_name}`,
        detail: "Compliance risk — schedule verification",
        page: "CommandSite",
        query: `?site=${s.site_id}`,
      });
    }

    const readiness = data?.readiness || {};
    if (readiness.score < 70 && list.length < 4) {
      list.push({
        severity: "warning",
        action: "Readiness score below threshold",
        detail: `Current score: ${readiness.score}/100 — ${readiness.risk_label}`,
      });
    }

    if (list.length === 0) {
      list.push({
        severity: "ok",
        action: "No recommended actions",
        detail: "All systems operational — continue monitoring",
      });
    }

    return list;
  }, [data, backendRecs]);

  const sevStyles = {
    critical: { border: "border-red-500/20", bg: "bg-red-500/5", icon: AlertOctagon, iconColor: "text-red-400" },
    warning: { border: "border-amber-500/15", bg: "bg-amber-500/5", icon: AlertTriangle, iconColor: "text-amber-400" },
    info: { border: "border-blue-500/15", bg: "bg-blue-500/5", icon: Activity, iconColor: "text-blue-400" },
    ok: { border: "border-emerald-500/15", bg: "bg-emerald-500/5", icon: CheckCircle2, iconColor: "text-emerald-400" },
  };

  return (
    <div className="bg-slate-900/80 rounded-xl border border-slate-800/60 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-800/40">
        <Target className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Recommended Actions</h3>
      </div>
      <div className="p-3 space-y-2">
        {recs.map((rec, i) => {
          const s = sevStyles[rec.severity] || sevStyles.info;
          const RIcon = s.icon;
          const isFirst = i === 0 && rec.severity !== "ok";
          const inner = (
            <div className={`flex items-start gap-3 rounded-lg border transition-colors ${
              isFirst
                ? `px-4 py-3.5 ${s.border} ${s.bg} ${rec.page ? "hover:bg-slate-800/40 cursor-pointer" : ""}`
                : `px-3.5 py-3 ${s.border} ${s.bg} ${rec.page ? "hover:bg-slate-800/40 cursor-pointer" : ""}`
            }`}>
              <RIcon className={`${isFirst ? "w-5 h-5" : "w-4 h-4"} ${s.iconColor} flex-shrink-0 mt-0.5`} />
              <div className="flex-1 min-w-0">
                <p className={`leading-snug text-slate-200 font-medium ${isFirst ? "text-[13px]" : "text-[12.5px]"}`}>{rec.action}</p>
                <p className={`text-slate-500 mt-0.5 ${isFirst ? "text-[11.5px]" : "text-[11px]"}`}>{rec.detail}</p>
              </div>
              {rec.page && <ChevronRight className="w-3.5 h-3.5 text-slate-600 flex-shrink-0 mt-0.5" />}
            </div>
          );
          if (rec.page) {
            return <Link key={i} to={createPageUrl(rec.page) + (rec.query || "")}>{inner}</Link>;
          }
          return <div key={i}>{inner}</div>;
        })}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// SITES NEEDING ATTENTION
// ═══════════════════════════════════════════════════════════════════

function AttentionSites({ siteSummaries = [] }) {
  const attention = siteSummaries.filter(s => s.needs_attention);
  return (
    <div className="bg-slate-900/80 rounded-xl border border-slate-800/60 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800/40">
        <h3 className="text-sm font-semibold text-white">Sites Needing Attention</h3>
        <Link to={createPageUrl("OperatorView")} className="text-[11px] text-red-400 hover:text-red-300 font-medium flex items-center gap-0.5">
          All Sites <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
      <div className="max-h-[340px] overflow-y-auto">
        {attention.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <CheckCircle2 className="w-6 h-6 text-emerald-500/40 mx-auto mb-1.5" />
            <p className="text-[12px] text-emerald-400/60 font-medium">All sites operational</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/30">
            {attention.slice(0, 6).map(site => {
              const isCrit = site.critical_incidents > 0;
              return (
                <Link
                  key={site.site_id}
                  to={createPageUrl("CommandSite") + `?site=${site.site_id}`}
                  className="flex items-center gap-3 px-5 py-3 hover:bg-slate-800/30 transition-colors"
                >
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isCrit ? "bg-red-500 animate-pulse" : "bg-amber-500"}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-[12.5px] text-slate-200 font-medium truncate">{site.site_name}</p>
                    <div className="flex items-center gap-2 text-[10px] text-slate-500">
                      {site.active_incidents > 0 && <span className={isCrit ? "text-red-400" : "text-amber-400"}>{site.active_incidents} incident{site.active_incidents > 1 ? "s" : ""}</span>}
                      {site.stale_devices > 0 && <span>{site.stale_devices} stale</span>}
                      {site.overdue_tasks > 0 && <span>{site.overdue_tasks} overdue</span>}
                    </div>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-700 flex-shrink-0" />
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// MAIN COMMAND CENTER V2
// ═══════════════════════════════════════════════════════════════════

export default function Command() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  const fetchData = useCallback(async () => {
    try {
      const result = await apiFetch("/command/summary");
      setData(result);
      setLastRefresh(new Date());
    } catch (err) {
      console.error("Command summary fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-slate-950 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-[12px] text-slate-500">Loading Command Center...</p>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const p = data?.portfolio || {};
  const readiness = data?.readiness || {};
  const systemHealth = data?.system_health || [];
  const incidents = data?.incident_feed || [];
  const siteSummaries = data?.site_summaries || [];
  const activities = data?.activity_timeline || [];
  const activeIncidents = data?.active_incidents || 0;
  const criticalIncidents = data?.critical_incidents || 0;

  const healthyPct = p.total_sites > 0 ? pct(p.connected_sites || 0, p.total_sites) : 100;
  const devicesAtRisk = (p.stale_devices || 0) + (p.devices_missing_telemetry || 0);

  return (
    <PageWrapper>
      <div className="min-h-screen bg-slate-950">
        <div className="p-5 lg:p-6 max-w-[1440px] mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-red-600 rounded-xl flex items-center justify-center shadow-lg shadow-red-600/20">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white tracking-tight">
                  Command <span className="text-red-500">Center</span>
                </h1>
                <p className="text-[11px] text-slate-500">
                  Life-safety operations · {user?.name}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <NotificationCenter unreadCount={data?.unread_notifications || 0} />
              <span className="text-[10px] text-slate-600 hidden sm:block tabular-nums">{timeSince(lastRefresh.toISOString())}</span>
              <button onClick={fetchData} className="p-2 rounded-lg border border-slate-800/60 hover:bg-slate-800/50 text-slate-500 transition-colors">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* AI Intelligence Banner */}
          <IntelligenceBanner data={data} />

          {/* Executive Metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <MetricCard
              label="Monitored Sites" value={p.total_sites || 0}
              icon={Building2} iconBg="bg-slate-800/80" iconColor="text-slate-400"
              sub={p.monitored_sites > 0 ? `${p.monitored_sites} with devices assigned` : "Onboarding in progress"}
            />
            <MetricCard
              label="Site Connectivity" value={`${healthyPct}%`}
              icon={Wifi}
              iconBg={healthyPct >= 90 ? "bg-emerald-500/10" : "bg-amber-500/10"}
              iconColor={healthyPct >= 90 ? "text-emerald-400" : "text-amber-400"}
              sub={`${p.connected_sites || 0} of ${p.total_sites || 0} sites reporting`}
              trend={healthyPct >= 90 ? "up" : healthyPct >= 70 ? "neutral" : "down"}
            />
            <MetricCard
              label="Active Incidents" value={activeIncidents}
              icon={AlertOctagon}
              iconBg={criticalIncidents > 0 ? "bg-red-500/10" : "bg-slate-800/80"}
              iconColor={criticalIncidents > 0 ? "text-red-400" : "text-slate-400"}
              border={criticalIncidents > 0 ? "border-red-500/20" : undefined}
              sub={activeIncidents === 0
                ? (devicesAtRisk > 0 ? "No incidents, but devices need attention" : "No open incidents")
                : criticalIncidents > 0 ? `${criticalIncidents} critical` : `${activeIncidents} open`}
            />
            <MetricCard
              label="Devices at Risk" value={devicesAtRisk}
              icon={WifiOff}
              iconBg={devicesAtRisk > 0 ? "bg-amber-500/10" : "bg-slate-800/80"}
              iconColor={devicesAtRisk > 0 ? "text-amber-400" : "text-slate-400"}
              sub={devicesAtRisk > 0
                ? `${p.stale_devices || 0} overdue heartbeat, ${p.devices_missing_telemetry || 0} never reported`
                : "All devices reporting on schedule"}
              trend={devicesAtRisk > 0 ? "down" : "neutral"}
            />
            <MetricCard
              label="Readiness Score" value={`${readiness.score || 0}%`}
              icon={ShieldCheck}
              iconBg={readiness.score >= 85 ? "bg-emerald-500/10" : readiness.score >= 60 ? "bg-amber-500/10" : "bg-red-500/10"}
              iconColor={readiness.score >= 85 ? "text-emerald-400" : readiness.score >= 60 ? "text-amber-400" : "text-red-400"}
              border={readiness.score < 60 ? "border-red-500/20" : undefined}
              sub={readiness.score >= 85 ? "Operational" : readiness.score >= 60 ? "Degraded — review recommended" : "At risk — action required"}
            />
            <MetricCard
              label="Total Devices" value={p.total_devices || 0}
              icon={Cpu} iconBg="bg-blue-500/10" iconColor="text-blue-400"
              sub={`${p.active_devices || 0} active, ${p.devices_with_telemetry || 0} reporting`}
            />
          </div>

          {/* Main Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">

            {/* Left Column — 8/12 */}
            <div className="lg:col-span-8 space-y-5">
              <IncidentStack incidents={incidents} onRefresh={fetchData} portfolio={p} siteSummaries={siteSummaries} />
              <SystemHealthCompact systems={systemHealth} />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <MapPreview siteSummaries={siteSummaries} />
                <AttentionSites siteSummaries={siteSummaries} />
              </div>
            </div>

            {/* Right Column — 4/12 */}
            <div className="lg:col-span-4 space-y-5">
              <ReadinessPanel readiness={readiness} portfolio={p} />
              <RecommendationsPanel data={data} />
              <ActionCenter />
              <TimelinePanel activities={activities} />
            </div>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
