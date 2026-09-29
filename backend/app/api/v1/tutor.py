from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import SessionDep, SettingsDep, UserConsented, UserTeacher
from app.core.errors import ForbiddenError
from app.db.models import UserRole
from app.services.tasks import TaskService

router = APIRouter(prefix="/tutor", tags=["Аналитика учителя"])


@router.get("/overview", summary="Аналитика по классам")
async def overview(
    session: SessionDep,
    settings: SettingsDep,
    user: UserTeacher,
    grades: list[int] | None = Query(default=None, description="Фильтр по классам"),
) -> dict[str, object]:
    service = TaskService(session, settings)
    overview_items = await service.teacher_overview(grades)
    return {
        "grades": [
            {
                "grade": item.grade,
                "students": item.students,
                "tasks_total": item.tasks_total,
                "tasks_solved": item.tasks_solved,
                "topics": item.topics,
            }
            for item in overview_items
        ]
    }


@router.get("/risk", summary="Группа риска")
async def risk(
    session: SessionDep,
    settings: SettingsDep,
    user: UserTeacher,
    grades: list[int] | None = Query(default=None),
) -> dict[str, object]:
    service = TaskService(session, settings)
    students = await service.risk_students(grades)
    return {
        "students": [
            {
                "user_id": str(item.user_id),
                "name": " ".join(part for part in (item.last_name, item.first_name) if part),
                "grade": item.grade,
                "unsolved": item.unsolved,
                "stuck_topics": item.stuck_topics,
            }
            for item in students
        ]
    }


@router.post("/link-code", summary="Код для привязки родителя", status_code=201)
async def link_code(user: UserConsented, session: SessionDep, settings: SettingsDep) -> dict[str, object]:
    if user.role != UserRole.student:
        raise ForbiddenError("Код выдаёт ученик со своего аккаунта")
    service = TaskService(session, settings)
    code = await service.issue_parent_code(user)
    await session.commit()
    return {"code": code}
