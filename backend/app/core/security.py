from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings

TokenType = Literal["access", "refresh"]

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class TokenError(Exception):
    pass


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class FieldCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(_derive_fernet_key(key)) if key else None

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None or plaintext == "":
            return None
        if self._fernet is None:
            raise TokenError("FIELD_ENCRYPTION_KEY не задан, запись персональных данных запрещена")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str | None) -> str | None:
        if not ciphertext:
            return None
        if self._fernet is None:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise TokenError("Не удалось расшифровать значение") from exc


def blind_index(secret: str, kind: str, value: str) -> str:
    payload = f"{kind}:{_normalize(kind, value)}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _normalize(kind: str, value: str) -> str:
    if kind == "phone":
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) == 11 and digits.startswith(("8", "7")):
            digits = "7" + digits[1:]
        return digits
    return "".join(ch for ch in value.strip().lower() if not ch.isspace())


def hash_ip(secret: str, ip: str | None) -> str | None:
    if not ip:
        return None
    return hmac.new(secret.encode(), ip.strip().encode(), hashlib.sha256).hexdigest()[:32]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, candidate: str) -> bool:
    try:
        return _hasher.verify(stored, candidate)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored)
    except InvalidHashError:
        return True


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if not settings.secret_key:
            raise TokenError("SECRET_KEY не задан")

    def issue(
        self,
        subject: str,
        kind: TokenType = "access",
        extra: dict[str, Any] | None = None,
    ) -> tuple[str, datetime]:
        now = datetime.now(UTC)
        ttl = (
            timedelta(minutes=self._settings.access_token_ttl_minutes)
            if kind == "access"
            else timedelta(days=self._settings.refresh_token_ttl_days)
        )
        expires_at = now + ttl
        claims: dict[str, Any] = {
            "sub": subject,
            "typ": kind,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": uuid.uuid4().hex,
        }
        if extra:
            claims.update(extra)
        token = jwt.encode(claims, self._settings.secret_key, algorithm=self._settings.jwt_algorithm)
        return str(token), expires_at

    def decode(self, token: str, expected_type: TokenType = "access") -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token,
                self._settings.secret_key,
                algorithms=[self._settings.jwt_algorithm],
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("Срок действия токена истёк") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError("Некорректный токен") from exc
        if claims.get("typ") != expected_type:
            raise TokenError("Некорректный тип токена")
        return claims


def request_id() -> str:
    return uuid.uuid4().hex


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def unix_seconds(moment: datetime) -> int:
    return int(moment.timestamp())


def seconds_since(moment: int | float) -> int:
    return int(time.time() - moment)
