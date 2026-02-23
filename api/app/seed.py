"""Seed the database with demo tenant, users, sites, telemetry, audits, incidents,
notification rules, lines, recordings, events, and providers.

Run: python -m app.seed
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from .database import AsyncSessionLocal
from .models.tenant import Tenant
from .models.user import User
from .models.site import Site
from .models.telemetry_event import TelemetryEvent
from .models.action_audit import ActionAudit
from .models.incident import Incident
from .models.notification_rule import NotificationRule
from .models.device import Device
from .models.line import Line
from .models.recording import Recording
from .models.event import Event
from .models.provider import Provider
from .services.auth import hash_password


def uid(prefix="ID"):
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def ago(days_ago=0, hours_ago=0, minutes_ago=0):
    """Return a timezone-aware datetime object for 'X time ago'."""
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)


TENANT_ID = "demo"

USERS = [
    {"email": "admin@true911.com", "name": "Sarah Chen", "role": "Admin", "password": "admin123"},
    {"email": "manager@true911.com", "name": "Mike Torres", "role": "Manager", "password": "manager123"},
    {"email": "user@true911.com", "name": "Alex Rivera", "role": "User", "password": "user123"},
]

SITES = [
    {"site_id": "SITE-001", "site_name": "Dallas Fire Station #7", "customer_name": "City of Dallas", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=2), "e911_street": "1234 Main St", "e911_city": "Dallas", "e911_state": "TX", "e911_zip": "75201", "lat": 32.7767, "lng": -96.7970, "heartbeat_interval": 5, "uptime_percent": 99.8},
    {"site_id": "SITE-002", "site_name": "Austin EMS Central", "customer_name": "Travis County EMS", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=5), "e911_street": "15th & Lavaca", "e911_city": "Austin", "e911_state": "TX", "e911_zip": "78701", "lat": 30.2672, "lng": -97.7431, "heartbeat_interval": 5, "uptime_percent": 99.5},
    {"site_id": "SITE-003", "site_name": "Houston Police Precinct 4", "customer_name": "Houston PD", "status": "Attention Needed", "firmware_version": "3.1.0", "csa_model": "CSA-400", "last_checkin": ago(hours_ago=2), "e911_street": "7300 N Shepherd Dr", "e911_city": "Houston", "e911_state": "TX", "e911_zip": "77091", "lat": 29.7604, "lng": -95.3698, "heartbeat_interval": 10, "uptime_percent": 94.2},
    {"site_id": "SITE-004", "site_name": "San Antonio Fire HQ", "customer_name": "SA Fire Dept", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=1), "e911_street": "801 Dolorosa St", "e911_city": "San Antonio", "e911_state": "TX", "e911_zip": "78207", "lat": 29.4241, "lng": -98.4936, "heartbeat_interval": 5, "uptime_percent": 99.9},
    {"site_id": "SITE-005", "site_name": "Fort Worth Station #12", "customer_name": "City of Fort Worth", "status": "Not Connected", "firmware_version": "3.0.5", "csa_model": "CSA-300", "last_checkin": ago(days_ago=2), "e911_street": "505 W Felix St", "e911_city": "Fort Worth", "e911_state": "TX", "e911_zip": "76115", "lat": 32.7555, "lng": -97.3308, "heartbeat_interval": 15, "uptime_percent": 72.1},
    {"site_id": "SITE-006", "site_name": "El Paso Border Station", "customer_name": "El Paso County", "status": "Connected", "firmware_version": "3.2.0", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=8), "e911_street": "221 N Kansas St", "e911_city": "El Paso", "e911_state": "TX", "e911_zip": "79901", "lat": 31.7619, "lng": -106.4850, "heartbeat_interval": 5, "uptime_percent": 98.7},
    {"site_id": "SITE-007", "site_name": "Plano Communications Center", "customer_name": "City of Plano", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=3), "e911_street": "909 14th St", "e911_city": "Plano", "e911_state": "TX", "e911_zip": "75074", "lat": 33.0198, "lng": -96.6989, "heartbeat_interval": 5, "uptime_percent": 99.6},
    {"site_id": "SITE-008", "site_name": "Arlington Fire #3", "customer_name": "City of Arlington", "status": "Attention Needed", "firmware_version": "3.1.2", "csa_model": "CSA-400", "last_checkin": ago(hours_ago=1), "e911_street": "220 E Main St", "e911_city": "Arlington", "e911_state": "TX", "e911_zip": "76010", "lat": 32.7357, "lng": -97.1081, "heartbeat_interval": 10, "uptime_percent": 91.3},
    {"site_id": "SITE-009", "site_name": "Corpus Christi PD Central", "customer_name": "CCPD", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=4), "e911_street": "321 John Sartain St", "e911_city": "Corpus Christi", "e911_state": "TX", "e911_zip": "78401", "lat": 27.8006, "lng": -97.3964, "heartbeat_interval": 5, "uptime_percent": 99.1},
    {"site_id": "SITE-010", "site_name": "Lubbock EMS Dispatch", "customer_name": "Lubbock County", "status": "Connected", "firmware_version": "3.2.0", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=6), "e911_street": "916 Main St", "e911_city": "Lubbock", "e911_state": "TX", "e911_zip": "79401", "lat": 33.5779, "lng": -101.8552, "heartbeat_interval": 5, "uptime_percent": 98.9},
    {"site_id": "SITE-011", "site_name": "Laredo Fire Station #1", "customer_name": "City of Laredo", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=7), "e911_street": "616 Salinas Ave", "e911_city": "Laredo", "e911_state": "TX", "e911_zip": "78040", "lat": 27.5036, "lng": -99.5076, "heartbeat_interval": 5, "uptime_percent": 97.5},
    {"site_id": "SITE-012", "site_name": "Irving 911 Center", "customer_name": "City of Irving", "status": "Not Connected", "firmware_version": "3.0.3", "csa_model": "CSA-300", "last_checkin": ago(days_ago=3), "e911_street": "825 W Irving Blvd", "e911_city": "Irving", "e911_state": "TX", "e911_zip": "75060", "lat": 32.8140, "lng": -96.9489, "heartbeat_interval": 15, "uptime_percent": 65.8},
    {"site_id": "SITE-013", "site_name": "Amarillo Fire #5", "customer_name": "City of Amarillo", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=10), "e911_street": "509 SE 7th Ave", "e911_city": "Amarillo", "e911_state": "TX", "e911_zip": "79101", "lat": 35.2220, "lng": -101.8313, "heartbeat_interval": 5, "uptime_percent": 99.0},
    {"site_id": "SITE-014", "site_name": "Brownsville PD South", "customer_name": "City of Brownsville", "status": "Connected", "firmware_version": "3.1.5", "csa_model": "CSA-400", "last_checkin": ago(minutes_ago=12), "e911_street": "600 E Jackson St", "e911_city": "Brownsville", "e911_state": "TX", "e911_zip": "78520", "lat": 25.9017, "lng": -97.4975, "heartbeat_interval": 10, "uptime_percent": 96.4},
    {"site_id": "SITE-015", "site_name": "McKinney Station #7", "customer_name": "City of McKinney", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=2), "e911_street": "222 N Tennessee St", "e911_city": "McKinney", "e911_state": "TX", "e911_zip": "75069", "lat": 33.1972, "lng": -96.6397, "heartbeat_interval": 5, "uptime_percent": 99.7},
    {"site_id": "SITE-016", "site_name": "Midland Fire Central", "customer_name": "City of Midland", "status": "Attention Needed", "firmware_version": "3.1.0", "csa_model": "CSA-400", "last_checkin": ago(hours_ago=3), "e911_street": "300 N Loraine St", "e911_city": "Midland", "e911_state": "TX", "e911_zip": "79701", "lat": 31.9973, "lng": -102.0779, "heartbeat_interval": 10, "uptime_percent": 88.5},
    {"site_id": "SITE-017", "site_name": "Round Rock EMS", "customer_name": "City of Round Rock", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=4), "e911_street": "221 E Main St", "e911_city": "Round Rock", "e911_state": "TX", "e911_zip": "78664", "lat": 30.5083, "lng": -97.6789, "heartbeat_interval": 5, "uptime_percent": 99.4},
    {"site_id": "SITE-018", "site_name": "Odessa Fire Station #2", "customer_name": "City of Odessa", "status": "Connected", "firmware_version": "3.2.0", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=9), "e911_street": "411 W 8th St", "e911_city": "Odessa", "e911_state": "TX", "e911_zip": "79761", "lat": 31.8457, "lng": -102.3676, "heartbeat_interval": 5, "uptime_percent": 97.8},
    {"site_id": "SITE-019", "site_name": "Frisco PD Communications", "customer_name": "City of Frisco", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=1), "e911_street": "7200 Stonebrook Pkwy", "e911_city": "Frisco", "e911_state": "TX", "e911_zip": "75034", "lat": 33.1507, "lng": -96.8236, "heartbeat_interval": 5, "uptime_percent": 99.9},
    {"site_id": "SITE-020", "site_name": "Killeen Fire #4", "customer_name": "City of Killeen", "status": "Not Connected", "firmware_version": "2.9.8", "csa_model": "CSA-300", "last_checkin": ago(days_ago=5), "e911_street": "101 E Avenue D", "e911_city": "Killeen", "e911_state": "TX", "e911_zip": "76541", "lat": 31.1171, "lng": -97.7278, "heartbeat_interval": 15, "uptime_percent": 45.2},
    {"site_id": "SITE-021", "site_name": "Tyler 911 Center", "customer_name": "Smith County", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=5), "e911_street": "100 N Broadway Ave", "e911_city": "Tyler", "e911_state": "TX", "e911_zip": "75702", "lat": 32.3513, "lng": -95.3011, "heartbeat_interval": 5, "uptime_percent": 98.6},
    {"site_id": "SITE-022", "site_name": "Denton Fire HQ", "customer_name": "City of Denton", "status": "Connected", "firmware_version": "3.2.0", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=3), "e911_street": "332 E Hickory St", "e911_city": "Denton", "e911_state": "TX", "e911_zip": "76201", "lat": 33.2148, "lng": -97.1331, "heartbeat_interval": 5, "uptime_percent": 99.2},
    {"site_id": "SITE-023", "site_name": "Waco PD Dispatch", "customer_name": "City of Waco", "status": "Attention Needed", "firmware_version": "3.1.1", "csa_model": "CSA-400", "last_checkin": ago(hours_ago=4), "e911_street": "721 N 4th St", "e911_city": "Waco", "e911_state": "TX", "e911_zip": "76707", "lat": 31.5493, "lng": -97.1467, "heartbeat_interval": 10, "uptime_percent": 85.7},
    {"site_id": "SITE-024", "site_name": "Abilene Fire #1", "customer_name": "City of Abilene", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=6), "e911_street": "555 Walnut St", "e911_city": "Abilene", "e911_state": "TX", "e911_zip": "79601", "lat": 32.4487, "lng": -99.7331, "heartbeat_interval": 5, "uptime_percent": 98.3},
    {"site_id": "SITE-025", "site_name": "Beaumont EMS Central", "customer_name": "Jefferson County", "status": "Connected", "firmware_version": "3.2.0", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=11), "e911_street": "801 Main St", "e911_city": "Beaumont", "e911_state": "TX", "e911_zip": "77701", "lat": 30.0802, "lng": -94.1266, "heartbeat_interval": 5, "uptime_percent": 97.1},
]

TELEMETRY = [
    {"site_id": "SITE-005", "category": "network", "severity": "critical", "message": "Device unreachable — no heartbeat for 48h", "ago_hours": 0},
    {"site_id": "SITE-012", "category": "network", "severity": "critical", "message": "Device offline — last heartbeat 72h ago", "ago_hours": 1},
    {"site_id": "SITE-020", "category": "network", "severity": "critical", "message": "Connection lost — 5 days since last checkin", "ago_hours": 2},
    {"site_id": "SITE-003", "category": "hardware", "severity": "warning", "message": "Battery backup below 30% threshold", "ago_hours": 3},
    {"site_id": "SITE-008", "category": "firmware", "severity": "warning", "message": "Firmware 3.1.2 is outdated — 3.2.1 available", "ago_hours": 4},
    {"site_id": "SITE-016", "category": "network", "severity": "warning", "message": "Intermittent connectivity — 3 drops in 6h", "ago_hours": 5},
    {"site_id": "SITE-023", "category": "e911", "severity": "warning", "message": "E911 address verification pending AHJ review", "ago_hours": 6},
    {"site_id": "SITE-001", "category": "system", "severity": "info", "message": "Routine check-in — all systems nominal", "ago_hours": 0},
    {"site_id": "SITE-002", "category": "system", "severity": "info", "message": "Firmware auto-update completed successfully", "ago_hours": 1},
    {"site_id": "SITE-004", "category": "system", "severity": "info", "message": "Container restart scheduled — maintenance window", "ago_hours": 2},
]

AUDITS = [
    {"action_type": "PING", "site_id": "SITE-001", "user_email": "admin@true911.com", "requester_name": "Sarah Chen", "role": "Admin", "result": "success", "details": "Ping OK — 42ms latency", "ago_minutes": 15},
    {"action_type": "REBOOT", "site_id": "SITE-005", "user_email": "admin@true911.com", "requester_name": "Sarah Chen", "role": "Admin", "result": "success", "details": "Remote reboot initiated", "ago_minutes": 45},
    {"action_type": "UPDATE_E911", "site_id": "SITE-003", "user_email": "admin@true911.com", "requester_name": "Sarah Chen", "role": "Admin", "result": "success", "details": "E911 address updated: 7300 N Shepherd Dr", "ago_minutes": 120},
    {"action_type": "PING", "site_id": "SITE-012", "user_email": "manager@true911.com", "requester_name": "Mike Torres", "role": "Manager", "result": "failure", "details": "Ping timed out — device unreachable", "ago_minutes": 180},
    {"action_type": "ACK_INCIDENT", "site_id": "SITE-005", "user_email": "manager@true911.com", "requester_name": "Mike Torres", "role": "Manager", "result": "success", "details": "Incident INC-001 acknowledged", "ago_minutes": 200},
    {"action_type": "PING", "site_id": "SITE-007", "user_email": "manager@true911.com", "requester_name": "Mike Torres", "role": "Manager", "result": "success", "details": "Ping OK — 38ms latency", "ago_minutes": 300},
    {"action_type": "RESTART_CONTAINER", "site_id": "SITE-008", "user_email": "admin@true911.com", "requester_name": "Sarah Chen", "role": "Admin", "result": "success", "details": "Container 'sip-proxy' restarted", "ago_minutes": 400},
    {"action_type": "GENERATE_REPORT", "site_id": "SITE-001", "user_email": "admin@true911.com", "requester_name": "Sarah Chen", "role": "Admin", "result": "success", "details": "Monthly uptime report generated", "ago_minutes": 500},
]

INCIDENTS = [
    {"site_id": "SITE-005", "severity": "critical", "status": "open", "summary": "Device completely offline — no heartbeat for 48+ hours. Possible hardware failure or network issue at site.", "opened_hours_ago": 48},
    {"site_id": "SITE-012", "severity": "critical", "status": "open", "summary": "CSA-300 unit unreachable for 72h. Site contact notified, awaiting physical inspection.", "opened_hours_ago": 72},
    {"site_id": "SITE-020", "severity": "critical", "status": "acknowledged", "summary": "Extended outage — 5 days offline. Replacement unit shipped, ETA 2 days.", "opened_hours_ago": 120, "ack_by": "Mike Torres"},
    {"site_id": "SITE-003", "severity": "warning", "status": "open", "summary": "Battery backup at 28%. UPS replacement recommended within 48h.", "opened_hours_ago": 6},
    {"site_id": "SITE-008", "severity": "warning", "status": "acknowledged", "summary": "Intermittent SIP registration failures. Container restarted, monitoring.", "opened_hours_ago": 12, "ack_by": "Sarah Chen"},
    {"site_id": "SITE-016", "severity": "warning", "status": "open", "summary": "Connectivity drops averaging 3x per 6h window. ISP ticket opened.", "opened_hours_ago": 18},
    {"site_id": "SITE-023", "severity": "info", "status": "open", "summary": "E911 address pending AHJ re-verification after recent municipal boundary change.", "opened_hours_ago": 24},
    {"site_id": "SITE-014", "severity": "info", "status": "acknowledged", "summary": "Firmware update available (3.1.5 → 3.2.1). Scheduled for next maintenance window.", "opened_hours_ago": 48, "ack_by": "Mike Torres"},
]

NOTIFICATION_RULES = [
    {
        "rule_id": "RULE-001", "rule_name": "Life Safety Offline Alert", "rule_type": "offline_timeout",
        "threshold_value": 30, "threshold_unit": "minutes", "scope": "life_safety_only",
        "channels": ["portal", "sms", "email"], "enabled": True,
        "escalation_steps": [
            {"step": 1, "delay_minutes": 0, "contact_role": "security", "contact_email": "security@manleysolutions.com", "contact_phone": "+1-555-0100"},
            {"step": 2, "delay_minutes": 15, "contact_role": "site_owner", "contact_email": "smanley@manleysolutions.com", "contact_phone": "+1-555-0200"},
            {"step": 3, "delay_minutes": 60, "contact_role": "psap", "contact_email": "psap-coordinator@911.gov", "contact_phone": "+1-555-0911"},
        ],
        "trigger_count": 3,
    },
    {
        "rule_id": "RULE-002", "rule_name": "Missed Heartbeat — FACP", "rule_type": "missed_heartbeat",
        "threshold_value": 1, "threshold_unit": "days", "scope": "all_sites",
        "channels": ["portal", "email"], "enabled": True,
        "escalation_steps": [
            {"step": 1, "delay_minutes": 0, "contact_role": "admin", "contact_email": "admin@manleysolutions.com", "contact_phone": ""},
            {"step": 2, "delay_minutes": 60, "contact_role": "site_owner", "contact_email": "smanley@manleysolutions.com", "contact_phone": ""},
        ],
        "trigger_count": 5,
    },
    {
        "rule_id": "RULE-003", "rule_name": "Weak Signal Warning", "rule_type": "signal_below_threshold",
        "threshold_value": -85, "threshold_unit": "dbm", "scope": "all_sites",
        "channels": ["portal"], "enabled": True,
        "escalation_steps": [
            {"step": 1, "delay_minutes": 0, "contact_role": "admin", "contact_email": "admin@manleysolutions.com", "contact_phone": ""},
        ],
        "trigger_count": 7,
    },
]

# Derive devices from sites (one device per site)
DEVICES = []
for _idx, _s in enumerate(SITES):
    _status_map = {"Connected": "active", "Not Connected": "inactive", "Attention Needed": "active"}
    DEVICES.append({
        "device_id": f"DEV-{_idx + 1:03d}",
        "site_id": _s["site_id"],
        "status": _status_map.get(_s["status"], "active"),
        "device_type": "CSA",
        "model": _s.get("csa_model", "CSA-500"),
        "serial_number": f"SN-{_idx + 1:04d}-{uuid.uuid4().hex[:6].upper()}",
        "mac_address": ":".join(f"{b:02X}" for b in [0x00, 0x1A, 0x2B, _idx, (_idx * 7) % 256, (_idx * 13) % 256]),
        "imei": f"35{_idx:013d}",
        "firmware_version": _s.get("firmware_version", "3.2.1"),
        "container_version": "1.4.2",
        "last_heartbeat": _s.get("last_checkin"),
        "heartbeat_interval": _s.get("heartbeat_interval", 5),
    })


PROVIDERS = [
    {"provider_id": "PROV-001", "provider_type": "telnyx", "display_name": "Telnyx SIP Trunking", "enabled": True, "config_json": {"region": "us-central", "sip_connection_id": "demo-conn-001"}},
    {"provider_id": "PROV-002", "provider_type": "tmobile", "display_name": "T-Mobile IoT SIM", "enabled": True, "config_json": {"plan": "iot-500mb", "apn": "fast.t-mobile.com"}},
    {"provider_id": "PROV-003", "provider_type": "bandwidth", "display_name": "Bandwidth Voice", "enabled": False, "config_json": None},
]

# Lines — voice lines assigned to first 15 sites/devices
LINES = []
_line_configs = [
    ("telnyx",   "+12145550101", "SIP",      "active",       "validated"),
    ("telnyx",   "+15125550102", "SIP",      "active",       "validated"),
    ("tmobile",  "+17135550103", "cellular", "active",       "pending"),
    ("telnyx",   "+12105550104", "SIP",      "active",       "validated"),
    ("tmobile",  "+18175550105", "cellular", "disconnected", "failed"),
    ("telnyx",   "+19155550106", "SIP",      "active",       "validated"),
    ("telnyx",   "+14695550107", "SIP",      "active",       "validated"),
    ("tmobile",  "+18175550108", "cellular", "active",       "pending"),
    ("telnyx",   "+13615550109", "SIP",      "active",       "validated"),
    ("telnyx",   "+18065550110", "SIP",      "active",       "validated"),
    ("telnyx",   "+19565550111", "SIP",      "provisioning", "none"),
    ("tmobile",  "+19725550112", "cellular", "disconnected", "none"),
    ("telnyx",   "+18065550113", "SIP",      "active",       "validated"),
    ("telnyx",   "+19565550114", "SIP",      "active",       "validated"),
    ("telnyx",   "+14695550115", "SIP",      "active",       "validated"),
]
for _i, (_prov, _did, _proto, _st, _e911) in enumerate(_line_configs):
    _site = SITES[_i]
    LINES.append({
        "line_id": f"LINE-{_i + 1:03d}",
        "site_id": _site["site_id"],
        "device_id": f"DEV-{_i + 1:03d}",
        "provider": _prov,
        "did": _did,
        "sip_uri": f"sip:{_did[2:]}@sip.telnyx.com" if _prov == "telnyx" else None,
        "protocol": _proto,
        "status": _st,
        "e911_status": _e911,
        "e911_street": _site.get("e911_street"),
        "e911_city": _site.get("e911_city"),
        "e911_state": _site.get("e911_state"),
        "e911_zip": _site.get("e911_zip"),
    })

# Recordings — sample call recordings for active lines
RECORDINGS = [
    {"line_idx": 0, "direction": "inbound",  "duration": 12, "ago_hours": 1,  "caller": "+12145559900", "callee": "+12145550101", "status": "available"},
    {"line_idx": 0, "direction": "outbound", "duration": 5,  "ago_hours": 3,  "caller": "+12145550101", "callee": "+19725550000", "status": "available"},
    {"line_idx": 1, "direction": "inbound",  "duration": 8,  "ago_hours": 2,  "caller": "+15125559900", "callee": "+15125550102", "status": "available"},
    {"line_idx": 3, "direction": "inbound",  "duration": 15, "ago_hours": 4,  "caller": "+12105559900", "callee": "+12105550104", "status": "available"},
    {"line_idx": 5, "direction": "outbound", "duration": 22, "ago_hours": 6,  "caller": "+19155550106", "callee": "+19155559900", "status": "available"},
    {"line_idx": 6, "direction": "inbound",  "duration": 3,  "ago_hours": 1,  "caller": "+14695559900", "callee": "+14695550107", "status": "available"},
    {"line_idx": 8, "direction": "inbound",  "duration": 45, "ago_hours": 8,  "caller": "+13615559900", "callee": "+13615550109", "status": "available"},
    {"line_idx": 9, "direction": "outbound", "duration": 7,  "ago_hours": 12, "caller": "+18065550110", "callee": "+18065559900", "status": "available"},
    {"line_idx": 2, "direction": "inbound",  "duration": 0,  "ago_hours": 5,  "caller": "+17135559900", "callee": "+17135550103", "status": "failed"},
    {"line_idx": 4, "direction": "inbound",  "duration": 0,  "ago_hours": 48, "caller": "+18175559900", "callee": "+18175550105", "status": "failed"},
]

# Events — unified immutable log
EVENTS = [
    {"event_type": "device.registered", "site_id": "SITE-001", "device_id": "DEV-001", "severity": "info",     "message": "Device DEV-001 registered and connected", "ago_hours": 168},
    {"event_type": "line.registered",   "site_id": "SITE-001", "device_id": "DEV-001", "line_id": "LINE-001", "severity": "info", "message": "Line LINE-001 SIP registration successful", "ago_hours": 167},
    {"event_type": "e911.validated",    "site_id": "SITE-001", "line_id": "LINE-001", "severity": "info",     "message": "E911 address validated for LINE-001", "ago_hours": 166},
    {"event_type": "call.completed",    "site_id": "SITE-001", "device_id": "DEV-001", "line_id": "LINE-001", "severity": "info", "message": "Inbound call completed — 12s duration", "ago_hours": 1},
    {"event_type": "device.heartbeat",  "site_id": "SITE-001", "device_id": "DEV-001", "severity": "info",     "message": "Heartbeat OK — all systems nominal", "ago_hours": 0},
    {"event_type": "device.offline",    "site_id": "SITE-005", "device_id": "DEV-005", "severity": "critical", "message": "Device DEV-005 missed 576 heartbeats — offline 48h", "ago_hours": 2},
    {"event_type": "line.down",         "site_id": "SITE-005", "device_id": "DEV-005", "line_id": "LINE-005", "severity": "critical", "message": "Line LINE-005 SIP registration lost", "ago_hours": 48},
    {"event_type": "alert.triggered",   "site_id": "SITE-005", "severity": "critical", "message": "Alert RULE-001 triggered: Life Safety Offline", "ago_hours": 47},
    {"event_type": "e911.updated",      "site_id": "SITE-003", "line_id": "LINE-003", "severity": "warning",  "message": "E911 address updated — pending AHJ verification", "ago_hours": 6},
    {"event_type": "device.registered", "site_id": "SITE-002", "device_id": "DEV-002", "severity": "info",     "message": "Device DEV-002 registered and connected", "ago_hours": 120},
    {"event_type": "call.started",      "site_id": "SITE-006", "device_id": "DEV-006", "line_id": "LINE-006", "severity": "info", "message": "Outbound call initiated on LINE-006", "ago_hours": 6},
    {"event_type": "call.completed",    "site_id": "SITE-006", "device_id": "DEV-006", "line_id": "LINE-006", "severity": "info", "message": "Outbound call completed — 22s duration", "ago_hours": 6},
    {"event_type": "recording.available", "site_id": "SITE-006", "line_id": "LINE-006", "severity": "info",   "message": "Call recording available for LINE-006", "ago_hours": 6},
    {"event_type": "device.offline",    "site_id": "SITE-012", "device_id": "DEV-012", "severity": "critical", "message": "Device DEV-012 offline — 72h since last heartbeat", "ago_hours": 1},
    {"event_type": "system.info",       "severity": "info", "message": "Nightly maintenance completed — all systems healthy", "ago_hours": 8},
    {"event_type": "device.heartbeat",  "site_id": "SITE-004", "device_id": "DEV-004", "severity": "info",     "message": "Heartbeat OK — uptime 99.9%", "ago_hours": 0},
    {"event_type": "line.registered",   "site_id": "SITE-003", "device_id": "DEV-003", "line_id": "LINE-003", "severity": "info", "message": "Line LINE-003 cellular registration successful", "ago_hours": 72},
    {"event_type": "e911.validated",    "site_id": "SITE-004", "line_id": "LINE-004", "severity": "info",     "message": "E911 address validated for LINE-004", "ago_hours": 96},
]


async def seed():
    from .config import settings
    if settings.APP_MODE != "demo":
        print(f"APP_MODE={settings.APP_MODE} — skipping demo seed.")
        return

    async with AsyncSessionLocal() as db:
        # Check if already seeded
        existing = (await db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_ID))).scalar_one_or_none()
        if existing:
            print("Database already seeded. Skipping.")
            return

        # Tenant
        tenant = Tenant(tenant_id=TENANT_ID, name="TRUE911 Demo")
        db.add(tenant)
        await db.flush()

        # Users
        for u in USERS:
            db.add(User(
                email=u["email"],
                name=u["name"],
                role=u["role"],
                password_hash=hash_password(u["password"]),
                tenant_id=TENANT_ID,
            ))

        # Sites
        for s in SITES:
            db.add(Site(tenant_id=TENANT_ID, **s))

        # Telemetry
        for t in TELEMETRY:
            db.add(TelemetryEvent(
                event_id=uid("EVT"),
                site_id=t["site_id"],
                tenant_id=TENANT_ID,
                timestamp=ago(hours_ago=t["ago_hours"]),
                category=t["category"],
                severity=t["severity"],
                message=t["message"],
            ))

        # Audits
        for a in AUDITS:
            db.add(ActionAudit(
                audit_id=uid("AUD"),
                request_id=uid("REQ"),
                tenant_id=TENANT_ID,
                user_email=a["user_email"],
                requester_name=a["requester_name"],
                role=a["role"],
                action_type=a["action_type"],
                site_id=a["site_id"],
                timestamp=ago(minutes_ago=a["ago_minutes"]),
                result=a["result"],
                details=a["details"],
            ))

        # Incidents
        for i in INCIDENTS:
            opened_at = ago(hours_ago=i["opened_hours_ago"])
            db.add(Incident(
                incident_id=uid("INC"),
                site_id=i["site_id"],
                tenant_id=TENANT_ID,
                severity=i["severity"],
                status=i["status"],
                summary=i["summary"],
                opened_at=opened_at,
                ack_by=i.get("ack_by"),
                ack_at=ago(hours_ago=i["opened_hours_ago"] - 1) if i.get("ack_by") else None,
                created_by="system",
            ))

        # Notification Rules
        for n in NOTIFICATION_RULES:
            db.add(NotificationRule(
                rule_id=n["rule_id"],
                tenant_id=TENANT_ID,
                rule_name=n["rule_name"],
                rule_type=n["rule_type"],
                threshold_value=n["threshold_value"],
                threshold_unit=n["threshold_unit"],
                scope=n["scope"],
                channels=n["channels"],
                escalation_steps=n["escalation_steps"],
                enabled=n["enabled"],
                trigger_count=n.get("trigger_count", 0),
            ))

        # Devices
        for d in DEVICES:
            db.add(Device(tenant_id=TENANT_ID, **d))

        # Providers
        for p in PROVIDERS:
            db.add(Provider(tenant_id=TENANT_ID, **p))

        # Lines
        for ln in LINES:
            db.add(Line(tenant_id=TENANT_ID, **ln))

        # Recordings
        for r in RECORDINGS:
            _ln = LINES[r["line_idx"]]
            db.add(Recording(
                recording_id=uid("REC"),
                tenant_id=TENANT_ID,
                site_id=_ln["site_id"],
                device_id=_ln["device_id"],
                line_id=_ln["line_id"],
                provider=_ln["provider"],
                direction=r["direction"],
                duration_seconds=r["duration"],
                started_at=ago(hours_ago=r["ago_hours"]),
                caller=r["caller"],
                callee=r["callee"],
                status=r["status"],
            ))

        # Events (unified log)
        for e in EVENTS:
            db.add(Event(
                event_id=uid("EVT"),
                tenant_id=TENANT_ID,
                event_type=e["event_type"],
                site_id=e.get("site_id"),
                device_id=e.get("device_id"),
                line_id=e.get("line_id"),
                severity=e["severity"],
                message=e["message"],
                created_at=ago(hours_ago=e["ago_hours"]),
            ))

        await db.commit()
        print(f"Seeded: 1 tenant, {len(USERS)} users, {len(SITES)} sites, "
              f"{len(TELEMETRY)} telemetry events, {len(AUDITS)} audits, "
              f"{len(INCIDENTS)} incidents, {len(NOTIFICATION_RULES)} notification rules, "
              f"{len(DEVICES)} devices, {len(PROVIDERS)} providers, "
              f"{len(LINES)} lines, {len(RECORDINGS)} recordings, "
              f"{len(EVENTS)} events.")


if __name__ == "__main__":
    asyncio.run(seed())
