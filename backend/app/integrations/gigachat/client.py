from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.max.http import ssl_verify

log = get_logger(__name__)


class GigaChatError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(slots=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str | None
    refused: bool = False


class GigaChatClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.gigachat_enabled and bool(self._settings.gigachat_credentials)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            bundle = self._settings.gigachat_ca_bundle
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(float(self._settings.gigachat_timeout), connect=10.0),
                verify=ssl_verify(bundle) if self._settings.gigachat_verify_ssl else False,
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
            )
        return self._http

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        async with self._token_lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token
            self._token, self._token_expires_at = await self._fetch_token()
            return self._token

    async def _fetch_token(self) -> tuple[str, float]:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self._settings.gigachat_credentials}",
        }
        data = {"scope": self._settings.gigachat_scope}
        try:
            response = await self._client().post(self._settings.gigachat_auth_url, headers=headers, data=data)
        except httpx.HTTPError as exc:
            raise GigaChatError("Не удалось получить токен GigaChat", retryable=True) from exc

        if response.status_code != 200:
            log.error("gigachat_oauth_failed", status=response.status_code)
            raise GigaChatError(
                f"OAuth GigaChat вернул {response.status_code}", retryable=response.status_code >= 500
            )

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise GigaChatError("OAuth GigaChat не вернул access_token")
        expires_at = float(payload.get("expires_at") or 0) / 1000.0
        if expires_at <= time.time():
            expires_at = time.time() + 1500
        return token, expires_at

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        top_p: float | None = None,
    ) -> Completion:
        if not self.enabled:
            raise GigaChatError("GigaChat отключён")

        body: dict[str, Any] = {
            "model": self._settings.gigachat_model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if top_p is not None:
            body["top_p"] = top_p

        token = await self._ensure_token()
        url = f"{self._settings.gigachat_base_url.rstrip('/')}/chat/completions"

        for attempt in range(3):
            try:
                response = await self._client().post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "X-Request-ID": uuid.uuid4().hex,
                    },
                    json=body,
                )
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise GigaChatError("Сервис генерации недоступен", retryable=True) from exc
                await asyncio.sleep(0.7 * (2**attempt))
                continue

            if response.status_code == 401:
                self._token = None
                token = await self._ensure_token()
                if attempt == 2:
                    raise GigaChatError("Авторизация в GigaChat не удалась")
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    raise GigaChatError("Сервис генерации перегружен", retryable=True)
                await asyncio.sleep(1.2 * (2**attempt))
                continue

            if response.status_code != 200:
                log.error("gigachat_completion_failed", status=response.status_code)
                raise GigaChatError(f"GigaChat вернул {response.status_code}")

            return self._parse(response.json())

        raise GigaChatError("Не удалось получить ответ модели", retryable=True)

    def _parse(self, payload: dict[str, Any]) -> Completion:
        choices = payload.get("choices") or []
        if not choices:
            raise GigaChatError("Пустой ответ модели")
        choice = choices[0]
        message = choice.get("message") or {}
        usage = payload.get("usage") or {}
        finish_reason = choice.get("finish_reason")
        return Completion(
            text=str(message.get("content") or "").strip(),
            model=str(payload.get("model") or self._settings.gigachat_model),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            finish_reason=finish_reason,
            refused=finish_reason == "content_filter",
        )
