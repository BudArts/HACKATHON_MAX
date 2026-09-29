from __future__ import annotations

import logging
import sys
from typing import cast

import structlog
from structlog.typing import EventDict, WrappedLogger

from app.core.config import Settings

REDACTED = "[redacted]"
SENSITIVE_KEYS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "secret_key",
        "password",
        "authorization",
        "cookie",
        "phone",
        "email",
        "initdata",
        "webappdata",
        "hash",
        "credentials",
        "field_encryption_key",
        "max_bot_token",
        "max_webhook_secret",
        "gigachat_credentials",
    }
)


def _redact(
    _logger: WrappedLogger,
    _method: str,
    event_dict: EventDict,
) -> EventDict:
    for key, value in list(event_dict.items()):
        if key.lower() in SENSITIVE_KEYS and value not in (None, ""):
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            _redact,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
