from __future__ import annotations

import asyncio
import contextlib

from app.core.logging import get_logger
from app.integrations.max.client import UPDATE_TYPES, MaxBotClient
from app.integrations.max.http import MaxApiError

log = get_logger(__name__)


class PollingTask:
    def __init__(self, client: MaxBotClient, *, long_poll_timeout: int = 25) -> None:
        self._client = client
        self._long_poll_timeout = long_poll_timeout
        self._marker: int | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="max-polling")
        log.info("polling_started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None
        log.info("polling_stopped")

    async def _run(self) -> None:
        from app.bot.dispatcher import dispatch

        backoff = 1.0
        while not self._stop.is_set():
            try:
                response = await self._client.get_updates(
                    marker=self._marker,
                    limit=50,
                    long_poll=self._long_poll_timeout,
                    types=UPDATE_TYPES,
                )
            except MaxApiError as exc:
                log.warning("polling_error", status=exc.status_code, code=exc.code)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("polling_unexpected_error", error=str(exc))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            backoff = 1.0
            updates = response.get("updates") or []
            for update in updates:
                if self._stop.is_set():
                    break
                if isinstance(update, dict):
                    await dispatch(update)

            marker = response.get("marker")
            if marker is not None:
                self._marker = int(marker)
            if not updates:
                await asyncio.sleep(0.5)
