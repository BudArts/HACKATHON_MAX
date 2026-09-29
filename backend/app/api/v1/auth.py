from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    RequestContextDep,
    SessionDep,
    SettingsDep,
    TokenServiceDep,
    UserServiceDep,
)
from app.api.schemas import AuthResponse, ConsentState, MaxAuthRequest, RefreshRequest, TokenPair, UserView
from app.core.config import Settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import TokenError, TokenService, as_utc
from app.db.models import AuthSession, ConsentPurpose, User, UserConsent
from app.integrations.max.initdata import InitDataError, validate_init_data
from app.services.audit import AuditService
from app.services.consents import ConsentService
from app.services.ratelimit import Bucket, limiter

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Авторизация"])

AUTH_BUCKET = Bucket(limit=10, window_seconds=60.0)
REFRESH_BUCKET = Bucket(limit=30, window_seconds=60.0)


async def consent_states(
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> list[ConsentState]:
    service = ConsentService(session, settings)
    result = await session.execute(
        select(UserConsent).where(UserConsent.user_id == user.id).order_by(UserConsent.granted_at.desc())
    )
    latest: dict[ConsentPurpose, UserConsent] = {}
    for record in result.scalars().all():
        current = latest.get(record.purpose)
        if current is None or (current.revoked_at is not None and record.revoked_at is None):
            latest[record.purpose] = record

    states: list[ConsentState] = []
    for purpose in ConsentPurpose:
        consent = latest.get(purpose)
        policy = await service.policy_for(purpose)
        states.append(
            ConsentState(
                purpose=purpose.value,
                granted=consent is not None and consent.revoked_at is None,
                policy_code=policy.code if policy else "",
                policy_version=policy.version if policy else "",
                granted_at=consent.granted_at if consent else None,
                revoked_at=consent.revoked_at if consent else None,
            )
        )
    return states


def issue_pair(
    tokens: TokenService,
    user: User,
    settings: Settings,
) -> tuple[TokenPair, str, datetime]:
    access, access_expires = tokens.issue(str(user.id), "access", {"role": user.role.value})
    refresh, _ = tokens.issue(str(user.id), "refresh", {"role": user.role.value})
    jti = tokens.decode(refresh, "refresh")["jti"]
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)
    pair = TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=max(0, int((access_expires - datetime.now(UTC)).total_seconds())),
    )
    return pair, jti, expires_at


@router.post("/max", response_model=AuthResponse, summary="Вход по стартовым данным MAX")
async def login_with_max(
    payload: MaxAuthRequest,
    response: Response,
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
    tokens: TokenServiceDep,
    users: UserServiceDep,
) -> AuthResponse:
    limiter.check(f"auth:{request.ip_index or 'unknown'}", AUTH_BUCKET)

    try:
        context = validate_init_data(
            payload.init_data,
            settings.max_bot_token,
            max_age_seconds=settings.miniapp_auth_window_seconds,
        )
    except InitDataError as exc:
        log.info("auth_rejected", reason=exc.reason)
        try:
            await AuditService(session, settings).record(
                "auth.miniapp_rejected",
                actor_kind="anonymous",
                outcome="failure",
                ip=request.ip,
                user_agent=request.user_agent,
                meta={"reason": exc.reason},
            )
            await session.commit()
        except Exception:
            await session.rollback()
        raise UnauthorizedError("Не удалось подтвердить вход через MAX") from exc

    user = await users.from_miniapp(context, ip=request.ip)
    if not user.is_active:
        raise ForbiddenError("Учётная запись заблокирована")

    await ConsentService(session, settings).sync_policies()
    pair, jti, expires_at = issue_pair(tokens, user, settings)
    session.add(
        AuthSession(
            user_id=user.id,
            refresh_jti=jti,
            ip_index=request.ip_index,
            user_agent=request.user_agent,
            expires_at=expires_at,
        )
    )
    await session.commit()

    consents = await consent_states(session, user, settings)
    service_granted = next(
        (item.granted for item in consents if item.purpose == ConsentPurpose.service.value),
        False,
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(
        user=UserView.from_user(user),
        tokens=pair,
        consents=consents,
        onboarding_required=not service_granted,
    )


@router.post("/refresh", response_model=TokenPair, summary="Обновление токена доступа")
async def refresh_tokens(
    payload: RefreshRequest,
    response: Response,
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
    tokens: TokenServiceDep,
) -> TokenPair:
    limiter.check(f"refresh:{request.ip_index or 'unknown'}", REFRESH_BUCKET)
    try:
        claims = tokens.decode(payload.refresh_token, "refresh")
    except TokenError as exc:
        raise UnauthorizedError("Требуется повторный вход") from exc

    stored = await session.execute(
        select(AuthSession).where(AuthSession.refresh_jti == claims["jti"], AuthSession.revoked_at.is_(None))
    )
    record = stored.scalar_one_or_none()
    if record is None or as_utc(record.expires_at) < datetime.now(UTC):
        raise UnauthorizedError("Требуется повторный вход")

    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Учётная запись недоступна")

    record.revoked_at = datetime.now(UTC)
    pair, jti, expires_at = issue_pair(tokens, user, settings)
    session.add(
        AuthSession(
            user_id=user.id,
            refresh_jti=jti,
            ip_index=request.ip_index,
            user_agent=request.user_agent,
            expires_at=expires_at,
        )
    )
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return pair


@router.post("/logout", status_code=204, summary="Завершение сессии")
async def logout(
    payload: RefreshRequest,
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
    tokens: TokenServiceDep,
    user: CurrentUser,
) -> Response:
    try:
        claims = tokens.decode(payload.refresh_token, "refresh")
    except TokenError:
        return Response(status_code=204)

    stored = await session.execute(
        select(AuthSession).where(AuthSession.refresh_jti == claims["jti"], AuthSession.user_id == user.id)
    )
    record = stored.scalar_one_or_none()
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        await AuditService(session, settings).record(
            "auth.logout",
            actor_user_id=user.id,
            entity_type="user",
            entity_id=str(user.id),
            ip=request.ip,
            user_agent=request.user_agent,
        )
        await session.commit()
    return Response(status_code=204)
