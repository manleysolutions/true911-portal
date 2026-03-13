import { useState, useEffect, useCallback } from "react";
import { X, MapPin, Phone, Mail, User, ChevronDown, ChevronUp, Pencil, Save, Loader2, Navigation, Crosshair, AlertTriangle, Cpu, Disc3, PhoneCall, ShieldCheck, Video, MessageSquare, Mic, CheckCircle2, XCircle, HelpCircle } from "lucide-react";
import { Incident, Site } from "@/api/entities";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import { uid } from "./actions";
import { useAuth } from "@/contexts/AuthContext";
import DrawerHeader from "./drawer/DrawerHeader";
import QuickActions from "./drawer/QuickActions";
import HealthSnapshot from "./drawer/HealthSnapshot";
import ActionTimeline from "./drawer/ActionTimeline";
import IncidentStatus from "./drawer/IncidentStatus";
import E911ChangeFlow from "./drawer/E911ChangeFlow";
import OpsSummary from "./drawer/OpsSummary";

function Section({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mb-1 border-b border-gray-50 last:border-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between py-3 text-left"
      >
        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400">{title}</span>
        {open ? <ChevronUp className="w-3.5 h-3.5 text-gray-300" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-300" />}
      </button>
      {open && <div className="pb-3">{children}</div>}
    </div>
  );
}

function ContactPOCSection({ site, onSiteUpdated }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pocName, setPocName] = useState(site.poc_name || "");
  const [pocPhone, setPocPhone] = useState(site.poc_phone || "");
  const [pocEmail, setPocEmail] = useState(site.poc_email || "");

  const handleSave = async () => {
    setSaving(true);
    try {
      await Site.update(site.id, { poc_name: pocName, poc_phone: pocPhone, poc_email: pocEmail });
      toast.success("Contact info updated");
      setEditing(false);
      onSiteUpdated?.();
    } catch (err) {
      toast.error(err?.message || "Failed to update contact info");
    }
    setSaving(false);
  };

  const handleCancel = () => {
    setPocName(site.poc_name || "");
    setPocPhone(site.poc_phone || "");
    setPocEmail(site.poc_email || "");
    setEditing(false);
  };

  return (
    <Section title="Contact / POC" defaultOpen={false}>
      {editing ? (
        <div className="space-y-2.5">
          <div>
            <label className="text-[10px] font-medium text-gray-500 mb-0.5 block">Name</label>
            <input value={pocName} onChange={e => setPocName(e.target.value)} className="w-full px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" placeholder="Contact name" />
          </div>
          <div>
            <label className="text-[10px] font-medium text-gray-500 mb-0.5 block">Phone</label>
            <input value={pocPhone} onChange={e => setPocPhone(e.target.value)} className="w-full px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" placeholder="(555) 123-4567" />
          </div>
          <div>
            <label className="text-[10px] font-medium text-gray-500 mb-0.5 block">Email</label>
            <input value={pocEmail} onChange={e => setPocEmail(e.target.value)} className="w-full px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" placeholder="contact@example.com" />
          </div>
          <div className="flex gap-2 pt-1">
            <button onClick={handleSave} disabled={saving} className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-xs font-medium rounded-lg transition-colors">
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {saving ? "Saving..." : "Save"}
            </button>
            <button onClick={handleCancel} disabled={saving} className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="space-y-2 flex-1">
              {site.poc_name && (
                <div className="flex items-center gap-2 text-xs text-gray-700">
                  <User className="w-3.5 h-3.5 text-gray-400" />
                  <span>{site.poc_name}</span>
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
              {!site.poc_name && !site.poc_phone && !site.poc_email && (
                <div className="text-xs text-gray-400">No contact info on file.</div>
              )}
            </div>
            <button onClick={() => setEditing(true)} title="Edit contact info" className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
              <Pencil className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </Section>
  );
}

function E911CoordsSection({ site, onSiteUpdated }) {
  const { can } = useAuth();
  const isAdmin = can("VIEW_ADMIN");
  const [geocoding, setGeocoding] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [manualLat, setManualLat] = useState(site.lat != null ? String(site.lat) : "");
  const [manualLng, setManualLng] = useState(site.lng != null ? String(site.lng) : "");
  const [savingCoords, setSavingCoords] = useState(false);

  const hasE911 = !!(site.e911_street || site.e911_city || site.e911_state || site.e911_zip);

  const handleGeocode = async () => {
    setGeocoding(true);
    try {
      await Site.geocode(site.id);
      toast.success("Coordinates resolved from E911 address");
      onSiteUpdated?.();
    } catch (err) {
      toast.error(err?.message || "Geocoding failed");
    }
    setGeocoding(false);
  };

  const handleSaveCoords = async () => {
    const lat = parseFloat(manualLat);
    const lng = parseFloat(manualLng);
    if (isNaN(lat) || isNaN(lng)) {
      toast.error("Enter valid numeric coordinates");
      return;
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      toast.error("Coordinates out of range");
      return;
    }
    setSavingCoords(true);
    try {
      await Site.update(site.id, { lat, lng });
      toast.success("Coordinates saved");
      setShowManual(false);
      onSiteUpdated?.();
    } catch (err) {
      toast.error(err?.message || "Failed to save coordinates");
    }
    setSavingCoords(false);
  };

  return (
    <Section title="E911 Address" defaultOpen={false}>
      {/* Missing coords badge */}
      {!site.has_coords && (
        <div className="flex items-center gap-1.5 mb-2.5 px-2 py-1.5 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
          <span className="text-[10px] font-medium text-amber-700">Missing coordinates — site won't appear on map</span>
        </div>
      )}

      <div className="flex items-start gap-2">
        <MapPin className="w-3.5 h-3.5 text-gray-400 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-gray-700">
          <div>{site.e911_street || "—"}</div>
          <div>{site.e911_city}, {site.e911_state} {site.e911_zip}</div>
        </div>
      </div>

      {/* Coordinates display */}
      {site.has_coords && (
        <div className="mt-2 flex items-center gap-1.5">
          <Crosshair className="w-3 h-3 text-gray-400" />
          <span className="text-[10px] font-mono text-gray-500">{site.lat?.toFixed(4)}, {site.lng?.toFixed(4)}</span>
        </div>
      )}

      {/* Admin actions for missing coords */}
      {isAdmin && !site.has_coords && (
        <div className="mt-3 space-y-2">
          <div className="flex gap-1.5">
            {hasE911 && (
              <button
                onClick={handleGeocode}
                disabled={geocoding}
                className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-100 disabled:opacity-60 transition-colors"
              >
                {geocoding ? <Loader2 className="w-3 h-3 animate-spin" /> : <Navigation className="w-3 h-3" />}
                Geocode from Address
              </button>
            )}
            <button
              onClick={() => setShowManual(!showManual)}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium bg-gray-50 text-gray-700 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <Crosshair className="w-3 h-3" />
              Set Manually
            </button>
          </div>

          {showManual && (
            <div className="bg-gray-50 rounded-lg p-2.5 space-y-2">
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="text-[9px] font-medium text-gray-500 mb-0.5 block">Latitude</label>
                  <input
                    type="number"
                    step="any"
                    value={manualLat}
                    onChange={e => setManualLat(e.target.value)}
                    placeholder="32.7767"
                    className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-400"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-[9px] font-medium text-gray-500 mb-0.5 block">Longitude</label>
                  <input
                    type="number"
                    step="any"
                    value={manualLng}
                    onChange={e => setManualLng(e.target.value)}
                    placeholder="-96.7970"
                    className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-400"
                  />
                </div>
              </div>
              <div className="flex gap-1.5">
                <button
                  onClick={handleSaveCoords}
                  disabled={savingCoords}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-60 transition-colors"
                >
                  {savingCoords ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  Save
                </button>
                <button
                  onClick={() => setShowManual(false)}
                  className="px-2.5 py-1.5 text-[10px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {site.notes && (
        <div className="mt-2 text-xs text-gray-400 italic leading-relaxed">{site.notes}</div>
      )}
    </Section>
  );
}

function InfrastructureSection({ site }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchInfra = useCallback(async () => {
    try {
      const result = await apiFetch(`/sites/${site.id}/infrastructure`);
      setData(result);
    } catch { /* endpoint may not exist yet */ }
    setLoading(false);
  }, [site.id]);

  useEffect(() => { fetchInfra(); }, [fetchInfra]);

  if (loading) {
    return (
      <Section title="Infrastructure" defaultOpen={true}>
        <div className="flex items-center gap-2 text-xs text-gray-400 py-2">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading...
        </div>
      </Section>
    );
  }

  if (!data) return null;

  const { devices, sims, lines, counts, e911 } = data;

  return (
    <Section title="Infrastructure" defaultOpen={true}>
      {/* E911 warning */}
      {e911?.warning && (
        <div className="flex items-center gap-1.5 mb-3 px-2.5 py-2 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
          <span className="text-[10px] font-medium text-amber-700">E911 address needed — infrastructure assigned but no validated address on file.</span>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <Cpu className="w-3 h-3 text-gray-400" />
            <span className="text-lg font-bold text-gray-900">{counts.devices}</span>
          </div>
          <div className="text-[10px] text-gray-500">Devices</div>
        </div>
        <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <Disc3 className="w-3 h-3 text-gray-400" />
            <span className="text-lg font-bold text-gray-900">{counts.sims}</span>
          </div>
          <div className="text-[10px] text-gray-500">SIMs</div>
        </div>
        <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <PhoneCall className="w-3 h-3 text-gray-400" />
            <span className="text-lg font-bold text-gray-900">{counts.lines}</span>
          </div>
          <div className="text-[10px] text-gray-500">Lines</div>
        </div>
      </div>

      {/* Devices list */}
      {devices.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Devices</div>
          <div className="space-y-1">
            {devices.map(d => (
              <div key={d.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-2.5 py-1.5">
                <div>
                  <div className="text-xs font-mono text-gray-700">{d.device_id}</div>
                  <div className="text-[10px] text-gray-500">{d.device_type || d.model || "—"}</div>
                </div>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${
                  d.status === "active" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                  d.status === "provisioning" ? "bg-blue-50 text-blue-700 border-blue-200" :
                  "bg-gray-100 text-gray-500 border-gray-200"
                }`}>{d.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SIMs list */}
      {sims.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">SIMs</div>
          <div className="space-y-1">
            {sims.map(s => (
              <div key={s.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-2.5 py-1.5">
                <div>
                  <div className="text-xs font-mono text-gray-700">{s.iccid}</div>
                  <div className="text-[10px] text-gray-500">{s.carrier}{s.msisdn ? ` | ${s.msisdn}` : ""}</div>
                </div>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${
                  s.status === "active" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                  s.status === "inventory" ? "bg-blue-50 text-blue-700 border-blue-200" :
                  "bg-gray-100 text-gray-500 border-gray-200"
                }`}>{s.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Lines list */}
      {lines.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Lines</div>
          <div className="space-y-1">
            {lines.map(l => (
              <div key={l.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-2.5 py-1.5">
                <div>
                  <div className="text-xs text-gray-700">{l.did || l.line_id}</div>
                  <div className="text-[10px] text-gray-500">{l.provider} | {l.protocol}</div>
                </div>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${
                  l.status === "active" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                  "bg-gray-100 text-gray-500 border-gray-200"
                }`}>{l.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {counts.devices === 0 && counts.sims === 0 && counts.lines === 0 && (
        <div className="text-xs text-gray-400 text-center py-3">No infrastructure assigned to this site yet.</div>
      )}
    </Section>
  );
}


const COMPLIANCE_BADGE = {
  compliant: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", icon: CheckCircle2, label: "Compliant" },
  partially_compliant: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", icon: AlertTriangle, label: "Partially Compliant" },
  review_required: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", icon: HelpCircle, label: "Review Required" },
  non_compliant: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200", icon: XCircle, label: "Non-Compliant" },
  no_units: { bg: "bg-gray-50", text: "text-gray-500", border: "border-gray-200", icon: HelpCircle, label: "No Units" },
};

function ComplianceSection({ site }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchCompliance = useCallback(async () => {
    try {
      const result = await apiFetch(`/service-units/site/${site.site_id}/compliance`);
      setData(result);
    } catch { /* endpoint may not be deployed yet */ }
    setLoading(false);
  }, [site.site_id]);

  useEffect(() => { fetchCompliance(); }, [fetchCompliance]);

  if (loading) {
    return (
      <Section title="Compliance" defaultOpen={true}>
        <div className="flex items-center gap-2 text-xs text-gray-400 py-2">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading...
        </div>
      </Section>
    );
  }

  if (!data) return null;

  const badge = COMPLIANCE_BADGE[data.status] || COMPLIANCE_BADGE.no_units;
  const BadgeIcon = badge.icon;

  return (
    <Section title="Compliance" defaultOpen={true}>
      {/* Overall status badge */}
      <div className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border mb-3 ${badge.bg} ${badge.border}`}>
        <BadgeIcon className={`w-4 h-4 ${badge.text} flex-shrink-0`} />
        <div>
          <div className={`text-xs font-bold ${badge.text}`}>{badge.label}</div>
          <div className="text-[10px] text-gray-500">{data.summary}</div>
        </div>
      </div>

      {/* Capability summary */}
      {data.unit_count > 0 && (
        <div className="grid grid-cols-2 gap-1.5 mb-3">
          <div className="flex items-center gap-1.5 text-[10px]">
            <Mic className="w-3 h-3 text-emerald-500" />
            <span className="text-gray-600">Voice</span>
            <CheckCircle2 className="w-3 h-3 text-emerald-400 ml-auto" />
          </div>
          <div className="flex items-center gap-1.5 text-[10px]">
            <Video className="w-3 h-3 text-gray-400" />
            <span className="text-gray-600">Video</span>
            {data.status === "no_units" ? null : (
              <span className="ml-auto text-[9px] text-gray-400">varies</span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-[10px]">
            <MessageSquare className="w-3 h-3 text-gray-400" />
            <span className="text-gray-600">Text/Visual</span>
            <span className="ml-auto text-[9px] text-gray-400">varies</span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px]">
            <MapPin className="w-3 h-3 text-gray-400" />
            <span className="text-gray-600">E911</span>
            {data.e911?.has_address ? (
              <CheckCircle2 className="w-3 h-3 text-emerald-400 ml-auto" />
            ) : (
              <AlertTriangle className="w-3 h-3 text-amber-400 ml-auto" />
            )}
          </div>
        </div>
      )}

      {/* Warnings */}
      {data.warnings?.length > 0 && (
        <div className="space-y-1.5">
          {data.warnings.slice(0, 5).map((w, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[10px] text-amber-700 bg-amber-50/50 rounded px-2 py-1.5">
              <AlertTriangle className="w-3 h-3 text-amber-400 flex-shrink-0 mt-0.5" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Disclaimer */}
      <div className="mt-3 text-[9px] text-gray-400 italic">
        Operational guidance only — not a legal compliance determination.
      </div>
    </Section>
  );
}


export default function SiteDrawer({ site, onClose, onSiteUpdated }) {
  const [lastActionResult, setLastActionResult] = useState(null);
  const [showE911, setShowE911] = useState(false);
  const [showCreateIncident, setShowCreateIncident] = useState(false);
  const [timelineKey, setTimelineKey] = useState(0);

  if (!site) return null;

  const handleSiteUpdated = () => {
    setTimelineKey(k => k + 1);
    onSiteUpdated?.();
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40 lg:hidden" onClick={onClose} />
      <div className="fixed top-0 right-0 h-full w-full max-w-[400px] bg-white shadow-2xl z-50 flex flex-col border-l border-gray-200">
        <DrawerHeader site={site} lastActionResult={lastActionResult} onClose={onClose} />

        <div className="flex-1 overflow-y-auto px-5 py-2">
          {/* Ops Summary */}
          <div className="py-3 border-b border-gray-50">
            <OpsSummary site={site} />
          </div>

          {/* Quick Actions */}
          <div className="py-3 border-b border-gray-50">
            <QuickActions
              site={site}
              onSiteUpdated={handleSiteUpdated}
              onOpenE911={() => setShowE911(true)}
              onCreateIncident={() => setShowCreateIncident(true)}
            />
          </div>

          <InfrastructureSection site={site} />

          <ComplianceSection site={site} />

          <Section title="Health Snapshot">
            <HealthSnapshot site={site} />
          </Section>

          <Section title="Incident Status" defaultOpen={true}>
            <IncidentStatus site={site} refreshKey={timelineKey} />
          </Section>

          <Section title="Action Timeline">
            <ActionTimeline site={site} refreshKey={timelineKey} />
          </Section>

          <ContactPOCSection site={site} onSiteUpdated={handleSiteUpdated} />

          <E911CoordsSection site={site} onSiteUpdated={handleSiteUpdated} />

          <Section title="Device Info" defaultOpen={false}>
            <div className="space-y-1.5">
              {[
                ["Model", site.device_model],
                ["Serial", site.device_serial],
                ["Firmware", site.device_firmware],
                ["Container", site.container_version],
              ].filter(([, v]) => v).map(([label, value]) => (
                <div key={label} className="flex justify-between items-center py-1 border-b border-gray-50 last:border-0">
                  <span className="text-xs text-gray-500">{label}</span>
                  <span className="text-xs font-mono text-gray-700">{value}</span>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </div>

      {/* E911 Change Modal */}
      {showE911 && (
        <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4 text-purple-600" />
                <h3 className="font-semibold text-gray-900 text-sm">Update E911 Address</h3>
              </div>
              <button onClick={() => setShowE911(false)} className="p-1 rounded hover:bg-gray-100 text-gray-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <E911ChangeFlow
              site={site}
              onClose={() => setShowE911(false)}
              onSiteUpdated={handleSiteUpdated}
            />
          </div>
        </div>
      )}

      {/* Create Incident Modal */}
      {showCreateIncident && (
        <CreateIncidentModal
          site={site}
          onClose={() => setShowCreateIncident(false)}
          onCreated={handleSiteUpdated}
        />
      )}
    </>
  );
}

function CreateIncidentModal({ site, onClose, onCreated }) {
  const { user } = useAuth();
  const [severity, setSeverity] = useState("warning");
  const [summary, setSummary] = useState(`${site.site_name}: `);
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    setLoading(true);
    await Incident.create({
      incident_id: uid("INC"),
      tenant_id: site.tenant_id,
      site_id: site.site_id,
      opened_at: new Date().toISOString(),
      severity,
      status: "open",
      summary,
      created_by: user.email,
    });
    toast.success("Incident created.");
    setLoading(false);
    onCreated?.();
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 text-sm">Create Incident</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="bg-gray-50 rounded-lg p-2.5 text-xs text-gray-600">
          Site: <span className="font-medium text-gray-900">{site.site_name}</span>
          <span className="text-gray-400 ml-1">({site.site_id})</span>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1.5">Severity</label>
          <div className="flex gap-2">
            {["critical", "warning", "info"].map(s => (
              <button
                key={s}
                onClick={() => setSeverity(s)}
                className={`flex-1 py-2 rounded-lg text-xs font-semibold border transition-colors ${
                  severity === s
                    ? s === "critical" ? "bg-red-600 text-white border-red-600"
                      : s === "warning" ? "bg-amber-500 text-white border-amber-500"
                      : "bg-blue-500 text-white border-blue-500"
                    : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
                }`}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1.5">Summary</label>
          <textarea
            value={summary}
            onChange={e => setSummary(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500 resize-none"
          />
        </div>

        <div className="flex gap-2">
          <button onClick={onClose} className="flex-1 px-3 py-2 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 font-medium">Cancel</button>
          <button
            onClick={handleCreate}
            disabled={!summary.trim() || loading}
            className="flex-1 px-3 py-2 text-xs bg-red-600 text-white rounded-lg hover:bg-red-700 font-semibold disabled:opacity-60"
          >
            {loading ? "Creating..." : "Create Incident"}
          </button>
        </div>
      </div>
    </div>
  );
}