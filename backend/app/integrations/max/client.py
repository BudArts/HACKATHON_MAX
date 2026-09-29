from __future__ import annotations

import asyncio
from typing import Any, Literal

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.max.http import MaxApiError, make_client, raise_for_status_detail

log = get_logger(__name__)

TextFormat = Literal["markdown", "html"]
UPDATE_TYPES = (
    "bot_added",
    "bot_started",
    "bot_stopped",
    "bot_removed",
    "chat_title_changed",
    "dialog_cleared",
    "dialog_muted",
    "dialog_unmuted",
    "dialog_removed",
    "message_callback",
    "message_created",
    "message_edited",
    "message_removed",
    "comment_created",
    "comment_edited",
    "comment_removed",
    "user_added",
    "user_removed",
    "bot_admin_permissions_changed",
)


class MaxBotClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.max_api_base.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._settings.max_bot_token)

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = make_client(
                        self._settings.max_ca_bundle,
                        float(self._settings.max_request_timeout),
                        verify_ssl=self._settings.max_verify_ssl,
                    )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        operation: str | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        if not self.configured:
            raise MaxApiError(operation or path, 0, "MAX_BOT_TOKEN не задан")
        client = await self.client()
        headers = {"Authorization": self._settings.max_bot_token, "Content-Type": "application/json"}
        url = f"{self._base_url}{path}"
        attempt = 0
        while True:
            try:
                response = await client.request(method, url, params=params, json=json_body, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt >= retries:
                    log.error("max_transport_error", operation=operation or path, error=str(exc))
                    raise MaxApiError(operation or path, 0, str(exc)) from exc
                attempt += 1
                await asyncio.sleep(0.5 * (2**attempt))
                continue

            try:
                raise_for_status_detail(response, operation or path)
            except MaxApiError as exc:
                if exc.retryable and attempt < retries:
                    attempt += 1
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise
            if response.status_code == 204 or not response.content:
                return {}
            payload: dict[str, Any] = response.json()
            return payload

    async def get_file_url(self, token: str) -> str:
        payload = await self._request("GET", "/files", params={"token": token}, operation="get_file")
        url = payload.get("url")
        if not url:
            raise MaxApiError("get_file", 0, "MAX API не вернул url файла")
        return str(url)

    async def download_file(self, token: str) -> bytes:
        url = await self.get_file_url(token)
        client = await self.client()
        response = await client.get(url)
        if response.status_code >= 400:
            raise MaxApiError("download_file", response.status_code, "файл недоступен")
        return response.content

    async def get_me(self) -> dict[str, Any]:
        return await self._request("GET", "/me", operation="get_me")

    async def send_message(
        self,
        text: str,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        attachments: list[dict[str, Any]] | None = None,
        format: TextFormat | None = None,
        notify: bool = True,
        link: dict[str, Any] | None = None,
        disable_link_preview: bool | None = None,
    ) -> dict[str, Any]:
        if user_id is None and chat_id is None:
            raise ValueError("Требуется user_id или chat_id")
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id
        if disable_link_preview is not None:
            params["disable_link_preview"] = disable_link_preview

        body: dict[str, Any] = {"text": text[:4000], "notify": notify}
        if attachments is not None:
            body["attachments"] = attachments
        if format is not None:
            body["format"] = format
        if link is not None:
            body["link"] = link
        return await self._request(
            "POST", "/messages", params=params, json_body=body, operation="send_message"
        )

    async def edit_message(
        self,
        message_id: str,
        text: str | None = None,
        *,
        attachments: list[dict[str, Any]] | None = None,
        format: TextFormat | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if text is not None:
            body["text"] = text[:4000]
        if attachments is not None:
            body["attachments"] = attachments
        if format is not None:
            body["format"] = format
        return await self._request(
            "PUT",
            "/messages",
            params={"message_id": message_id},
            json_body=body,
            operation="edit_message",
        )

    async def answer_callback(
        self,
        callback_id: str,
        *,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if notification is not None:
            body["notification"] = notification
        if message is not None:
            body["message"] = message
        return await self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json_body=body,
            operation="answer_callback",
        )

    async def send_typing(self, chat_id: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/chats/{chat_id}/actions",
            json_body={"action": "typing_on"},
            operation="send_typing",
            retries=0,
        )

    async def set_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        return await self._request(
            "PATCH",
            "/me/commands",
            json_body={"commands": commands[:32]},
            operation="set_commands",
        )

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        limit: int = 100,
        long_poll: int = 30,
        types: tuple[str, ...] = UPDATE_TYPES,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "timeout": long_poll}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        return await self._request("GET", "/updates", params=params, operation="get_updates", retries=0)

    async def subscribe(self, url: str, secret: str, types: tuple[str, ...] = UPDATE_TYPES) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url, "update_types": list(types)}
        if secret:
            body["secret"] = secret
        return await self._request("POST", "/subscriptions", json_body=body, operation="subscribe")

    async def list_subscriptions(self) -> dict[str, Any]:
        return await self._request("GET", "/subscriptions", operation="list_subscriptions")

    async def unsubscribe(self, url: str) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            "/subscriptions",
            params={"url": url},
            operation="unsubscribe",
        )
