// Canonical service inventory (#186b, D-023) - machine-readable readiness.
//
// The backend sends `service_inventory` ONLY when the canonical model is enabled
// for the tenant; when it is absent every caller keeps the existing
// "Being finalized by True911" placeholder exactly.  This is INVENTORY truth -
// never "certified", never an E911 statement, never a service or connection
// total.  Probable / unresolved records only ever surface as "being finalized".

export const INVENTORY_PLACEHOLDER = "Being finalized by True911";

export const INVENTORY_STATES = Object.freeze({
  READY: "READY",
  PARTIALLY_READY: "PARTIALLY_READY",
  BEING_FINALIZED: "BEING_FINALIZED",
  NO_SERVICES_ON_RECORD: "NO_SERVICES_ON_RECORD",
});

const FALLBACK_MESSAGES = {
  READY: "Service inventory confirmed by True911",
  PARTIALLY_READY: "Some service inventory is confirmed. Additional records are being finalized by True911.",
  BEING_FINALIZED: INVENTORY_PLACEHOLDER,
  NO_SERVICES_ON_RECORD: "No life-safety services on record",
};

// Portfolio tile: null when the canonical inventory is not enabled (caller keeps
// its placeholder).  Never a service total and never a connection total.
export function portfolioInventoryView(summary) {
  const inv = summary && summary.service_inventory;
  if (!inv) return null;
  const withInventory = (inv.locations_ready || 0) + (inv.locations_partially_ready || 0);
  // location READINESS is the headline - never a service or connection total
  const breakdown = [
    [inv.locations_ready, "ready"],
    [inv.locations_partially_ready, "partially ready"],
    [inv.locations_being_finalized, "being finalized"],
    [inv.locations_no_services_on_record, "no services on record"],
  ].filter(([n]) => n > 0).map(([n, w]) => `${n} ${w}`).join(" · ");
  return {
    value: withInventory
      ? `${withInventory} ${withInventory === 1 ? "location has" : "locations have"} confirmed inventory`
      : INVENTORY_PLACEHOLDER,
    numeric: false,
    pending: !!inv.records_being_finalized || !withInventory,
    detail: breakdown || "Service inventory appears as True911 confirms it",
  };
}

// Location block: null when absent.
export function locationInventoryView(inventory) {
  if (!inventory || !inventory.state) return null;
  const state = INVENTORY_STATES[inventory.state] ? inventory.state : INVENTORY_STATES.BEING_FINALIZED;
  return {
    state,
    message: inventory.message || FALLBACK_MESSAGES[state],
    services: (inventory.ready_services || []).map((s) => ({
      key: s.service_ref,
      label: s.name && s.name !== s.service ? `${s.service} · ${s.name}` : s.service,
      // a requirement, never a provisioned path / number / IP
      paths: s.required_paths > 1 ? `${s.required_paths} required communication paths` : null,
      phone: s.telephone_number || null,
    })),
    pending: state === INVENTORY_STATES.PARTIALLY_READY || state === INVENTORY_STATES.BEING_FINALIZED,
    // the drawer header: readiness language, never a synthetic service / line total
    headline: HEADLINES[state],
    finalizingNote: state === INVENTORY_STATES.PARTIALLY_READY
      ? "Additional service records are being finalized by True911."
      : state === INVENTORY_STATES.BEING_FINALIZED ? "Service records are being finalized by True911." : null,
  };
}

const HEADLINES = {
  READY: "Service inventory confirmed",
  PARTIALLY_READY: "Some service inventory confirmed · additional records being finalized",
  BEING_FINALIZED: "Service inventory being finalized by True911",
  NO_SERVICES_ON_RECORD: "No life-safety services on record",
};
