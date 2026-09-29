from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.integrations.gigachat.client import GigaChatClient
from app.integrations.max.client import MaxBotClient
from app.services.tutor import TutorService


@dataclass(slots=True)
class Runtime:
    settings: Settings
    max_client: MaxBotClient
    gigachat: GigaChatClient
    tutor: TutorService

    async def close(self) -> None:
        await self.max_client.close()
        await self.gigachat.close()


_runtime: Runtime | None = None


def init_runtime(settings: Settings) -> Runtime:
    global _runtime
    _runtime = Runtime(
        settings=settings,
        max_client=MaxBotClient(settings),
        gigachat=GigaChatClient(settings),
        tutor=TutorService(GigaChatClient(settings)),
    )
    return _runtime


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("Runtime is not initialized")
    return _runtime
