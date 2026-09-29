"""Первичная схема

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
TIMESTAMPTZ = sa.DateTime(timezone=True)

user_role = postgresql.ENUM(
    "guest", "parent", "teacher", "administrator", name="user_role", create_type=False
)
consent_purpose = postgresql.ENUM(
    "service", "notifications", "ai_processing", name="consent_purpose", create_type=False
)
consent_source = postgresql.ENUM(
    "miniapp", "bot", "paper", "operator", name="consent_source", create_type=False
)
appeal_category = postgresql.ENUM(
    "academic",
    "attendance",
    "behaviour",
    "meals",
    "health",
    "organization",
    "other",
    name="appeal_category",
    create_type=False,
)
appeal_priority = postgresql.ENUM("low", "normal", "high", name="appeal_priority", create_type=False)
appeal_status = postgresql.ENUM(
    "draft", "new", "in_progress", "answered", "closed", "rejected", name="appeal_status", create_type=False
)

ENUMS = (user_role, consent_purpose, consent_source, appeal_category, appeal_priority, appeal_status)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "policy_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("published_at", TIMESTAMPTZ, nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", "version", name="uq_policy_documents_code_version"),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("max_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64)),
        sa.Column("first_name", sa.String(length=64)),
        sa.Column("last_name", sa.String(length=64)),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("role", user_role, nullable=False, server_default="guest"),
        sa.Column("phone_encrypted", sa.Text()),
        sa.Column("phone_index", sa.String(length=64)),
        sa.Column("email_encrypted", sa.Text()),
        sa.Column("email_index", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bot_stopped_at", TIMESTAMPTZ),
        sa.Column("last_seen_at", TIMESTAMPTZ),
        sa.Column("password_hash", sa.String(length=255)),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", TIMESTAMPTZ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("max_user_id", name="uq_users_max_user_id"),
    )
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_phone_index", "users", ["phone_index"])
    op.create_index("ix_users_email_index", "users", ["email_index"])

    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_name", sa.String(length=64)),
        sa.Column("inn", sa.String(length=12)),
        sa.Column("address", sa.String(length=255)),
        sa.Column("contact_phone", sa.String(length=32)),
        sa.Column("contact_email", sa.String(length=255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "class_groups",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey(
                "organizations.id", ondelete="CASCADE", name="fk_class_groups_organization_id_organizations"
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("academic_year", sa.String(length=9), nullable=False),
        sa.Column(
            "homeroom_teacher_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_class_groups_homeroom_teacher_id_users"),
        ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "name", name="uq_class_groups_org_name"),
    )

    op.create_table(
        "students",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "class_group_id",
            UUID,
            sa.ForeignKey(
                "class_groups.id", ondelete="CASCADE", name="fk_students_class_group_id_class_groups"
            ),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(length=64), nullable=False),
        sa.Column("last_name", sa.String(length=64), nullable=False),
        sa.Column("patronymic", sa.String(length=64)),
        sa.Column("birth_date", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_students_class_group", "students", ["class_group_id"])

    op.create_table(
        "guardian_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "student_id",
            UUID,
            sa.ForeignKey("students.id", ondelete="CASCADE", name="fk_guardian_links_student_id_students"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_guardian_links_user_id_users"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(length=32), nullable=False, server_default="parent"),
        sa.Column("verified_at", TIMESTAMPTZ),
        sa.Column("verification_code_index", sa.String(length=64)),
        sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("student_id", "user_id", name="uq_guardian_links_student_user"),
    )
    op.create_index("ix_guardian_links_user", "guardian_links", ["user_id"])

    op.create_table(
        "teacher_assignments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "teacher_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_teacher_assignments_teacher_id_users"),
            nullable=False,
        ),
        sa.Column(
            "class_group_id",
            UUID,
            sa.ForeignKey(
                "class_groups.id",
                ondelete="CASCADE",
                name="fk_teacher_assignments_class_group_id_class_groups",
            ),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("teacher_id", "class_group_id", "subject", name="uq_teacher_assignments_unique"),
    )

    op.create_table(
        "user_consents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_consents_user_id_users"),
            nullable=False,
        ),
        sa.Column("purpose", consent_purpose, nullable=False),
        sa.Column(
            "policy_id",
            UUID,
            sa.ForeignKey(
                "policy_documents.id", ondelete="SET NULL", name="fk_user_consents_policy_id_policy_documents"
            ),
        ),
        sa.Column("policy_version", sa.String(length=16), nullable=False),
        sa.Column("source", consent_source, nullable=False),
        sa.Column("ip_index", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=255)),
        sa.Column("granted_at", TIMESTAMPTZ, nullable=False),
        sa.Column("revoked_at", TIMESTAMPTZ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_consents_user_purpose", "user_consents", ["user_id", "purpose"])
    op.create_index("ix_user_consents_active", "user_consents", ["purpose", "revoked_at"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_auth_sessions_user_id_users"),
            nullable=False,
        ),
        sa.Column("refresh_jti", sa.String(length=64), nullable=False),
        sa.Column("ip_index", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=255)),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=False),
        sa.Column("revoked_at", TIMESTAMPTZ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("refresh_jti", name="uq_auth_sessions_refresh_jti"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "appeals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("number", sa.String(length=24), nullable=False),
        sa.Column(
            "author_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_appeals_author_id_users"),
            nullable=False,
        ),
        sa.Column(
            "assignee_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_appeals_assignee_id_users"),
        ),
        sa.Column(
            "student_id",
            UUID,
            sa.ForeignKey("students.id", ondelete="SET NULL", name="fk_appeals_student_id_students"),
        ),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey(
                "organizations.id", ondelete="SET NULL", name="fk_appeals_organization_id_organizations"
            ),
        ),
        sa.Column("category", appeal_category, nullable=False, server_default="other"),
        sa.Column("priority", appeal_priority, nullable=False, server_default="normal"),
        sa.Column("status", appeal_status, nullable=False, server_default="new"),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("ai_meta", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("responded_at", TIMESTAMPTZ),
        sa.Column("closed_at", TIMESTAMPTZ),
        sa.Column("due_at", TIMESTAMPTZ),
        sa.Column("rating", sa.Integer()),
        sa.Column("is_personal_data_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("number", name="uq_appeals_number"),
    )
    op.create_index("ix_appeals_author", "appeals", ["author_id", "created_at"])
    op.create_index("ix_appeals_assignee", "appeals", ["assignee_id", "status"])
    op.create_index("ix_appeals_status_created", "appeals", ["status", "created_at"])
    op.create_index("ix_appeals_student", "appeals", ["student_id"])

    op.create_table(
        "appeal_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "appeal_id",
            UUID,
            sa.ForeignKey("appeals.id", ondelete="CASCADE", name="fk_appeal_messages_appeal_id_appeals"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_appeal_messages_author_id_users"),
        ),
        sa.Column("author_role", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_ai_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delivered_at", TIMESTAMPTZ),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_appeal_messages_appeal", "appeal_messages", ["appeal_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_notifications_user_id_users"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="max"),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("sent_at", TIMESTAMPTZ),
        sa.Column("read_at", TIMESTAMPTZ),
        sa.Column("max_message_id", sa.String(length=64)),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("actor_user_id", UUID),
        sa.Column("actor_kind", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64)),
        sa.Column("entity_id", sa.String(length=64)),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="success"),
        sa.Column("ip_index", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=255)),
        sa.Column("meta", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_actor", "audit_events", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])

    op.create_table(
        "processed_updates",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("update_type", sa.String(length=48), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_for", TIMESTAMPTZ, nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", TIMESTAMPTZ),
    )
    op.create_index("ix_outbox_messages_due", "outbox_messages", ["status", "scheduled_for"])


def downgrade() -> None:
    for table in (
        "outbox_messages",
        "processed_updates",
        "audit_events",
        "notifications",
        "appeal_messages",
        "appeals",
        "auth_sessions",
        "user_consents",
        "teacher_assignments",
        "guardian_links",
        "students",
        "class_groups",
        "organizations",
        "users",
        "policy_documents",
    ):
        op.drop_table(table)

    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
