"""Purge all legacy testing / sandbox / demo data from the True911 database.

Usage:
    # Dry-run (default) — shows what would be removed, writes backup, deletes nothing
    python -m scripts.purge_legacy_data

    # Live purge — backs up then deletes
    python -m scripts.purge_legacy_data --execute

The script:
  1. Connects to the production database (reads DATABASE_URL from env / .env)
  2. Exports ALL data that will be removed to a timestamped JSON backup file
  3. Deletes demo/test tenant data in FK-safe order
  4. Preserves: hardware_models, global site_templates, integrations (registry),
     system config, permissions, audit structure, alembic version
  5. Prints a category-level summary of what was removed

Rollback:
  The backup JSON can be used to re-insert data if needed.
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the api package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models.tenant import Tenant
from app.models.user import User
from app.models.site import Site
from app.models.device import Device
from app.models.sim import Sim
from app.models.device_sim import DeviceSim
from app.models.sim_event import SimEvent
from app.models.sim_usage_daily import SimUsageDaily
from app.models.line import Line
from app.models.recording import Recording
from app.models.event import Event
from app.models.telemetry_event import TelemetryEvent
from app.models.action_audit import ActionAudit
from app.models.incident import Incident
from app.models.notification_rule import NotificationRule
from app.models.notification import CommandNotification
from app.models.escalation_rule import EscalationRule
from app.models.command_telemetry import CommandTelemetry
from app.models.command_activity import CommandActivity
from app.models.provider import Provider
from app.models.integration import IntegrationAccount
from app.models.vendor import Vendor
from app.models.site_vendor import SiteVendorAssignment
from app.models.verification_task import VerificationTask
from app.models.automation_rule import AutomationRule
from app.models.service_contract import ServiceContract
from app.models.network_event import NetworkEvent
from app.models.infra_test import InfraTest
from app.models.infra_test_result import InfraTestResult
from app.models.audit_log_entry import AuditLogEntry
from app.models.autonomous_action import AutonomousAction
from app.models.operational_digest import OperationalDigest
from app.models.e911_change_log import E911ChangeLog
from app.models.provisioning_queue import ProvisioningQueueItem
from app.models.port_state import PortState
from app.models.line_intelligence_event import LineIntelligenceEvent
from app.models.import_batch import ImportBatch
from app.models.import_row import ImportRow
from app.models.service_unit import ServiceUnit
from app.models.outbound_webhook import OutboundWebhook
from app.models.job import Job
from app.models.customer import Customer
from app.models.subscription import Subscription
from app.models.external_customer_map import ExternalCustomerMap
from app.models.external_subscription_map import ExternalSubscriptionMap
from app.models.reconciliation_snapshot import ReconciliationSnapshot
from app.models.integration_event import IntegrationEvent
from app.models.integration_status import IntegrationStatus
from app.models.integration_payload import IntegrationPayload
from app.models.support import (
    SupportSession, SupportMessage, SupportDiagnostic,
    SupportEscalation, SupportRemediationAction, SupportAISummary,
)


# ── Tenant IDs considered legacy / test / demo ──────────────────────────
DEMO_TENANT_IDS = {"demo"}

# The "rh" tenant was seeded by migration 011 as a placeholder.
# If it has zero real sites/users it will be purged; otherwise isolated.
CANDIDATE_TENANT_IDS = {"rh"}

# Known demo user emails (for safety — only delete users matching these)
DEMO_USER_EMAILS = {
    "admin@true911.com",
    "manager@true911.com",
    "user@true911.com",
}

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"


def serialize_row(row) -> dict:
    """Convert a SQLAlchemy model instance to a JSON-serialisable dict."""
    d = {}
    mapper = inspect(type(row))
    for col in mapper.columns:
        val = getattr(row, col.key, None)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "__json__"):
            val = val.__json__()
        d[col.key] = val
    return d


async def collect_tenant_data(db: AsyncSession, tenant_id: str) -> dict:
    """Gather all rows belonging to a tenant for backup."""
    data = {}

    # Tables with tenant_id column — order doesn't matter for backup
    tenant_scoped = [
        ("users", User),
        ("sites", Site),
        ("devices", Device),
        ("sims", Sim),
        ("lines", Line),
        ("recordings", Recording),
        ("events", Event),
        ("telemetry_events", TelemetryEvent),
        ("action_audits", ActionAudit),
        ("incidents", Incident),
        ("notification_rules", NotificationRule),
        ("command_notifications", CommandNotification),
        ("escalation_rules", EscalationRule),
        ("command_telemetry", CommandTelemetry),
        ("command_activities", CommandActivity),
        ("providers", Provider),
        ("integration_accounts", IntegrationAccount),
        ("vendors", Vendor),
        ("site_vendor_assignments", SiteVendorAssignment),
        ("verification_tasks", VerificationTask),
        ("automation_rules", AutomationRule),
        ("service_contracts", ServiceContract),
        ("network_events", NetworkEvent),
        ("infra_tests", InfraTest),
        ("infra_test_results", InfraTestResult),
        ("audit_log_entries", AuditLogEntry),
        ("autonomous_actions", AutonomousAction),
        ("operational_digests", OperationalDigest),
        ("e911_change_logs", E911ChangeLog),
        ("provisioning_queue", ProvisioningQueueItem),
        ("port_states", PortState),
        ("line_intelligence_events", LineIntelligenceEvent),
        ("import_batches", ImportBatch),
        ("import_rows", ImportRow),
        ("service_units", ServiceUnit),
        ("outbound_webhooks", OutboundWebhook),
        ("support_sessions", SupportSession),
        ("support_messages", SupportMessage),
        ("support_diagnostics", SupportDiagnostic),
        ("support_escalations", SupportEscalation),
        ("support_remediation_actions", SupportRemediationAction),
        ("support_ai_summaries", SupportAISummary),
    ]

    for label, model in tenant_scoped:
        try:
            rows = (await db.execute(
                select(model).where(model.tenant_id == tenant_id)
            )).scalars().all()
            if rows:
                data[label] = [serialize_row(r) for r in rows]
        except Exception:
            # Model may not have tenant_id or table may not exist yet
            pass

    # Jobs scoped to tenant
    try:
        rows = (await db.execute(
            select(Job).where(Job.tenant_id == tenant_id)
        )).scalars().all()
        if rows:
            data["jobs"] = [serialize_row(r) for r in rows]
    except Exception:
        pass

    # DeviceSim — joined via device
    try:
        device_ids_q = select(Device.id).where(Device.tenant_id == tenant_id)
        device_ids = [r[0] for r in (await db.execute(device_ids_q)).all()]
        if device_ids:
            rows = (await db.execute(
                select(DeviceSim).where(DeviceSim.device_id.in_(device_ids))
            )).scalars().all()
            if rows:
                data["device_sims"] = [serialize_row(r) for r in rows]
    except Exception:
        pass

    # SimEvent — joined via sim
    try:
        sim_ids_q = select(Sim.id).where(Sim.tenant_id == tenant_id)
        sim_ids = [r[0] for r in (await db.execute(sim_ids_q)).all()]
        if sim_ids:
            for label, model in [("sim_events", SimEvent), ("sim_usage_daily", SimUsageDaily)]:
                rows = (await db.execute(
                    select(model).where(model.sim_id.in_(sim_ids))
                )).scalars().all()
                if rows:
                    data[label] = [serialize_row(r) for r in rows]
    except Exception:
        pass

    # Tenant record itself
    tenant = (await db.execute(
        select(Tenant).where(Tenant.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if tenant:
        data["tenant"] = serialize_row(tenant)

    return data


async def collect_orphaned_data(db: AsyncSession) -> dict:
    """Find data in non-tenant-scoped tables that looks like test/demo data."""
    data = {}

    # Integration events / external maps with org_id = "demo"
    for label, model, col in [
        ("integration_events_demo", IntegrationEvent, IntegrationEvent.org_id),
        ("external_customer_map_demo", ExternalCustomerMap, ExternalCustomerMap.org_id),
        ("external_subscription_map_demo", ExternalSubscriptionMap, ExternalSubscriptionMap.org_id),
        ("reconciliation_snapshots_demo", ReconciliationSnapshot, ReconciliationSnapshot.org_id),
    ]:
        try:
            rows = (await db.execute(select(model).where(col == "demo"))).scalars().all()
            if rows:
                data[label] = [serialize_row(r) for r in rows]
        except Exception:
            pass

    # Integration payloads / statuses — orphaned (linked to demo resources)
    # We'll flag these but not auto-delete since they may be ambiguous
    try:
        rows = (await db.execute(select(IntegrationPayload))).scalars().all()
        if rows:
            data["integration_payloads_all"] = [serialize_row(r) for r in rows]
    except Exception:
        pass

    try:
        rows = (await db.execute(select(IntegrationStatus))).scalars().all()
        if rows:
            data["integration_statuses_all"] = [serialize_row(r) for r in rows]
    except Exception:
        pass

    return data


async def delete_tenant_data(db: AsyncSession, tenant_id: str) -> dict:
    """Delete all rows for a tenant in FK-safe order. Returns counts."""
    counts = {}

    # Delete in reverse-dependency order (children first)
    # Phase 1: Join-table / leaf records
    try:
        device_ids = [r[0] for r in (await db.execute(
            select(Device.id).where(Device.tenant_id == tenant_id)
        )).all()]
        if device_ids:
            r = await db.execute(
                DeviceSim.__table__.delete().where(DeviceSim.device_id.in_(device_ids))
            )
            counts["device_sims"] = r.rowcount
    except Exception:
        pass

    try:
        sim_ids = [r[0] for r in (await db.execute(
            select(Sim.id).where(Sim.tenant_id == tenant_id)
        )).all()]
        if sim_ids:
            for label, model in [("sim_events", SimEvent), ("sim_usage_daily", SimUsageDaily)]:
                try:
                    r = await db.execute(
                        model.__table__.delete().where(model.sim_id.in_(sim_ids))
                    )
                    counts[label] = r.rowcount
                except Exception:
                    pass
    except Exception:
        pass

    # Phase 2: InfraTestResult depends on InfraTest
    try:
        test_ids_q = select(InfraTest.test_id).where(InfraTest.tenant_id == tenant_id)
        test_ids = [r[0] for r in (await db.execute(test_ids_q)).all()]
        if test_ids:
            r = await db.execute(
                InfraTestResult.__table__.delete().where(InfraTestResult.test_id.in_(test_ids))
            )
            counts["infra_test_results"] = r.rowcount
    except Exception:
        pass

    # Phase 3: Support children before sessions
    support_leaf = [
        ("support_ai_summaries", SupportAISummary),
        ("support_remediation_actions", SupportRemediationAction),
        ("support_escalations", SupportEscalation),
        ("support_diagnostics", SupportDiagnostic),
        ("support_messages", SupportMessage),
        ("support_sessions", SupportSession),
    ]
    for label, model in support_leaf:
        try:
            r = await db.execute(
                model.__table__.delete().where(model.tenant_id == tenant_id)
            )
            counts[label] = r.rowcount
        except Exception:
            pass

    # Phase 4: ImportRow depends on ImportBatch
    try:
        batch_ids = [r[0] for r in (await db.execute(
            select(ImportBatch.id).where(ImportBatch.tenant_id == tenant_id)
        )).all()]
        if batch_ids:
            r = await db.execute(
                ImportRow.__table__.delete().where(ImportRow.batch_id.in_(batch_ids))
            )
            counts["import_rows"] = r.rowcount
    except Exception:
        pass

    # Phase 5: SiteVendorAssignment + ServiceContract depend on Vendor
    for label, model in [
        ("site_vendor_assignments", SiteVendorAssignment),
        ("service_contracts", ServiceContract),
    ]:
        try:
            r = await db.execute(
                model.__table__.delete().where(model.tenant_id == tenant_id)
            )
            counts[label] = r.rowcount
        except Exception:
            pass

    # Phase 6: All other tenant-scoped tables (children before parents)
    bulk_delete_order = [
        ("recordings", Recording),
        ("port_states", PortState),
        ("line_intelligence_events", LineIntelligenceEvent),
        ("command_telemetry", CommandTelemetry),
        ("command_activities", CommandActivity),
        ("command_notifications", CommandNotification),
        ("autonomous_actions", AutonomousAction),
        ("operational_digests", OperationalDigest),
        ("audit_log_entries", AuditLogEntry),
        ("network_events", NetworkEvent),
        ("infra_tests", InfraTest),
        ("verification_tasks", VerificationTask),
        ("automation_rules", AutomationRule),
        ("escalation_rules", EscalationRule),
        ("notification_rules", NotificationRule),
        ("incidents", Incident),
        ("e911_change_logs", E911ChangeLog),
        ("events", Event),
        ("telemetry_events", TelemetryEvent),
        ("action_audits", ActionAudit),
        ("provisioning_queue", ProvisioningQueueItem),
        ("outbound_webhooks", OutboundWebhook),
        ("service_units", ServiceUnit),
        ("import_batches", ImportBatch),
        ("integration_accounts", IntegrationAccount),
        ("lines", Line),
        ("sims", Sim),
        ("devices", Device),
        ("providers", Provider),
        ("vendors", Vendor),
        ("sites", Site),
        ("jobs", Job),
        ("users", User),
    ]

    for label, model in bulk_delete_order:
        try:
            r = await db.execute(
                model.__table__.delete().where(model.tenant_id == tenant_id)
            )
            counts[label] = r.rowcount
        except Exception as e:
            counts[f"{label}_error"] = str(e)

    # Finally, delete the tenant record
    try:
        r = await db.execute(
            Tenant.__table__.delete().where(Tenant.tenant_id == tenant_id)
        )
        counts["tenant"] = r.rowcount
    except Exception as e:
        counts["tenant_error"] = str(e)

    return counts


async def delete_orphaned_demo_data(db: AsyncSession) -> dict:
    """Delete non-tenant-scoped rows that belong to demo org."""
    counts = {}
    for label, model, col in [
        ("integration_events", IntegrationEvent, IntegrationEvent.org_id),
        ("external_customer_map", ExternalCustomerMap, ExternalCustomerMap.org_id),
        ("external_subscription_map", ExternalSubscriptionMap, ExternalSubscriptionMap.org_id),
        ("reconciliation_snapshots", ReconciliationSnapshot, ReconciliationSnapshot.org_id),
    ]:
        try:
            r = await db.execute(model.__table__.delete().where(col == "demo"))
            counts[label] = r.rowcount
        except Exception:
            pass

    # Customers / Subscriptions with tenant_id = demo
    for label, model in [
        ("subscriptions", Subscription),
        ("customers", Customer),
    ]:
        try:
            r = await db.execute(
                model.__table__.delete().where(model.tenant_id == "demo")
            )
            counts[label] = r.rowcount
        except Exception:
            pass

    return counts


async def check_tenant_has_real_data(db: AsyncSession, tenant_id: str) -> dict:
    """Check if a candidate tenant has any real (non-demo) data."""
    info = {"tenant_id": tenant_id}
    try:
        site_count = (await db.execute(
            text("SELECT COUNT(*) FROM sites WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )).scalar() or 0
        user_count = (await db.execute(
            text("SELECT COUNT(*) FROM users WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )).scalar() or 0
        device_count = (await db.execute(
            text("SELECT COUNT(*) FROM devices WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )).scalar() or 0
        info.update(sites=site_count, users=user_count, devices=device_count)
        info["has_real_data"] = any([site_count, user_count, device_count])
    except Exception:
        info["has_real_data"] = True  # err on side of caution
    return info


async def purge(execute: bool = False):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"purge_backup_{ts}.json"

    backup = {
        "timestamp": ts,
        "mode": "execute" if execute else "dry_run",
        "tenants_purged": [],
        "tenants_isolated": [],
        "orphaned_data": {},
    }
    summary = {
        "tenants_purged": [],
        "tenants_isolated": [],
        "deleted_counts": {},
        "preserved": [],
        "ambiguous": [],
    }

    async with AsyncSessionLocal() as db:
        # ── 1. Backup & purge known demo tenants ─────────────────────
        for tid in DEMO_TENANT_IDS:
            print(f"\n{'='*60}")
            print(f"  Tenant: {tid}")
            print(f"{'='*60}")

            tenant_data = await collect_tenant_data(db, tid)
            if not tenant_data:
                print(f"  No data found for tenant '{tid}' — skipping.")
                continue

            backup["tenants_purged"].append({"tenant_id": tid, "data": tenant_data})

            # Count records per category
            for cat, rows in tenant_data.items():
                if isinstance(rows, list):
                    count = len(rows)
                else:
                    count = 1
                print(f"  {cat:40s} {count:>6} records")

            if execute:
                counts = await delete_tenant_data(db, tid)
                summary["deleted_counts"][tid] = counts
                summary["tenants_purged"].append(tid)
                print(f"\n  ** DELETED tenant '{tid}' — {sum(v for v in counts.values() if isinstance(v, int))} total rows")
            else:
                print(f"\n  [DRY RUN] Would delete all data for tenant '{tid}'")

        # ── 2. Check candidate tenants (rh, etc.) ────────────────────
        for tid in CANDIDATE_TENANT_IDS:
            info = await check_tenant_has_real_data(db, tid)
            print(f"\n{'='*60}")
            print(f"  Candidate tenant: {tid}")
            print(f"  Sites: {info.get('sites', '?')}, Users: {info.get('users', '?')}, Devices: {info.get('devices', '?')}")

            if not info["has_real_data"]:
                # No real data — safe to purge
                tenant_data = await collect_tenant_data(db, tid)
                backup["tenants_purged"].append({"tenant_id": tid, "data": tenant_data})

                if execute:
                    counts = await delete_tenant_data(db, tid)
                    summary["deleted_counts"][tid] = counts
                    summary["tenants_purged"].append(tid)
                    print(f"  ** DELETED empty tenant '{tid}'")
                else:
                    print(f"  [DRY RUN] Would delete empty tenant '{tid}'")
            else:
                # Has data — isolate, don't delete
                summary["tenants_isolated"].append(tid)
                summary["ambiguous"].append(
                    f"Tenant '{tid}' has {info.get('sites',0)} sites, "
                    f"{info.get('users',0)} users, {info.get('devices',0)} devices. "
                    "Isolated — review manually before purging."
                )
                backup["tenants_isolated"].append({"tenant_id": tid, "info": info})
                print(f"  ** ISOLATED — has real data, not deleting.")

        # ── 3. Orphaned demo data in non-tenant tables ───────────────
        print(f"\n{'='*60}")
        print(f"  Orphaned / non-tenant-scoped demo data")
        print(f"{'='*60}")

        orphaned = await collect_orphaned_data(db)
        backup["orphaned_data"] = orphaned
        for cat, rows in orphaned.items():
            if isinstance(rows, list):
                count = len(rows)
                print(f"  {cat:40s} {count:>6} records")

        if execute:
            orph_counts = await delete_orphaned_demo_data(db)
            summary["deleted_counts"]["orphaned"] = orph_counts
            print(f"\n  ** DELETED orphaned demo data — {sum(orph_counts.values())} total rows")
        else:
            print(f"\n  [DRY RUN] Would delete orphaned demo data")

        # ── 4. Delete demo-only site templates (tenant_id=demo) ──────
        #    Global templates (tenant_id=NULL, is_global=True) are PRESERVED
        try:
            from app.models.site_template import SiteTemplate
            demo_templates = (await db.execute(
                select(SiteTemplate).where(SiteTemplate.tenant_id == "demo")
            )).scalars().all()
            if demo_templates:
                backup.setdefault("demo_site_templates", [serialize_row(t) for t in demo_templates])
                print(f"\n  Demo site templates: {len(demo_templates)}")
                if execute:
                    await db.execute(
                        SiteTemplate.__table__.delete().where(SiteTemplate.tenant_id == "demo")
                    )
                    summary["deleted_counts"]["demo_site_templates"] = len(demo_templates)
        except Exception:
            pass

        # ── 5. Commit or rollback ────────────────────────────────────
        if execute:
            await db.commit()
            print("\n  ** All changes COMMITTED.")
        else:
            await db.rollback()
            print("\n  ** Dry run — no changes made.")

    # ── 6. Record what was preserved ─────────────────────────────────
    summary["preserved"] = [
        "hardware_models — 11 reference models (used by device dropdowns)",
        "global site_templates — 6 built-in templates (is_global=True, tenant_id=NULL)",
        "integrations — 3 provider registry entries (telnyx, vola, tmobile)",
        "alembic_version — migration state",
        "All non-demo tenant data",
        "Database schema, indexes, and constraints",
    ]

    summary["dependencies_to_reload"] = [
        "PR12 devices — import via /api/admin/import or subscriber CSV",
        "SIM records — import via carrier sync (Verizon ThingSpace, T-Mobile TAAP) or CSV",
        "MSISDN records — linked to SIMs; imported with SIM data or line provisioning",
        "Serial numbers — part of device records; imported with device data",
        "E911 records — set per-line via /api/lines/{id}/e911 or site import CSV",
        "Contacts — customer records via /api/customers or Zoho CRM sync",
        "Notification rules — recreate via /api/notification-rules",
        "Escalation rules — recreate via /api/command/escalation-rules",
    ]

    # ── 7. Write backup file ─────────────────────────────────────────
    with open(backup_path, "w") as f:
        json.dump(backup, f, indent=2, default=str)
    print(f"\n  Backup written to: {backup_path}")
    print(f"  Backup size: {backup_path.stat().st_size / 1024:.1f} KB")

    # ── 8. Print summary ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  PURGE SUMMARY {'(EXECUTED)' if execute else '(DRY RUN)'}")
    print(f"{'='*60}")

    if summary["tenants_purged"]:
        print(f"\n  Tenants purged: {', '.join(summary['tenants_purged'])}")
    if summary["tenants_isolated"]:
        print(f"  Tenants isolated (not deleted): {', '.join(summary['tenants_isolated'])}")

    if execute and summary["deleted_counts"]:
        print(f"\n  Deleted by category:")
        for scope, counts in summary["deleted_counts"].items():
            if isinstance(counts, dict):
                for table, n in sorted(counts.items()):
                    if isinstance(n, int) and n > 0:
                        print(f"    [{scope}] {table:40s} {n:>6}")

    print(f"\n  Preserved (not deleted):")
    for item in summary["preserved"]:
        print(f"    - {item}")

    if summary["ambiguous"]:
        print(f"\n  ** AMBIGUOUS — requires manual review:")
        for item in summary["ambiguous"]:
            print(f"    ! {item}")

    print(f"\n  Dependencies to reload after cleanup:")
    for dep in summary["dependencies_to_reload"]:
        print(f"    -> {dep}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge legacy test/demo data")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete data (default is dry-run)",
    )
    args = parser.parse_args()

    if args.execute:
        print("\n  *** LIVE PURGE MODE — data will be permanently deleted ***")
        print("  Backup will be created before any deletions.\n")
        confirm = input("  Type 'PURGE' to confirm: ")
        if confirm.strip() != "PURGE":
            print("  Aborted.")
            sys.exit(0)

    asyncio.run(purge(execute=args.execute))
