"""Drop all tables and the alembic_version table so that
`alembic upgrade head` + `seed` can rebuild from scratch.

SAFETY: Requires BOTH of:
  1. APP_MODE=demo       (or unset — defaults to "production" which is denied)
  2. ALLOW_DB_RESET=1    (explicit opt-in)

If either is missing, the script exits with a message and zero side-effects.
"""

import asyncio
import os
import sys

from sqlalchemy import text


def _check_guards() -> None:
    app_mode = os.environ.get("APP_MODE", "production")
    allow = os.environ.get("ALLOW_DB_RESET", "")

    if app_mode != "demo":
        print(f"ABORT: APP_MODE={app_mode!r} — reset_db only runs in demo mode.")
        sys.exit(0)

    if allow != "1":
        print("ABORT: ALLOW_DB_RESET is not set to '1' — refusing to drop tables.")
        sys.exit(0)


async def reset():
    _check_guards()

    from .database import engine, Base

    # Import all models so Base.metadata knows about them
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    print("All tables dropped (demo reset).")


if __name__ == "__main__":
    _check_guards()
    asyncio.run(reset())
