from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import hash_ip, utcnow
from app.db.models import AuditEvent

log = get_logger(__name__)


class AuditService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def record(
        self,
        action: str,
        *,
        actor_user_id: UUID | None = None,
        actor_kind: str = "user",
        entity_type: str | None = None,
        entity_id: str | None = None,
        outcome: str = "success",
        ip: str | None = None,
        user_agent: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            actor_user_id=actor_user_id,
            actor_kind=actor_kind,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            ip_index=hash_ip(self._settings.secret_key, ip),
            user_agent=(user_agent or "")[:255] or None,
            meta=meta or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def purge(self, before: datetime | None = None) -> int:
        cutoff = before or utcnow() - timedelta(days=self._settings.audit_retention_days)
        result: CursorResult[Any] = cast(
            CursorResult[Any],
            await self._session.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff)),
        )
        return int(result.rowcount or 0)

    async def recent(self, *, actor_user_id: UUID | None = None, limit: int = 100) -> list[AuditEvent]:
        statement = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        if actor_user_id is not None:
            statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())
