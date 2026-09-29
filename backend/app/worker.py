from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update

from app.bot.profile import load_profile
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.base import get_engine, init_engine
from app.db.models import Appeal, AuthSession, Notification, OutboxMessage, ProcessedUpdate, User
from app.integrations.max.client import MaxBotClient
from app.runtime import init_runtime
from app.services.appeals import AppealService
from app.services.audit import AuditService
from app.services.notifications import NotificationService, OutboxDispatcher

log = get_logger(__name__)

OUTBOX_INTERVAL = 5.0
REMINDER_INTERVAL = 1800.0
RETENTION_INTERVAL = 86400.0


async def run_outbox(client: MaxBotClient) -> None:
    async for session in get_engine().open_session():
        try:
            dispatcher = OutboxDispatcher(session, get_settings(), client)
            sent = await dispatcher.dispatch()
            await session.commit()
            if sent:
                log.info("outbox_dispatched", count=sent)
        except Exception as exc:
            await session.rollback()
            log.error("outbox_cycle_failed", error=str(exc))
        finally:
            await session.close()
        break


async def run_reminders() -> None:
    settings = get_settings()
    async for session in get_engine().open_session():
        try:
            appeals = AppealService(session, settings)
            notifications = NotificationService(session, settings)
            overdue = await appeals.overdue()
            for appeal in overdue:
                already = await session.execute(
                    select(Notification.id).where(
                        Notification.kind == "appeal_overdue",
                        Notification.payload["appeal_id"].as_string() == str(appeal.id),
                    )
                )
                if already.scalar_one_or_none() is not None:
                    continue
                if appeal.assignee_id is None:
                    continue
                assignee = await session.get(User, appeal.assignee_id)
                if assignee is None:
                    continue
                await notifications.notify(
                    assignee,
                    kind="appeal_overdue",
                    title=f"Нарушен срок ответа по обращению {appeal.number}",
                    body=appeal.subject,
                    payload={"appeal_id": str(appeal.id)},
                )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.error("reminder_cycle_failed", error=str(exc))
        finally:
            await session.close()
        break


async def run_retention() -> None:
    settings = get_settings()
    async for session in get_engine().open_session():
        try:
            update_cutoff = datetime.now(UTC) - timedelta(days=7)
            outbox_cutoff = datetime.now(UTC) - timedelta(days=30)
            appeal_cutoff = datetime.now(UTC) - timedelta(days=settings.personal_data_retention_days)
            session_cutoff = datetime.now(UTC) - timedelta(days=settings.refresh_token_ttl_days)

            removed_updates = cast(
                CursorResult[Any],
                await session.execute(
                    delete(ProcessedUpdate).where(ProcessedUpdate.created_at < update_cutoff)
                ),
            ).rowcount
            removed_outbox = cast(
                CursorResult[Any],
                await session.execute(
                    delete(OutboxMessage).where(
                        OutboxMessage.status.in_(["sent", "failed"]),
                        OutboxMessage.created_at < outbox_cutoff,
                    )
                ),
            ).rowcount
            expired_appeals = (
                (await session.execute(select(Appeal).where(Appeal.updated_at < appeal_cutoff)))
                .scalars()
                .all()
            )
            for appeal in expired_appeals:
                appeal.body = "Содержание удалено по истечении срока хранения"
                appeal.ai_summary = None
                appeal.ai_meta = {}

            revoked_sessions = cast(
                CursorResult[Any],
                await session.execute(
                    update(AuthSession)
                    .where(AuthSession.expires_at < session_cutoff, AuthSession.revoked_at.is_(None))
                    .values(revoked_at=datetime.now(UTC))
                ),
            ).rowcount
            removed_audit = await AuditService(session, settings).purge()

            await session.commit()
            log.info(
                "retention_cycle",
                updates=int(removed_updates or 0),
                outbox=int(removed_outbox or 0),
                appeals=len(expired_appeals),
                sessions=int(revoked_sessions or 0),
                audit=int(removed_audit or 0),
            )
        except Exception as exc:
            await session.rollback()
            log.error("retention_cycle_failed", error=str(exc))
        finally:
            await session.close()
        break


async def _loop(name: str, interval: float, job: Callable[[], Awaitable[None]]) -> None:
    while True:
        try:
            await job()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("worker_loop_failed", loop=name, error=str(exc))
        await asyncio.sleep(interval)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    runtime = init_runtime(settings)
    await load_profile(runtime.max_client)

    stop = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, _request_stop)

    tasks = [
        asyncio.create_task(_loop("outbox", OUTBOX_INTERVAL, lambda: run_outbox(runtime.max_client))),
        asyncio.create_task(_loop("reminders", REMINDER_INTERVAL, run_reminders)),
        asyncio.create_task(_loop("retention", RETENTION_INTERVAL, run_retention)),
    ]
    log.info("worker_started", env=settings.app_env)
    await stop.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await runtime.close()
    await get_engine().dispose()
    log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
