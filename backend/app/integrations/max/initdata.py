from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urldefrag
from uuid import uuid4

from app.core.logging import get_logger

log = get_logger(__name__)

SIGNATURE_KEY = b"WebAppData"
MAX_START_PARAM_LENGTH = 512


class InitDataError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True)
class MiniAppUser:
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    photo_url: str | None = None


@dataclass(slots=True)
class MiniAppChat:
    id: int
    type: str


@dataclass(slots=True)
class MiniAppContext:
    query_id: str
    auth_date: int
    user: MiniAppUser | None
    chat: MiniAppChat | None
    start_param: str | None
    ip: str | None
    platform: str | None
    version: str | None
    raw_hash: str


def _split_pairs(app_data: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for chunk in app_data.split("&"):
        if not chunk:
            continue
        key, separator, value = chunk.partition("=")
        if not separator:
            raise InitDataError("malformed")
        pairs.append((key, unquote(value)))
    return pairs


def _parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def sign_launch_params(launch_params: str, bot_token: str) -> str:
    secret_key = hmac.new(SIGNATURE_KEY, bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()


def compute_signature(app_data: str, bot_token: str) -> str:
    pairs = _split_pairs(app_data)
    hashes = [value for key, value in pairs if key == "hash"]
    if len(hashes) != 1:
        raise InitDataError("malformed")

    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise InitDataError("malformed")

    launch_params = "\n".join(
        f"{key}={value}" for key, value in sorted(pairs, key=lambda item: item[0]) if key != "hash"
    )
    return sign_launch_params(launch_params, bot_token)


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 3600,
    now: int | None = None,
) -> MiniAppContext:
    if not init_data or not init_data.strip():
        raise InitDataError("missing")
    if not bot_token:
        raise InitDataError("not_configured")

    app_data = init_data.strip()
    if "=" not in app_data or "&" not in app_data:
        raise InitDataError("malformed")

    pairs = _split_pairs(app_data)
    params = dict(pairs)
    provided_hash = params.pop("hash", "")

    try:
        expected_hash = compute_signature(app_data, bot_token)
    except InitDataError as exc:
        log.warning("miniapp_initdata_rejected", reason=exc.reason)
        raise

    if not hmac.compare_digest(expected_hash, provided_hash):
        log.warning("miniapp_initdata_rejected", reason="bad_signature")
        raise InitDataError("bad_signature")

    try:
        auth_date = int(params["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InitDataError("malformed") from exc

    current = int(now if now is not None else time.time())
    if auth_date > current + 60:
        raise InitDataError("stale")
    if max_age_seconds and current - auth_date > max_age_seconds:
        log.warning("miniapp_initdata_rejected", reason="stale")
        raise InitDataError("stale")

    user_payload = _parse_json(params.get("user", "")) if "user" in params else None
    user = None
    if isinstance(user_payload, dict) and user_payload.get("id") is not None:
        user = MiniAppUser(
            id=int(user_payload["id"]),
            first_name=user_payload.get("first_name"),
            last_name=user_payload.get("last_name"),
            username=user_payload.get("username"),
            language_code=user_payload.get("language_code"),
            photo_url=user_payload.get("photo_url"),
        )

    chat_payload = _parse_json(params.get("chat", "")) if "chat" in params else None
    chat = None
    if isinstance(chat_payload, dict) and chat_payload.get("id") is not None:
        chat = MiniAppChat(id=int(chat_payload["id"]), type=str(chat_payload.get("type", "DIALOG")))

    start_param = params.get("start_param") or None
    if start_param and len(start_param) > MAX_START_PARAM_LENGTH:
        start_param = start_param[:MAX_START_PARAM_LENGTH]

    return MiniAppContext(
        query_id=params.get("query_id", ""),
        auth_date=auth_date,
        user=user,
        chat=chat,
        start_param=start_param,
        ip=params.get("ip"),
        platform=params.get("platform"),
        version=params.get("version"),
        raw_hash=provided_hash,
    )


def extract_init_data(url_with_fragment: str) -> str:
    _, fragment = urldefrag(url_with_fragment)
    if not fragment:
        return ""
    values = [value for key, value in parse_qsl(fragment, keep_blank_values=True) if key == "WebAppData"]
    if len(values) != 1:
        return ""
    return values[0]


def build_init_data(
    bot_token: str,
    *,
    user_id: int,
    first_name: str = "Пользователь",
    last_name: str | None = None,
    chat_id: int | None = None,
    start_param: str | None = None,
    auth_date: int | None = None,
) -> str:
    issued = auth_date if auth_date is not None else int(time.time())
    params: dict[str, str] = {
        "query_id": str(uuid4()),
        "auth_date": str(issued),
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": first_name,
                "last_name": last_name,
                "username": None,
                "language_code": "ru",
                "photo_url": None,
            },
            ensure_ascii=False,
        ),
        "chat": json.dumps({"id": chat_id if chat_id is not None else user_id, "type": "DIALOG"}),
    }
    if start_param:
        params["start_param"] = start_param[:MAX_START_PARAM_LENGTH]

    launch_params = "\n".join(f"{key}={params[key]}" for key in sorted(params))
    params["hash"] = sign_launch_params(launch_params, bot_token)
    return "&".join(f"{key}={quote(value, safe='')}" for key, value in params.items())


def verify_miniapp_contact(
    auth_date: str,
    phone: str,
    user_id: int,
    provided_hash: str,
    bot_token: str,
    *,
    max_age_seconds: int = 3600,
) -> bool:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits or not provided_hash or not bot_token:
        return False
    try:
        issued = int(auth_date)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - issued) > max_age_seconds:
        return False
    launch_params = f"auth_date={auth_date}\nphone={digits}\nuser_id={user_id}"
    digest = hmac.new(bot_token.encode(), launch_params.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, provided_hash)


def verify_contact_hash(vcf_info: str, provided_hash: str, bot_token: str) -> bool:
    normalized = vcf_info.replace("\\r\\n", "\r\n")
    digest = hmac.new(bot_token.encode(), normalized.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, provided_hash)
