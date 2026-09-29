from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response

from app.api.deps import CurrentUser, NotificationServiceDep, SessionDep
from app.api.schemas import NotificationView
from app.core.errors import NotFoundError

router = APIRouter(prefix="/notifications", tags=["Уведомления"])


@router.get("", response_model=list[NotificationView], summary="Входящие уведомления")
async def list_notifications(
    user: CurrentUser,
    service: NotificationServiceDep,
    unread_only: bool = False,
    limit: int = 50,
) -> list[NotificationView]:
    items = await service.inbox(user.id, unread_only=unread_only, limit=min(max(limit, 1), 100))
    return [NotificationView.model_validate(item) for item in items]


@router.post("/{notification_id}/read", status_code=204, summary="Отметить прочитанным")
async def mark_read(
    notification_id: UUID,
    user: CurrentUser,
    service: NotificationServiceDep,
    session: SessionDep,
) -> Response:
    updated = await service.mark_read(user.id, notification_id)
    if not updated:
        raise NotFoundError("Уведомление не найдено")
    await session.commit()
    return Response(status_code=204)


@router.post("/read-all", status_code=204, summary="Отметить все прочитанными")
async def mark_all_read(
    user: CurrentUser,
    session: SessionDep,
    service: NotificationServiceDep,
) -> Response:
    from datetime import UTC, datetime

    from sqlalchemy import update

    from app.db.models import Notification

    await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
    return Response(status_code=204)
