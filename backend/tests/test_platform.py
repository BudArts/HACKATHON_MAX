from __future__ import annotations

import time

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.core.security import FieldCipher, TokenService, blind_index, hash_ip, hash_password, verify_password
from app.services.legal import latest_by_code, load_documents
from app.services.ratelimit import Bucket, SlidingWindowLimiter


def test_field_cipher_roundtrip() -> None:
    cipher = FieldCipher("encryption-key-for-unit-tests-0123456789")
    secret = cipher.encrypt("+79123456789")
    assert secret is not None
    assert "+79123456789" not in secret
    assert cipher.decrypt(secret) == "+79123456789"


def test_field_cipher_requires_key() -> None:
    cipher = FieldCipher("")
    with pytest.raises(Exception):
        cipher.encrypt("value")


def test_blind_index_is_deterministic_and_keyed() -> None:
    first = blind_index("key-a", "phone", "+7 912 345-67-89")
    second = blind_index("key-a", "phone", "+79123456789")
    third = blind_index("key-b", "phone", "+79123456789")
    assert first == second
    assert first != third


def test_hash_ip_is_irreversible_prefix() -> None:
    digest = hash_ip("secret", "203.0.113.7")
    assert digest is not None and len(digest) == 32
    assert "203.0.113.7" not in digest
    assert hash_ip("secret", None) is None


def test_token_service_roundtrip() -> None:
    service = TokenService(get_settings())
    token, expires = service.issue("user-1", "access", {"role": "parent"})
    claims = service.decode(token)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "parent"
    assert expires.timestamp() >= time.time()

    refresh, _ = service.issue("user-1", "refresh")
    with pytest.raises(Exception):
        service.decode(refresh, "access")


def test_password_hashing() -> None:
    stored = hash_password("S3cret-password")
    assert verify_password(stored, "S3cret-password") is True
    assert verify_password(stored, "wrong") is False
    assert stored != hash_password("S3cret-password")


def test_legal_documents_are_versioned() -> None:
    documents = load_documents()
    codes = {document.code for document in documents}
    assert {"privacy_policy", "consent_processing", "consent_ai", "terms"} <= codes
    latest = latest_by_code()
    assert latest["privacy_policy"].version == "1.1.0"
    assert len(latest["privacy_policy"].checksum) == 64


def test_rate_limiter_blocks_after_limit() -> None:
    limiter = SlidingWindowLimiter()
    bucket = Bucket(limit=2, window_seconds=60.0)
    limiter.check("k", bucket)
    limiter.check("k", bucket)
    with pytest.raises(RateLimitedError):
        limiter.check("k", bucket)


@pytest.mark.anyio
async def test_healthz_reports_degraded_without_database() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.anyio
async def test_unknown_route_returns_structured_error() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"


@pytest.mark.anyio
async def test_webhook_rejects_wrong_secret() -> None:
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        response = await client.post(
            "/webhook/max",
            json={"update_type": "bot_started", "timestamp": 1},
            headers={"X-Max-Bot-Api-Secret": "wrong-secret"},
        )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_auth_rejects_invalid_init_data() -> None:
    from app.main import create_app
    from app.services.ratelimit import limiter

    limiter._hits.clear()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        response = await client.post(
            "/api/v1/auth/max", json={"init_data": "query_id=abc&auth_date=1&hash=deadbeef"}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
