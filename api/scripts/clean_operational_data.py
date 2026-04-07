"""Clean Operational Data — reset platform to empty onboarding state.

Removes all sample/demo/imported operational data while preserving:
  - User accounts & authentication
  - Tenant settings & configuration
  - RBAC roles & permissions
  - Integration & carrier configuration
  - Provider configuration
  - Hardware model catalog
  - Site templates
  - Automation, escalation, & notification rules
  - Outbound webhook registrations
  - Audit logs (action_audits, audit_log_entries)
  - Vendor registry & service contracts

Usage:
  # Dry run (preview only, no changes):
  python -m scripts.clean_operational_data

  # Execute cleanup:
  python -m scripts.clean_operational_data --execute

Run from the api/ directory.
"""

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure app modules are importable
sys.path.insert(0, ".")


async def run(execute: bool = False):
    from app.database import engine, AsyncSessionLocal

    # Import all models so metadata is populated
    import app.models  # noqa: F401

    async with AsyncSessionLocal() as db:
        db: AsyncSession

        # ── Tables to delete (FK-safe order: leaves → parents) ────
        tables_to_clean = [
            # Tier 1: Leaf/event tables (no children reference them)
            ("support_messages", "Support Messages"),
            ("support_diagnostics", "Support Diagnostics"),
            ("support_escalations", "Support Escalations"),
            ("support_remediation_actions", "Support Remediation Actions"),
            ("support_ai_summaries", "Support AI Summaries"),
            ("support_sessions", "Support Sessions"),
            ("device_sims", "Device-SIM Links"),
            ("sim_events", "SIM Events"),
            ("sim_usage_daily", "SIM Usage Daily"),
            ("port_states", "Port States"),
            ("line_intelligence_events", "Line Intelligence Events"),
            ("command_activities", "Command Activities"),
            ("command_telemetry", "Command Telemetry"),
            ("command_notifications", "Command Notifications"),
            ("e911_change_logs", "E911 Change Logs"),
            ("recordings", "Recordings"),
            ("events", "Events"),
            ("telemetry_events", "Telemetry Events"),
            ("network_events", "Network Events"),
            ("verification_tasks", "Verification Tasks"),
            ("infra_test_results", "Infra Test Results"),
            ("infra_tests", "Infra Tests"),
            ("autonomous_actions", "Autonomous Actions"),
            ("operational_digests", "Operational Digests"),
            ("reconciliation_snapshots", "Reconciliation Snapshots"),
            ("jobs", "Jobs"),
            ("integration_payloads", "Integration Payloads"),
            ("integration_events", "Integration Events"),
            ("import_rows", "Import Rows"),
            ("import_batches", "Import Batches"),
            ("provisioning_queue", "Provisioning Queue"),
            ("site_vendor_assignments", "Site Vendor Assignments"),
            ("external_subscription_map", "External Subscription Map"),
            ("external_customer_map", "External Customer Map"),

            # Tier 2: Mid-level tables
            ("service_units", "Service Units"),
            ("incidents", "Incidents"),
            ("lines", "Lines"),
            ("sims", "SIMs"),
            ("devices", "Devices"),
            ("subscriptions", "Subscriptions"),

            # Tier 3: Parent tables
            ("sites", "Sites"),
            ("customers", "Customers"),
        ]

        # ── Tables explicitly preserved ───────────────────────────
        preserve_tables = [
            ("users", "User Accounts"),
            ("tenants", "Tenants"),
            ("integrations", "Integrations"),
            ("integration_accounts", "Integration Accounts"),
            ("integration_status", "Integration Status"),
            ("providers", "Providers"),
            ("hardware_models", "Hardware Models"),
            ("site_templates", "Site Templates"),
            ("automation_rules", "Automation Rules"),
            ("escalation_rules", "Escalation Rules"),
            ("notification_rules", "Notification Rules"),
            ("outbound_webhooks", "Outbound Webhooks"),
            ("action_audits", "Action Audits (security log)"),
            ("audit_log_entries", "Audit Log Entries (RBAC log)"),
            ("vendors", "Vendors (config registry)"),
            ("service_contracts", "Service Contracts"),
        ]

        print("=" * 64)
        print("  True911+ Operational Data Cleanup")
        print("=" * 64)
        print()
        print(f"  Mode: {'EXECUTE — changes will be committed' if execute else 'DRY RUN — preview only'}")
        print()

        # ── Step 1: Count records to delete ───────────────────────
        counts = {}
        total = 0
        print("  Records to DELETE:")
        print("  " + "-" * 50)
        for table_name, label in tables_to_clean:
            try:
                result = await db.execute(text(f"SELECT count(*) FROM {table_name}"))
                count = result.scalar() or 0
            except Exception:
                count = -1  # table doesn't exist
            counts[table_name] = count
            if count > 0:
                print(f"    {label:40s} {count:>6,}")
                total += count
            elif count == -1:
                print(f"    {label:40s}  (table not found)")

        print("  " + "-" * 50)
        print(f"    {'TOTAL':40s} {total:>6,}")
        print()

        # Show what we're preserving
        print("  Records PRESERVED (not touched):")
        print("  " + "-" * 50)
        for table_name, label in preserve_tables:
            try:
                result = await db.execute(text(f"SELECT count(*) FROM {table_name}"))
                count = result.scalar() or 0
            except Exception:
                count = -1
            if count >= 0:
                print(f"    {label:40s} {count:>6,}")
        print()

        if total == 0:
            print("  Nothing to clean — all operational tables are already empty.")
            return

        if not execute:
            print("  This is a DRY RUN. No data was modified.")
            print("  To execute, run with --execute flag.")
            return

        # ── Step 2: Execute deletion in a single transaction ──────
        print("  Executing cleanup...")
        print()

        deleted = {}
        try:
            for table_name, label in tables_to_clean:
                if counts.get(table_name, 0) <= 0:
                    continue  # skip empty or missing tables

                result = await db.execute(text(f"DELETE FROM {table_name}"))
                row_count = result.rowcount
                deleted[table_name] = row_count
                print(f"    Deleted {row_count:>6,} from {label}")

            # All deletes succeeded — commit the transaction
            await db.commit()

        except Exception as e:
            err_msg = str(e).split("\n")[0][:200]
            print()
            print(f"  ERROR during deletion: {err_msg}")
            print()
            print("  Rolling back ALL changes — no data was modified.")
            await db.rollback()
            await engine.dispose()
            return

        print()
        print("  " + "=" * 50)
        print(f"  CLEANUP COMPLETE — {sum(deleted.values()):,} total records deleted")
        print("  " + "=" * 50)

        # ── Step 3: Verify ─────────────────────────────────────────
        print()
        print("  Verification:")
        all_clean = True
        for table_name, label in tables_to_clean:
            try:
                result = await db.execute(text(f"SELECT count(*) FROM {table_name}"))
                remaining = result.scalar() or 0
                if remaining > 0:
                    print(f"    WARNING: {label} still has {remaining} records")
                    all_clean = False
            except Exception:
                pass

        if all_clean:
            print("    All operational tables verified empty.")

        # Confirm preserved tables are intact
        print()
        print("  Preserved tables verification:")
        for table_name, label in preserve_tables:
            try:
                result = await db.execute(text(f"SELECT count(*) FROM {table_name}"))
                count = result.scalar() or 0
                print(f"    {label:40s} {count:>6,} (intact)")
            except Exception:
                pass
        print()

    await engine.dispose()


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    asyncio.run(run(execute=execute))
