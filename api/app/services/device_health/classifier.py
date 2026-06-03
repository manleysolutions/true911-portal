"""Hardware-agnostic device classifier.

Given a device's identity fields (model / device_type / hardware_model_id /
manufacturer / carrier), decide:

  * which vendor-cloud manages it (if any) — e.g. Vola
  * its connection type — cellular / sip_over_lte / analog_fxs / ...
  * its voice path — volte / sip / analog / unknown
  * which carrier it rides — tmobile / verizon / ...
  * which voice provider carries its calls — telnyx / ...
  * therefore which status-probe adapters apply

This is the ONLY place hardware identity is interpreted.  Adding a new device
class = adding a row to ``_RULES`` (or a new adapter), not touching core
health logic.  No customer/site names appear here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DeviceClassification:
    vendor_cloud: Optional[str] = None        # "vola" | "napco_portal" | None
    connection_type: str = "unknown"          # cellular | sip_over_lte | analog_fxs | cellular_modem | unknown
    voice_type: str = "unknown"               # volte | sip | analog | unknown
    carrier_vendor: Optional[str] = None      # "tmobile" | "verizon" | "att" | None
    voice_vendor: Optional[str] = None        # "telnyx" | None
    probe_vendors: tuple[str, ...] = field(default_factory=tuple)
    # Vendor-managed devices monitored OUT-OF-BAND (no live probe adapter) —
    # e.g. NAPCO StarLink fire communicators synced from the NAPCO portal XLS.
    vendor_managed: bool = False
    device_family: Optional[str] = None       # "napco_starlink" | None
    monitoring_source: Optional[str] = None   # "napco_xls_import" | None


# Substring-matched identity rules.  First match wins.  Match is tested
# (case-insensitive) against model, device_type, and hardware_model_id.
# Each rule: (needles, vendor_cloud, connection_type, voice_type, voice_vendor)
_RULES: tuple[tuple[tuple[str, ...], Optional[str], str, str, Optional[str]], ...] = (
    (("lm150", "flyingvoice-lm150"),        "vola", "cellular",       "volte",   None),
    (("pr12", "flyingvoice-pr12"),          "vola", "cellular",       "sip",     None),
    (("ms130", "ms130v4"),                  None,   "cellular",       "unknown", None),
    (("ata191", "ata190", "cisco-ata", "cisco_ata"),
                                            None,   "sip_over_lte",   "analog",  "telnyx"),
    (("inseego", "fw3100", "fx3100", "fx3110"),
                                            None,   "cellular_modem", "unknown", None),
    (("teltonika",),                        None,   "cellular",       "unknown", None),
)

_CARRIER_ALIASES = {
    "tmobile": "tmobile", "t-mobile": "tmobile", "t mobile": "tmobile",
    "verizon": "verizon", "vzw": "verizon",
    "att": "att", "at&t": "att",
}


def _norm(s: Optional[str]) -> str:
    return (s or "").lower().strip()


def normalize_carrier(carrier: Optional[str]) -> Optional[str]:
    return _CARRIER_ALIASES.get(_norm(carrier))


# NAPCO StarLink model codes / markers. Deliberately does NOT include bare
# "starlink" (that also means SpaceX Starlink) — only the unambiguous SLE* model
# codes, "starlink communicator", or a NAPCO manufacturer/carrier.
_NAPCO_NEEDLES = (
    "slelte", "sle-lte", "sleltevi", "sle-ltevi", "slemaxvi", "sle5g",
    "starlink communicator", "napco",
)


def _is_napco(haystacks: list[str], carrier: Optional[str]) -> bool:
    if "napco" in _norm(carrier):
        return True
    return any(h and any(n in h for n in _NAPCO_NEEDLES) for h in haystacks)


def classify(
    *,
    model: Optional[str] = None,
    device_type: Optional[str] = None,
    hardware_model_id: Optional[str] = None,
    manufacturer: Optional[str] = None,
    carrier: Optional[str] = None,
) -> DeviceClassification:
    """Classify a device from its identity fields. Pure / no I/O."""
    haystacks = [_norm(model), _norm(device_type), _norm(hardware_model_id), _norm(manufacturer)]

    # NAPCO StarLink fire communicators — Manley-supplied, billed to the
    # subscriber, managed in the NAPCO portal. No public API: monitored via the
    # portal's XLS export, NOT a live probe adapter (probe_vendors stays empty).
    if _is_napco(haystacks, carrier):
        return DeviceClassification(
            vendor_cloud="napco_portal",
            connection_type="cellular",
            voice_type="unknown",
            carrier_vendor=normalize_carrier(carrier),
            probe_vendors=(),
            vendor_managed=True,
            device_family="napco_starlink",
            monitoring_source="napco_xls_import",
        )

    vendor_cloud: Optional[str] = None
    connection_type = "unknown"
    voice_type = "unknown"
    voice_vendor: Optional[str] = None

    for needles, v_cloud, conn, voice, v_vendor in _RULES:
        if any(n in h for n in needles for h in haystacks if h):
            vendor_cloud, connection_type, voice_type, voice_vendor = (
                v_cloud, conn, voice, v_vendor)
            break

    carrier_vendor = normalize_carrier(carrier)
    # If we couldn't classify connection but a carrier is present, it's at
    # least a cellular endpoint.
    if connection_type == "unknown" and carrier_vendor:
        connection_type = "cellular"

    probes: list[str] = []
    if vendor_cloud:
        probes.append(vendor_cloud)
    if carrier_vendor:
        probes.append(carrier_vendor)
    if voice_vendor:
        probes.append(voice_vendor)

    return DeviceClassification(
        vendor_cloud=vendor_cloud,
        connection_type=connection_type,
        voice_type=voice_type,
        carrier_vendor=carrier_vendor,
        voice_vendor=voice_vendor,
        probe_vendors=tuple(dict.fromkeys(probes)),  # de-dup, keep order
    )
