from __future__ import annotations

from app.core.logging import get_logger
from app.db.base import get_engine
from app.integrations.max.updates import parse_update

log = get_logger(__name__)


async def dispatch(update: dict[str, object]) -> None:
    event = parse_update(update)
    if event is None:
        return

    from app.bot.handlers import handle_event

    engine = get_engine()
    async for session in engine.open_session():
        try:
            await handle_event(session, event)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.exception("bot_handler_failed", update_type=event.update_type, error=str(exc))
        finally:
            await session.close()
        break
