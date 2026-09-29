from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

if TYPE_CHECKING:
    from app.db.models.user import User


class ConsentPurpose(StrEnum):
    service = "service"
    notifications = "notifications"
    ai_processing = "ai_processing"


class ConsentSource(StrEnum):
    miniapp = "miniapp"
    bot = "bot"
    paper = "paper"
    operator = "operator"


class PolicyDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policy_documents"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_policy_documents_code_version"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UserConsent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        Index("ix_user_consents_user_purpose", "user_id", "purpose"),
        Index("ix_user_consents_active", "purpose", "revoked_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[ConsentPurpose] = mapped_column(
        pg_enum(ConsentPurpose, "consent_purpose"), nullable=False
    )
    policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("policy_documents.id", ondelete="SET NULL"),
    )
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[ConsentSource] = mapped_column(pg_enum(ConsentSource, "consent_source"), nullable=False)
    ip_index: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="consents")
    policy: Mapped[PolicyDocument | None] = relationship()


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_actor", "actor_user_id", "created_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    ip_index: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    update_type: Mapped[str] = mapped_column(String(48), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OutboxMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (Index("ix_outbox_messages_due", "status", "scheduled_for"),)

    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
