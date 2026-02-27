"""Read-only database sanity check.

Run:  python -m app.db_check

Prints the current alembic_version and lists all tables in public schema.
Makes ZERO changes.  Safe to call from any environment.
"""

import asyncio

from sqlalchemy import text

from .database import engine


async def check():
    async with engine.connect() as conn:
        # Current alembic revision
        try:
            row = await conn.execute(text("SELECT version_num FROM alembic_version"))
            version = row.scalar_one_or_none()
            print(f"alembic_version: {version or '(no rows)'}")
        except Exception:
            print("alembic_version: (table does not exist)")

        # All tables in public schema
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        )
        tables = [r[0] for r in rows]
        print(f"tables ({len(tables)}): {', '.join(tables) or '(none)'}")


if __name__ == "__main__":
    asyncio.run(check())
