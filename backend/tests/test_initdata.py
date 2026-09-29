from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import quote

import pytest

from app.integrations.max.initdata import (
    InitDataError,
    extract_init_data,
    validate_init_data,
    verify_contact_hash,
)

BOT_TOKEN = "unit-test-bot-token"


def build_init_data(
    *,
    user_id: int = 67890,
    chat_id: int = 12345,
    auth_date: int | None = None,
    start_param: str | None = None,
    token: str = BOT_TOKEN,
    tamper: bool = False,
) -> str:
    auth_date = auth_date if auth_date is not None else int(time.time())
    params: dict[str, str] = {
        "query_id": "4c0ab423-342b-4e45-aea4-2747dbc500cd",
        "ip": "192.168.0.1",
        "auth_date": str(auth_date),
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Мария",
                "last_name": "Иванова",
                "username": None,
                "language_code": "ru",
                "photo_url": None,
            },
            ensure_ascii=False,
        ),
        "chat": json.dumps({"id": chat_id, "type": "DIALOG"}),
    }
    if start_param:
        params["start_param"] = start_param

    launch_params = "\n".join(f"{key}={params[key]}" for key in sorted(params))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()
    if tamper:
        signature = "0" * len(signature)
    params["hash"] = signature
    return "&".join(f"{key}={quote(value, safe='')}" for key, value in params.items())


def test_valid_init_data_is_accepted() -> None:
    context = validate_init_data(build_init_data(), BOT_TOKEN)
    assert context.user is not None
    assert context.user.id == 67890
    assert context.user.first_name == "Мария"
    assert context.chat is not None
    assert context.chat.type == "DIALOG"


def test_tampered_signature_is_rejected() -> None:
    with pytest.raises(InitDataError) as excinfo:
        validate_init_data(build_init_data(tamper=True), BOT_TOKEN)
    assert excinfo.value.reason == "bad_signature"


def test_foreign_bot_token_is_rejected() -> None:
    with pytest.raises(InitDataError) as excinfo:
        validate_init_data(build_init_data(), "another-bot-token")
    assert excinfo.value.reason == "bad_signature"


def test_stale_auth_date_is_rejected() -> None:
    old = int(time.time()) - 7200
    with pytest.raises(InitDataError) as excinfo:
        validate_init_data(build_init_data(auth_date=old), BOT_TOKEN, max_age_seconds=3600)
    assert excinfo.value.reason == "stale"


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(InitDataError) as excinfo:
        validate_init_data("   ", BOT_TOKEN)
    assert excinfo.value.reason == "missing"


def test_duplicated_hash_is_rejected() -> None:
    payload = build_init_data()
    with pytest.raises(InitDataError):
        validate_init_data(f"{payload}&{payload.split('&')[-1]}", BOT_TOKEN)


def test_start_param_is_passed_through() -> None:
    context = validate_init_data(build_init_data(start_param="appeals"), BOT_TOKEN)
    assert context.start_param == "appeals"


def test_extract_init_data_from_url_fragment() -> None:
    data = build_init_data()
    fragment = f"WebAppData={quote(data, safe='')}&WebAppPlatform=web&WebAppVersion=26.2.8"
    url = f"https://example.ru/cabinet#{fragment}"
    assert extract_init_data(url) == data


def test_contact_hash_verification() -> None:
    vcf_info = "BEGIN:VCARD\r\nVERSION:3.0\r\nTEL;TYPE=cell:79990000000\r\nFN:Ivan Ivanov\r\nEND:VCARD\r\n"
    digest = hmac.new(BOT_TOKEN.encode(), vcf_info.encode(), hashlib.sha256).hexdigest()
    assert verify_contact_hash(vcf_info.replace("\r\n", "\\r\\n"), digest, BOT_TOKEN) is True
    assert verify_contact_hash(vcf_info.replace("\r\n", "\\r\\n"), "0" * 64, BOT_TOKEN) is False


def test_build_init_data_produces_valid_payload() -> None:
    from app.integrations.max.initdata import build_init_data

    init_data = build_init_data(
        BOT_TOKEN,
        user_id=4242,
        first_name="Игорь",
        last_name="Носов",
        start_param="appeals",
    )
    context = validate_init_data(init_data, BOT_TOKEN)
    assert context.user is not None
    assert context.user.id == 4242
    assert context.user.first_name == "Игорь"
    assert context.start_param == "appeals"

    with pytest.raises(InitDataError):
        validate_init_data(init_data, "another-token")
