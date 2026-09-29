from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-value-0123456789")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "unit-test-encryption-key-0123456789")
os.environ.setdefault("MAX_BOT_TOKEN", "unit-test-bot-token")
os.environ.setdefault("MAX_WEBHOOK_SECRET", "unit-test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unit:unit@127.0.0.1:5432/unit")
os.environ.setdefault("GIGACHAT_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("MAX_TRANSPORT", "polling")
os.environ.setdefault("DEV_LOGIN_ENABLED", "false")

import pytest

from app.core.config import get_settings
from app.db.base import init_engine
from app.runtime import init_runtime


@pytest.fixture(scope="session", autouse=True)
def runtime() -> None:
    settings = get_settings()
    init_engine(settings)
    init_runtime(settings)
