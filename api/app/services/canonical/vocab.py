"""Closed vocabularies for the canonical model (D-023).

Confidence, approval and lifecycle are three independent axes and are never
collapsed into one another.
"""

# ── confidence: strength of evidence (never self-promoting) ─────────────
CONFIRMED = "CONFIRMED"
PROBABLE = "PROBABLE"
UNRESOLVED = "UNRESOLVED"
CONFIDENCE_RANK = {CONFIRMED: 2, PROBABLE: 1, UNRESOLVED: 0}


def weakest(*levels: str) -> str:
    """The weakest of several confidence levels (evidence is only as strong as
    its weakest required link)."""
    return min(levels, key=lambda c: CONFIDENCE_RANK.get(c, 0)) if levels else UNRESOLVED


# ── approval: the operator's decision ───────────────────────────────────
APPROVAL_NONE = "NONE"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
APPROVALS = (APPROVAL_NONE, APPROVED, REJECTED)

# ── lifecycle (services and assets) ─────────────────────────────────────
CURRENT = "CURRENT"
DECOMMISSIONED = "DECOMMISSIONED"
REPLACED = "REPLACED"
SUSPENDED = "SUSPENDED"
HISTORICAL = "HISTORICAL"
UNKNOWN = "UNKNOWN"
LIFECYCLES = (CURRENT, DECOMMISSIONED, REPLACED, SUSPENDED, HISTORICAL, UNKNOWN)
# lifecycle states that never contribute to CURRENT counts
NOT_CURRENT = (DECOMMISSIONED, REPLACED, SUSPENDED, HISTORICAL)

# lifecycle reasons
REASON_CARRIER_MIGRATION = "CARRIER_MIGRATION"
REASON_OPERATOR = "OPERATOR_DECISION"
REASON_SOURCE_DEACTIVATED = "SOURCE_DEACTIVATED"
REASON_SOURCE_SUSPENDED = "SOURCE_SUSPENDED"
REASON_SOURCE_ACTIVE = "SOURCE_ACTIVE"
REASON_TRUE911_STATUS = "TRUE911_STATUS"
# CURRENT established by independent deployment evidence (below)
REASON_DEPLOYMENT_ACTIVITY = "DEPLOYMENT_ACTIVITY"     # recent source-native activity
REASON_DEPLOYMENT_TELEMETRY = "DEPLOYMENT_TELEMETRY"   # recent True911 heartbeat
# a source says "Active"/"Activated" but nothing shows the equipment deployed:
# lifecycle stays UNKNOWN (an administrative status is never deployment proof)
REASON_ADMIN_STATUS_ONLY = "ADMIN_STATUS_ONLY"

# ── deployment: is the equipment shown to be in service now? ────────────
# Its own axis, never inferred from confidence, approval or an administrative
# status (Zoho "Activated", a True911 or carrier "active" status).  Only an
# operator lifecycle decision, recent True911 telemetry or recent source-native
# activity (NAPCO last signal, carrier last CDR) establishes it.  Absence of
# evidence leaves NOT_ESTABLISHED - never "not deployed".
DEPLOYED = "DEPLOYED"
DEPLOYMENT_NOT_ESTABLISHED = "NOT_ESTABLISHED"
# Window for SOURCE-DERIVED (inferred) liveness only: inferred deployment ages
# out when exports stop showing activity.  Operator lifecycle decisions never
# age - they persist until superseded.
DEPLOYMENT_ACTIVITY_DAYS = 30
# Sources whose activity column is a genuine liveness signal (NAPCO
# LastSignalReceived, T-Mobile Last CDR).  Verizon / Red Pocket exports carry
# inventory status only and never establish deployment.
DEPLOYMENT_ACTIVITY_SOURCES = ("NAPCO", "T_MOBILE")
# reason when equipment is live but not deterministically placed at the building
REASON_PLACEMENT_UNVERIFIED = "ACTIVE_PLACEMENT_UNVERIFIED"

# ── service types ───────────────────────────────────────────────────────
FACP = "FACP"
ELEVATOR = "ELEVATOR"
EMERGENCY_PHONE = "EMERGENCY_PHONE"
UNCLASSIFIED = "UNCLASSIFIED"                 # a telephone service of unknown purpose
OTHER = "OTHER_NON_LIFE_SAFETY"               # desk / fax / POS / data - never life-safety
FACP_ASSET = "FACP_ASSET"                     # a number that belongs to FACP equipment
LIFE_SAFETY_TYPES = (FACP, ELEVATOR, EMERGENCY_PHONE)

# Domain cardinality: required communications paths per CONFIRMED service.
REQUIRED_CONNECTIONS = {FACP: 2, ELEVATOR: 1, EMERGENCY_PHONE: 1}
CONNECTION_TYPE = {FACP: "FACP_PATH", ELEVATOR: "ELEVATOR_LINE",
                   EMERGENCY_PHONE: "EMERGENCY_PHONE_LINE"}

# connection requirement / provisioning
REQUIRED = "REQUIRED"
NOT_REQUIRED = "NOT_REQUIRED"
ASSET_LINKED = "ASSET_LINKED"
NO_ASSET_LINKED = "NO_ASSET_LINKED"
NOT_EVALUATED = "NOT_EVALUATED"

# ── asset types ─────────────────────────────────────────────────────────
TELEPHONE_NUMBER = "TELEPHONE_NUMBER"
NAPCO_RADIO = "NAPCO_RADIO"
SIM_ICCID = "SIM_ICCID"
DEVICE_IMEI = "DEVICE_IMEI"
ASSET_TYPES = (TELEPHONE_NUMBER, NAPCO_RADIO, SIM_ICCID, DEVICE_IMEI)
MASKED_ASSET_TYPES = (SIM_ICCID, DEVICE_IMEI)

# connection -> asset relationships
REL_CARRIER_LINE = "CARRIER_LINE"             # the telephone line that carries the path
REL_SERVICE_EQUIPMENT = "SERVICE_EQUIPMENT"   # communicator / SIM / radio of the service

# ── sources ─────────────────────────────────────────────────────────────
SRC_ZOHO = "ZOHO"
SRC_TRUE911 = "TRUE911"
SRC_NAPCO = "NAPCO"
SRC_REGISTRY = "REGISTRY"
SRC_OPERATOR = "OPERATOR"

# ── placement bases, in priority order (lower = stronger) ───────────────
P_OPERATOR = "OPERATOR_DECISION"
P_ASSET_IDENTIFIER = "ASSET_IDENTIFIER"       # exact NAPCO / ICCID / IMEI mapping
P_TELEPHONE_MAPPING = "TELEPHONE_MAPPING"     # exact telephone mapping
P_FACILITY = "FACILITY_NAME"                  # building-specific source record
P_STORE_NUMBER = "STORE_NUMBER"               # unique store number
P_ADDRESS = "ADDRESS"                         # exact normalised address
P_ACCOUNT_ALIAS = "ACCOUNT_ALIAS"             # a specific (non-generic) account alias
P_EXISTING_MAPPING = "EXISTING_MAPPING"       # historical site link - support only
P_GENERIC_ALIAS = "GENERIC_ALIAS"             # parent / generic name - never places
PLACEMENT_PRIORITY = {
    P_OPERATOR: 0, P_ASSET_IDENTIFIER: 1, P_TELEPHONE_MAPPING: 2, P_FACILITY: 3,
    P_STORE_NUMBER: 4, P_ADDRESS: 5, P_ACCOUNT_ALIAS: 6, P_EXISTING_MAPPING: 7,
    P_GENERIC_ALIAS: 8,
}
STRONG_BASES = (P_ASSET_IDENTIFIER, P_TELEPHONE_MAPPING)
LOCATION_BASES = (P_FACILITY, P_STORE_NUMBER, P_ADDRESS, P_ACCOUNT_ALIAS)
SUPPORT_BASES = (P_EXISTING_MAPPING, P_GENERIC_ALIAS)
# Placement that is independent of the record's own CRM location fields: only
# this can carry liveness to DEPLOYED at a building (activity proves the
# equipment is alive, never WHERE it is).
DEPLOYMENT_PLACEMENT_BASES = (P_OPERATOR,) + STRONG_BASES

# ── operator decision types ─────────────────────────────────────────────
D_BUILDING_IDENTITY_SUSPECT = "BUILDING_IDENTITY_SUSPECT"
D_CARRIER_MIGRATION = "CARRIER_MIGRATION"
D_ASSET_LIFECYCLE = "ASSET_LIFECYCLE"
D_SERVICE_CLASSIFICATION = "SERVICE_CLASSIFICATION"
D_SERVICE_APPROVAL = "SERVICE_APPROVAL"
# ONE FACP service at a building and the communicator radio(s) that serve it
# (service != communications asset: 1 FACP may have 2 radios)
D_FACP_SERVICE = "FACP_SERVICE"
# disposition of ONE source record: a duplicate, a placeholder with no physical
# location, or a record that belongs to a different building
D_SOURCE_RECORD = "SOURCE_RECORD"
# aggregate operator knowledge: these lines are collectively e.g. emergency
# phone / fax, but which line is which is NOT known - no per-line class implied
D_SERVICE_POOL = "SERVICE_POOL"
DECISION_TYPES = (D_BUILDING_IDENTITY_SUSPECT, D_CARRIER_MIGRATION, D_ASSET_LIFECYCLE,
                  D_SERVICE_CLASSIFICATION, D_SERVICE_APPROVAL, D_FACP_SERVICE,
                  D_SOURCE_RECORD, D_SERVICE_POOL)

# SOURCE_RECORD dispositions
REC_DUPLICATE = "DUPLICATE"            # evidence already carried by another record
REC_PLACEHOLDER = "PLACEHOLDER"        # belongs to no physical location
REC_BUILDING = "BUILDING"              # belongs to the named building
# belongs to a real location that is NOT an approved building of this portfolio
# (e.g. a store not yet in the registry): never placed in any approved building
REC_OUTSIDE = "OUTSIDE_PORTFOLIO"
RECORD_DISPOSITIONS = (REC_DUPLICATE, REC_PLACEHOLDER, REC_BUILDING, REC_OUTSIDE)
REC_EXCLUDING = (REC_DUPLICATE, REC_PLACEHOLDER, REC_OUTSIDE)
# service types a SERVICE_POOL may name (OTHER = fax / desk / data)
POOL_SERVICE_TYPES = (ELEVATOR, EMERGENCY_PHONE, OTHER)

# ── findings ────────────────────────────────────────────────────────────
HIGH = "HIGH"
MEDIUM = "MEDIUM"
INFO = "INFO"
