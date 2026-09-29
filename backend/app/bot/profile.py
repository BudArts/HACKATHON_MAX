from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.integrations.max.client import MaxBotClient

log = get_logger(__name__)


@dataclass(slots=True)
class BotProfile:
    user_id: int | None = None
    username: str | None = None
    loaded: bool = False
    error: str | None = field(default=None)

    @property
    def ready(self) -> bool:
        return self.loaded and self.user_id is not None and bool(self.username)


_profile = BotProfile()


async def load_profile(max_client: MaxBotClient) -> BotProfile:
    if _profile.loaded:
        return _profile
    try:
        info = await max_client.get_me()
        _profile.user_id = int(info.get("user_id") or 0) or None
        _profile.username = str(info.get("username") or "") or None
        _profile.loaded = True
    except Exception as exc:
        _profile.loaded = True
        _profile.error = str(exc)
        log.warning("bot_profile_unavailable", error=str(exc))
    return _profile


def cached_profile() -> BotProfile:
    return _profile
