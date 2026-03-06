"""
True911 — Site template engine.

Applies a site template to initialize verification tasks,
automation rules, and vendor assignments for a new site.
"""

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.site_template import SiteTemplate
from ..models.verification_task import VerificationTask
from ..models.automation_rule import AutomationRule
from ..models.command_activity import CommandActivity


async def apply_template(
    db: AsyncSession,
    template: SiteTemplate,
    site_id: str,
    tenant_id: str,
    created_by: str,
):
    """Apply a site template to a newly created site.

    Creates verification tasks and monitoring rules defined in the template.
    Returns a summary of what was created.
    """
    results = {"verification_tasks": 0, "automation_rules": 0}
    now = datetime.now(timezone.utc)

    # Create verification tasks from template
    if template.verification_tasks_json:
        try:
            tasks = json.loads(template.verification_tasks_json)
        except (json.JSONDecodeError, TypeError):
            tasks = []

        for task_def in tasks:
            due_days = task_def.get("due_days", 30)
            db.add(VerificationTask(
                tenant_id=tenant_id,
                site_id=site_id,
                task_type=task_def.get("task_type", "inspection"),
                title=task_def.get("title", "Verification Task"),
                description=task_def.get("description"),
                system_category=task_def.get("system_category"),
                priority=task_def.get("priority", "medium"),
                due_date=now + timedelta(days=due_days),
                created_by=created_by,
            ))
            results["verification_tasks"] += 1

    # Create monitoring/automation rules from template
    if template.monitoring_rules_json:
        try:
            rules = json.loads(template.monitoring_rules_json)
        except (json.JSONDecodeError, TypeError):
            rules = []

        for rule_def in rules:
            condition = rule_def.get("condition", {})
            condition["site_id"] = site_id
            db.add(AutomationRule(
                tenant_id=tenant_id,
                name=f"{rule_def.get('name', 'Rule')} — {site_id}",
                description=rule_def.get("description"),
                trigger_type=rule_def.get("trigger_type", "heartbeat_missing"),
                condition_json=json.dumps(condition),
                action_type=rule_def.get("action_type", "notify"),
                action_config_json=json.dumps(rule_def.get("action_config", {})),
                enabled=True,
            ))
            results["automation_rules"] += 1

    # Log activity
    db.add(CommandActivity(
        tenant_id=tenant_id,
        activity_type="template_applied",
        site_id=site_id,
        actor=created_by,
        summary=f"Template '{template.name}' applied: {results['verification_tasks']} tasks, {results['automation_rules']} rules",
    ))

    return results


# Built-in template definitions (seeded as global templates)
BUILTIN_TEMPLATES = [
    {
        "name": "Retail Store",
        "building_type": "retail",
        "description": "Standard retail location with fire alarm and elevator phone systems",
        "systems_json": json.dumps(["fire_alarm", "elevator_phone"]),
        "verification_tasks_json": json.dumps([
            {"task_type": "annual_inspection", "title": "Annual Fire Alarm Inspection", "system_category": "fire_alarm", "priority": "high", "due_days": 30},
            {"task_type": "line_test", "title": "E911 Line Test", "system_category": "call_station", "priority": "medium", "due_days": 14},
            {"task_type": "battery_test", "title": "UPS Battery Check", "system_category": "backup_power", "priority": "medium", "due_days": 60},
        ]),
        "monitoring_rules_json": json.dumps([
            {"name": "Heartbeat Monitor", "trigger_type": "heartbeat_missing", "condition": {"threshold_minutes": 30}, "action_type": "create_incident", "action_config": {"severity": "warning"}},
        ]),
    },
    {
        "name": "Commercial Office Building",
        "building_type": "commercial_office",
        "description": "Multi-tenant office building with full life-safety systems",
        "systems_json": json.dumps(["fire_alarm", "elevator_phone", "das_radio", "call_station", "backup_power"]),
        "verification_tasks_json": json.dumps([
            {"task_type": "annual_inspection", "title": "Annual FACP Inspection", "system_category": "fire_alarm", "priority": "high", "due_days": 30},
            {"task_type": "signal_test", "title": "DAS Signal Coverage Test", "system_category": "das_radio", "priority": "high", "due_days": 30},
            {"task_type": "elevator_test", "title": "Elevator Phone Test", "system_category": "elevator_phone", "priority": "high", "due_days": 14},
            {"task_type": "battery_test", "title": "Backup Power Load Test", "system_category": "backup_power", "priority": "medium", "due_days": 90},
            {"task_type": "line_test", "title": "E911 Line Verification", "system_category": "call_station", "priority": "medium", "due_days": 14},
        ]),
        "monitoring_rules_json": json.dumps([
            {"name": "Heartbeat Monitor", "trigger_type": "heartbeat_missing", "condition": {"threshold_minutes": 15}, "action_type": "create_incident", "action_config": {"severity": "warning"}},
            {"name": "Verification Overdue", "trigger_type": "verification_overdue", "condition": {}, "action_type": "notify", "action_config": {"notify_role": "Admin"}},
        ]),
    },
    {
        "name": "Hospital / Healthcare Facility",
        "building_type": "hospital",
        "description": "Healthcare facility with critical life-safety and communication systems",
        "systems_json": json.dumps(["fire_alarm", "elevator_phone", "das_radio", "call_station", "backup_power"]),
        "verification_tasks_json": json.dumps([
            {"task_type": "annual_inspection", "title": "FACP Annual Inspection (NFPA 72)", "system_category": "fire_alarm", "priority": "high", "due_days": 14},
            {"task_type": "signal_test", "title": "Responder Radio Coverage Test", "system_category": "das_radio", "priority": "high", "due_days": 14},
            {"task_type": "elevator_test", "title": "Elevator Phone Two-Way Test", "system_category": "elevator_phone", "priority": "high", "due_days": 7},
            {"task_type": "battery_test", "title": "Generator / UPS Load Test", "system_category": "backup_power", "priority": "high", "due_days": 30},
            {"task_type": "line_test", "title": "E911 PSAP Routing Test", "system_category": "call_station", "priority": "high", "due_days": 7},
            {"task_type": "compliance_review", "title": "Joint Commission Compliance Review", "system_category": "other", "priority": "high", "due_days": 30},
        ]),
        "monitoring_rules_json": json.dumps([
            {"name": "Critical Heartbeat", "trigger_type": "heartbeat_missing", "condition": {"threshold_minutes": 10}, "action_type": "create_incident", "action_config": {"severity": "critical"}},
            {"name": "Unresolved Critical", "trigger_type": "incident_unresolved", "condition": {"threshold_minutes": 60, "severity": "critical"}, "action_type": "notify", "action_config": {"notify_role": "Admin"}},
        ]),
    },
    {
        "name": "Airport Terminal",
        "building_type": "airport",
        "description": "Airport terminal with DAS, emergency call stations, and fire systems",
        "systems_json": json.dumps(["fire_alarm", "das_radio", "call_station", "backup_power"]),
        "verification_tasks_json": json.dumps([
            {"task_type": "annual_inspection", "title": "FACP Annual Inspection", "system_category": "fire_alarm", "priority": "high", "due_days": 14},
            {"task_type": "signal_test", "title": "DAS In-Building Coverage Test", "system_category": "das_radio", "priority": "high", "due_days": 14},
            {"task_type": "call_station_test", "title": "Emergency Call Station Test", "system_category": "call_station", "priority": "high", "due_days": 7},
            {"task_type": "battery_test", "title": "Backup Power Systems Test", "system_category": "backup_power", "priority": "high", "due_days": 30},
        ]),
        "monitoring_rules_json": json.dumps([
            {"name": "Critical Heartbeat", "trigger_type": "heartbeat_missing", "condition": {"threshold_minutes": 10}, "action_type": "create_incident", "action_config": {"severity": "critical"}},
        ]),
    },
    {
        "name": "Data Center",
        "building_type": "data_center",
        "description": "Data center with fire suppression, backup power, and environmental monitoring",
        "systems_json": json.dumps(["fire_alarm", "backup_power"]),
        "verification_tasks_json": json.dumps([
            {"task_type": "annual_inspection", "title": "Fire Suppression System Inspection", "system_category": "fire_alarm", "priority": "high", "due_days": 14},
            {"task_type": "battery_test", "title": "UPS / Generator Load Test", "system_category": "backup_power", "priority": "high", "due_days": 30},
            {"task_type": "environmental_check", "title": "Environmental Monitoring Baseline", "system_category": "other", "priority": "medium", "due_days": 7},
        ]),
        "monitoring_rules_json": json.dumps([
            {"name": "Heartbeat Monitor", "trigger_type": "heartbeat_missing", "condition": {"threshold_minutes": 5}, "action_type": "create_incident", "action_config": {"severity": "critical"}},
        ]),
    },
    {
        "name": "Elevator Bank Deployment",
        "building_type": "elevator_bank",
        "description": "Standalone elevator phone deployment with line monitoring",
        "systems_json": json.dumps(["elevator_phone"]),
        "verification_tasks_json": json.dumps([
            {"task_type": "elevator_test", "title": "Two-Way Voice Test (AHJ)", "system_category": "elevator_phone", "priority": "high", "due_days": 14},
            {"task_type": "line_test", "title": "E911 Line Verification", "system_category": "elevator_phone", "priority": "high", "due_days": 14},
        ]),
        "monitoring_rules_json": json.dumps([
            {"name": "Heartbeat Monitor", "trigger_type": "heartbeat_missing", "condition": {"threshold_minutes": 30}, "action_type": "create_incident", "action_config": {"severity": "warning"}},
        ]),
    },
]
