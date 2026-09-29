from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, Request, Response
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import ForbiddenError
from app.core.logging import get_logger
from app.core.security import constant_time_equals
from app.db.base import get_engine
from app.db.models import ProcessedUpdate
from app.integrations.max.updates import parse_update

log = get_logger(__name__)
router = APIRouter(tags=["MAX"])


@router.post("/webhook/max", status_code=200, include_in_schema=False)
async def max_webhook(
    request: Request,
    background: BackgroundTasks,
    x_max_bot_api_secret: str | None = Header(default=None),
) -> Response:
    settings = get_settings()
    expected = settings.max_webhook_secret
    if expected and not (x_max_bot_api_secret and constant_time_equals(x_max_bot_api_secret, expected)):
        log.warning("webhook_secret_mismatch")
        raise ForbiddenError("Источник запроса не подтверждён")

    try:
        update: dict[str, Any] = await request.json()
    except Exception as exc:
        log.warning("webhook_bad_payload", error=str(exc))
        return Response(status_code=200)

    if not isinstance(update, dict) or "update_type" not in update:
        return Response(status_code=200)

    event = parse_update(update)
    if event is None:
        return Response(status_code=200)

    engine = get_engine()
    async for session in engine.open_session():
        try:
            exists = await session.execute(
                select(ProcessedUpdate.key).where(ProcessedUpdate.key == event.dedupe_key)
            )
            if exists.scalar_one_or_none() is not None:
                return Response(status_code=200)
            session.add(ProcessedUpdate(key=event.dedupe_key, update_type=event.update_type))
            await session.commit()
        finally:
            await session.close()
        break

    background.add_task(process_event, update)
    return Response(status_code=200)


async def process_event(update: dict[str, Any]) -> None:
    from app.bot.dispatcher import dispatch

    try:
        await dispatch(update)
    except Exception as exc:
        log.exception("webhook_processing_failed", update_type=update.get("update_type"), error=str(exc))
