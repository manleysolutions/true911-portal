import { useState, useEffect } from "react";
import {
  X,
  MapPin,
  Phone,
  Building2,
  Cpu,
  Activity,
  FileText,
  Loader2,
} from "lucide-react";
import { Device, Incident } from "@/api/entities";
import CustomerStatusBadge from "@/components/ui/CustomerStatusBadge";
import { useAuth } from "@/contexts/AuthContext";
import { isCustomerRole } from "@/lib/attention";

/**
 * Customer-facing right-side drawer for a single site.
 *
 * Renders ONLY for customer roles (User / Manager).  Internal /
 * operations roles (SuperAdmin, Admin, DataSteward, DataEntry)
 * continue to see the existing internal SiteDrawer or SiteDetail
 * page — this component is purely additive.
 *
 * Six sections, calm enterprise styling, inventory + telemetry
 * language (never "monitoring" / "actively monitored").  Soft
 * placeholders are used whenever data is absent so no section ever
 * shows a blank field.
 */
export default function CustomerSiteDetailDrawer({ site, onClose }) {
  const { user } = useAuth();

  const [devices, setDevices] = useState([]);
  const [openIncidents, setOpenIncidents] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [loadingIncidents, setLoadingIncidents] = useState(false);

  // ── Data fetch on open ────────────────────────────────────────
  // Hooks must run on every render; the early-return below is *after*
  // every hook call.  See React rules-of-hooks.
  useEffect(() => {
    if (!site?.site_id) return undefined;
    let cancelled = false;

    setLoadingDevices(true);
    Device.filter({ site_id: site.site_id })
      .then((rows) => {
        if (cancelled) return;
        // Defensive: client-side filter in case the backend ignores
        // the site_id query param.  Either way the drawer ends up
        // with only devices that actually belong to this site.
        const arr = Array.isArray(rows) ? rows : [];
        setDevices(arr.filter((d) => d.site_id === site.site_id));
      })
      .catch(() => { if (!cancelled) setDevices([]); })
      .finally(() => { if (!cancelled) setLoadingDevices(false); });

    setLoadingIncidents(true);
    Incident.filter({ site_id: site.site_id })
      .then((rows) => {
        if (cancelled) return;
        const arr = Array.isArray(rows) ? rows : [];
        const open = arr.filter(
          (i) => i.site_id === site.site_id &&
                 !["resolved", "dismissed", "closed"].includes((i.status || "").toLowerCase()),
        );
        setOpenIncidents(open);
      })
      .catch(() => { if (!cancelled) setOpenIncidents([]); })
      .finally(() => { if (!cancelled) setLoadingIncidents(false); });

    return () => { cancelled = true; };
  }, [site?.site_id]);

  // Defensive role guard — caller should already gate this.
  if (!site || !isCustomerRole(user?.role)) return null;

  const primaryDevice = devices[0] || null;

  return (
    <>
      {/* Overlay (closes on click) */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <aside
        role="dialog"
        aria-label={`Details for ${site.site_name || site.site_id}`}
        className="fixed top-0 right-0 h-full w-full sm:max-w-md md:max-w-lg bg-white shadow-2xl z-50 flex flex-col"
      >
        {/* Header — sticky so the close button is always reachable */}
        <header className="sticky top-0 bg-white border-b border-slate-200 px-5 sm:px-6 py-4 flex items-start justify-between gap-3 z-10">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-slate-900 truncate">
              {site.site_name || "Unnamed location"}
            </h2>
            <p className="text-xs text-slate-500 font-mono mt-0.5 truncate">
              {site.site_id}
            </p>
            <div className="mt-2">
              <CustomerStatusBadge site={site} role={user.role} />
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors flex-shrink-0"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
          <Section title="Location Summary" icon={Building2}>
            <Field label="Site name" value={site.site_name} />
            <Field label="Site ID" value={site.site_id} monospace />
            <Field label="Customer" value={site.customer_name} />
            <Field label="Service class" value={site.service_class} />
            <Field label="Endpoint type" value={site.endpoint_type || site.kit_type} />
          </Section>

          <Section title="E911 Information" icon={MapPin}>
            <Field label="Street" value={site.e911_street} />
            <Field label="City" value={site.e911_city} />
            <Field label="State" value={site.e911_state} />
            <Field label="ZIP" value={site.e911_zip} />
            <Field label="Address notes" value={site.address_notes} />
          </Section>

          <Section title="Installed Equipment" icon={Cpu}>
            {loadingDevices ? (
              <LoadingRow label="Loading device details" />
            ) : (
              <>
                <Field
                  label="Device model"
                  value={primaryDevice?.model || site.device_model}
                />
                <Field
                  label="Vendor"
                  value={primaryDevice?.manufacturer}
                  fallback={PENDING_INTEGRATION}
                />
                <Field
                  label="Carrier"
                  value={primaryDevice?.carrier || site.carrier}
                  fallback={PENDING_INTEGRATION}
                />
                <Field label="Voice provider" value={site.voice_provider} fallback={PENDING_INTEGRATION} />
                <Field label="Kit type" value={site.kit_type} />
                <Field
                  label="ICCID"
                  value={maskIdentifier(primaryDevice?.iccid)}
                  fallback={PENDING_INTEGRATION}
                  monospace
                />
                <Field
                  label="IMEI"
                  value={maskIdentifier(primaryDevice?.imei)}
                  fallback={PENDING_INTEGRATION}
                  monospace
                />
                <Field
                  label="Device ID"
                  value={primaryDevice?.device_id}
                  fallback={PENDING_INTEGRATION}
                  monospace
                />
                {devices.length > 1 && (
                  <p className="text-[11px] text-slate-400 pt-1">
                    +{devices.length - 1} additional device
                    {devices.length - 1 > 1 ? "s" : ""} registered at this location.
                  </p>
                )}
              </>
            )}
          </Section>

          <Section title="Connectivity & Activity" icon={Activity}>
            <Field
              label="Connectivity source"
              value={site.network_tech}
              fallback={PENDING_INTEGRATION}
            />
            <Field
              label="Last inventory sync"
              value={formatTimestamp(site.last_portal_sync)}
              fallback={NOT_CONFIGURED}
            />
            <Field
              label="Last carrier update"
              value={formatTimestamp(primaryDevice?.vola_last_sync)}
              fallback={NO_TELEMETRY}
            />
            <Field
              label="Last device telemetry"
              value={formatTimestamp(primaryDevice?.last_heartbeat || site.last_checkin)}
              fallback={NO_TELEMETRY}
            />
            <p className="text-[11px] text-slate-400 leading-relaxed pt-1">
              Telemetry timestamps appear only when a device has reported to True911.
              A device may still be operational on site even when telemetry is absent.
            </p>
          </Section>

          <Section title="Contacts" icon={Phone}>
            <Field label="Site contact" value={site.poc_name} />
            <Field label="Phone" value={site.poc_phone} />
            <Field label="Email" value={site.poc_email} />
            <Field label="Property manager" value={site.property_manager} />
            <Field label="Elevator vendor" value={site.elevator_vendor} />
            <Field label="True911 support" value="support@true911.com" />
          </Section>

          <Section title="Support & Notes" icon={FileText}>
            <Field
              label="Open support tickets"
              value={loadingIncidents ? "—" : String(openIncidents.length)}
            />
            <Field
              label="Last service visit"
              value={formatTimestamp(site.last_service_visit)}
            />
            <Field label="Deployment notes" value={site.notes} />
            <Field label="Install notes" value={site.install_notes} />
          </Section>
        </div>

        {/* Footer — calm contextual reminder */}
        <footer className="border-t border-slate-200 bg-slate-50 px-5 sm:px-6 py-3">
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Inventory snapshot · Telemetry shown only when received from devices ·
            True911 does not perform active monitoring unless an explicit integration is in place.
          </p>
        </footer>
      </aside>
    </>
  );
}


// ──────────────────────────────────────────────────────────────────
// Layout primitives
// ──────────────────────────────────────────────────────────────────

function Section({ title, icon: Icon, children }) {
  return (
    <section className="px-5 sm:px-6 py-5">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-slate-400" />
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {title}
        </h3>
      </div>
      <dl className="space-y-2">{children}</dl>
    </section>
  );
}

/**
 * Single label/value row.  If value is empty, render the fallback
 * in a calm slate italic instead of leaving the cell blank.
 */
function Field({ label, value, fallback = NOT_CONFIGURED, monospace = false }) {
  const isEmpty =
    value === null ||
    value === undefined ||
    (typeof value === "string" && value.trim() === "");
  const rendered = isEmpty ? fallback : value;
  const placeholderClass = isEmpty ? "text-slate-400 italic" : "text-slate-900";
  const fontClass = monospace ? "font-mono text-[12.5px]" : "text-sm";
  return (
    <div className="grid grid-cols-3 gap-3 items-baseline">
      <dt className="text-[13px] text-slate-500">{label}</dt>
      <dd className={`col-span-2 ${fontClass} ${placeholderClass} break-words`}>
        {rendered}
      </dd>
    </div>
  );
}

function LoadingRow({ label }) {
  return (
    <div className="flex items-center gap-2 text-[13px] text-slate-400 py-1">
      <Loader2 className="w-3.5 h-3.5 animate-spin" />
      <span>{label}…</span>
    </div>
  );
}


// ──────────────────────────────────────────────────────────────────
// Customer-safe formatting helpers
//
// Kept inline to keep Phase A's diff small — single consumer.  If a
// second customer surface ever needs the same helpers, factor into
// web/src/lib/customerSiteFormat.js then.
// ──────────────────────────────────────────────────────────────────

const NOT_CONFIGURED = "Not yet configured";
const PENDING_INTEGRATION = "Pending integration";
const NO_TELEMETRY = "No live telemetry available yet";

/**
 * Mask a sensitive identifier so only the last `visible` characters
 * are readable.  Returns null for empty input (caller will fall back
 * to the placeholder).
 *
 *   maskIdentifier("8901260123456789012", 4) -> "•••••••••••••••9012"
 */
function maskIdentifier(value, visible = 4) {
  if (value === null || value === undefined) return null;
  const v = String(value).trim();
  if (!v) return null;
  if (v.length <= visible) return v;
  const hiddenLength = Math.max(4, v.length - visible);
  return "•".repeat(hiddenLength) + v.slice(-visible);
}

/**
 * Format an ISO timestamp into a calm, locale-aware string.
 * Returns null on missing / unparseable input so the caller can
 * choose its own fallback (NOT_CONFIGURED vs NO_TELEMETRY).
 */
function formatTimestamp(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
