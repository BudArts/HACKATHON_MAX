from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import RequestContextDep, SessionDep, SettingsDep
from app.api.schemas import DevInitDataResponse, DevUserView
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.db.models import User
from app.integrations.max.initdata import build_init_data
from app.services.audit import AuditService

router = APIRouter(prefix="/dev", tags=["Локальная проверка"])


def ensure_enabled(settings: Settings) -> None:
    if settings.is_production or not settings.dev_login_enabled or not settings.max_bot_token:
        raise NotFoundError("Не найдено")


@router.get("/users", response_model=list[DevUserView], summary="Пользователи для демо-входа")
async def dev_users(session: SessionDep, settings: SettingsDep) -> list[DevUserView]:
    ensure_enabled(settings)
    result = await session.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.role, User.last_name).limit(50)
    )
    return [
        DevUserView(
            max_user_id=user.max_user_id,
            role=user.role.value,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        for user in result.scalars().all()
    ]


@router.get("/init-data", response_model=DevInitDataResponse, summary="Подписать стартовые данные")
async def dev_init_data(
    max_user_id: Annotated[int, Query(ge=1, description="Идентификатор пользователя MAX")],
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
) -> DevInitDataResponse:
    ensure_enabled(settings)
    result = await session.execute(select(User).where(User.max_user_id == max_user_id).limit(1))
    user = result.scalar_one_or_none()

    init_data = build_init_data(
        settings.max_bot_token,
        user_id=max_user_id,
        first_name=(user.first_name if user else None) or "Гость",
        last_name=user.last_name if user else None,
    )

    await AuditService(session, settings).record(
        "dev.init_data_issued",
        actor_user_id=user.id if user else None,
        actor_kind="anonymous",
        entity_type="user",
        entity_id=str(max_user_id),
        ip=request.ip,
        user_agent=request.user_agent,
    )
    await session.commit()
    return DevInitDataResponse(init_data=init_data, max_user_id=max_user_id)
