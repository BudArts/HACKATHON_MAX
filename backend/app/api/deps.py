from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import TokenService, hash_ip
from app.db.base import get_session
from app.db.models import ConsentPurpose, User, UserRole
from app.integrations.gigachat.client import GigaChatClient
from app.integrations.max.client import MaxBotClient
from app.runtime import get_runtime
from app.services.consents import ConsentService
from app.services.notifications import NotificationService
from app.services.users import UserService

log = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False, description="JWT доступа мини-приложения")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@dataclass(slots=True)
class RequestContext:
    ip: str | None
    user_agent: str | None
    request_id: str

    @property
    def ip_index(self) -> str | None:
        return hash_ip(get_settings().secret_key, self.ip)


def request_context(request: Request) -> RequestContext:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return RequestContext(
        ip=ip,
        user_agent=request.headers.get("user-agent", "")[:255] or None,
        request_id=str(getattr(request.state, "request_id", "")),
    )


RequestContextDep = Annotated[RequestContext, Depends(request_context)]


def token_service(settings: SettingsDep) -> TokenService:
    return TokenService(settings)


TokenServiceDep = Annotated[TokenService, Depends(token_service)]


def max_client() -> MaxBotClient:
    return get_runtime().max_client


MaxClientDep = Annotated[MaxBotClient, Depends(max_client)]


def gigachat_client() -> GigaChatClient:
    return get_runtime().gigachat


GigaChatDep = Annotated[GigaChatClient, Depends(gigachat_client)]


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    tokens: TokenServiceDep,
    session: SessionDep,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise UnauthorizedError("Требуется авторизация", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = tokens.decode(credentials.credentials)
    except Exception as exc:
        log.info("token_rejected", reason=str(exc))
        raise UnauthorizedError("Требуется авторизация", headers={"WWW-Authenticate": "Bearer"}) from exc

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Некорректный токен") from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Учётная запись недоступна")
    if user.role != UserRole(claims.get("role", user.role.value)) and user.role != UserRole.administrator:
        raise UnauthorizedError("Сессия устарела, войдите заново")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


RoleGuard = Callable[..., Coroutine[Any, Any, User]]


def require_role(*roles: UserRole) -> RoleGuard:
    async def guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError("Недостаточно прав")
        return user

    return guard


def require_consent(purpose: ConsentPurpose) -> RoleGuard:
    async def guard(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> User:
        service = ConsentService(session, settings)
        if not await service.is_granted(user.id, purpose):
            raise ForbiddenError(
                "Требуется согласие на обработку персональных данных",
                detail={"purpose": purpose.value},
            )
        return user

    return guard


UserConsented = Annotated[User, Depends(require_consent(ConsentPurpose.service))]
UserTeacher = Annotated[User, Depends(require_role(UserRole.teacher, UserRole.administrator))]


def user_service(session: SessionDep, settings: SettingsDep) -> UserService:
    return UserService(session, settings)


UserServiceDep = Annotated[UserService, Depends(user_service)]


def consent_service(session: SessionDep, settings: SettingsDep) -> ConsentService:
    return ConsentService(session, settings)


ConsentServiceDep = Annotated[ConsentService, Depends(consent_service)]


def notification_service(session: SessionDep, settings: SettingsDep) -> NotificationService:
    return NotificationService(session, settings)


NotificationServiceDep = Annotated[NotificationService, Depends(notification_service)]
