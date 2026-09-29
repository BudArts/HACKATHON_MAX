from __future__ import annotations

from app.integrations.max.keyboard import deeplink, inline_keyboard, link_button, open_app_button
from app.integrations.max.updates import contact_from_attachments, parse_update


def test_keyboard_limits_wide_buttons() -> None:
    rows = [
        [
            link_button("Один", "https://example.ru/1"),
            link_button("Два", "https://example.ru/2"),
            link_button("Три", "https://example.ru/3"),
            link_button("Четыре", "https://example.ru/4"),
        ],
        [],
    ]
    keyboard = inline_keyboard(rows)
    assert keyboard["type"] == "inline_keyboard"
    assert len(keyboard["payload"]["buttons"]) == 1
    assert len(keyboard["payload"]["buttons"][0]) == 3


def test_open_app_button_drops_invalid_start_param() -> None:
    button = open_app_button("Кабинет", "school_bridge_bot", 42, "appeals")
    assert button == {
        "type": "open_app",
        "text": "Кабинет",
        "web_app": "school_bridge_bot",
        "contact_id": 42,
        "payload": "appeals",
    }

    unsafe = open_app_button("Кабинет", "school_bridge_bot", 42, " appeals! ")
    assert "payload" not in unsafe


def test_deeplink() -> None:
    assert deeplink("school_bridge_bot") == "https://max.ru/school_bridge_bot?startapp"
    assert deeplink("school_bridge_bot", "appeals") == "https://max.ru/school_bridge_bot?startapp=appeals"
    assert deeplink("school_bridge_bot", "недопустимо") == "https://max.ru/school_bridge_bot?startapp"


def test_parse_message_created() -> None:
    update = {
        "update_type": "message_created",
        "timestamp": 1771409719000,
        "message": {
            "mid": "mid-1",
            "sender": {"id": 67890, "first_name": "Мария", "last_name": "Иванова", "username": None},
            "recipient": {"chat_id": 12345},
            "body": {"text": "/start", "mid": "mid-1"},
        },
    }
    event = parse_update(update)
    assert event is not None
    assert event.actor is not None and event.actor.user_id == 67890
    assert event.chat_id == 12345
    assert event.message_id == "mid-1"
    assert event.is_command and event.command == "start"
    assert event.dedupe_key == "message_created:1771409719000:mid-1"


def test_parse_callback() -> None:
    update = {
        "update_type": "message_callback",
        "timestamp": 1771409720000,
        "callback": {
            "id": "cb-1",
            "payload": "consent:service:accept",
            "user": {"id": 67890},
            "state": {"chat_id": 12345, "mid": "mid-1"},
        },
    }
    event = parse_update(update)
    assert event is not None
    assert event.callback_id == "cb-1"
    assert event.callback_payload == "consent:service:accept"
    assert event.chat_id == 12345


def test_uninteresting_update_is_skipped() -> None:
    assert parse_update({"update_type": "chat_title_changed", "timestamp": 1}) is None


VCARD_LINES = ["BEGIN:VCARD", "VERSION:3.0", "TEL;TYPE=cell:79990000000", "FN:Ivan Ivanov", "END:VCARD", ""]
VCARD = "\\r\\n".join(VCARD_LINES)


def test_contact_extraction() -> None:
    attachments = [
        {
            "type": "contact",
            "payload": {
                "vcf_info": VCARD,
                "max_info": {"phone": "+79990000000"},
                "hash": "abc123",
            },
        }
    ]
    phone, _contact_name, digest = contact_from_attachments(attachments)
    assert phone == "+79990000000"
    assert digest == "abc123"
