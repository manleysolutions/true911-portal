-- Zoho ↔ True911 remediation — READ-ONLY discovery (run first, confirms A1–A4).
-- Pure SELECTs. Modifies nothing. Run in the Render psql shell or a read replica.
-- Replace the customer name patterns as needed.

-- ── A1: which tenant do RH / Integrity / R&R customers live under? ──────────
SELECT id, name, tenant_id, status, zoho_account_id
FROM customers
WHERE name ILIKE ANY (ARRAY['%restoration hardware%','%integrity%','%r&r%','%r and r%','%rr realty%'])
ORDER BY name;

-- ── A1: per-tenant footprint (is 'default' a shared catch-all?) ─────────────
SELECT t.tenant_id, t.name,
       (SELECT count(*) FROM customers c WHERE c.tenant_id=t.tenant_id) customers,
       (SELECT count(*) FROM sites   s WHERE s.tenant_id=t.tenant_id) sites,
       (SELECT count(*) FROM devices d WHERE d.tenant_id=t.tenant_id) devices,
       (SELECT count(*) FROM lines   l WHERE l.tenant_id=t.tenant_id) lines
FROM tenants t ORDER BY devices DESC;

-- ── A2: Restoration Hardware — Zoho subs vs True911 devices vs lifecycle ────
-- Staged Zoho subscriptions by lifecycle/activation status:
SELECT COALESCE(device_activation_status,'(null)') status, count(*)
FROM zoho_subscription_records
WHERE account_name ILIKE '%restoration%' OR facility_name ILIKE '%restoration%'
GROUP BY 1 ORDER BY 2 DESC;
-- True911 device count (customer-scoped via sites.customer_id):
SELECT count(*) rh_devices
FROM devices d WHERE d.site_id IN
  (SELECT site_id FROM sites WHERE customer_id IN
    (SELECT id FROM customers WHERE name ILIKE '%restoration%'));

-- ── A3: R&R duplicate inflation — devices and lines sharing one MSISDN ──────
-- Count MSISDNs that appear on BOTH a device and a line (false-positive dups):
SELECT count(*) shared_msisdns FROM (
  SELECT regexp_replace(d.msisdn,'\D','','g') m
  FROM devices d WHERE d.msisdn IS NOT NULL
  INTERSECT
  SELECT regexp_replace(l.did,'\D','','g')
  FROM lines l WHERE l.did IS NOT NULL
) x WHERE length(m) >= 10;

-- ── A4: FacilityName vs Site name — sample the mismatch ─────────────────────
SELECT DISTINCT z.facility_name
FROM zoho_subscription_records z
WHERE (z.account_name ILIKE '%r&r%' OR z.facility_name ILIKE '%dodge%'
       OR z.facility_name ILIKE '%port miami%')
ORDER BY 1;
SELECT site_id, site_name FROM sites
WHERE site_name ILIKE '%dodge%' OR site_name ILIKE '%watson%' OR site_name ILIKE '%miami%'
ORDER BY site_name;
