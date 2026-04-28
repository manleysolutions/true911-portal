# Operator tools — NOT DEPLOYED

This directory holds destructive maintenance utilities that **must not**
ride along with the deployed API image.

## Why this directory exists

Render's `true911-api` and `true911-worker` services are configured with
`rootDir: api`.  Anything outside `api/` is excluded from those build
contexts, so the files in this folder are **not present on the running
production pod and cannot be invoked from a Render shell session**.

This is intentional.  The scripts here can permanently delete or
overwrite production data and we do not want them one shell-tab away
from a tired operator.

## Contents

| File | Effect | Risk |
|---|---|---|
| `clean_operational_data.py`     | Truncates operational tables (devices, sims, lines, sites, etc.). | **High** — irreversible. |
| `purge_legacy_data.py`          | Deletes legacy rows by hand-coded criteria. | **High** — irreversible. |
| `reset_admin_password.py`       | Sets the `Admin` user's password to a value passed on the command line. | **Medium** — bypasses the change-password / invite flow.  Logs the password to shell history. |
| `reset_superadmin_password.py`  | Same as above for the bootstrap SuperAdmin. | **Medium** — same. |
| `reset_all_data.sql`            | Truncates the entire database. | **Critical** — full reset. |

## How to run one (when you actually need to)

These tools are meant to be invoked locally, against a copy of the
database (e.g. a `pg_dump` restored to your laptop) — **never** by
sshing into Render and running them on the live DB.

If you must run one against production, the safe path is:

1. Take a manual Postgres backup from the Render dashboard.
2. Open a Render shell on the API service.
3. Use `scp` / paste the script contents into a temp file in `/tmp`.
4. Run with the explicit `DATABASE_URL` environment variable from the
   service's env (so the operator path is identical to the runtime).
5. Verify the result.  Restore from the backup if anything looks wrong.

## What stays in `api/scripts/`

Read-only diagnostics — `inspect_user_access.py`,
`inspect_tenant_data.py`, `decode_token.py`, `test_verizon_connection.py`
— are kept inside `api/scripts/` because they are safe to invoke from a
Render shell during incident response and do not modify any data.
