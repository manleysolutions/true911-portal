"""Drop all tables and the alembic_version table so that
`alembic upgrade head` + `seed` can rebuild from scratch.

Only suitable for demo / dev environments.
"""

import asyncio

from sqlalchemy import text

from .database import engine, Base

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401


async def reset():
    async with engine.begin() as conn:
        # Drop all application tables
        await conn.run_sync(Base.metadata.drop_all)
        # Drop alembic tracking table if it exists
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    print("All tables dropped.")


if __name__ == "__main__":
    asyncio.run(reset())
