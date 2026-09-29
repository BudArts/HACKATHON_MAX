from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import SessionDep, SettingsDep, UserConsented
from app.core.errors import NotFoundError
from app.db.models import Task, TaskStatus
from app.services.tasks import TaskService

router = APIRouter(prefix="/tasks", tags=["Задачи"])


def _view(task: Task, message_count: int = 0) -> dict[str, object]:
    return {
        "id": str(task.id),
        "subject": task.subject.value,
        "grade": task.grade,
        "topic": task.topic,
        "status": task.status.value,
        "steps": task.steps,
        "summary": task.summary,
        "started_at": task.started_at.isoformat(),
        "solved_at": task.solved_at.isoformat() if task.solved_at else None,
        "messages": message_count,
    }


@router.get("", summary="История задач ученика")
async def list_tasks(
    user: UserConsented, session: SessionDep, settings: SettingsDep
) -> list[dict[str, object]]:
    service = TaskService(session, settings)
    tasks = await service.user_tasks(user.id)
    result = []
    for task in tasks:
        history = await service.history(task)
        result.append(_view(task, len(history)))
    return result


@router.get("/statistics", summary="Статистика ученика")
async def statistics(user: UserConsented, session: SessionDep, settings: SettingsDep) -> dict[str, object]:
    service = TaskService(session, settings)
    return await service.student_statistics(user.id)


@router.get("/{task_id}", summary="Диалог по задаче")
async def task_detail(
    task_id: UUID, user: UserConsented, session: SessionDep, settings: SettingsDep
) -> dict[str, object]:
    service = TaskService(session, settings)
    tasks = await service.user_tasks(user.id, limit=100)
    task = next((item for item in tasks if item.id == task_id), None)
    if task is None:
        raise NotFoundError("Задача не найдена")
    history = await service.history(task)
    messages = [
        {"author": item.author.value, "content": item.content, "created_at": item.created_at.isoformat()}
        for item in history
    ]
    view = _view(task, len(messages))
    view["thread"] = messages
    return view


@router.post("/{task_id}/abandon", status_code=204, summary="Оставить задачу")
async def abandon_task(
    task_id: UUID, user: UserConsented, session: SessionDep, settings: SettingsDep
) -> None:
    service = TaskService(session, settings)
    tasks = await service.user_tasks(user.id, limit=100)
    task = next((item for item in tasks if item.id == task_id), None)
    if task is None:
        raise NotFoundError("Задача не найдена")
    if task.status == TaskStatus.active:
        task.status = TaskStatus.abandoned
        task.last_activity_at = datetime.now(UTC)
        await session.commit()
