"""Auth overhaul: UUID user IDs, updated_at, case-insensitive email index.

Revision ID: 009
Revises: 008
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add updated_at column
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )

    # 2. Convert id from INTEGER serial to UUID
    # 2a. Add a new UUID column
    op.add_column(
        "users",
        sa.Column(
            "uuid_id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )

    # 2b. Drop old primary key constraint and the integer id column
    op.drop_constraint("users_pkey", "users", type_="primary")
    op.drop_column("users", "id")

    # 2c. Rename uuid_id → id and set as primary key
    op.alter_column("users", "uuid_id", new_column_name="id")
    op.create_primary_key("users_pkey", "users", ["id"])

    # 3. Case-insensitive unique index on email
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    # Remove case-insensitive email index
    op.drop_index("uq_users_email_lower", table_name="users")

    # Convert id back from UUID to INTEGER serial
    op.drop_constraint("users_pkey", "users", type_="primary")
    op.alter_column("users", "id", new_column_name="uuid_id")

    op.add_column(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    )
    op.create_primary_key("users_pkey", "users", ["id"])
    op.drop_column("users", "uuid_id")

    # Remove updated_at column
    op.drop_column("users", "updated_at")
