import { useState } from "react";
import { X, MapPin, Phone, Mail, User, ChevronDown, ChevronUp } from "lucide-react";
import { Incident } from "@/api/entities";
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

          <Section title="Health Snapshot">
            <HealthSnapshot site={site} />
          </Section>

          <Section title="Incident Status" defaultOpen={true}>
            <IncidentStatus site={site} refreshKey={timelineKey} />
          </Section>

          <Section title="Action Timeline">
            <ActionTimeline site={site} refreshKey={timelineKey} />
          </Section>

          <Section title="Contact / POC" defaultOpen={false}>
            <div className="space-y-2">
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
          </Section>

          <Section title="E911 Address" defaultOpen={false}>
            <div className="flex items-start gap-2">
              <MapPin className="w-3.5 h-3.5 text-gray-400 mt-0.5 flex-shrink-0" />
              <div className="text-xs text-gray-700">
                <div>{site.e911_street || "—"}</div>
                <div>{site.e911_city}, {site.e911_state} {site.e911_zip}</div>
              </div>
            </div>
            {site.notes && (
              <div className="mt-2 text-xs text-gray-400 italic leading-relaxed">{site.notes}</div>
            )}
          </Section>

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