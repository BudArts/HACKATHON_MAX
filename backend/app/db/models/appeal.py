from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class AppealCategory(StrEnum):
    academic = "academic"
    attendance = "attendance"
    behaviour = "behaviour"
    meals = "meals"
    health = "health"
    organization = "organization"
    other = "other"


class AppealStatus(StrEnum):
    draft = "draft"
    new = "new"
    in_progress = "in_progress"
    answered = "answered"
    closed = "closed"
    rejected = "rejected"


class AppealPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"


class Appeal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appeals"
    __table_args__ = (
        Index("ix_appeals_author", "author_id", "created_at"),
        Index("ix_appeals_assignee", "assignee_id", "status"),
        Index("ix_appeals_status_created", "status", "created_at"),
        Index("ix_appeals_student", "student_id"),
    )

    number: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    author_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    student_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("students.id", ondelete="SET NULL"),
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
    )
    category: Mapped[AppealCategory] = mapped_column(
        pg_enum(AppealCategory, "appeal_category"), default=AppealCategory.other, nullable=False
    )
    priority: Mapped[AppealPriority] = mapped_column(
        pg_enum(AppealPriority, "appeal_priority"), default=AppealPriority.normal, nullable=False
    )
    status: Mapped[AppealStatus] = mapped_column(
        pg_enum(AppealStatus, "appeal_status"), default=AppealStatus.new, nullable=False
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rating: Mapped[int | None] = mapped_column(Integer)
    is_personal_data_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AppealMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appeal_messages"
    __table_args__ = (Index("ix_appeal_messages_appeal", "appeal_id", "created_at"),)

    appeal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("appeals.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    author_role: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default="max", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_message_id: Mapped[str | None] = mapped_column(String(64))
