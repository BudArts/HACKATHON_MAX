from __future__ import annotations

import re
from typing import Any

CALLBACK_PAYLOAD_MAX = 1024
BUTTON_TEXT_MAX = 128
START_PARAM_PATTERN = re.compile(r"^[A-Za-z0-9_-]{0,512}$")
MAX_ROWS = 30
MAX_BUTTONS_PER_ROW = 7
MAX_BUTTONS_PER_ROW_WIDE = 3
WIDE_BUTTON_TYPES = {"link", "open_app", "request_geo_location", "request_contact"}


def callback_button(text: str, payload: str) -> dict[str, Any]:
    return {"type": "callback", "text": text[:BUTTON_TEXT_MAX], "payload": payload[:CALLBACK_PAYLOAD_MAX]}


def link_button(text: str, url: str) -> dict[str, Any]:
    return {"type": "link", "text": text[:BUTTON_TEXT_MAX], "url": url[:2048]}


def message_button(text: str, message: str) -> dict[str, Any]:
    return {"type": "message", "text": text[:BUTTON_TEXT_MAX], "payload": message[:CALLBACK_PAYLOAD_MAX]}


def request_contact_button(text: str = "Поделиться контактом") -> dict[str, Any]:
    return {"type": "request_contact", "text": text[:BUTTON_TEXT_MAX]}


def open_app_button(
    text: str, bot_username: str, bot_user_id: int, start_param: str | None = None
) -> dict[str, Any]:
    button: dict[str, Any] = {
        "type": "open_app",
        "text": text[:BUTTON_TEXT_MAX],
        "web_app": bot_username,
        "contact_id": bot_user_id,
    }
    if start_param and START_PARAM_PATTERN.match(start_param):
        button["payload"] = start_param
    return button


def inline_keyboard(rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {"type": "inline_keyboard", "payload": {"buttons": _normalize(rows)}}


def _normalize(rows: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    prepared: list[list[dict[str, Any]]] = []
    for row in rows[:MAX_ROWS]:
        if not row:
            continue
        wide = any(button.get("type") in WIDE_BUTTON_TYPES for button in row)
        limit = MAX_BUTTONS_PER_ROW_WIDE if wide else MAX_BUTTONS_PER_ROW
        prepared.append(list(row[:limit]))
    return prepared


def deeplink(bot_username: str, start_param: str | None = None) -> str:
    base = f"https://max.ru/{bot_username}"
    if start_param and START_PARAM_PATTERN.match(start_param):
        return f"{base}?startapp={start_param}"
    return f"{base}?startapp"
