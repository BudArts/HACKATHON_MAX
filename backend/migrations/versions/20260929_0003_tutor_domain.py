"""Ядро ИИ-наставника

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
TIMESTAMPTZ = sa.DateTime(timezone=True)

user_role = postgresql.ENUM(
    "student", "parent", "teacher", "administrator", name="user_role", create_type=False
)
task_subject = postgresql.ENUM("math", "physics", name="task_subject", create_type=True)
task_status = postgresql.ENUM("active", "solved", "abandoned", name="task_status", create_type=True)
message_author = postgresql.ENUM("student", "tutor", name="task_message_author", create_type=True)


def upgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=True)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::text::user_role")
    op.execute("UPDATE users SET role = 'student' WHERE role = 'guest'")
    op.add_column("users", sa.Column("grade", sa.Integer(), nullable=True))

    op.create_table(
        "tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject", task_subject, nullable=False, server_default="math"),
        sa.Column("grade", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("topic", sa.String(length=160)),
        sa.Column("status", task_status, nullable=False, server_default="active"),
        sa.Column("steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text()),
        sa.Column("redaction_categories", JSONB, nullable=False, server_default="{}"),
        sa.Column("started_at", TIMESTAMPTZ, nullable=False),
        sa.Column("last_activity_at", TIMESTAMPTZ, nullable=False),
        sa.Column("solved_at", TIMESTAMPTZ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False),
    )
    op.create_index("ix_tasks_user_status", "tasks", ["user_id", "status"])
    op.create_index("ix_tasks_user_started", "tasks", ["user_id", "started_at"])

    op.create_table(
        "task_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author", message_author, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
    )
    op.create_index("ix_task_messages_task", "task_messages", ["task_id", "created_at"])

    op.create_table(
        "parent_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guardian_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("code_index", sa.String(length=64)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_at", TIMESTAMPTZ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False),
        sa.UniqueConstraint("student_user_id", "guardian_user_id", name="uq_parent_links_pair"),
    )
    op.create_index("ix_parent_links_guardian", "parent_links", ["guardian_user_id"])
    op.create_index("ix_parent_links_code_index", "parent_links", ["code_index"])


def downgrade() -> None:
    op.drop_table("parent_links")
    op.drop_table("task_messages")
    op.drop_table("tasks")
    op.drop_column("users", "grade")
    op.execute("UPDATE users SET role = 'parent' WHERE role = 'student'")
    task_subject.drop(op.get_bind(), checkfirst=True)
    task_status.drop(op.get_bind(), checkfirst=True)
    message_author.drop(op.get_bind(), checkfirst=True)
