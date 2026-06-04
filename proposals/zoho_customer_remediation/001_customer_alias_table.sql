-- PROPOSED (not applied; not an Alembic migration). Additive customer-alias table
-- to canonicalize Zoho/True911 customer spellings for the mapping cascade.
-- Additive + nullable; touches no existing table. Review before promoting to a
-- real Alembic revision.

-- BEGIN;  -- uncomment to run; keep wrapped + review the result before COMMIT.

CREATE TABLE IF NOT EXISTS customer_alias (
    id             SERIAL PRIMARY KEY,
    canonical_key  VARCHAR(100) NOT NULL,          -- e.g. 'rr-realty'
    source         VARCHAR(50)  NOT NULL,          -- 'zoho_account' | 'zoho_parent_account' | 'true911_customer'
    alias          VARCHAR(255) NOT NULL,          -- the raw spelling seen in that source
    account_id     VARCHAR(50),                    -- Zoho Account/Parent_Account id when known
    customer_id    INTEGER REFERENCES customers(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, alias)
);

-- Seed candidates (operator to verify the exact Zoho spellings first):
-- INSERT INTO customer_alias (canonical_key, source, alias) VALUES
--   ('restoration-hardware','true911_customer','Restoration Hardware'),
--   ('integrity-pm','true911_customer','Integrity Property Management'),
--   ('rr-realty','true911_customer','R&R Realty Group'),
--   ('rr-realty','zoho_account','R & R Realty'),
--   ('rr-realty','zoho_account','R and R Realty');

-- ROLLBACK;  -- default: review the created table, then re-run with COMMIT.
