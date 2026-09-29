from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUser,
    RequestContextDep,
    SessionDep,
    SettingsDep,
    UserServiceDep,
    require_consent,
)
from app.api.schemas import PersonalDataReport, PhoneShareRequest, ProfileUpdate, UserView
from app.api.v1.auth import consent_states
from app.core.errors import ConflictError, ForbiddenError
from app.db.models import (
    AuditEvent,
    ConsentPurpose,
    Notification,
    ParentLink,
    Task,
    TaskMessage,
    User,
    UserRole,
)
from app.integrations.max.initdata import verify_miniapp_contact
from app.services.audit import AuditService

ANONYMIZED_BODY = "Содержание удалено по заявлению субъекта персональных данных"

router = APIRouter(tags=["Кабинет"])

ConsentedUser = Annotated[User, Depends(require_consent(ConsentPurpose.service))]


@router.get("/me", response_model=UserView, summary="Профиль")
async def me(user: CurrentUser) -> UserView:
    return UserView.from_user(user)


@router.patch("/me", response_model=UserView, summary="Обновить профиль")
async def update_me(
    payload: ProfileUpdate,
    user: ConsentedUser,
    session: SessionDep,
    users: UserServiceDep,
) -> UserView:
    if payload.email is not None:
        if payload.email == "":
            user.email_index = None
            user.email_encrypted = None
        elif not await users.store_email(user, payload.email, source="miniapp"):
            raise ConflictError("Некорректный адрес электронной почты")
    await session.commit()
    return UserView.from_user(user)


@router.patch("/me/phone", response_model=UserView, summary="Сохранить номер телефона из MAX")
async def share_phone(
    payload: PhoneShareRequest,
    user: ConsentedUser,
    session: SessionDep,
    settings: SettingsDep,
    users: UserServiceDep,
) -> UserView:
    confirmed = verify_miniapp_contact(
        payload.auth_date,
        payload.phone,
        user.max_user_id,
        payload.hash,
        settings.max_bot_token,
    )
    if not confirmed:
        raise ConflictError("Не удалось подтвердить номер телефона через MAX")
    if not await users.store_phone(user, payload.phone, source="miniapp"):
        raise ConflictError("Некорректный номер телефона")
    await session.commit()
    return UserView.from_user(user)


@router.get(
    "/me/personal-data", response_model=PersonalDataReport, summary="Выписка об обрабатываемых данных"
)
async def personal_data_report(
    user: ConsentedUser,
    session: SessionDep,
    settings: SettingsDep,
) -> PersonalDataReport:
    tasks_total = (
        await session.execute(select(func.count(Task.id)).where(Task.user_id == user.id))
    ).scalar_one()
    notifications_total = (
        await session.execute(select(func.count(Notification.id)).where(Notification.user_id == user.id))
    ).scalar_one()
    events = (
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.actor_user_id == user.id)
                .order_by(AuditEvent.created_at.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )

    return PersonalDataReport(
        profile=UserView.from_user(user),
        consents=await consent_states(session, user, settings),
        tasks_total=int(tasks_total),
        notifications_total=int(notifications_total),
        audit_entries=[
            {
                "action": event.action,
                "outcome": event.outcome,
                "entity_type": event.entity_type,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    )


@router.delete("/me", status_code=202, summary="Прекращение обработки и удаление данных")
async def erase_me(
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> dict[str, Any]:
    if user.role == UserRole.administrator:
        raise ForbiddenError("Удаление учётной записи администратора выполняется оператором системы")

    await AuditService(session, settings).record(
        "personal_data.erasure_requested",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        ip=request.ip,
        user_agent=request.user_agent,
    )

    user.phone_encrypted = None
    user.phone_index = None
    user.email_encrypted = None
    user.email_index = None
    user.first_name = None
    user.last_name = None
    user.username = None
    user.is_active = False

    links = (
        (await session.execute(select(ParentLink).where(ParentLink.guardian_user_id == user.id)))
        .scalars()
        .all()
    )
    for link in links:
        await session.delete(link)

    tasks = (await session.execute(select(Task).where(Task.user_id == user.id))).scalars().all()
    for task in tasks:
        task.topic = None
        task.summary = None
        messages = (
            (await session.execute(select(TaskMessage).where(TaskMessage.task_id == task.id))).scalars().all()
        )
        for message in messages:
            message.content = ANONYMIZED_BODY

    await session.commit()
    return {
        "status": "accepted",
        "message": (
            "Обработка прекращена, персональные данные обезличены. Журнал действий сохраняется три года."
        ),
    }
