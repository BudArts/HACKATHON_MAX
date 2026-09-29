from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class TaskSubject(StrEnum):
    math = "math"
    physics = "physics"


class TaskStatus(StrEnum):
    active = "active"
    solved = "solved"
    abandoned = "abandoned"


class MessageAuthor(StrEnum):
    student = "student"
    tutor = "tutor"


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_user_started", "user_id", "started_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject: Mapped[TaskSubject] = mapped_column(
        pg_enum(TaskSubject, "task_subject"), default=TaskSubject.math, nullable=False
    )
    grade: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    topic: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[TaskStatus] = mapped_column(
        pg_enum(TaskStatus, "task_status"), default=TaskStatus.active, nullable=False
    )
    steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    redaction_categories: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[TaskMessage]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TaskMessage.created_at",
    )


class TaskMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "task_messages"
    __table_args__ = (Index("ix_task_messages_task", "task_id", "created_at"),)

    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    author: Mapped[MessageAuthor] = mapped_column(
        pg_enum(MessageAuthor, "task_message_author"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped[Task] = relationship(back_populates="messages")


class ParentLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "parent_links"
    __table_args__ = (
        UniqueConstraint("student_user_id", "guardian_user_id", name="uq_parent_links_pair"),
        Index("ix_parent_links_guardian", "guardian_user_id"),
        Index("ix_parent_links_code_index", "code_index"),
    )

    student_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    guardian_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    code_index: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
