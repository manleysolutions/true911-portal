-- ============================================================
-- True911+ Full Data Reset Script
-- ============================================================
-- Purpose : Wipe ALL data from every table while keeping
--           schema, migrations, and Alembic version intact.
-- Engine  : PostgreSQL 16
-- Safety  : Wrapped in a single transaction — all-or-nothing.
-- Usage   : psql -f reset_all_data.sql  (or paste into a client)
-- ============================================================

BEGIN;

-- ────────────────────────────────────────────────────────────
-- TRUNCATE CASCADE removes all rows and automatically handles
-- foreign-key dependencies.  Identity / serial counters are
-- reset via RESTART IDENTITY.
--
-- Tables are listed in dependency order (leaves → roots) for
-- readability, but CASCADE makes the ordering informational.
-- ────────────────────────────────────────────────────────────

TRUNCATE TABLE

  -- Support tree (cascade-deletes from support_sessions anyway)
  support_messages,
  support_diagnostics,
  support_escalations,
  support_remediation_actions,
  support_ai_summaries,
  support_sessions,

  -- Device / SIM tree
  device_sims,
  sim_events,
  sim_usage_daily,
  sims,
  devices,
  hardware_models,

  -- Customer / billing tree
  external_customer_map,
  external_subscription_map,
  lines,
  subscriptions,
  customers,

  -- Tenant tree
  outbound_webhooks,
  site_templates,
  service_contracts,
  sites,
  users,
  tenants,

  -- Integrations tree
  integration_accounts,
  integration_status,
  integration_payloads,
  integration_events,
  integrations,

  -- Service / vendor
  site_vendor_assignments,
  vendors,
  service_units,

  -- Provisioning & import
  provisioning_queue,
  import_rows,
  import_batches,

  -- Port / line intelligence
  port_states,
  line_intelligence_events,

  -- Command center
  command_notifications,
  command_telemetry,
  command_activities,

  -- Automation & audit
  automation_rules,
  escalation_rules,
  action_audits,
  audit_log_entries,
  verification_tasks,

  -- Events / telemetry / jobs
  events,
  telemetry_events,
  network_events,
  jobs,

  -- Recordings & notifications
  recordings,
  notification_rules,

  -- E911
  e911_change_logs,

  -- Providers
  providers,

  -- Incidents
  incidents,

  -- Reconciliation
  reconciliation_snapshots,

  -- Infrastructure tests
  infra_test_results,
  infra_tests,

  -- Autonomous ops
  autonomous_actions,
  operational_digests

RESTART IDENTITY CASCADE;

-- ────────────────────────────────────────────────────────────
-- Verify: every application table should now have 0 rows.
-- (alembic_version is intentionally excluded.)
-- ────────────────────────────────────────────────────────────
DO $$
DECLARE
  _tbl  text;
  _cnt  bigint;
  _ok   boolean := true;
BEGIN
  FOR _tbl IN
    SELECT tablename
      FROM pg_tables
     WHERE schemaname = 'public'
       AND tablename <> 'alembic_version'
  LOOP
    EXECUTE format('SELECT count(*) FROM %I', _tbl) INTO _cnt;
    IF _cnt <> 0 THEN
      RAISE WARNING 'Table % still has % row(s)', _tbl, _cnt;
      _ok := false;
    END IF;
  END LOOP;

  IF _ok THEN
    RAISE NOTICE '✓ All tables empty — reset complete.';
  ELSE
    RAISE NOTICE '✗ Some tables still contain data (see warnings above).';
  END IF;
END
$$;

COMMIT;
