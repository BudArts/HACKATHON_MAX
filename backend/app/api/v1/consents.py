from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, RequestContextDep, SessionDep, SettingsDep
from app.api.schemas import ConsentDecision, ConsentState, PolicyView
from app.api.v1.auth import consent_states
from app.core.errors import ConflictError, NotFoundError
from app.db.models import ConsentPurpose, ConsentSource
from app.services.audit import AuditService
from app.services.consents import ConsentService
from app.services.legal import latest_by_code

router = APIRouter(tags=["Персональные данные"])


def _purpose(value: str) -> ConsentPurpose:
    try:
        return ConsentPurpose(value)
    except ValueError as exc:
        raise NotFoundError("Неизвестная цель обработки") from exc


@router.get("/legal", response_model=list[PolicyView], summary="Действующие редакции документов")
async def list_documents() -> list[PolicyView]:
    return [
        PolicyView(code=document.code, version=document.version, title=document.title, body=document.body)
        for document in sorted(latest_by_code().values(), key=lambda item: item.code)
    ]


@router.get("/legal/{code}", response_model=PolicyView, summary="Текст документа")
async def get_document(code: str) -> PolicyView:
    document = latest_by_code().get(code)
    if document is None:
        raise NotFoundError("Документ не найден")
    return PolicyView(
        code=document.code,
        version=document.version,
        title=document.title,
        body=document.body,
    )


@router.get("/consents", response_model=list[ConsentState], summary="Состояние согласий")
async def my_consents(
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> list[ConsentState]:
    return await consent_states(session, user, settings)


@router.post("/consents/{purpose}", response_model=list[ConsentState], summary="Предоставить согласие")
async def grant_consent(
    purpose: str,
    decision: ConsentDecision,
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> list[ConsentState]:
    target = _purpose(purpose)
    if not decision.accept:
        raise ConflictError("Для отказа от согласия используйте запрос на удаление")

    service = ConsentService(session, settings)
    await service.grant(
        user, target, source=ConsentSource.miniapp, ip=request.ip, user_agent=request.user_agent
    )
    await session.commit()
    return await consent_states(session, user, settings)


@router.delete("/consents/{purpose}", response_model=list[ConsentState], summary="Отозвать согласие")
async def revoke_consent(
    purpose: str,
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> list[ConsentState]:
    target = _purpose(purpose)
    service = ConsentService(session, settings)
    revoked = await service.revoke(user, target, ip=request.ip, user_agent=request.user_agent)
    await session.commit()
    if not revoked:
        raise ConflictError("Согласие уже отозвано или не предоставлялось")
    return await consent_states(session, user, settings)


@router.post(
    "/personal-data/erasure-request", status_code=202, summary="Запрос на удаление персональных данных"
)
async def erasure_request(
    request: RequestContextDep,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> dict[str, str]:
    await AuditService(session, settings).record(
        "personal_data.erasure_requested",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        ip=request.ip,
        user_agent=request.user_agent,
    )
    await session.commit()
    return {
        "status": "accepted",
        "message": (
            "Заявление зарегистрировано. Обработка прекращается, "
            "данные будут уничтожены в течение десяти рабочих дней."
        ),
    }
