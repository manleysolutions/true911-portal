import { useState, useEffect, useCallback } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { apiFetch } from "@/api/client";
import {
  Building2, ArrowLeft, MapPin, Phone, Mail, User, Cpu, Disc3, PhoneCall, ShieldCheck,
  AlertTriangle, CheckCircle2, XCircle, HelpCircle, Loader2, Plus, RefreshCw, ChevronRight,
  Video, Mic, MessageSquare, ExternalLink, Clock, Radio, FileText, Pencil,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import SitePickerModal from "@/components/SitePickerModal";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

/* ── Helpers ── */
function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STAT_BADGE = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  provisioning: "bg-blue-50 text-blue-700 border-blue-200",
  inventory: "bg-blue-50 text-blue-700 border-blue-200",
  Connected: "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Attention Needed": "bg-amber-50 text-amber-700 border-amber-200",
  "Not Connected": "bg-red-50 text-red-700 border-red-200",
  suspended: "bg-amber-50 text-amber-700 border-amber-200",
  inactive: "bg-red-50 text-red-700 border-red-200",
  decommissioned: "bg-gray-100 text-gray-500 border-gray-200",
};

const COMPLIANCE_COLORS = {
  compliant: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", icon: CheckCircle2, label: "Compliant" },
  partially_compliant: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", icon: AlertTriangle, label: "Partially Compliant" },
  review_required: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", icon: HelpCircle, label: "Review Required" },
  non_compliant: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200", icon: XCircle, label: "Non-Compliant" },
  no_units: { bg: "bg-gray-50", text: "text-gray-500", border: "border-gray-200", icon: HelpCircle, label: "No Units" },
};

function Badge({ status }) {
  const cls = STAT_BADGE[status] || "bg-gray-100 text-gray-500 border-gray-200";
  return <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${cls}`}>{status}</span>;
}


/* ═══════════════════════════════════════════════════════════════════
   Section card wrapper
   ═══════════════════════════════════════════════════════════════════ */
function Card({ title, icon: Icon, count, children, action }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4 text-gray-400" />}
          <span className="text-sm font-bold text-gray-800">{title}</span>
          {count != null && (
            <span className="ml-1 text-[10px] font-bold bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">{count}</span>
          )}
        </div>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════
   Main SiteDetail page
   ═══════════════════════════════════════════════════════════════════ */
export default function SiteDetail() {
  const [params] = useSearchParams();
  const siteId = params.get("id");
  const { can, isSuperAdmin } = useAuth();
  const isNOC = can("VIEW_ADMIN");

  const [site, setSite] = useState(null);
  const [infra, setInfra] = useState(null);
  const [compliance, setCompliance] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    if (!siteId) return;
    setLoading(true);
    try {
      // Fetch site by site_id — need to get the numeric id first
      const sites = await apiFetch(`/sites?limit=1&site_id=${siteId}`);
      const s = sites?.[0];
      if (!s) { setSite(null); setLoading(false); return; }
      setSite(s);

      // Fetch infrastructure and compliance in parallel
      const [infraData, compData] = await Promise.all([
        apiFetch(`/sites/${s.id}/infrastructure`).catch(() => null),
        apiFetch(`/service-units/site/${siteId}/compliance`).catch(() => null),
      ]);
      setInfra(infraData);
      setCompliance(compData);
    } catch { setSite(null); }
    setLoading(false);
  }, [siteId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 text-red-600 animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  if (!site) {
    return (
      <PageWrapper>
        <div className="p-6 max-w-4xl mx-auto text-center py-20">
          <h2 className="text-lg font-bold text-gray-900 mb-2">Site Not Found</h2>
          <p className="text-sm text-gray-500 mb-4">The site "{siteId}" could not be loaded.</p>
          <Link to={createPageUrl("Sites")} className="text-sm text-red-600 hover:text-red-700 font-medium">Back to Sites</Link>
        </div>
      </PageWrapper>
    );
  }

  const hasE911 = !!(site.e911_street && site.e911_city && site.e911_state);
  const devices = infra?.devices || [];
  const sims = infra?.sims || [];
  const lines = infra?.lines || [];
  const comp = COMPLIANCE_COLORS[compliance?.status] || COMPLIANCE_COLORS.no_units;
  const CompIcon = comp.icon;

  // Collect warnings
  const warnings = [];
  if (!hasE911 && (devices.length > 0 || sims.length > 0)) {
    warnings.push({ text: "E911 address missing — emergency routing cannot be confirmed", severity: "critical" });
  }
  if (compliance?.warnings) {
    compliance.warnings.slice(0, 5).forEach(w => warnings.push({ text: w, severity: "warning" }));
  }
  if (lines.length === 0 && devices.length > 0) {
    warnings.push({ text: "No voice lines assigned — site cannot route emergency calls", severity: "warning" });
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-5xl mx-auto space-y-6">

        {/* ── Back nav ── */}
        <Link to={createPageUrl("Sites")} className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft className="w-4 h-4" /> All Sites
        </Link>

        {/* ═══════════════════════════════════════════════════════════
            Site Header
            ═══════════════════════════════════════════════════════════ */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h1 className="text-xl font-bold text-gray-900">{site.site_name}</h1>
              <div className="text-sm text-gray-500 mt-0.5">
                {site.customer_name} <span className="text-gray-300 mx-1">|</span>
                <span className="font-mono text-xs">{site.site_id}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge status={site.status} />
              <button onClick={fetchAll} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-400">
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Status row */}
          <div className="flex flex-wrap gap-3">
            {/* E911 */}
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium ${
              hasE911 ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-amber-50 text-amber-700 border-amber-200"
            }`}>
              <MapPin className="w-3.5 h-3.5" />
              {hasE911 ? `${site.e911_city}, ${site.e911_state}` : "E911 Missing"}
            </div>

            {/* Compliance */}
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium ${comp.bg} ${comp.text} ${comp.border}`}>
              <CompIcon className="w-3.5 h-3.5" />
              {comp.label}
            </div>

            {/* Infrastructure counts */}
            <div className="flex items-center gap-3 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-xs text-gray-600">
              <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> {devices.length}</span>
              <span className="flex items-center gap-1"><Disc3 className="w-3 h-3" /> {sims.length}</span>
              <span className="flex items-center gap-1"><PhoneCall className="w-3 h-3" /> {lines.length}</span>
            </div>

            {/* Last heartbeat */}
            {site.last_checkin && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-xs text-gray-500">
                <Clock className="w-3 h-3" /> {timeSince(site.last_checkin)}
              </div>
            )}
          </div>
        </div>


        {/* ═══════════════════════════════════════════════════════════
            Warnings
            ═══════════════════════════════════════════════════════════ */}
        {warnings.length > 0 && (
          <div className="space-y-2">
            {warnings.map((w, i) => (
              <div key={i} className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border ${
                w.severity === "critical"
                  ? "bg-red-50 border-red-200 text-red-700"
                  : "bg-amber-50 border-amber-200 text-amber-700"
              }`}>
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span className="text-xs">{w.text}</span>
              </div>
            ))}
          </div>
        )}


        {/* ═══════════════════════════════════════════════════════════
            Quick Actions
            ═══════════════════════════════════════════════════════════ */}
        {can("MANAGE_SIMS") && (
          <div className="flex flex-wrap gap-2">
            <Link to={`${createPageUrl("SiteOnboarding")}?site=${site.site_id}`}
              className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold">
              <Plus className="w-3.5 h-3.5" /> Add Service Unit
            </Link>
            <Link to={`${createPageUrl("SimManagement")}`}
              className="flex items-center gap-1.5 px-3 py-2 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-lg text-xs font-medium">
              <Disc3 className="w-3.5 h-3.5" /> Assign SIMs
            </Link>
            <Link to={`${createPageUrl("Devices")}`}
              className="flex items-center gap-1.5 px-3 py-2 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-lg text-xs font-medium">
              <Cpu className="w-3.5 h-3.5" /> Assign Devices
            </Link>
            {isNOC && (
              <Link to={`${createPageUrl("CommandSite")}?site=${site.site_id}`}
                className="flex items-center gap-1.5 px-3 py-2 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-lg text-xs font-medium">
                <ShieldCheck className="w-3.5 h-3.5" /> Command View
              </Link>
            )}
          </div>
        )}


        {/* ═══════════════════════════════════════════════════════════
            Main grid — 2 columns on desktop
            ═══════════════════════════════════════════════════════════ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* ── Service Units ── */}
          <Card title="Service Units" icon={Phone} count={compliance?.unit_count || 0}>
            {(compliance?.unit_count || 0) === 0 ? (
              <div className="text-center py-4">
                <p className="text-xs text-gray-400 mb-2">No service units configured.</p>
                {can("MANAGE_SIMS") && (
                  <Link to={`${createPageUrl("SiteOnboarding")}?site=${site.site_id}`}
                    className="text-xs text-red-600 hover:text-red-700 font-medium">Add Service Units</Link>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {/* Capability grid */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex items-center gap-2 text-xs">
                    <Mic className="w-3.5 h-3.5 text-emerald-500" />
                    <span className="text-gray-600">Voice</span>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 ml-auto" />
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <Video className="w-3.5 h-3.5 text-gray-400" />
                    <span className="text-gray-600">Video</span>
                    <span className="text-[9px] text-gray-400 ml-auto">varies</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <MessageSquare className="w-3.5 h-3.5 text-gray-400" />
                    <span className="text-gray-600">Text/Visual</span>
                    <span className="text-[9px] text-gray-400 ml-auto">varies</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <MapPin className="w-3.5 h-3.5 text-gray-400" />
                    <span className="text-gray-600">E911</span>
                    {hasE911 ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 ml-auto" /> : <AlertTriangle className="w-3.5 h-3.5 text-amber-400 ml-auto" />}
                  </div>
                </div>
                <div className="text-[9px] text-gray-400 italic">Operational guidance only — not a legal compliance determination.</div>
              </div>
            )}
          </Card>

          {/* ── E911 & Address ── */}
          <Card title="E911 Address" icon={MapPin}>
            {hasE911 ? (
              <div className="space-y-2">
                <div className="text-sm text-gray-800">{site.e911_street}</div>
                <div className="text-sm text-gray-600">{site.e911_city}, {site.e911_state} {site.e911_zip}</div>
                {site.has_coords && (
                  <div className="text-[10px] text-gray-400 font-mono">{site.lat?.toFixed(4)}, {site.lng?.toFixed(4)}</div>
                )}
              </div>
            ) : (
              <div className="text-center py-4">
                <AlertTriangle className="w-6 h-6 text-amber-400 mx-auto mb-2" />
                <p className="text-xs text-gray-500 mb-1">No E911 address on file.</p>
                <p className="text-[10px] text-gray-400">Emergency routing cannot be confirmed until an address is validated.</p>
              </div>
            )}
          </Card>

          {/* ── Devices ── */}
          <Card title="Devices" icon={Cpu} count={devices.length}>
            {devices.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-3">No devices assigned.</p>
            ) : (
              <div className="space-y-2">
                {devices.map(d => (
                  <div key={d.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                    <div>
                      <div className="text-xs font-mono text-gray-700">{d.device_id}</div>
                      <div className="text-[10px] text-gray-500">
                        {d.device_type || d.model || "—"}
                        {isNOC && d.imei && <> <span className="text-gray-400">| IMEI</span> {d.imei}</>}
                        {isNOC && d.carrier && <> <span className="text-gray-400">|</span> {d.carrier}</>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {d.last_heartbeat && (
                        <span className="text-[10px] text-gray-400">{timeSince(d.last_heartbeat)}</span>
                      )}
                      <Badge status={d.status} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* ── SIMs ── */}
          <Card title="SIMs" icon={Disc3} count={sims.length}>
            {sims.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-3">No SIMs assigned.</p>
            ) : (
              <div className="space-y-2">
                {sims.map(s => (
                  <div key={s.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                    <div>
                      <div className="text-xs font-mono text-gray-700">{s.iccid}</div>
                      <div className="text-[10px] text-gray-500">
                        {s.carrier} {s.msisdn && <>| {s.msisdn}</>} {s.plan && <>| {s.plan}</>}
                      </div>
                    </div>
                    <Badge status={s.status} />
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* ── Lines ── */}
          <Card title="Voice Lines" icon={PhoneCall} count={lines.length}>
            {lines.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-3">No lines assigned.</p>
            ) : (
              <div className="space-y-2">
                {lines.map(l => (
                  <div key={l.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                    <div>
                      <div className="text-xs text-gray-700">{l.did || l.line_id}</div>
                      <div className="text-[10px] text-gray-500">{l.provider} | {l.protocol}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      {l.e911_status && (
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${
                          l.e911_status === "validated" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                          l.e911_status === "pending" ? "bg-amber-50 text-amber-700 border-amber-200" :
                          "bg-gray-100 text-gray-500 border-gray-200"
                        }`}>{l.e911_status}</span>
                      )}
                      <Badge status={l.status} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* ── Contact ── */}
          <Card title="Site Contact" icon={User}>
            {(site.poc_name || site.poc_phone || site.poc_email) ? (
              <div className="space-y-2">
                {site.poc_name && (
                  <div className="flex items-center gap-2 text-xs text-gray-700">
                    <User className="w-3.5 h-3.5 text-gray-400" /> {site.poc_name}
                  </div>
                )}
                {site.poc_phone && (
                  <div className="flex items-center gap-2 text-xs text-gray-700">
                    <Phone className="w-3.5 h-3.5 text-gray-400" />
                    <a href={`tel:${site.poc_phone}`} className="hover:text-blue-600">{site.poc_phone}</a>
                  </div>
                )}
                {site.poc_email && (
                  <div className="flex items-center gap-2 text-xs text-gray-700">
                    <Mail className="w-3.5 h-3.5 text-gray-400" />
                    <a href={`mailto:${site.poc_email}`} className="hover:text-blue-600 truncate">{site.poc_email}</a>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-gray-400 text-center py-3">No contact info on file.</p>
            )}
          </Card>

        </div>

        {/* ── NOC-only: Technical Details ── */}
        {isNOC && (
          <Card title="Technical Details" icon={Radio}>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                ["Device Model", site.device_model],
                ["Serial", site.device_serial],
                ["Firmware", site.firmware_version],
                ["Container", site.container_version],
                ["CSA Model", site.csa_model],
                ["Carrier", site.carrier],
                ["Network", site.network_tech],
                ["Signal", site.signal_dbm ? `${site.signal_dbm} dBm` : null],
                ["Heartbeat Int.", site.heartbeat_interval ? `${site.heartbeat_interval}s` : null],
                ["Uptime", site.uptime_percent != null ? `${site.uptime_percent.toFixed(1)}%` : null],
                ["Kit Type", site.kit_type],
                ["Service Class", site.service_class],
              ].filter(([, v]) => v).map(([label, value]) => (
                <div key={label} className="bg-gray-50 rounded-lg px-3 py-2">
                  <div className="text-[10px] text-gray-400 uppercase tracking-wide">{label}</div>
                  <div className="text-xs font-medium text-gray-700 mt-0.5 font-mono">{value}</div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* ── Site Notes ── */}
        {site.notes && (
          <Card title="Notes" icon={FileText}>
            <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-line">{site.notes}</p>
          </Card>
        )}

      </div>
    </PageWrapper>
  );
}
