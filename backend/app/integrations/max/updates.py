from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INTERESTING_UPDATES = (
    "bot_started",
    "bot_stopped",
    "bot_added",
    "bot_removed",
    "message_created",
    "message_callback",
    "message_edited",
    "dialog_cleared",
    "user_added",
    "user_removed",
)


@dataclass(slots=True)
class Actor:
    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_bot: bool = False


@dataclass(slots=True)
class IncomingEvent:
    update_type: str
    timestamp: int
    actor: Actor | None
    chat_id: int | None
    text: str | None
    message_id: str | None
    callback_id: str | None
    callback_payload: str | None
    start_param: str | None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        marker = self.message_id or self.callback_id or (str(self.actor.user_id) if self.actor else "-")
        return f"{self.update_type}:{self.timestamp}:{marker}"

    @property
    def is_command(self) -> bool:
        return bool(self.text and self.text.startswith("/"))

    @property
    def command(self) -> str | None:
        if not self.is_command or not self.text:
            return None
        return self.text.split(maxsplit=1)[0][1:].split("@")[0].lower()

    @property
    def command_argument(self) -> str | None:
        if not self.is_command or not self.text:
            return None
        parts = self.text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else None


def _actor_from(payload: Any) -> Actor | None:
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("id") or payload.get("user_id")
    if user_id is None:
        return None
    return Actor(
        user_id=int(user_id),
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        username=payload.get("username"),
        language_code=payload.get("language_code"),
        is_bot=bool(payload.get("is_bot", False)),
    )


def _chat_id(message: dict[str, Any]) -> int | None:
    recipient = message.get("recipient")
    if isinstance(recipient, dict) and recipient.get("chat_id") is not None:
        return int(recipient["chat_id"])
    if message.get("chat_id") is not None:
        return int(message["chat_id"])
    return None


def parse_update(update: dict[str, Any]) -> IncomingEvent | None:
    update_type = str(update.get("update_type", ""))
    if update_type not in INTERESTING_UPDATES:
        return None

    timestamp = int(update.get("timestamp") or 0)
    actor: Actor | None = None
    chat_id: int | None = update.get("chat_id")
    text: str | None = None
    message_id: str | None = None
    callback_id: str | None = None
    callback_payload: str | None = None
    start_param: str | None = None
    attachments: list[dict[str, Any]] = []

    message = update.get("message")
    if isinstance(message, dict):
        actor = _actor_from(message.get("sender")) or _actor_from(update.get("user"))
        chat_id = _chat_id(message) or chat_id
        message_id = str(message.get("mid") or (message.get("body") or {}).get("mid") or "") or None
        body = message.get("body")
        if isinstance(body, dict):
            text = body.get("text")
            raw_attachments = body.get("attachments")
        else:
            text = message.get("text")
            raw_attachments = message.get("attachments")
        if isinstance(raw_attachments, list):
            attachments = [item for item in raw_attachments if isinstance(item, dict)]
        link = message.get("link")
        if isinstance(link, dict):
            start_param = link.get("start_param") or None

    if actor is None:
        actor = _actor_from(update.get("user"))

    payload = update.get("payload")
    if isinstance(payload, dict):
        start_param = start_param or payload.get("start_param") or None

    callback = update.get("callback")
    if isinstance(callback, dict):
        callback_id = str(callback.get("id") or "") or None
        callback_payload = callback.get("payload")
        actor = _actor_from(callback.get("user")) or actor
        state = callback.get("state")
        if isinstance(state, dict):
            chat_id = int(state.get("chat_id") or chat_id or 0) or chat_id
            message_id = str(state.get("mid") or message_id or "") or None

    user_ids = update.get("user_ids")
    if actor is None and isinstance(user_ids, list) and user_ids:
        actor = Actor(user_id=int(user_ids[0]))

    return IncomingEvent(
        update_type=update_type,
        timestamp=timestamp,
        actor=actor,
        chat_id=int(chat_id) if chat_id else None,
        text=text,
        message_id=message_id,
        callback_id=callback_id,
        callback_payload=callback_payload,
        start_param=start_param,
        attachments=attachments,
        raw=update,
    )


def contact_from_attachments(attachments: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None]:
    for attachment in attachments:
        if attachment.get("type") != "contact":
            continue
        payload = attachment.get("payload") or {}
        vcf_info = payload.get("vcf_info")
        phone = None
        name = None
        if isinstance(payload.get("max_info"), dict):
            max_info = payload["max_info"]
            phone = max_info.get("phone")
            name = max_info.get("name")
        if phone is None and isinstance(vcf_info, str):
            for line in vcf_info.replace("\\r\\n", "\n").splitlines():
                if line.upper().startswith("TEL"):
                    phone = line.split(":", 1)[-1].strip()
                elif line.upper().startswith("FN"):
                    name = line.split(":", 1)[-1].strip()
        return phone, name, payload.get("hash")
    return None, None, None
