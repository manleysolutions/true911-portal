"""Standalone script to drop ALL tables in the database.

SAFETY: Requires BOTH of:
  1. APP_MODE=demo
  2. ALLOW_DB_RESET=1

If either is missing, the script prints a message and exits cleanly.
This script is NEVER called from render.yaml or any deploy pipeline.
It exists only for local development convenience.
"""

import asyncio
import os
import sys


def _check_guards() -> None:
    app_mode = os.environ.get("APP_MODE", "production")
    allow = os.environ.get("ALLOW_DB_RESET", "")

    if app_mode != "demo":
        print(f"ABORT: APP_MODE={app_mode!r} — reset only runs in demo mode.")
        sys.exit(0)

    if allow != "1":
        print("ABORT: ALLOW_DB_RESET is not set to '1' — refusing to drop tables.")
        sys.exit(0)


async def drop_all():
    _check_guards()

    try:
        import asyncpg
    except ImportError:
        print("asyncpg not installed, skipping reset")
        return

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set, skipping reset")
        return

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    print("Connecting to database...")
    conn = await asyncpg.connect(url)

    await conn.execute("""
        DO $$ DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """)

    await conn.close()
    print("All public tables dropped (demo reset).")


if __name__ == "__main__":
    _check_guards()
    asyncio.run(drop_all())
