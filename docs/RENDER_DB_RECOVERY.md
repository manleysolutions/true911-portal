# Render Database Recovery

## When to use this

- Deploy fails with `DuplicateTableError: relation "X" already exists`
- Deploy fails with `relation "users" does not exist` (partial migration state)
- `alembic_version` table is missing or contains a revision that doesn't match the migration chain

All of these mean the database schema is in a state that Alembic can't reconcile.
The fastest fix is to wipe the public schema and let `alembic upgrade head` rebuild from 001.

> **This destroys all data.** Only do this if the database has no production data you need,
> or you have a backup.

## Option A: Drop and recreate the schema (fastest)

1. Go to **Render Dashboard > your Postgres database > Shell** (or connect via `psql`).
2. Run:

```sql
-- Drop everything in public schema (tables, sequences, functions, etc.)
DROP SCHEMA public CASCADE;

-- Recreate the empty schema with default grants
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO true911_prod_db_user;
GRANT ALL ON SCHEMA public TO public;
```

Replace `true911_prod_db_user` with the actual DB user shown in your Render database info panel.

3. Go to **Render Dashboard > true911-api > Manual Deploy** and trigger a deploy.
4. The start command runs `alembic upgrade head` which will create all tables from scratch.

## Option B: Delete and recreate the database

If Option A doesn't work (e.g. permission issues):

1. Go to **Render Dashboard > your Postgres database > Settings > Delete Database**.
2. Create a new Postgres database with the same name and region.
3. Update the `DATABASE_URL` env var on `true911-api` to point to the new database
   (or re-link it via `fromDatabase` in render.yaml).
4. Trigger a manual deploy.

## Preventing this in the future

The root cause was `reset_db.py` / `reset_and_migrate.py` being called during deploys.
These scripts now require **both**:

- `APP_MODE=demo`
- `ALLOW_DB_RESET=1`

Neither is set on Render production, so they are no-ops.

The deploy pipeline is now:

```
Build:  pip install -r requirements.txt
Start:  alembic upgrade head && python -m app.seed && uvicorn ...
```

- `alembic upgrade head` is idempotent — if all migrations are applied, it does nothing.
- `python -m app.seed` checks `APP_MODE` and exits immediately in production.

## Checking current DB state

Run from the Render Shell tab on the API service:

```bash
python -m app.db_check
```

This prints the current `alembic_version` and lists all tables. It makes zero changes.
