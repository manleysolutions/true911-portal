"""Standalone script to drop ALL tables in the database.

Uses raw SQL via asyncpg directly — no dependency on app modules.
This guarantees it works even if the app has import issues.
"""

import asyncio
import os
import sys


async def drop_all():
    try:
        import asyncpg
    except ImportError:
        print("asyncpg not installed, skipping reset")
        return

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set, skipping reset")
        return

    # asyncpg needs postgresql:// (not postgres://)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    print(f"Connecting to database...")
    conn = await asyncpg.connect(url)

    # Drop ALL tables in public schema (CASCADE handles foreign keys)
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
    print("All public tables dropped (including alembic_version).")


if __name__ == "__main__":
    asyncio.run(drop_all())
