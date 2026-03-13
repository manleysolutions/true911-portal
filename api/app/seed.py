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
from .models.command_activity import CommandActivity
from .models.notification import CommandNotification
from .models.escalation_rule import EscalationRule
from .models.command_telemetry import CommandTelemetry
from .models.line import Line
from .models.recording import Recording
from .models.event import Event
from .models.provider import Provider
from .models.hardware_model import HardwareModel
from .models.integration import Integration, IntegrationAccount
from .models.sim import Sim
from .models.device_sim import DeviceSim
from .models.vendor import Vendor
from .models.site_vendor import SiteVendorAssignment
from .models.verification_task import VerificationTask
from .models.automation_rule import AutomationRule
from .models.site_template import SiteTemplate
from .models.service_contract import ServiceContract
from .models.network_event import NetworkEvent
from .models.infra_test import InfraTest
from .models.infra_test_result import InfraTestResult
from .models.audit_log_entry import AuditLogEntry
from .models.autonomous_action import AutonomousAction
from .models.operational_digest import OperationalDigest
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
    {"site_id": "SITE-024", "site_name": "Abilene Fire #1", "customer_name": "City of Abilene", "status": "Connected", "firmware_version": "3.2.1", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=6), "e911_street": "555 Walnut St", "e911_city": "Abilene", "e911_state": "TX", "e911_zip": "79601", "lat": None, "lng": None, "heartbeat_interval": 5, "uptime_percent": 98.3},
    {"site_id": "SITE-025", "site_name": "Beaumont EMS Central", "customer_name": "Jefferson County", "status": "Connected", "firmware_version": "3.2.0", "csa_model": "CSA-500", "last_checkin": ago(minutes_ago=11), "e911_street": "801 Main St", "e911_city": "Beaumont", "e911_state": "TX", "e911_zip": "77701", "lat": None, "lng": None, "heartbeat_interval": 5, "uptime_percent": 97.1},
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

COMMAND_INCIDENTS = [
    {"site_id": "SITE-001", "severity": "warning", "status": "acknowledged", "incident_type": "fire_alarm_comm",
     "source": "monitoring", "summary": "Fire alarm communicator latency exceeding threshold — 450ms avg",
     "location_detail": "Floor 3, FACP Room", "opened_hours_ago": 4, "ack_by": "Sarah Chen",
     "assigned_to": "Mike Torres"},
    {"site_id": "SITE-003", "severity": "critical", "status": "new", "incident_type": "elevator_phone_fail",
     "source": "verification", "summary": "Elevator emergency phone verification failed — no dial tone on line test",
     "location_detail": "Floor 12, Elevator Bank A", "opened_hours_ago": 2},
    {"site_id": "SITE-005", "severity": "critical", "status": "in_progress", "incident_type": "das_signal_loss",
     "source": "monitoring", "summary": "DAS responder radio signal lost in sub-basement — BDA offline",
     "location_detail": "Sub-basement B2", "opened_hours_ago": 8, "ack_by": "Mike Torres",
     "assigned_to": "Mike Torres"},
    {"site_id": "SITE-008", "severity": "warning", "status": "new", "incident_type": "call_station_offline",
     "source": "heartbeat", "summary": "Emergency call station offline — missed 6 consecutive heartbeats",
     "location_detail": "Parking Garage Level P3", "opened_hours_ago": 1},
    {"site_id": "SITE-012", "severity": "critical", "status": "acknowledged", "incident_type": "backup_power_fail",
     "source": "monitoring", "summary": "UPS battery bank failure — backup power at 0% capacity",
     "location_detail": "Electrical Room ER-1", "opened_hours_ago": 6, "ack_by": "Sarah Chen"},
    {"site_id": "SITE-016", "severity": "info", "status": "resolved", "incident_type": "fire_alarm_comm",
     "source": "verification", "summary": "Fire alarm annual verification completed — all panels passed",
     "location_detail": "All floors", "opened_hours_ago": 24, "resolved": True},
    {"site_id": "SITE-020", "severity": "warning", "status": "dismissed", "incident_type": "elevator_phone_fail",
     "source": "monitoring", "summary": "Elevator phone intermittent static — cleared after line reset",
     "location_detail": "Floor 5, Service Elevator", "opened_hours_ago": 36, "dismissed": True},
]

COMMAND_ACTIVITIES = [
    {"activity_type": "incident_created", "site_id": "SITE-003", "actor": "system",
     "summary": "Incident created: Elevator emergency phone verification failed", "ago_minutes": 120},
    {"activity_type": "incident_created", "site_id": "SITE-005", "actor": "system",
     "summary": "Incident created: DAS responder radio signal lost in sub-basement", "ago_minutes": 480},
    {"activity_type": "incident_acknowledged", "site_id": "SITE-005", "actor": "manager@true911.com",
     "summary": "Incident acknowledged by Mike Torres", "ago_minutes": 450},
    {"activity_type": "incident_in_progress", "site_id": "SITE-005", "actor": "manager@true911.com",
     "summary": "Incident assigned to Mike Torres — dispatching technician", "ago_minutes": 420},
    {"activity_type": "incident_acknowledged", "site_id": "SITE-001", "actor": "admin@true911.com",
     "summary": "Fire alarm communicator latency acknowledged by Sarah Chen", "ago_minutes": 200},
    {"activity_type": "incident_assigned", "site_id": "SITE-001", "actor": "admin@true911.com",
     "summary": "Incident assigned to Mike Torres", "ago_minutes": 190},
    {"activity_type": "incident_resolved", "site_id": "SITE-016", "actor": "admin@true911.com",
     "summary": "Fire alarm verification completed and resolved", "ago_minutes": 60},
    {"activity_type": "incident_dismissed", "site_id": "SITE-020", "actor": "admin@true911.com",
     "summary": "Elevator phone static issue dismissed — self-resolved", "ago_minutes": 30},
    {"activity_type": "readiness_recalculated", "actor": "system",
     "summary": "Portfolio readiness score recalculated: 74% — Attention Needed", "ago_minutes": 15},
    {"activity_type": "incident_created", "site_id": "SITE-008", "actor": "system",
     "summary": "Emergency call station offline — missed heartbeats", "ago_minutes": 60},
]

ESCALATION_RULES = [
    {"name": "Critical — 15min escalation", "severity": "critical", "escalate_after_minutes": 15, "escalation_target": "Admin", "notify_channel": "in_app"},
    {"name": "Critical — 30min supervisor", "severity": "critical", "escalate_after_minutes": 30, "escalation_target": "admin@true911.com", "notify_channel": "in_app"},
    {"name": "Warning — 60min escalation", "severity": "warning", "escalate_after_minutes": 60, "escalation_target": "Manager", "notify_channel": "in_app"},
]

COMMAND_NOTIFICATIONS = [
    {"severity": "critical", "title": "New critical incident: Elevator emergency phone verification failed", "site_id": "SITE-003", "ago_minutes": 120},
    {"severity": "critical", "title": "Escalation L1: DAS responder radio signal lost in sub-basement", "site_id": "SITE-005", "ago_minutes": 100},
    {"severity": "warning", "title": "Emergency call station offline — missed heartbeats", "site_id": "SITE-008", "ago_minutes": 60},
    {"severity": "info", "title": "Fire alarm verification completed — all panels passed", "site_id": "SITE-016", "ago_minutes": 30, "read": True},
    {"severity": "warning", "title": "UPS battery bank failure — backup power at 0%", "site_id": "SITE-012", "ago_minutes": 360},
    {"severity": "info", "title": "Portfolio readiness score recalculated: 74%", "ago_minutes": 15},
]

COMMAND_TELEMETRY_DATA = [
    {"device_id": "DEV-001", "site_id": "SITE-001", "signal_strength": -45.0, "battery_pct": 98.0, "uptime_seconds": 864000, "temperature_c": 24.5, "error_count": 0, "ago_minutes": 5},
    {"device_id": "DEV-002", "site_id": "SITE-002", "signal_strength": -52.0, "battery_pct": 95.0, "uptime_seconds": 720000, "temperature_c": 23.1, "error_count": 0, "ago_minutes": 10},
    {"device_id": "DEV-003", "site_id": "SITE-003", "signal_strength": -68.0, "battery_pct": 72.0, "uptime_seconds": 432000, "temperature_c": 27.3, "error_count": 3, "ago_minutes": 15},
    {"device_id": "DEV-005", "site_id": "SITE-005", "signal_strength": -95.0, "battery_pct": 8.0, "uptime_seconds": 0, "temperature_c": 31.2, "error_count": 42, "ago_minutes": 2880},
    {"device_id": "DEV-008", "site_id": "SITE-008", "signal_strength": -78.0, "battery_pct": 45.0, "uptime_seconds": 172800, "temperature_c": 29.8, "error_count": 7, "ago_minutes": 30},
    {"device_id": "DEV-012", "site_id": "SITE-012", "signal_strength": -92.0, "battery_pct": 12.0, "uptime_seconds": 0, "temperature_c": 35.0, "error_count": 28, "ago_minutes": 4320},
    {"device_id": "DEV-004", "site_id": "SITE-004", "signal_strength": -40.0, "battery_pct": 100.0, "uptime_seconds": 950000, "temperature_c": 22.0, "error_count": 0, "ago_minutes": 3},
    {"device_id": "DEV-007", "site_id": "SITE-007", "signal_strength": -48.0, "battery_pct": 97.0, "uptime_seconds": 800000, "temperature_c": 23.5, "error_count": 0, "ago_minutes": 8},
    {"device_id": "DEV-009", "site_id": "SITE-009", "signal_strength": -55.0, "battery_pct": 91.0, "uptime_seconds": 650000, "temperature_c": 25.0, "error_count": 1, "ago_minutes": 12},
    {"device_id": "DEV-010", "site_id": "SITE-010", "signal_strength": -60.0, "battery_pct": 88.0, "uptime_seconds": 550000, "temperature_c": 26.0, "error_count": 2, "ago_minutes": 20},
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
        "hardware_model_id": "flyingvoice-pr12",
        "serial_number": f"SN-{_idx + 1:04d}-{uuid.uuid4().hex[:6].upper()}",
        "mac_address": ":".join(f"{b:02X}" for b in [0x00, 0x1A, 0x2B, _idx, (_idx * 7) % 256, (_idx * 13) % 256]),
        "imei": f"35{_idx:013d}",
        "firmware_version": _s.get("firmware_version", "3.2.1"),
        "container_version": "1.4.2",
        "last_heartbeat": _s.get("last_checkin"),
        "heartbeat_interval": _s.get("heartbeat_interval", 5),
    })


HARDWARE_MODELS = [
    # Cellular modem devices (IMEI / SIM required)
    {"id": "etross-ms130v4",   "manufacturer": "ETROSS",        "model_name": "MS130v4 (ETROSS 8848)",      "device_type": "Cellular Modem"},
    {"id": "atel-ms130v5",     "manufacturer": "ATEL",          "model_name": "MS130v5 (ATEL V810V)",       "device_type": "Cellular Modem"},
    {"id": "flyingvoice-pr12", "manufacturer": "Flying Voice",  "model_name": "PR12 (Flying Voice / Vola)", "device_type": "Cellular Router"},
    {"id": "inseego-fw3100",   "manufacturer": "Inseego",       "model_name": "Inseego FW3100",             "device_type": "Cellular Router"},
    # Napco StarLink devices (StarLink ID — no SIM/IMEI)
    {"id": "napco-slelte",     "manufacturer": "Napco",         "model_name": "SLELTE",                     "device_type": "StarLink Communicator"},
    {"id": "napco-sle5g",      "manufacturer": "Napco",         "model_name": "SLE5G",                      "device_type": "StarLink Communicator"},
    # ATA / appliance devices (serial + MAC — no SIM/IMEI)
    {"id": "cisco-ata191",     "manufacturer": "Cisco",         "model_name": "ATA191",                     "device_type": "ATA"},
    {"id": "cisco-ata192",     "manufacturer": "Cisco",         "model_name": "ATA192",                     "device_type": "ATA"},
    # CSA units
    {"id": "rtl-csa-v1",       "manufacturer": "Red Tag Lines", "model_name": "CSA v1",                     "device_type": "CSA"},
    {"id": "rtl-csa-v1-4p",    "manufacturer": "Red Tag Lines", "model_name": "CSA v1 4-Port",              "device_type": "CSA"},
    # Catch-all
    {"id": "other",            "manufacturer": "Other",         "model_name": "Other",                      "device_type": "Other"},
]

INTEGRATIONS = [
    {"slug": "telnyx", "display_name": "Telnyx", "category": "sip", "base_url": "https://api.telnyx.com/v2", "docs_url": "https://developers.telnyx.com", "enabled": True},
    {"slug": "vola", "display_name": "VolaCloud", "category": "hardware", "base_url": "https://api.volacloud.com/v1", "docs_url": "https://docs.volacloud.com", "enabled": True},
    {"slug": "tmobile", "display_name": "T-Mobile IoT", "category": "carrier", "base_url": "https://api.t-mobile.com/iot/v1", "docs_url": "https://developer.t-mobile.com", "enabled": True},
]

# Demo SIMs — one per first 10 devices
SIMS = []
_sim_configs = [
    # carrier, msisdn, iccid, imsi, status, plan, apn, notes
    ("verizon",  "+12145550201", "8914800000000000001", "311480000000001", "active",    "ThingSpace IoT 1GB",  "vzwinternet",       "Verizon primary SIM - Dallas site"),
    ("verizon",  "+15125550202", "8914800000000000002", "311480000000002", "active",    "ThingSpace IoT 1GB",  "vzwinternet",       "Verizon SIM - Austin site"),
    ("verizon",  "+17135550203", "8914800000000000003", "311480000000003", "inventory", "ThingSpace IoT 500MB","vzwinternet",       "Verizon spare SIM - unassigned"),
    ("tmobile",  "+12105550204", "8901260882902000004", "310260000000004", "active",    "T-Mobile IoT 500MB",  "fast.t-mobile.com", "T-Mobile SIM - San Antonio site"),
    ("tmobile",  "+18175550205", "8901260882902000005", "310260000000005", "suspended", "T-Mobile IoT 500MB",  "fast.t-mobile.com", "T-Mobile SIM - suspended for billing"),
    ("att",      "+19155550206", "8901410000000000006", "310410000000006", "active",    "AT&T IoT DataConnect", "broadband",        "AT&T SIM - El Paso site"),
    ("verizon",  "+14695550207", "8914800000000000007", "311480000000007", "active",    "ThingSpace IoT 1GB",  "vzwinternet",       None),
    ("tmobile",  "+18175550208", "8901260882902000008", "310260000000008", "active",    "T-Mobile IoT 1GB",    "fast.t-mobile.com", None),
    ("telnyx",   "+13615550209", "8942110000000000009", None,              "active",    "Global IoT",          None,                None),
    ("tmobile",  "+18065550210", "8901260882902000010", "310260000000010", "inventory", "T-Mobile IoT 500MB",  "fast.t-mobile.com", "Spare SIM for field kit"),
]
for _i, (_carrier, _msisdn, _iccid, _imsi, _st, _plan, _apn, _notes) in enumerate(_sim_configs):
    SIMS.append({
        "iccid": _iccid,
        "msisdn": _msisdn,
        "imsi": _imsi,
        "carrier": _carrier,
        "status": _st,
        "plan": _plan,
        "apn": _apn or None,
        "notes": _notes,
    })

PROVIDERS = [
    {"provider_id": "PROV-001", "provider_type": "telnyx", "display_name": "Telnyx SIP Trunking", "category": "sip", "enabled": True, "config_json": {"region": "us-central", "sip_connection_id": "demo-conn-001"}},
    {"provider_id": "PROV-002", "provider_type": "tmobile", "display_name": "T-Mobile IoT SIM", "category": "carrier", "enabled": True, "config_json": {"plan": "iot-500mb", "apn": "fast.t-mobile.com"}},
    {"provider_id": "PROV-003", "provider_type": "bandwidth", "display_name": "Bandwidth Voice", "category": "sip", "enabled": False, "config_json": None},
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


# -- Phase 4 seed data --

VENDORS = [
    {"name": "FireGuard Systems", "vendor_type": "fire_alarm", "contact_name": "James Walker", "contact_email": "jwalker@fireguard.com", "contact_phone": "+1-214-555-0101", "specialties_json": '["fire_alarm", "monitoring"]'},
    {"name": "Kone Elevator Services", "vendor_type": "elevator", "contact_name": "Lisa Chen", "contact_email": "lchen@kone.com", "contact_phone": "+1-972-555-0202", "specialties_json": '["elevator_phone", "elevator_monitoring"]'},
    {"name": "DAS Solutions Inc", "vendor_type": "radio", "contact_name": "Robert Martinez", "contact_email": "rmartinez@dassolutions.com", "contact_phone": "+1-817-555-0303", "specialties_json": '["das_radio", "signal_boosting"]'},
    {"name": "SecureComm Electric", "vendor_type": "electrical", "contact_name": "Amanda Hayes", "contact_email": "ahayes@securecomm.com", "contact_phone": "+1-469-555-0404", "specialties_json": '["backup_power", "electrical"]'},
]

SITE_VENDOR_ASSIGNMENTS = [
    {"site_id": "SITE-001", "vendor_idx": 0, "system_category": "fire_alarm", "is_primary": True},
    {"site_id": "SITE-001", "vendor_idx": 1, "system_category": "elevator_phone", "is_primary": True},
    {"site_id": "SITE-002", "vendor_idx": 0, "system_category": "fire_alarm", "is_primary": True},
    {"site_id": "SITE-003", "vendor_idx": 0, "system_category": "fire_alarm", "is_primary": True},
    {"site_id": "SITE-003", "vendor_idx": 2, "system_category": "das_radio", "is_primary": True},
    {"site_id": "SITE-004", "vendor_idx": 0, "system_category": "fire_alarm", "is_primary": True},
    {"site_id": "SITE-005", "vendor_idx": 3, "system_category": "backup_power", "is_primary": True},
    {"site_id": "SITE-008", "vendor_idx": 0, "system_category": "fire_alarm", "is_primary": True},
]

VERIFICATION_TASKS = [
    {"site_id": "SITE-001", "task_type": "annual_inspection", "title": "Annual FACP Inspection", "description": "Fire alarm control panel annual test per NFPA 72", "system_category": "fire_alarm", "priority": "high", "status": "completed", "result": "pass", "due_days_ago": 10, "completed_days_ago": 12},
    {"site_id": "SITE-001", "task_type": "line_test", "title": "E911 Line Test", "description": "Verify E911 line connectivity and PSAP routing", "system_category": "call_station", "priority": "medium", "status": "completed", "result": "pass", "due_days_ago": 5, "completed_days_ago": 6},
    {"site_id": "SITE-002", "task_type": "annual_inspection", "title": "Annual FACP Inspection", "system_category": "fire_alarm", "priority": "high", "status": "pending", "due_days_ago": -15},
    {"site_id": "SITE-003", "task_type": "signal_test", "title": "DAS Signal Coverage Test", "description": "Verify responder radio coverage meets AHJ requirements", "system_category": "das_radio", "priority": "high", "status": "pending", "due_days_ago": 3},
    {"site_id": "SITE-003", "task_type": "battery_test", "title": "UPS Battery Load Test", "system_category": "backup_power", "priority": "medium", "status": "in_progress", "due_days_ago": -5},
    {"site_id": "SITE-005", "task_type": "annual_inspection", "title": "Annual System Inspection", "system_category": "fire_alarm", "priority": "high", "status": "pending", "due_days_ago": 20},
    {"site_id": "SITE-005", "task_type": "line_test", "title": "E911 Line Verification", "system_category": "call_station", "priority": "high", "status": "pending", "due_days_ago": 15},
    {"site_id": "SITE-008", "task_type": "firmware_update", "title": "Firmware Update Verification", "description": "Verify firmware update to v3.2.1 completed successfully", "system_category": "other", "priority": "medium", "status": "pending", "due_days_ago": 1},
    {"site_id": "SITE-012", "task_type": "connectivity_check", "title": "Connectivity Restoration Check", "description": "Verify site connectivity after outage", "system_category": "other", "priority": "high", "status": "pending", "due_days_ago": 5},
    {"site_id": "SITE-004", "task_type": "annual_inspection", "title": "Annual FACP Inspection", "system_category": "fire_alarm", "priority": "high", "status": "completed", "result": "pass", "due_days_ago": 30, "completed_days_ago": 32},
    {"site_id": "SITE-007", "task_type": "line_test", "title": "Quarterly Line Test", "system_category": "call_station", "priority": "medium", "status": "completed", "result": "pass", "due_days_ago": 7, "completed_days_ago": 8},
]

AUTOMATION_RULES = [
    {"name": "Heartbeat Missing > 30min", "description": "Create incident when device heartbeat exceeds 30 minutes", "trigger_type": "heartbeat_missing", "condition_json": '{"threshold_minutes": 30}', "action_type": "create_incident", "action_config_json": '{"severity": "warning"}', "enabled": True},
    {"name": "Critical Incident Unresolved > 2h", "description": "Notify admin when critical incidents remain unresolved for 2+ hours", "trigger_type": "incident_unresolved", "condition_json": '{"threshold_minutes": 120, "severity": "critical"}', "action_type": "notify", "action_config_json": '{"notify_role": "Admin", "notify_target": "admin@true911.com"}', "enabled": True},
    {"name": "Verification Overdue Alert", "description": "Daily alert when verification tasks are past due", "trigger_type": "verification_overdue", "condition_json": '{}', "action_type": "notify", "action_config_json": '{"notify_role": "Admin"}', "enabled": True},
]


async def seed():
    from .config import settings
    if settings.SEED_DEMO.lower() != "true":
        print(f"SEED_DEMO={settings.SEED_DEMO} — skipping demo seed.")
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

        # Command Incidents (Phase 2)
        for ci in COMMAND_INCIDENTS:
            opened_at = ago(hours_ago=ci["opened_hours_ago"])
            inc_obj = Incident(
                incident_id=uid("CMD"),
                site_id=ci["site_id"],
                tenant_id=TENANT_ID,
                severity=ci["severity"],
                status=ci["status"],
                summary=ci["summary"],
                incident_type=ci.get("incident_type"),
                source=ci.get("source", "command"),
                location_detail=ci.get("location_detail"),
                opened_at=opened_at,
                ack_by=ci.get("ack_by"),
                ack_at=ago(hours_ago=ci["opened_hours_ago"] - 1) if ci.get("ack_by") else None,
                assigned_to=ci.get("assigned_to"),
                resolved_at=ago(hours_ago=1) if ci.get("resolved") else None,
                closed_at=ago(hours_ago=1) if ci.get("resolved") or ci.get("dismissed") else None,
                created_by="system",
            )
            db.add(inc_obj)

        # Command Activities (Phase 2)
        for ca in COMMAND_ACTIVITIES:
            db.add(CommandActivity(
                tenant_id=TENANT_ID,
                activity_type=ca["activity_type"],
                site_id=ca.get("site_id"),
                actor=ca.get("actor"),
                summary=ca["summary"],
                created_at=ago(minutes_ago=ca["ago_minutes"]),
            ))

        # Escalation Rules (Phase 3)
        for er in ESCALATION_RULES:
            db.add(EscalationRule(tenant_id=TENANT_ID, **er))

        # Command Notifications (Phase 3)
        for cn in COMMAND_NOTIFICATIONS:
            db.add(CommandNotification(
                tenant_id=TENANT_ID,
                channel="in_app",
                severity=cn["severity"],
                title=cn["title"],
                site_id=cn.get("site_id"),
                read=cn.get("read", False),
                created_at=ago(minutes_ago=cn["ago_minutes"]),
            ))

        # Command Telemetry (Phase 3)
        for ct in COMMAND_TELEMETRY_DATA:
            db.add(CommandTelemetry(
                tenant_id=TENANT_ID,
                device_id=ct["device_id"],
                site_id=ct["site_id"],
                signal_strength=ct.get("signal_strength"),
                battery_pct=ct.get("battery_pct"),
                uptime_seconds=ct.get("uptime_seconds"),
                temperature_c=ct.get("temperature_c"),
                error_count=ct.get("error_count", 0),
                recorded_at=ago(minutes_ago=ct["ago_minutes"]),
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

        # Hardware Models
        for hm in HARDWARE_MODELS:
            db.add(HardwareModel(**hm))

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

        # Integrations
        integration_ids = {}
        for intg in INTEGRATIONS:
            obj = Integration(**intg)
            db.add(obj)
            await db.flush()
            integration_ids[intg["slug"]] = obj.id

        # Integration Accounts (demo credentials)
        for slug, intg_id in integration_ids.items():
            db.add(IntegrationAccount(
                tenant_id=TENANT_ID,
                integration_id=intg_id,
                label=f"Demo {slug} account",
                api_key_encrypted="demo-key-not-real",
                enabled=True,
            ))

        # SIMs
        sim_objects = []
        for s in SIMS:
            obj = Sim(tenant_id=TENANT_ID, **s)
            db.add(obj)
            sim_objects.append(obj)
        await db.flush()

        # Device-SIM assignments (first 9 active SIMs → first 9 devices)
        # We need device PKs — query them
        from sqlalchemy import select as sel
        dev_rows = (await db.execute(
            sel(Device).where(Device.tenant_id == TENANT_ID).order_by(Device.id).limit(10)
        )).scalars().all()
        for idx, sim_obj in enumerate(sim_objects):
            if idx < len(dev_rows) and sim_obj.status == "active":
                db.add(DeviceSim(
                    device_id=dev_rows[idx].id,
                    sim_id=sim_obj.id,
                    slot=1,
                    active=True,
                    assigned_by="seed",
                ))

        # Vendors (Phase 4)
        vendor_objects = []
        for v in VENDORS:
            obj = Vendor(tenant_id=TENANT_ID, **v)
            db.add(obj)
            vendor_objects.append(obj)
        await db.flush()

        # Site Vendor Assignments (Phase 4)
        for sva in SITE_VENDOR_ASSIGNMENTS:
            db.add(SiteVendorAssignment(
                tenant_id=TENANT_ID,
                site_id=sva["site_id"],
                vendor_id=vendor_objects[sva["vendor_idx"]].id,
                system_category=sva["system_category"],
                is_primary=sva["is_primary"],
            ))

        # Verification Tasks (Phase 4)
        now = datetime.now(timezone.utc)
        for vt in VERIFICATION_TASKS:
            due_date = now - timedelta(days=vt["due_days_ago"]) if "due_days_ago" in vt else None
            completed_at = now - timedelta(days=vt["completed_days_ago"]) if vt.get("completed_days_ago") else None
            db.add(VerificationTask(
                tenant_id=TENANT_ID,
                site_id=vt["site_id"],
                task_type=vt["task_type"],
                title=vt["title"],
                description=vt.get("description"),
                system_category=vt.get("system_category"),
                priority=vt["priority"],
                status=vt["status"],
                due_date=due_date,
                result=vt.get("result"),
                completed_at=completed_at,
                completed_by="admin@true911.com" if completed_at else None,
                created_by="admin@true911.com",
            ))

        # Automation Rules (Phase 4)
        for ar in AUTOMATION_RULES:
            db.add(AutomationRule(tenant_id=TENANT_ID, **ar))

        # Site Templates (Phase 5) — global built-in templates
        from .services.template_engine import BUILTIN_TEMPLATES
        for tmpl in BUILTIN_TEMPLATES:
            db.add(SiteTemplate(
                tenant_id=None,
                is_global=True,
                created_by="system",
                **tmpl,
            ))
        await db.flush()

        # Service Contracts (Phase 5)
        for i, v_obj in enumerate(vendor_objects):
            db.add(ServiceContract(
                tenant_id=TENANT_ID,
                vendor_id=v_obj.id,
                contract_type="annual_maintenance",
                description=f"Annual maintenance contract with {v_obj.name}",
                start_date=ago(days_ago=180),
                end_date=ago(days_ago=-185),
                sla_response_minutes=60 if i < 2 else 120,
                sla_resolution_hours=24 if i < 2 else 48,
                status="active",
            ))

        # ── Phase 7: Network events, infra tests, audit entries ──────
        NETWORK_EVENTS = [
            {"device_id": DEVICES[0]["device_id"], "site_id": SITES[0]["site_id"], "carrier": "t-mobile",
             "event_type": "signal_degradation", "severity": "warning",
             "summary": "Signal at -102 dBm", "signal_dbm": -102.0},
            {"device_id": DEVICES[1]["device_id"], "site_id": SITES[1]["site_id"], "carrier": "verizon",
             "event_type": "device_disconnected", "severity": "critical",
             "summary": "Device disconnected from network"},
            {"device_id": DEVICES[2]["device_id"], "site_id": SITES[2]["site_id"], "carrier": "att",
             "event_type": "roaming_detected", "severity": "warning",
             "summary": "Device roaming on AT&T", "roaming": True},
        ]
        for ne in NETWORK_EVENTS:
            db.add(NetworkEvent(
                event_id=uid("NE"),
                tenant_id=TENANT_ID,
                **ne,
            ))

        INFRA_TESTS = [
            {"name": "Voice Path — Site 1", "test_type": "voice_path",
             "site_id": SITES[0]["site_id"], "device_id": DEVICES[0]["device_id"],
             "description": "End-to-end voice path test", "schedule_cron": "0 6 * * *"},
            {"name": "Emergency Call — Site 2", "test_type": "emergency_call",
             "site_id": SITES[1]["site_id"],
             "description": "E911 call routing verification", "schedule_cron": "0 0 1 * *"},
            {"name": "Heartbeat Check — Site 3", "test_type": "heartbeat_verify",
             "site_id": SITES[2]["site_id"], "device_id": DEVICES[2]["device_id"],
             "description": "Heartbeat timing validation"},
            {"name": "Connectivity — Site 1", "test_type": "connectivity",
             "site_id": SITES[0]["site_id"],
             "description": "Network connectivity and latency test", "run_after_provision": True},
            {"name": "Radio Coverage — Site 4", "test_type": "radio_coverage",
             "site_id": SITES[3]["site_id"],
             "description": "Cellular coverage quality check"},
        ]
        for it in INFRA_TESTS:
            db.add(InfraTest(
                test_id=uid("IT"),
                tenant_id=TENANT_ID,
                **it,
            ))

        AUDIT_ENTRIES = [
            {"category": "device", "action": "device_registered", "actor": "admin@true911.com",
             "target_type": "device", "target_id": DEVICES[0]["device_id"],
             "summary": f"Device {DEVICES[0]['device_id']} registered"},
            {"category": "firmware", "action": "firmware_updated", "actor": "system",
             "target_type": "device", "target_id": DEVICES[1]["device_id"],
             "summary": f"Firmware updated to v2.1.0 on {DEVICES[1]['device_id']}"},
            {"category": "incident", "action": "incident_escalated", "actor": "admin@true911.com",
             "target_type": "incident", "summary": "Incident escalated to level 2"},
            {"category": "network", "action": "carrier_telemetry_ingested", "actor": "system",
             "device_id": DEVICES[0]["device_id"],
             "summary": "Carrier telemetry ingested from T-Mobile"},
            {"category": "verification", "action": "infra_test_executed", "actor": "admin@true911.com",
             "site_id": SITES[0]["site_id"],
             "summary": "Voice path test executed — result: pass"},
        ]
        for ae in AUDIT_ENTRIES:
            db.add(AuditLogEntry(
                entry_id=uid("AU"),
                tenant_id=TENANT_ID,
                **ae,
            ))

        # ── Phase 8: Autonomous actions & operational digests ─────────
        import json as _json

        AUTO_ACTIONS = [
            {"action_type": "incident_created", "trigger_source": "autonomous_engine",
             "site_id": SITES[0]["site_id"], "device_id": DEVICES[0]["device_id"],
             "summary": "Incident AUTO-DEMO0001 created for device offline",
             "incident_id": "AUTO-DEMO0001", "status": "completed", "result": "incident_opened"},
            {"action_type": "diagnostic_executed", "trigger_source": "autonomous_engine",
             "site_id": SITES[0]["site_id"], "device_id": DEVICES[0]["device_id"],
             "summary": "Diagnostic 'Voice Path' executed — result: pass",
             "status": "completed", "result": "pass"},
            {"action_type": "incident_routed", "trigger_source": "autonomous_engine",
             "site_id": SITES[1]["site_id"],
             "summary": "Incident routed to vendor technician",
             "incident_id": "AUTO-DEMO0002", "status": "completed"},
            {"action_type": "self_heal_device_reboot", "trigger_source": "self_healing_engine",
             "site_id": SITES[2]["site_id"], "device_id": DEVICES[2]["device_id"],
             "summary": "Self-heal device_reboot attempted — resolved",
             "status": "completed", "result": "resolved"},
            {"action_type": "escalations_processed", "trigger_source": "escalation_autopilot",
             "summary": "2 incident(s) escalated",
             "status": "completed"},
            {"action_type": "verifications_scheduled", "trigger_source": "verification_scheduler",
             "summary": "3 verification task(s) auto-scheduled",
             "status": "completed"},
            {"action_type": "problem_verified", "trigger_source": "device_monitor",
             "site_id": SITES[3]["site_id"], "device_id": DEVICES[3]["device_id"] if len(DEVICES) > 3 else DEVICES[0]["device_id"],
             "summary": "Problem verified for device — heartbeat overdue",
             "status": "completed", "result": "confirmed"},
            {"action_type": "readiness_recalculated", "trigger_source": "autonomous_engine",
             "summary": "Portfolio readiness recalculated after autonomous cycle",
             "status": "completed"},
        ]
        for aa in AUTO_ACTIONS:
            db.add(AutonomousAction(
                action_id=uid("AA"),
                tenant_id=TENANT_ID,
                **aa,
            ))

        DIGESTS = [
            {"digest_type": "daily",
             "period_start": ago(days_ago=1),
             "period_end": ago(),
             "summary_json": _json.dumps({
                 "period": "daily", "sites_total": 25, "sites_needing_attention": 3,
                 "devices_total": 10, "devices_offline": 1,
                 "verification_tasks_due": 4, "verification_tasks_overdue": 1,
                 "incidents_opened": 2, "incidents_resolved": 1,
                 "incidents_currently_open": 3, "autonomous_actions": 8,
             })},
            {"digest_type": "weekly",
             "period_start": ago(days_ago=7),
             "period_end": ago(),
             "summary_json": _json.dumps({
                 "period": "weekly",
                 "incidents": {"opened": 5, "resolved": 4, "trend": "decreasing",
                               "prev_opened": 7, "prev_resolved": 5},
                 "devices": {"total": 10, "active": 9, "health_pct": 90.0},
                 "verifications": {"completed": 6, "pending": 3},
                 "autonomous_ops": {"total_actions": 18, "self_heals_resolved": 2},
             })},
        ]
        for dg in DIGESTS:
            db.add(OperationalDigest(
                digest_id=uid("DG"),
                tenant_id=TENANT_ID,
                **dg,
            ))

        await db.commit()
        print(f"Seeded: 1 tenant, {len(USERS)} users, {len(SITES)} sites, "
              f"{len(TELEMETRY)} telemetry events, {len(AUDITS)} audits, "
              f"{len(INCIDENTS)} + {len(COMMAND_INCIDENTS)} incidents, "
              f"{len(COMMAND_ACTIVITIES)} command activities, "
              f"{len(ESCALATION_RULES)} escalation rules, "
              f"{len(COMMAND_NOTIFICATIONS)} command notifications, "
              f"{len(COMMAND_TELEMETRY_DATA)} command telemetry snapshots, "
              f"{len(NOTIFICATION_RULES)} notification rules, "
              f"{len(HARDWARE_MODELS)} hardware models, {len(DEVICES)} devices, "
              f"{len(PROVIDERS)} providers, {len(LINES)} lines, "
              f"{len(RECORDINGS)} recordings, {len(EVENTS)} events, "
              f"{len(INTEGRATIONS)} integrations, {len(SIMS)} SIMs, "
              f"{len(VENDORS)} vendors, {len(SITE_VENDOR_ASSIGNMENTS)} vendor assignments, "
              f"{len(VERIFICATION_TASKS)} verification tasks, {len(AUTOMATION_RULES)} automation rules, "
              f"{len(BUILTIN_TEMPLATES)} site templates, {len(VENDORS)} service contracts, "
              f"{len(NETWORK_EVENTS)} network events, {len(INFRA_TESTS)} infra tests, "
              f"{len(AUDIT_ENTRIES)} audit entries, "
              f"{len(AUTO_ACTIONS)} autonomous actions, {len(DIGESTS)} digests.")


if __name__ == "__main__":
    asyncio.run(seed())
