from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Notification, OutboxMessage, User
from app.integrations.max.client import MaxBotClient
from app.integrations.max.http import MaxApiError
from app.services.audit import AuditService

log = get_logger(__name__)

MAX_ATTEMPTS = 5
RETRY_BASE_SECONDS = 60


class NotificationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._audit = AuditService(session, settings)

    async def notify(
        self,
        user: User,
        *,
        kind: str,
        title: str,
        body: str | None = None,
        payload: dict[str, Any] | None = None,
        deliver: bool = True,
    ) -> Notification:
        notification = Notification(
            user_id=user.id,
            kind=kind,
            title=title[:200],
            body=body,
            payload=payload or {},
            channel="max",
            created_at=datetime.now(UTC),
        )
        self._session.add(notification)
        await self._session.flush()

        if deliver and user.bot_stopped_at is None:
            text = f"{title}\n\n{body}".strip() if body else title
            self._session.add(
                OutboxMessage(
                    status="pending",
                    kind="max_message",
                    payload={
                        "user_id": user.max_user_id,
                        "text": text,
                        "notification_id": str(notification.id),
                    },
                    attempts=0,
                    scheduled_for=datetime.now(UTC),
                )
            )
        await self._session.flush()
        return notification

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> bool:
        statement = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )
        result = cast(CursorResult[Any], await self._session.execute(statement))
        return int(result.rowcount or 0) > 0

    async def inbox(self, user_id: UUID, *, unread_only: bool = False, limit: int = 50) -> list[Notification]:
        statement = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        result = await self._session.execute(statement)
        return list(result.scalars().all())


class OutboxDispatcher:
    def __init__(self, session: AsyncSession, settings: Settings, max_client: MaxBotClient) -> None:
        self._session = session
        self._settings = settings
        self._max = max_client
        self._audit = AuditService(session, settings)

    async def dispatch(self, batch_size: int = 20) -> int:
        result = await self._session.execute(
            select(OutboxMessage)
            .where(OutboxMessage.status == "pending", OutboxMessage.scheduled_for <= datetime.now(UTC))
            .order_by(OutboxMessage.scheduled_for)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        messages = list(result.scalars().all())
        sent = 0
        for message in messages:
            if await self._deliver(message):
                sent += 1
        await self._session.flush()
        return sent

    async def _deliver(self, message: OutboxMessage) -> bool:
        payload = message.payload or {}
        message.attempts += 1
        try:
            response = await self._max.send_message(
                str(payload.get("text", "")), user_id=int(payload["user_id"])
            )
        except MaxApiError as exc:
            message.last_error = f"{exc.operation}:{exc.status_code}:{exc.code or ''}"[:500]
            if exc.status_code == 403 or not exc.retryable or message.attempts >= MAX_ATTEMPTS:
                message.status = "failed"
                log.warning("outbox_failed", kind=message.kind, error=message.last_error)
            else:
                message.scheduled_for = datetime.now(UTC) + timedelta(
                    seconds=RETRY_BASE_SECONDS * (2.5 ** (message.attempts - 1))
                )
            return False
        except (KeyError, TypeError, ValueError) as exc:
            message.status = "failed"
            message.last_error = f"malformed_payload:{exc}"[:500]
            return False

        mid = ((response.get("message") or {}).get("body") or {}).get("mid")
        message.status = "sent"
        message.processed_at = datetime.now(UTC)
        message.last_error = None

        notification_id = payload.get("notification_id")
        if notification_id and mid:
            await self._session.execute(
                update(Notification)
                .where(Notification.id == UUID(str(notification_id)))
                .values(sent_at=datetime.now(UTC), max_message_id=str(mid))
            )
        return True
