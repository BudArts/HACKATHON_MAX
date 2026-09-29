from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import FieldCipher, as_utc, blind_index
from app.db.models import GuardianLink, Student, User, UserRole
from app.integrations.max.initdata import MiniAppContext
from app.services.audit import AuditService

log = get_logger(__name__)

PHONE_RE = re.compile(r"^\+?\d{10,15}$")
VERIFICATION_TTL = timedelta(minutes=15)
VERIFICATION_MAX_ATTEMPTS = 5


class UserService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._cipher = FieldCipher(settings.field_encryption_key)
        self._audit = AuditService(session, settings)

    async def by_max_id(self, max_user_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.max_user_id == max_user_id))
        return result.scalar_one_or_none()

    async def by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def ensure(
        self,
        max_user_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
        locale: str | None = None,
    ) -> User:
        user = await self.by_max_id(max_user_id)
        created = user is None
        if user is None:
            user = User(max_user_id=max_user_id, role=UserRole.student)
            self._session.add(user)

        if first_name:
            user.first_name = first_name[:64]
        if last_name:
            user.last_name = last_name[:64]
        if username:
            user.username = username[:64]
        if locale:
            user.locale = locale[:8]
        user.last_seen_at = datetime.now(UTC)
        if created:
            await self._session.flush()
            await self._audit.record(
                "user.registered",
                actor_user_id=user.id,
                entity_type="user",
                entity_id=str(user.id),
                meta={"max_user_id": max_user_id},
            )
        await self._session.flush()
        return user

    async def from_miniapp(self, context: MiniAppContext, *, ip: str | None = None) -> User:
        if context.user is None:
            raise ValueError("В стартовых данных отсутствует пользователь")
        payload = context.user
        user = await self.ensure(
            payload.id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            username=payload.username,
            locale=payload.language_code,
        )
        await self._audit.record(
            "auth.miniapp",
            actor_user_id=user.id,
            entity_type="user",
            entity_id=str(user.id),
            ip=ip,
            meta={"query_id": context.query_id, "platform": context.platform or ""},
        )
        return user

    async def store_phone(self, user: User, phone: str, *, source: str) -> bool:
        normalized = re.sub(r"[^\d+]", "", phone)
        if not PHONE_RE.match(normalized):
            return False
        if normalized.startswith("8") and len(normalized) == 11:
            normalized = "+7" + normalized[1:]
        elif normalized.startswith("7") and len(normalized) == 11:
            normalized = "+" + normalized

        index = blind_index(self._settings.secret_key, "phone", normalized)
        if user.phone_index == index:
            return True

        user.phone_index = index
        user.phone_encrypted = self._cipher.encrypt(normalized)
        await self._audit.record(
            "user.phone_updated",
            actor_user_id=user.id,
            entity_type="user",
            entity_id=str(user.id),
            meta={"source": source},
        )
        await self._session.flush()
        return True

    def read_phone(self, user: User) -> str | None:
        return self._cipher.decrypt(user.phone_encrypted)

    async def store_email(self, user: User, email: str, *, source: str) -> bool:
        normalized = email.strip().lower()
        if "@" not in normalized or len(normalized) > 254:
            return False
        user.email_index = blind_index(self._settings.secret_key, "email", normalized)
        user.email_encrypted = self._cipher.encrypt(normalized)
        await self._audit.record(
            "user.email_updated",
            actor_user_id=user.id,
            entity_type="user",
            entity_id=str(user.id),
            meta={"source": source},
        )
        await self._session.flush()
        return True

    async def assign_role(self, user: User, role: UserRole, *, reason: str) -> None:
        if user.role == role:
            return
        previous = user.role
        user.role = role
        await self._audit.record(
            "user.role_changed",
            actor_user_id=user.id,
            actor_kind="system",
            entity_type="user",
            entity_id=str(user.id),
            meta={"from": previous.value, "to": role.value, "reason": reason},
        )
        await self._session.flush()

    async def linked_students(self, user_id: UUID) -> list[Student]:
        result = await self._session.execute(
            select(Student)
            .join(GuardianLink, GuardianLink.student_id == Student.id)
            .where(GuardianLink.user_id == user_id, Student.is_active.is_(True))
            .order_by(Student.last_name, Student.first_name)
        )
        return list(result.scalars().all())

    async def pending_links(self, user_id: UUID) -> list[GuardianLink]:
        result = await self._session.execute(
            select(GuardianLink).where(GuardianLink.user_id == user_id, GuardianLink.verified_at.is_(None))
        )
        return list(result.scalars().all())

    async def issue_verification_code(self, link: GuardianLink) -> str:
        code = f"{secrets.randbelow(1000000):06d}"
        link.verification_code_index = blind_index(self._settings.secret_key, "guardian_code", code)
        link.verification_attempts = 0
        link.created_at = datetime.now(UTC)
        await self._session.flush()
        return code

    async def confirm_verification_code(self, link: GuardianLink, code: str) -> bool:
        if link.verification_attempts >= VERIFICATION_MAX_ATTEMPTS:
            return False
        if link.created_at is None or datetime.now(UTC) - as_utc(link.created_at) > VERIFICATION_TTL:
            return False

        link.verification_attempts += 1
        expected = blind_index(self._settings.secret_key, "guardian_code", code.strip())
        if link.verification_code_index != expected:
            await self._session.flush()
            return False

        link.verified_at = datetime.now(UTC)
        link.verification_code_index = None
        await self._audit.record(
            "guardian.link_verified",
            actor_user_id=link.user_id,
            entity_type="guardian_link",
            entity_id=str(link.id),
        )
        await self._session.flush()
        return True

    def display_name(self, user: User) -> str:
        parts = [user.first_name, user.last_name]
        name = " ".join(part for part in parts if part)
        return name or "Пользователь"


def anonymize_name(user: User) -> str:
    initials = "".join(f"{part[0]}." for part in (user.first_name, user.last_name) if part)
    return initials or "Пользователь"
