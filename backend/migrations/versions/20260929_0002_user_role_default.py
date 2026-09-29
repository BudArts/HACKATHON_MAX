"""Родительская роль по умолчанию

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "guest", "parent", "teacher", "administrator", name="user_role", create_type=False
)


def upgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=user_role,
        existing_nullable=False,
        server_default="parent",
    )
    op.execute("UPDATE users SET role = 'parent' WHERE role = 'guest'")


def downgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=user_role,
        existing_nullable=False,
        server_default="guest",
    )
