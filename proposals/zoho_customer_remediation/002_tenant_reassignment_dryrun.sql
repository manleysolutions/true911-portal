-- PROPOSED, DRY-RUN-FIRST (not applied; not an Alembic migration).
-- Optional: move ONE customer's sites/devices/lines from the shared 'default'
-- tenant to a dedicated tenant. ONLY needed if the dedicated-tenant model is
-- chosen (the plan recommends staying customer-scoped under 'default').
--
-- Wrapped in a transaction that ROLLS BACK by default. Inspect the SELECT counts
-- in the same transaction, and only change ROLLBACK -> COMMIT after review and an
-- explicit go-ahead. Never deletes. Customer-scoped via sites.customer_id.

-- Parameters (edit before running):
--   :cust_name   e.g. 'R&R Realty Group'
--   :new_tenant  e.g. 'rr-realty'   (must already exist in tenants)

BEGIN;

-- 0) Resolve the customer + its site ids (read-only check).
--    SELECT id, name, tenant_id FROM customers WHERE name ILIKE :cust_name;

-- 1) Preview what WOULD move (run these SELECTs and eyeball the counts):
--    SELECT count(*) sites_to_move   FROM sites   WHERE customer_id = (SELECT id FROM customers WHERE name ILIKE :cust_name);
--    SELECT count(*) devices_to_move FROM devices WHERE site_id IN (SELECT site_id FROM sites WHERE customer_id = (SELECT id FROM customers WHERE name ILIKE :cust_name));
--    SELECT count(*) lines_to_move   FROM lines   WHERE customer_id = (SELECT id FROM customers WHERE name ILIKE :cust_name);

-- 2) PROPOSED updates (kept commented; uncomment ONLY after the previews look right):
-- UPDATE customers SET tenant_id = :new_tenant WHERE name ILIKE :cust_name;
-- UPDATE sites     SET tenant_id = :new_tenant WHERE customer_id = (SELECT id FROM customers WHERE name ILIKE :cust_name);
-- UPDATE devices   SET tenant_id = :new_tenant WHERE site_id IN (SELECT site_id FROM sites WHERE customer_id = (SELECT id FROM customers WHERE name ILIKE :cust_name));
-- UPDATE lines     SET tenant_id = :new_tenant WHERE customer_id = (SELECT id FROM customers WHERE name ILIKE :cust_name);

ROLLBACK;  -- default. Change to COMMIT only after dry-run review + explicit approval.
