/**
 * Device-class display manifest (Phase A — UI-only).
 *
 * Single source of truth for *which fields to surface in the primary
 * UI* for each device class.  Does **not** change the database — every
 * underlying column still exists and is still editable in the
 * Admin/SuperAdmin form.  This module only affects how a list cell
 * or detail card decides what to show by default.
 *
 * The current goal is to stop Napco / StarLink / SLELTE devices —
 * which are manually-verified, non-API endpoints — from displaying
 * SIM/IMEI/carrier signal as if they were live cellular gateways.
 * Those fields move into the "collapsed / technical details" bucket.
 *
 * Returned shape:
 *   {
 *     class: "napco" | "starlink" | "slelte" | "cellular" | "ata" | "generic",
 *     primary:    Set<string>,   // fields safe to surface in primary UI
 *     collapsed:  Set<string>,   // exists but should be hidden / collapsed
 *     liveTelemetry: boolean,    // whether live signal/heartbeat is meaningful
 *     manualVerification: boolean, // class uses manual portal verification
 *   }
 *
 * Helper functions:
 *   - classifyDevice(device): returns the manifest for a device row
 *   - isFieldPrimary(device, fieldName): convenience boolean
 *   - shouldHide(device, fieldName): convenience boolean — primary UIs
 *       should suppress the field entirely (not even in a collapsed
 *       section).  Currently always false; collapsed fields stay
 *       reachable in "Technical details" disclosures.
 */

// Field name constants — keep aligned with the Device model on the
// backend (api/app/models/device.py) and the form fields in
// web/src/components/DeviceFormModal.jsx.
const FIELDS = {
  STARLINK_ID: "starlink_id",
  SERIAL_NUMBER: "serial_number",
  MODEL: "model",
  MANUFACTURER: "manufacturer",
  NOTES: "notes",
  SITE: "site_id",
  CUSTOMER: "customer_id",
  ROLE: "device_type",
  STATUS: "status",
  ACTIVATED_AT: "activated_at",
  // Cellular-only — primary for cellular, collapsed for manual classes.
  IMEI: "imei",
  ICCID: "iccid",
  MSISDN: "msisdn",
  CARRIER: "carrier",
  NETWORK_STATUS: "network_status",
  SIGNAL: "signal_dbm",
  IMSI: "imsi",
  SIM_ID: "sim_id",
  DATA_USAGE_MB: "data_usage_mb",
  LAST_HEARTBEAT: "last_heartbeat",
  TELEMETRY_SOURCE: "telemetry_source",
  // ATA / SIP-only.
  MAC_ADDRESS: "mac_address",
};

// Manual-verification classes share a single visibility manifest.
// Order matters for ``classifyDevice`` — Napco / SLELTE detection
// runs before the generic StarLink detection so a Napco device that
// also happens to store a StarLink id reads as Napco.
const MANUAL_VERIFICATION_CLASSES = new Set(["napco", "starlink", "slelte"]);

const MANUAL_VERIFICATION_PRIMARY = new Set([
  FIELDS.STARLINK_ID,
  FIELDS.SERIAL_NUMBER,
  FIELDS.MODEL,
  FIELDS.MANUFACTURER,
  FIELDS.SITE,
  FIELDS.CUSTOMER,
  FIELDS.ROLE,
  FIELDS.STATUS,
  FIELDS.NOTES,
  FIELDS.ACTIVATED_AT,
]);

const MANUAL_VERIFICATION_COLLAPSED = new Set([
  FIELDS.IMEI,
  FIELDS.ICCID,
  FIELDS.MSISDN,
  FIELDS.CARRIER,
  FIELDS.NETWORK_STATUS,
  FIELDS.SIGNAL,
  FIELDS.IMSI,
  FIELDS.SIM_ID,
  FIELDS.DATA_USAGE_MB,
  FIELDS.LAST_HEARTBEAT,
  FIELDS.TELEMETRY_SOURCE,
]);

const CELLULAR_PRIMARY = new Set([
  FIELDS.IMEI,
  FIELDS.ICCID,
  FIELDS.MSISDN,
  FIELDS.CARRIER,
  FIELDS.NETWORK_STATUS,
  FIELDS.SIGNAL,
  FIELDS.MODEL,
  FIELDS.MANUFACTURER,
  FIELDS.SITE,
  FIELDS.STATUS,
  FIELDS.LAST_HEARTBEAT,
  FIELDS.ROLE,
  FIELDS.NOTES,
]);

const ATA_PRIMARY = new Set([
  FIELDS.MAC_ADDRESS,
  FIELDS.MODEL,
  FIELDS.MANUFACTURER,
  FIELDS.SITE,
  FIELDS.STATUS,
  FIELDS.ROLE,
  FIELDS.NOTES,
]);

function normalize(s) {
  return (s || "").toString().toLowerCase().trim();
}

/**
 * Classify a device row by inspecting manufacturer / model / device_type
 * / identifier_type.  The check is deliberately fuzzy because the
 * source data spans CSV imports, hand-entered records, and Zoho sync.
 */
export function classifyDevice(device = {}) {
  const mfr = normalize(device.manufacturer);
  const model = normalize(device.model);
  const dtype = normalize(device.device_type);
  const idType = normalize(device.identifier_type);
  const haystack = `${mfr} ${model} ${dtype} ${idType}`;

  if (haystack.includes("napco")) return buildManifest("napco");
  if (haystack.includes("slelte") || haystack.includes("sl-elte") || haystack.includes("sl elte")) {
    return buildManifest("slelte");
  }
  if (
    haystack.includes("starlink")
    || idType === "starlink"
    || (device.starlink_id && !device.imei && !device.iccid)
  ) {
    return buildManifest("starlink");
  }
  if (idType === "ata" || haystack.includes(" ata") || haystack.startsWith("ata")) {
    return buildManifest("ata");
  }
  if (idType === "cellular" || device.iccid || device.imei || device.msisdn) {
    return buildManifest("cellular");
  }
  return buildManifest("generic");
}

function buildManifest(cls) {
  if (MANUAL_VERIFICATION_CLASSES.has(cls)) {
    return {
      class: cls,
      primary: MANUAL_VERIFICATION_PRIMARY,
      collapsed: MANUAL_VERIFICATION_COLLAPSED,
      liveTelemetry: false,
      manualVerification: true,
    };
  }
  if (cls === "cellular") {
    return {
      class: cls,
      primary: CELLULAR_PRIMARY,
      collapsed: new Set([FIELDS.IMSI, FIELDS.SIM_ID, FIELDS.DATA_USAGE_MB]),
      liveTelemetry: true,
      manualVerification: false,
    };
  }
  if (cls === "ata") {
    return {
      class: cls,
      primary: ATA_PRIMARY,
      collapsed: new Set([
        FIELDS.IMEI, FIELDS.ICCID, FIELDS.MSISDN, FIELDS.CARRIER,
        FIELDS.SIGNAL, FIELDS.STARLINK_ID,
      ]),
      liveTelemetry: false,
      manualVerification: false,
    };
  }
  // Generic / unknown — be permissive.  All non-cellular-specific
  // fields are primary; cellular fields stay collapsed so a record
  // missing classification still doesn't surface IMEI in a card.
  return {
    class: "generic",
    primary: new Set([
      FIELDS.MODEL, FIELDS.MANUFACTURER, FIELDS.SERIAL_NUMBER, FIELDS.SITE,
      FIELDS.CUSTOMER, FIELDS.STATUS, FIELDS.ROLE, FIELDS.NOTES,
    ]),
    collapsed: new Set([
      FIELDS.IMEI, FIELDS.ICCID, FIELDS.MSISDN, FIELDS.CARRIER,
      FIELDS.SIGNAL, FIELDS.NETWORK_STATUS, FIELDS.IMSI, FIELDS.SIM_ID,
    ]),
    liveTelemetry: false,
    manualVerification: false,
  };
}

export function isFieldPrimary(device, fieldName) {
  return classifyDevice(device).primary.has(fieldName);
}

export function isFieldCollapsed(device, fieldName) {
  return classifyDevice(device).collapsed.has(fieldName);
}

/**
 * Convenience used by list-view cells: should this row's identifier
 * cell prefer the StarLink/serial path (true for Napco/StarLink/SLELTE)
 * or the IMEI/ICCID path (cellular)?
 */
export function preferManualIdentifier(device) {
  return classifyDevice(device).manualVerification;
}

/**
 * Human-readable label for the class, suitable for a small chip.
 */
export function deviceClassLabel(device) {
  const cls = classifyDevice(device).class;
  switch (cls) {
    case "napco": return "Napco";
    case "starlink": return "StarLink";
    case "slelte": return "SLELTE";
    case "cellular": return "Cellular";
    case "ata": return "ATA";
    default: return "Generic";
  }
}

export { FIELDS as DEVICE_FIELDS };
