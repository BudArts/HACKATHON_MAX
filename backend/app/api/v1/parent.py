from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import SessionDep, SettingsDep, UserConsented
from app.services.tasks import TaskService

router = APIRouter(prefix="/parent", tags=["Кабинет родителя"])


class LinkRequest(BaseModel):
    code: str


@router.get("/children", summary="Дети, привязанные к кабинету")
async def children(
    user: UserConsented, session: SessionDep, settings: SettingsDep
) -> list[dict[str, object]]:
    service = TaskService(session, settings)
    students = await service.children_of(user.id)
    return [
        {
            "user_id": str(student.id),
            "name": " ".join(part for part in (student.first_name, student.last_name) if part),
            "grade": student.grade,
        }
        for student in students
    ]


@router.post("/link", summary="Привязать ребёнка по коду")
async def link(
    payload: LinkRequest, user: UserConsented, session: SessionDep, settings: SettingsDep
) -> dict[str, object]:
    if user.role.value != "parent":
        from app.core.errors import ForbiddenError

        raise ForbiddenError("Раздел доступен родителям")
    service = TaskService(session, settings)
    student = await service.redeem_parent_code(user, payload.code.strip())
    await session.commit()
    return {
        "user_id": str(student.id),
        "name": " ".join(part for part in (student.first_name, student.last_name) if part),
        "grade": student.grade,
    }


@router.get("/children/{student_id}/digest", summary="Недельный дайджест по ребёнку")
async def digest(
    student_id: UUID, user: UserConsented, session: SessionDep, settings: SettingsDep
) -> dict[str, object]:
    service = TaskService(session, settings)
    await service.assert_guardian(user.id, student_id)
    students = await service.children_of(user.id)
    student = next((item for item in students if item.id == student_id), None)
    if student is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Ребёнок не найден")
    digest_data = await service.child_digest(student)
    return {
        "student": {
            "user_id": str(student.id),
            "name": " ".join(part for part in (student.first_name, student.last_name) if part),
            "grade": student.grade,
        },
        "started": digest_data.started,
        "solved": digest_data.solved,
        "topics": digest_data.topics,
        "daily": digest_data.daily,
        "last_activity_at": (
            digest_data.last_activity_at.isoformat() if digest_data.last_activity_at else None
        ),
    }
