"""Static Resolution-Intelligence catalog (single source of truth for seeds).

This module holds the deterministic knowledge content as immutable Python
dataclasses.  It is BOTH:
  * the source the idempotent DB seeder loads into the ops_* tables, AND
  * the in-memory catalog the rules-based recommendation engine reads, so
    recommendations need neither a database nor an LLM.

Adding/changing knowledge = edit this file (and re-run the seeder).  Each entry
carries a stable ``code`` so seeding is idempotent and workflows cross-link by
code rather than by a generated id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.services.ops_center.resolution_intelligence.constants import (
    EscalationQueue,
    IncidentSeverity,
)

# ── Domains (the OpsKnownIssue.category value) ───────────────────────
DOMAIN_ELEVATOR = "elevator_phone"
DOMAIN_FACP = "fire_alarm_communicator"
DOMAIN_GATE = "gate_phone"
DOMAIN_CARRIER = "carrier"


# ── Spec dataclasses ─────────────────────────────────────────────────

@dataclass(frozen=True)
class DiagnosticSpec:
    code: str
    title: str
    ordered_steps: list[dict]      # [{"order":1,"action":"...","expect":"..."}]
    expected_results: list[str]
    failure_paths: list[dict]      # [{"when":"...","do":"...","escalate_to":"NOC"}]
    escalation_queue: str


@dataclass(frozen=True)
class ResolutionSpec:
    code: str
    title: str
    resolution_steps: list[dict]   # [{"order":1,"action":"..."}]
    estimated_time_minutes: int
    escalation_trigger: str
    success_criteria: list[str]


@dataclass(frozen=True)
class KnownIssueSpec:
    code: str
    title: str
    category: str                  # domain (persisted as OpsKnownIssue.category)
    severity: str                  # IncidentSeverity value
    description: str
    symptoms: list[str]
    probable_causes: list[str]
    escalation_queue: str
    diagnostic: DiagnosticSpec
    resolution: ResolutionSpec
    vendor: Optional[str] = None
    carrier: Optional[str] = None
    hardware_model: Optional[str] = None
    # Ops Center issue categories this maps to (used by the recommendation
    # engine for matching; not a persisted column).
    ops_issue_categories: list[str] = field(default_factory=list)


# ── tiny builders to keep the catalog readable ───────────────────────

def _s(order: int, action: str, expect: Optional[str] = None) -> dict:
    d = {"order": order, "action": action}
    if expect:
        d["expect"] = expect
    return d


def _f(when: str, do: str, escalate_to: str) -> dict:
    return {"when": when, "do": do, "escalate_to": escalate_to}


def _rs(order: int, action: str) -> dict:
    return {"order": order, "action": action}


# ═════════════════════════════════════════════════════════════════════
# ELEVATOR PHONES
# ═════════════════════════════════════════════════════════════════════

_ELEVATOR = [
    KnownIssueSpec(
        code="elev_no_dial_tone",
        title="Elevator phone — no dial tone (LM150)",
        category=DOMAIN_ELEVATOR,
        severity=IncidentSeverity.HIGH.value,
        description="An elevator emergency phone reports no dial tone; the line cannot originate a call.",
        symptoms=["No dial tone when handset lifted", "Cannot dial out", "Phone appears dead"],
        probable_causes=[
            "Device offline / no power",
            "Cellular signal too low",
            "SIM inactive / not provisioned",
            "IMS not registered",
            "SIP not registered to the trunk",
        ],
        vendor="FlyingVoice",
        carrier=None,
        hardware_model="LM150",
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["no_dial_tone", "elevator_phone_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_elev_no_dial_tone",
            title="LM150 No Dial Tone",
            ordered_steps=[
                _s(1, "Verify device is online (last check-in recent)", "Device online"),
                _s(2, "Verify cellular signal level", "RSSI within usable range"),
                _s(3, "Verify SIM is active with the carrier", "SIM active"),
                _s(4, "Verify IMS registration", "IMS registered"),
                _s(5, "Verify SIP registration to the trunk", "SIP registered"),
                _s(6, "Place a test outbound call", "Call connects with two-way audio"),
            ],
            expected_results=["Dial tone present", "Test call completes with two-way audio"],
            failure_paths=[
                _f("Device offline", "Check power and connectivity on site", EscalationQueue.NOC.value),
                _f("SIM inactive", "Carrier SIM activation", EscalationQueue.CARRIER.value),
                _f("SIP not registered", "Trunk/credentials review", EscalationQueue.TIER2_VOICE.value),
            ],
            escalation_queue=EscalationQueue.NOC.value,
        ),
        resolution=ResolutionSpec(
            code="res_elev_no_dial_tone",
            title="Restore elevator dial tone",
            resolution_steps=[
                _rs(1, "Power-cycle the device and confirm it re-registers"),
                _rs(2, "If signal is low, reposition antenna / confirm coverage"),
                _rs(3, "If SIM inactive, request carrier activation and re-test"),
                _rs(4, "If SIP fails, re-apply trunk credentials and re-register"),
                _rs(5, "Place a verified test call to confirm two-way audio"),
            ],
            estimated_time_minutes=30,
            escalation_trigger="No dial tone after device + SIM + SIP verified",
            success_criteria=["Dial tone restored", "Verified two-way test call to a known number"],
        ),
    ),
    KnownIssueSpec(
        code="elev_one_way_audio",
        title="Elevator phone — one-way audio",
        category=DOMAIN_ELEVATOR,
        severity=IncidentSeverity.HIGH.value,
        description="Call connects but audio is heard in only one direction.",
        symptoms=["Caller cannot be heard", "Or remote party cannot be heard", "Call connects but audio path incomplete"],
        probable_causes=["RTP/NAT path issue", "One-way firewall/ALG", "Codec mismatch", "Faulty handset mic/speaker"],
        vendor="FlyingVoice",
        hardware_model="LM150",
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["elevator_phone_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_elev_one_way_audio",
            title="Elevator one-way audio",
            ordered_steps=[
                _s(1, "Confirm call connects (signaling OK)"),
                _s(2, "Check RTP flow direction in CDR / SBC", "RTP present both directions"),
                _s(3, "Check for SIP ALG / NAT on the site router"),
                _s(4, "Verify negotiated codec on both legs"),
                _s(5, "Test handset mic and speaker locally"),
            ],
            expected_results=["Two-way RTP", "Two-way audible test call"],
            failure_paths=[
                _f("RTP one direction only", "Disable SIP ALG / fix NAT traversal", EscalationQueue.TIER2_VOICE.value),
                _f("Hardware mic/speaker dead", "Replace handset", EscalationQueue.INSTALLER.value),
            ],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_elev_one_way_audio",
            title="Restore two-way audio",
            resolution_steps=[
                _rs(1, "Disable SIP ALG on the site router; confirm RTP both ways"),
                _rs(2, "Align codecs between device and trunk"),
                _rs(3, "If hardware fault, dispatch installer to replace handset"),
                _rs(4, "Verify a two-way test call"),
            ],
            estimated_time_minutes=45,
            escalation_trigger="Two-way audio not restored after NAT/codec fixes",
            success_criteria=["Two-way audio confirmed on a test call"],
        ),
    ),
    KnownIssueSpec(
        code="elev_cannot_reach_psap",
        title="Elevator phone — cannot reach PSAP",
        category=DOMAIN_ELEVATOR,
        severity=IncidentSeverity.CRITICAL.value,
        description="The elevator line connects to test numbers but cannot reach the correct PSAP / 911 routing.",
        symptoms=["911 test call fails or misroutes", "Reaches wrong jurisdiction", "ALI/location incorrect"],
        probable_causes=["E911 record missing/incorrect", "DID not provisioned for E911", "ALI mismatch", "Routing/trunk E911 config"],
        carrier=None,
        escalation_queue=EscalationQueue.E911.value,
        ops_issue_categories=["elevator_phone_issue", "e911_question"],
        diagnostic=DiagnosticSpec(
            code="diag_elev_cannot_reach_psap",
            title="Elevator cannot reach PSAP",
            ordered_steps=[
                _s(1, "Confirm the line can complete an ordinary outbound call"),
                _s(2, "Verify the DID is E911-registered", "E911 record present + validated"),
                _s(3, "Verify the ALI/address matches the physical location"),
                _s(4, "Confirm trunk E911 routing for the jurisdiction"),
                _s(5, "Coordinate a supervised 911 test with the PSAP if required"),
            ],
            expected_results=["E911 record validated", "Supervised test reaches correct PSAP with correct ALI"],
            failure_paths=[
                _f("E911 record missing/incorrect", "Correct E911/ALI record", EscalationQueue.E911.value),
                _f("Trunk routing wrong", "Carrier/trunk E911 routing fix", EscalationQueue.CARRIER.value),
            ],
            escalation_queue=EscalationQueue.E911.value,
        ),
        resolution=ResolutionSpec(
            code="res_elev_cannot_reach_psap",
            title="Restore PSAP reachability",
            resolution_steps=[
                _rs(1, "Create/correct the E911 record and ALI for the DID"),
                _rs(2, "Confirm jurisdiction routing with the carrier"),
                _rs(3, "Run a supervised 911 test where policy permits"),
                _rs(4, "Record evidence of the verified PSAP reach"),
            ],
            estimated_time_minutes=120,
            escalation_trigger="Any failure to reach the correct PSAP — life-safety priority",
            success_criteria=["Validated E911 record", "Evidence of correct PSAP reach with correct ALI"],
        ),
    ),
    KnownIssueSpec(
        code="elev_dtmf_failure",
        title="Elevator phone — DTMF failures",
        category=DOMAIN_ELEVATOR,
        severity=IncidentSeverity.MODERATE.value,
        description="Digits are not recognized downstream (auto-attendant / monitoring station mishears tones).",
        symptoms=["Monitoring station cannot read digits", "IVR does not respond to keypresses", "Intermittent digit capture"],
        probable_causes=["RFC2833 vs in-band DTMF mismatch", "Low DTMF level", "Transcoding distortion"],
        vendor="FlyingVoice",
        hardware_model="LM150",
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["elevator_phone_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_elev_dtmf_failure",
            title="Elevator DTMF failure",
            ordered_steps=[
                _s(1, "Confirm DTMF mode (RFC2833 / SIP INFO / in-band) on device and trunk"),
                _s(2, "Capture a call and inspect DTMF events"),
                _s(3, "Test against a digit-echo number"),
            ],
            expected_results=["Consistent DTMF mode end-to-end", "All digits echoed correctly"],
            failure_paths=[_f("Mode mismatch", "Align DTMF mode device↔trunk", EscalationQueue.TIER2_VOICE.value)],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_elev_dtmf_failure",
            title="Fix DTMF handling",
            resolution_steps=[
                _rs(1, "Set DTMF to RFC2833 on both device and trunk"),
                _rs(2, "Re-test against a digit-echo number"),
            ],
            estimated_time_minutes=20,
            escalation_trigger="Digits still dropped after DTMF mode alignment",
            success_criteria=["All test digits captured correctly"],
        ),
    ),
    KnownIssueSpec(
        code="elev_busy_signal",
        title="Elevator phone — busy signal",
        category=DOMAIN_ELEVATOR,
        severity=IncidentSeverity.HIGH.value,
        description="Outbound attempts return a busy signal instead of connecting.",
        symptoms=["Fast busy on dial-out", "Calls never connect", "Reorder tone"],
        probable_causes=["Trunk channels exhausted", "Blocked/suspended DID", "Routing/dial-plan reject"],
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["no_dial_tone", "elevator_phone_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_elev_busy_signal",
            title="Elevator busy signal",
            ordered_steps=[
                _s(1, "Confirm trunk has available channels"),
                _s(2, "Verify the DID is active and not suspended"),
                _s(3, "Check dial-plan / routing for a reject"),
            ],
            expected_results=["Channels available", "DID active", "Routing accepts the call"],
            failure_paths=[
                _f("DID suspended", "Restore/verify the DID with carrier", EscalationQueue.CARRIER.value),
                _f("Routing reject", "Fix dial-plan/routing", EscalationQueue.TIER2_VOICE.value),
            ],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_elev_busy_signal",
            title="Clear busy condition",
            resolution_steps=[
                _rs(1, "Free/expand trunk channels or fix routing reject"),
                _rs(2, "Restore the DID if suspended"),
                _rs(3, "Verify a completing test call"),
            ],
            estimated_time_minutes=30,
            escalation_trigger="Busy persists after trunk + DID + routing verified",
            success_criteria=["Test call completes (no busy)"],
        ),
    ),
]


# ═════════════════════════════════════════════════════════════════════
# FIRE ALARM COMMUNICATORS (FACP)
# ═════════════════════════════════════════════════════════════════════

_FACP = [
    KnownIssueSpec(
        code="facp_napco_not_checking_in",
        title="Napco communicator not checking in",
        category=DOMAIN_FACP,
        severity=IncidentSeverity.CRITICAL.value,
        description="A NAPCO StarLink fire communicator has stopped its supervisory check-ins.",
        symptoms=["No recent check-in", "Supervision overdue", "Central station shows comm fault"],
        probable_causes=["Device offline / power loss", "Cellular signal loss", "SIM inactive", "Antenna fault"],
        vendor="NAPCO",
        carrier=None,
        hardware_model="StarLink",
        escalation_queue=EscalationQueue.VENDOR.value,
        ops_issue_categories=["fire_panel_issue", "device_offline"],
        diagnostic=DiagnosticSpec(
            code="diag_facp_napco_not_checking_in",
            title="Napco not checking in",
            ordered_steps=[
                _s(1, "Verify device last check-in timestamp", "Recent check-in"),
                _s(2, "Verify power to the communicator"),
                _s(3, "Verify cellular signal level", "Usable signal"),
                _s(4, "Verify SIM/radio active with carrier"),
                _s(5, "Inspect antenna and connections"),
            ],
            expected_results=["Device checking in on schedule", "Central station supervision clear"],
            failure_paths=[
                _f("No power", "Restore power on site", EscalationQueue.INSTALLER.value),
                _f("SIM inactive", "Carrier radio activation", EscalationQueue.CARRIER.value),
                _f("Radio fault", "NAPCO RMA/replacement", EscalationQueue.VENDOR.value),
            ],
            escalation_queue=EscalationQueue.NOC.value,
        ),
        resolution=ResolutionSpec(
            code="res_facp_napco_not_checking_in",
            title="Restore Napco supervision",
            resolution_steps=[
                _rs(1, "Restore power / reseat the radio; confirm check-in"),
                _rs(2, "If signal low, relocate/replace antenna"),
                _rs(3, "If SIM inactive, activate with carrier"),
                _rs(4, "Confirm central station shows supervision restored"),
            ],
            estimated_time_minutes=60,
            escalation_trigger="No check-in after power + signal + SIM verified",
            success_criteria=["Scheduled check-ins resume", "Central station supervision clear"],
        ),
    ),
    KnownIssueSpec(
        code="facp_starlink_offline",
        title="Starlink communicator offline",
        category=DOMAIN_FACP,
        severity=IncidentSeverity.CRITICAL.value,
        description="A StarLink radio shows fully offline (no network presence).",
        symptoms=["Offline in dashboard", "No carrier network event", "Supervision lost"],
        probable_causes=["Power loss", "Carrier outage / tower issue", "SIM deactivated", "Hardware failure"],
        vendor="NAPCO",
        hardware_model="StarLink",
        escalation_queue=EscalationQueue.NOC.value,
        ops_issue_categories=["fire_panel_issue", "device_offline"],
        diagnostic=DiagnosticSpec(
            code="diag_facp_starlink_offline",
            title="Starlink offline",
            ordered_steps=[
                _s(1, "Confirm last network event timestamp"),
                _s(2, "Check carrier status for outage in the area"),
                _s(3, "Verify SIM/radio active"),
                _s(4, "Verify on-site power"),
            ],
            expected_results=["Device back online", "Network event recent"],
            failure_paths=[
                _f("Carrier outage", "Track carrier ticket; monitor restore", EscalationQueue.CARRIER.value),
                _f("Hardware dead", "Vendor replacement", EscalationQueue.VENDOR.value),
            ],
            escalation_queue=EscalationQueue.NOC.value,
        ),
        resolution=ResolutionSpec(
            code="res_facp_starlink_offline",
            title="Bring Starlink back online",
            resolution_steps=[
                _rs(1, "Restore power; confirm radio boots and registers"),
                _rs(2, "If carrier outage, monitor and confirm on restore"),
                _rs(3, "If hardware dead, RMA/replace and re-commission"),
            ],
            estimated_time_minutes=90,
            escalation_trigger="Still offline after power + carrier + SIM checks",
            success_criteria=["Device online", "Supervision restored at central station"],
        ),
    ),
    KnownIssueSpec(
        code="facp_iccid_inactive",
        title="Fire communicator — ICCID inactive",
        category=DOMAIN_FACP,
        severity=IncidentSeverity.CRITICAL.value,
        description="The communicator's SIM (ICCID) is inactive/suspended with the carrier.",
        symptoms=["Carrier shows SIM inactive", "No data session", "Cannot register to network"],
        probable_causes=["SIM never activated", "Billing suspension", "Deactivated in error", "Wrong rate plan"],
        vendor="NAPCO",
        carrier=None,
        escalation_queue=EscalationQueue.CARRIER.value,
        ops_issue_categories=["fire_panel_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_facp_iccid_inactive",
            title="ICCID inactive",
            ordered_steps=[
                _s(1, "Look up the ICCID status with the carrier", "Status = active"),
                _s(2, "Confirm the rate plan supports the device"),
                _s(3, "Check for a billing suspension"),
            ],
            expected_results=["SIM active on a correct plan"],
            failure_paths=[
                _f("Billing suspension", "Resolve account/billing", EscalationQueue.CUSTOMER_SUPPORT.value),
                _f("Wrong plan", "Carrier plan change", EscalationQueue.CARRIER.value),
            ],
            escalation_queue=EscalationQueue.CARRIER.value,
        ),
        resolution=ResolutionSpec(
            code="res_facp_iccid_inactive",
            title="Reactivate SIM",
            resolution_steps=[
                _rs(1, "Request carrier activation on the correct plan"),
                _rs(2, "Confirm a data session and check-in"),
            ],
            estimated_time_minutes=45,
            escalation_trigger="SIM not active after carrier request",
            success_criteria=["SIM active", "Device checks in"],
        ),
    ),
    KnownIssueSpec(
        code="facp_failed_supervision",
        title="Fire communicator — failed supervision",
        category=DOMAIN_FACP,
        severity=IncidentSeverity.CRITICAL.value,
        description="Supervisory signals are not being received within the required window.",
        symptoms=["Supervision overdue at central station", "Intermittent check-ins", "Comm-fail trouble on panel"],
        probable_causes=["Marginal signal", "Check-in interval misconfig", "Panel-to-communicator wiring", "Carrier latency"],
        vendor="NAPCO",
        escalation_queue=EscalationQueue.VENDOR.value,
        ops_issue_categories=["fire_panel_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_facp_failed_supervision",
            title="Failed supervision",
            ordered_steps=[
                _s(1, "Verify configured supervision interval vs central station expectation"),
                _s(2, "Check signal stability over time"),
                _s(3, "Inspect panel-to-communicator wiring/zones"),
            ],
            expected_results=["Supervision within window", "Stable signal"],
            failure_paths=[
                _f("Interval mismatch", "Align interval config", EscalationQueue.VENDOR.value),
                _f("Wiring fault", "On-site repair", EscalationQueue.INSTALLER.value),
            ],
            escalation_queue=EscalationQueue.VENDOR.value,
        ),
        resolution=ResolutionSpec(
            code="res_facp_failed_supervision",
            title="Restore supervision",
            resolution_steps=[
                _rs(1, "Correct supervision interval to match central station"),
                _rs(2, "Stabilize signal (antenna) or repair wiring"),
                _rs(3, "Confirm consecutive successful supervisions"),
            ],
            estimated_time_minutes=60,
            escalation_trigger="Supervision still failing after config + signal + wiring checks",
            success_criteria=["Consecutive on-time supervisions", "Panel comm-fail cleared"],
        ),
    ),
    KnownIssueSpec(
        code="facp_central_station_mismatch",
        title="Fire communicator — central station account mismatch",
        category=DOMAIN_FACP,
        severity=IncidentSeverity.HIGH.value,
        description="Signals arrive but are mapped to the wrong central station account / receiver.",
        symptoms=["Signals attributed to wrong account", "Central station cannot identify site", "Account number rejected"],
        probable_causes=["Wrong account number programmed", "Receiver/line-card mapping", "Stale central station record"],
        vendor="NAPCO",
        escalation_queue=EscalationQueue.VENDOR.value,
        ops_issue_categories=["fire_panel_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_facp_central_station_mismatch",
            title="Central station mismatch",
            ordered_steps=[
                _s(1, "Confirm the account number programmed in the communicator"),
                _s(2, "Confirm the central station's record for the site"),
                _s(3, "Verify receiver/line-card routing"),
            ],
            expected_results=["Programmed account matches central station record"],
            failure_paths=[_f("Mismatch", "Correct account number / central station record", EscalationQueue.VENDOR.value)],
            escalation_queue=EscalationQueue.VENDOR.value,
        ),
        resolution=ResolutionSpec(
            code="res_facp_central_station_mismatch",
            title="Align central station account",
            resolution_steps=[
                _rs(1, "Reprogram the correct account number, or correct the central station record"),
                _rs(2, "Send a test signal and confirm correct attribution"),
            ],
            estimated_time_minutes=45,
            escalation_trigger="Signals still misattributed after account correction",
            success_criteria=["Test signal attributed to the correct account/site"],
        ),
    ),
]


# ═════════════════════════════════════════════════════════════════════
# GATE / AREA-OF-REFUGE / EMERGENCY PHONES
# ═════════════════════════════════════════════════════════════════════

_GATE = [
    KnownIssueSpec(
        code="gate_registration_failure",
        title="Gate phone — registration failure",
        category=DOMAIN_GATE,
        severity=IncidentSeverity.HIGH.value,
        description="A gate/area-of-refuge phone will not register to the voice trunk.",
        symptoms=["SIP not registered", "Device shows unregistered", "No service"],
        probable_causes=["Bad credentials", "Network/firewall blocking SIP", "Expired registration", "Trunk down"],
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["gate_phone_issue", "area_of_refuge_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_gate_registration_failure",
            title="Gate registration failure",
            ordered_steps=[
                _s(1, "Verify network connectivity at the device"),
                _s(2, "Verify SIP credentials and registrar address"),
                _s(3, "Check firewall for SIP/UDP blocking"),
                _s(4, "Attempt a manual re-register"),
            ],
            expected_results=["SIP registered", "Device shows in-service"],
            failure_paths=[
                _f("Credentials wrong", "Re-provision credentials", EscalationQueue.TIER2_VOICE.value),
                _f("Trunk down", "Carrier/trunk restoration", EscalationQueue.CARRIER.value),
            ],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_gate_registration_failure",
            title="Restore gate registration",
            resolution_steps=[
                _rs(1, "Re-apply correct SIP credentials/registrar"),
                _rs(2, "Open SIP ports / fix firewall as needed"),
                _rs(3, "Confirm registration and a test call"),
            ],
            estimated_time_minutes=30,
            escalation_trigger="Still unregistered after credentials + network verified",
            success_criteria=["SIP registered", "Verified test call"],
        ),
    ),
    KnownIssueSpec(
        code="gate_call_completion_failure",
        title="Gate phone — call completion failure",
        category=DOMAIN_GATE,
        severity=IncidentSeverity.HIGH.value,
        description="The phone registers but calls do not complete to the destination.",
        symptoms=["Registers but calls fail", "No answer at destination", "Call drops on setup"],
        probable_causes=["Dial-plan/routing error", "Wrong destination number", "Trunk capacity", "Codec negotiation failure"],
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["gate_phone_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_gate_call_completion_failure",
            title="Gate call completion failure",
            ordered_steps=[
                _s(1, "Confirm the programmed destination number"),
                _s(2, "Trace the call in CDR/SBC for the failure point"),
                _s(3, "Verify codec negotiation"),
            ],
            expected_results=["Call routes and completes", "Two-way audio"],
            failure_paths=[
                _f("Routing/number wrong", "Fix dial-plan/destination", EscalationQueue.TIER2_VOICE.value),
                _f("Codec fail", "Align codecs", EscalationQueue.TIER2_VOICE.value),
            ],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_gate_call_completion_failure",
            title="Restore call completion",
            resolution_steps=[
                _rs(1, "Correct destination number / routing"),
                _rs(2, "Align codecs; confirm completion"),
            ],
            estimated_time_minutes=30,
            escalation_trigger="Calls still fail after routing + codec fixes",
            success_criteria=["Completing test call with two-way audio"],
        ),
    ),
    KnownIssueSpec(
        code="gate_audio_quality",
        title="Gate phone — audio quality issues",
        category=DOMAIN_GATE,
        severity=IncidentSeverity.MODERATE.value,
        description="Calls complete but audio is choppy, delayed, or distorted.",
        symptoms=["Choppy audio", "High latency/echo", "Dropouts"],
        probable_causes=["Packet loss / jitter", "Insufficient bandwidth", "Marginal cellular signal", "Faulty handset"],
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["gate_phone_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_gate_audio_quality",
            title="Gate audio quality",
            ordered_steps=[
                _s(1, "Measure packet loss / jitter on a test call"),
                _s(2, "Check available bandwidth and QoS"),
                _s(3, "Check cellular signal if wireless"),
                _s(4, "Test the handset locally"),
            ],
            expected_results=["Low loss/jitter", "Clear two-way audio"],
            failure_paths=[
                _f("Loss/jitter high", "Fix network/QoS or signal", EscalationQueue.NOC.value),
                _f("Hardware fault", "Replace handset", EscalationQueue.INSTALLER.value),
            ],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_gate_audio_quality",
            title="Improve audio quality",
            resolution_steps=[
                _rs(1, "Resolve packet loss/jitter (QoS, bandwidth, signal)"),
                _rs(2, "Replace handset if hardware is at fault"),
                _rs(3, "Confirm a clean test call"),
            ],
            estimated_time_minutes=45,
            escalation_trigger="Quality still poor after network + hardware checks",
            success_criteria=["Clear two-way audio on a test call"],
        ),
    ),
]


# ═════════════════════════════════════════════════════════════════════
# CARRIER ISSUES
# ═════════════════════════════════════════════════════════════════════

_CARRIER = [
    # ── T-Mobile ──
    KnownIssueSpec(
        code="carrier_tmobile_activation_failure",
        title="T-Mobile — activation failure",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.HIGH.value,
        description="A T-Mobile line/SIM fails to activate on the wholesale platform.",
        symptoms=["Activation request rejected", "Device never gets service", "Activation error from carrier"],
        probable_causes=["Invalid partner/account params", "ICCID not eligible", "Plan/product mismatch", "Provisioning backlog"],
        carrier="T-Mobile",
        escalation_queue=EscalationQueue.CARRIER.value,
        ops_issue_categories=["device_offline", "general_support"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_tmobile_activation_failure",
            title="T-Mobile activation failure",
            ordered_steps=[
                _s(1, "Confirm activation request params (partner/account/product)"),
                _s(2, "Confirm the ICCID is eligible for the plan"),
                _s(3, "Capture the carrier activation error/correlation id"),
            ],
            expected_results=["Activation accepted", "Device provisioned"],
            failure_paths=[_f("Carrier rejects params", "Carrier provisioning ticket with correlation id", EscalationQueue.CARRIER.value)],
            escalation_queue=EscalationQueue.CARRIER.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_tmobile_activation_failure",
            title="Complete T-Mobile activation",
            resolution_steps=[
                _rs(1, "Correct activation params / plan and resubmit"),
                _rs(2, "If carrier-side, open a provisioning ticket with the correlation id"),
                _rs(3, "Confirm the device registers and checks in"),
            ],
            estimated_time_minutes=120,
            escalation_trigger="Activation rejected after params verified — carrier engineering",
            success_criteria=["SIM active", "Device registered and checking in"],
        ),
    ),
    KnownIssueSpec(
        code="carrier_tmobile_ims_registration_failure",
        title="T-Mobile — IMS registration failure",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.HIGH.value,
        description="The device attaches to data but fails IMS registration (no voice).",
        symptoms=["Data works, voice does not", "IMS not registered", "No dial tone despite data"],
        probable_causes=["IMS APN/profile wrong", "VoLTE not provisioned", "Firmware/profile mismatch"],
        carrier="T-Mobile",
        escalation_queue=EscalationQueue.CARRIER.value,
        ops_issue_categories=["no_dial_tone", "device_offline"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_tmobile_ims_registration_failure",
            title="T-Mobile IMS registration failure",
            ordered_steps=[
                _s(1, "Confirm data attach works"),
                _s(2, "Check IMS APN/profile on the device"),
                _s(3, "Confirm VoLTE/IMS provisioned on the line"),
            ],
            expected_results=["IMS registered", "Voice service available"],
            failure_paths=[_f("VoLTE not provisioned", "Carrier IMS/VoLTE provisioning", EscalationQueue.CARRIER.value)],
            escalation_queue=EscalationQueue.CARRIER.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_tmobile_ims_registration_failure",
            title="Restore IMS registration",
            resolution_steps=[
                _rs(1, "Apply correct IMS APN/profile"),
                _rs(2, "Request VoLTE/IMS provisioning from carrier"),
                _rs(3, "Confirm IMS registers and a test call works"),
            ],
            estimated_time_minutes=90,
            escalation_trigger="IMS not registering after profile + provisioning",
            success_criteria=["IMS registered", "Verified test call"],
        ),
    ),
    KnownIssueSpec(
        code="carrier_tmobile_sim_inactive",
        title="T-Mobile — SIM inactive",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.HIGH.value,
        description="A T-Mobile SIM is inactive/suspended.",
        symptoms=["SIM shows inactive", "No network attach"],
        probable_causes=["Never activated", "Suspended for billing", "Deactivated in error"],
        carrier="T-Mobile",
        escalation_queue=EscalationQueue.CARRIER.value,
        ops_issue_categories=["device_offline"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_tmobile_sim_inactive",
            title="T-Mobile SIM inactive",
            ordered_steps=[
                _s(1, "Check SIM status with the carrier"),
                _s(2, "Check for billing suspension"),
            ],
            expected_results=["SIM active"],
            failure_paths=[_f("Billing suspension", "Resolve billing", EscalationQueue.CUSTOMER_SUPPORT.value)],
            escalation_queue=EscalationQueue.CARRIER.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_tmobile_sim_inactive",
            title="Reactivate T-Mobile SIM",
            resolution_steps=[_rs(1, "Activate/restore the SIM"), _rs(2, "Confirm network attach + check-in")],
            estimated_time_minutes=45,
            escalation_trigger="SIM not active after carrier request",
            success_criteria=["SIM active", "Device attaches"],
        ),
    ),
    # ── Verizon ──
    KnownIssueSpec(
        code="carrier_verizon_provisioning_mismatch",
        title="Verizon — provisioning mismatch",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.HIGH.value,
        description="Verizon line is provisioned with the wrong plan/feature set for the device.",
        symptoms=["Service partially works", "Feature missing", "Wrong plan on the line"],
        probable_causes=["Wrong rate plan", "Feature code missing", "ThingSpace record mismatch"],
        carrier="Verizon",
        escalation_queue=EscalationQueue.CARRIER.value,
        ops_issue_categories=["device_offline", "general_support"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_verizon_provisioning_mismatch",
            title="Verizon provisioning mismatch",
            ordered_steps=[
                _s(1, "Pull the ThingSpace/account record for the line"),
                _s(2, "Compare plan/features to the device requirement"),
            ],
            expected_results=["Plan/features match the device"],
            failure_paths=[_f("Mismatch", "Carrier plan/feature correction", EscalationQueue.CARRIER.value)],
            escalation_queue=EscalationQueue.CARRIER.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_verizon_provisioning_mismatch",
            title="Correct Verizon provisioning",
            resolution_steps=[_rs(1, "Apply the correct plan/feature set"), _rs(2, "Confirm full service + check-in")],
            estimated_time_minutes=60,
            escalation_trigger="Service incomplete after plan correction",
            success_criteria=["Correct plan/features", "Full service verified"],
        ),
    ),
    KnownIssueSpec(
        code="carrier_verizon_device_offline",
        title="Verizon — device offline",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.CRITICAL.value,
        description="A Verizon-connected device is offline with no recent network event.",
        symptoms=["Offline", "No network event", "No check-in"],
        probable_causes=["Power loss", "Coverage/tower issue", "SIM suspended", "Hardware fault"],
        carrier="Verizon",
        escalation_queue=EscalationQueue.NOC.value,
        ops_issue_categories=["device_offline"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_verizon_device_offline",
            title="Verizon device offline",
            ordered_steps=[
                _s(1, "Confirm last network event"),
                _s(2, "Check coverage/outage for the area"),
                _s(3, "Verify SIM active and on-site power"),
            ],
            expected_results=["Device online", "Recent network event"],
            failure_paths=[
                _f("Coverage issue", "Track carrier ticket", EscalationQueue.CARRIER.value),
                _f("Hardware dead", "Replace device", EscalationQueue.VENDOR.value),
            ],
            escalation_queue=EscalationQueue.NOC.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_verizon_device_offline",
            title="Bring Verizon device online",
            resolution_steps=[_rs(1, "Restore power / SIM"), _rs(2, "If coverage, monitor restore"), _rs(3, "Confirm online + check-in")],
            estimated_time_minutes=90,
            escalation_trigger="Offline after power + SIM + coverage checks",
            success_criteria=["Device online", "Check-in resumes"],
        ),
    ),
    # ── AT&T / Red Pocket ──
    KnownIssueSpec(
        code="carrier_attredpocket_renewal_failure",
        title="AT&T / Red Pocket — renewal failure",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.HIGH.value,
        description="A Red Pocket (AT&T MVNO) plan failed to renew, risking suspension.",
        symptoms=["Renewal failed notice", "Plan expired", "Service about to suspend"],
        probable_causes=["Payment method failed", "Auto-renew off", "Account balance"],
        carrier="Red Pocket",
        escalation_queue=EscalationQueue.CUSTOMER_SUPPORT.value,
        ops_issue_categories=["device_offline", "billing_question"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_attredpocket_renewal_failure",
            title="Red Pocket renewal failure",
            ordered_steps=[
                _s(1, "Check plan expiry/renewal status"),
                _s(2, "Check payment method / balance"),
                _s(3, "Confirm auto-renew setting"),
            ],
            expected_results=["Plan renewed and active"],
            failure_paths=[_f("Payment failed", "Resolve payment with account owner", EscalationQueue.CUSTOMER_SUPPORT.value)],
            escalation_queue=EscalationQueue.CUSTOMER_SUPPORT.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_attredpocket_renewal_failure",
            title="Complete renewal",
            resolution_steps=[_rs(1, "Renew the plan / fix payment"), _rs(2, "Enable auto-renew"), _rs(3, "Confirm active service")],
            estimated_time_minutes=30,
            escalation_trigger="Renewal cannot complete without customer billing action",
            success_criteria=["Plan active", "Auto-renew enabled"],
        ),
    ),
    KnownIssueSpec(
        code="carrier_attredpocket_service_suspension",
        title="AT&T / Red Pocket — service suspension",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.CRITICAL.value,
        description="A Red Pocket line has been suspended; the life-safety device is offline.",
        symptoms=["Line suspended", "Device offline", "No service"],
        probable_causes=["Non-payment suspension", "Fraud/security hold", "Expired plan not renewed"],
        carrier="Red Pocket",
        escalation_queue=EscalationQueue.CUSTOMER_SUPPORT.value,
        ops_issue_categories=["device_offline"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_attredpocket_service_suspension",
            title="Red Pocket service suspension",
            ordered_steps=[
                _s(1, "Confirm suspension reason with carrier"),
                _s(2, "Determine the required action to restore"),
            ],
            expected_results=["Suspension reason known", "Restore path identified"],
            failure_paths=[_f("Non-payment", "Account owner resolves balance", EscalationQueue.CUSTOMER_SUPPORT.value)],
            escalation_queue=EscalationQueue.CUSTOMER_SUPPORT.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_attredpocket_service_suspension",
            title="Restore suspended line",
            resolution_steps=[_rs(1, "Clear the suspension cause (payment/hold)"), _rs(2, "Request reactivation"), _rs(3, "Confirm device back online")],
            estimated_time_minutes=60,
            escalation_trigger="Reactivation blocked pending customer billing resolution",
            success_criteria=["Line active", "Device online"],
        ),
    ),
    # ── Telnyx ──
    KnownIssueSpec(
        code="carrier_telnyx_sip_registration_failure",
        title="Telnyx — SIP registration failure",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.HIGH.value,
        description="A device cannot register to the Telnyx SIP trunk.",
        symptoms=["SIP 401/403/timeout", "Unregistered", "No voice"],
        probable_causes=["Wrong credentials", "IP/auth connection misconfig", "Firewall blocking", "Outbound voice profile"],
        carrier="Telnyx",
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["no_dial_tone", "device_offline"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_telnyx_sip_registration_failure",
            title="Telnyx SIP registration failure",
            ordered_steps=[
                _s(1, "Verify SIP connection credentials / auth method"),
                _s(2, "Confirm the registrar/outbound voice profile"),
                _s(3, "Check firewall for SIP/RTP"),
            ],
            expected_results=["SIP registered", "Test call completes"],
            failure_paths=[_f("Auth/profile wrong", "Correct Telnyx connection config", EscalationQueue.TIER2_VOICE.value)],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_telnyx_sip_registration_failure",
            title="Restore Telnyx SIP registration",
            resolution_steps=[_rs(1, "Fix credentials / connection profile"), _rs(2, "Open SIP/RTP on firewall"), _rs(3, "Confirm registration + test call")],
            estimated_time_minutes=30,
            escalation_trigger="Still unregistered after credentials + profile + firewall",
            success_criteria=["SIP registered", "Verified test call"],
        ),
    ),
    KnownIssueSpec(
        code="carrier_telnyx_routing_issue",
        title="Telnyx — routing issue",
        category=DOMAIN_CARRIER,
        severity=IncidentSeverity.HIGH.value,
        description="Calls register but route incorrectly or fail on the Telnyx side.",
        symptoms=["Calls misroute", "One-way or failed completion", "Wrong outbound profile"],
        probable_causes=["Outbound voice profile misconfig", "Number/route mapping", "Geo/permission restriction"],
        carrier="Telnyx",
        escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ops_issue_categories=["gate_phone_issue", "elevator_phone_issue"],
        diagnostic=DiagnosticSpec(
            code="diag_carrier_telnyx_routing_issue",
            title="Telnyx routing issue",
            ordered_steps=[
                _s(1, "Inspect the outbound voice profile and routing"),
                _s(2, "Verify number/route mapping"),
                _s(3, "Check geo-permissions for the destination"),
            ],
            expected_results=["Correct route", "Call completes"],
            failure_paths=[_f("Profile/route wrong", "Correct Telnyx routing/profile", EscalationQueue.TIER2_VOICE.value)],
            escalation_queue=EscalationQueue.TIER2_VOICE.value,
        ),
        resolution=ResolutionSpec(
            code="res_carrier_telnyx_routing_issue",
            title="Fix Telnyx routing",
            resolution_steps=[_rs(1, "Correct outbound profile / route mapping"), _rs(2, "Enable required geo-permissions"), _rs(3, "Confirm a completing call")],
            estimated_time_minutes=30,
            escalation_trigger="Routing still wrong after profile + mapping fixes",
            success_criteria=["Calls route correctly and complete"],
        ),
    ),
]


# The full catalog (order is stable for deterministic output).
RESOLUTION_CATALOG: list[KnownIssueSpec] = [*_ELEVATOR, *_FACP, *_GATE, *_CARRIER]


def catalog_by_code() -> dict[str, KnownIssueSpec]:
    return {spec.code: spec for spec in RESOLUTION_CATALOG}
