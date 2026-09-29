from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import hash_ip
from app.db.models import ConsentPurpose, ConsentSource, PolicyDocument, User, UserConsent
from app.services.audit import AuditService
from app.services.legal import LegalDocument, latest_by_code, load_documents

log = get_logger(__name__)

POLICY_BY_PURPOSE: dict[ConsentPurpose, str] = {
    ConsentPurpose.service: "consent_processing",
    ConsentPurpose.notifications: "consent_processing",
    ConsentPurpose.ai_processing: "consent_ai",
}


class ConsentService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._audit = AuditService(session, settings)

    async def sync_policies(self) -> list[PolicyDocument]:
        documents: dict[str, LegalDocument] = latest_by_code()
        stored: dict[str, PolicyDocument] = {}
        result = await self._session.execute(
            select(PolicyDocument).where(PolicyDocument.is_current.is_(True))
        )
        for record in result.scalars().all():
            stored[record.code] = record

        touched: list[PolicyDocument] = []
        for code, document in documents.items():
            existing = stored.get(code)
            if (
                existing is not None
                and existing.version == document.version
                and existing.checksum == document.checksum
            ):
                touched.append(existing)
                continue
            if existing is not None:
                await self._session.execute(
                    update(PolicyDocument).where(PolicyDocument.code == code).values(is_current=False)
                )
            record = PolicyDocument(
                code=code,
                version=document.version,
                title=document.title,
                body=document.body,
                checksum=document.checksum,
                published_at=datetime.now(UTC),
                is_current=True,
            )
            self._session.add(record)
            touched.append(record)
            log.info("policy_published", code=code, version=document.version)
        await self._session.flush()
        return touched

    async def policy_for(self, purpose: ConsentPurpose) -> PolicyDocument | None:
        code = POLICY_BY_PURPOSE[purpose]
        result = await self._session.execute(
            select(PolicyDocument).where(PolicyDocument.code == code, PolicyDocument.is_current.is_(True))
        )
        return result.scalar_one_or_none()

    async def is_granted(self, user_id: UUID, purpose: ConsentPurpose) -> bool:
        result = await self._session.execute(
            select(UserConsent.id).where(
                UserConsent.user_id == user_id,
                UserConsent.purpose == purpose,
                UserConsent.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none() is not None

    async def active(self, user_id: UUID) -> list[UserConsent]:
        result = await self._session.execute(
            select(UserConsent)
            .where(UserConsent.user_id == user_id, UserConsent.revoked_at.is_(None))
            .order_by(UserConsent.granted_at.desc())
        )
        return list(result.scalars().all())

    async def grant(
        self,
        user: User,
        purpose: ConsentPurpose,
        *,
        source: ConsentSource,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> UserConsent:
        policy = await self.policy_for(purpose)
        if policy is None:
            await self.sync_policies()
            policy = await self.policy_for(purpose)
        if policy is None:
            raise RuntimeError(f"Не найден документ согласия для цели {purpose.value}")

        existing = await self._session.execute(
            select(UserConsent).where(
                UserConsent.user_id == user.id,
                UserConsent.purpose == purpose,
                UserConsent.policy_id == policy.id,
                UserConsent.revoked_at.is_(None),
            )
        )
        consent = existing.scalar_one_or_none()
        if consent is not None:
            return consent

        consent = UserConsent(
            user_id=user.id,
            purpose=purpose,
            policy_id=policy.id,
            policy_version=policy.version,
            source=source,
            ip_index=hash_ip(self._settings.secret_key, ip),
            user_agent=(user_agent or "")[:255] or None,
            granted_at=datetime.now(UTC),
        )
        self._session.add(consent)
        await self._audit.record(
            "consent.granted",
            actor_user_id=user.id,
            entity_type="user_consent",
            entity_id=str(user.id),
            ip=ip,
            user_agent=user_agent,
            meta={
                "purpose": purpose.value,
                "policy": policy.code,
                "version": policy.version,
                "source": source.value,
            },
        )
        await self._session.flush()
        return consent

    async def revoke(
        self,
        user: User,
        purpose: ConsentPurpose,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        result = await self._session.execute(
            select(UserConsent).where(
                UserConsent.user_id == user.id,
                UserConsent.purpose == purpose,
                UserConsent.revoked_at.is_(None),
            )
        )
        consent = result.scalar_one_or_none()
        if consent is None:
            return False
        consent.revoked_at = datetime.now(UTC)
        await self._audit.record(
            "consent.revoked",
            actor_user_id=user.id,
            entity_type="user_consent",
            entity_id=str(user.id),
            ip=ip,
            user_agent=user_agent,
            meta={"purpose": purpose.value},
        )
        await self._session.flush()
        return True

    async def documents(self) -> list[LegalDocument]:
        return list(load_documents())
