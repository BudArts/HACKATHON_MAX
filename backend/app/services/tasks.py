from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError, ForbiddenError, NotFoundError
from app.core.security import blind_index
from app.db.models import (
    MessageAuthor,
    ParentLink,
    Task,
    TaskMessage,
    TaskStatus,
    User,
)
from app.services.audit import AuditService
from app.services.tutor import TutorService, TutorTurn

CODE_TTL_MINUTES = 30
CODE_MAX_ATTEMPTS = 5
DIGEST_DAYS = 7
RISK_UNSOLVED = 3
RISK_INACTIVE_HOURS = 24


@dataclass(slots=True)
class GradeOverview:
    grade: int
    students: int
    tasks_total: int
    tasks_solved: int
    topics: list[dict[str, object]]


@dataclass(slots=True)
class RiskStudent:
    user_id: UUID
    first_name: str | None
    last_name: str | None
    grade: int
    unsolved: int
    stuck_topics: list[str]


@dataclass(slots=True)
class ChildDigest:
    student: User
    started: int
    solved: int
    topics: list[str]
    daily: list[dict[str, object]]
    last_activity_at: datetime | None


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class TaskService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        tutor: TutorService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._tutor = tutor
        self._audit = AuditService(session, settings)

    async def create_task(self, user: User, problem: str) -> tuple[Task, str]:
        task = Task(
            user_id=user.id,
            grade=user.grade or 7,
            status=TaskStatus.active,
            started_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
        )
        self._session.add(task)
        await self._session.flush()
        await self._append(task, MessageAuthor.student, problem)
        return task, problem

    async def _append(self, task: Task, author: MessageAuthor, content: str) -> TaskMessage:
        message = TaskMessage(
            task_id=task.id,
            author=author,
            content=content[:8000],
            created_at=datetime.now(UTC),
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def active_task(self, user_id: UUID) -> Task | None:
        result = await self._session.execute(
            select(Task)
            .where(Task.user_id == user_id, Task.status == TaskStatus.active)
            .order_by(Task.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def history(self, task: Task) -> list[TaskMessage]:
        result = await self._session.execute(
            select(TaskMessage)
            .where(TaskMessage.task_id == task.id)
            .order_by(TaskMessage.created_at)
            .limit(60)
        )
        return list(result.scalars().all())

    async def user_tasks(self, user_id: UUID, limit: int = 30) -> list[Task]:
        result = await self._session.execute(
            select(Task).where(Task.user_id == user_id).order_by(Task.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def student_reply(self, user: User, task: Task, answer: str) -> TutorTurn:
        if self._tutor is None:
            raise DependencyUnavailableError("ИИ-наставник недоступен")
        history = await self.history(task)
        await self._append(task, MessageAuthor.student, answer)
        turn = await self._tutor.advance(task, history[:-1], answer)
        TutorService.apply_turn(task, turn)
        await self._append(task, MessageAuthor.tutor, _reply_with_solution(turn))
        await self._audit.record(
            "tutor.turn",
            actor_user_id=user.id,
            entity_type="task",
            entity_id=str(task.id),
            meta={
                "phase": turn.phase,
                "steps": turn.steps_done,
                "redaction": list(turn.redaction_categories),
            },
        )
        return turn

    async def start_with_tutor(self, user: User, task: Task, problem: str) -> TutorTurn:
        if self._tutor is None:
            raise DependencyUnavailableError("ИИ-наставник недоступен")
        turn = await self._tutor.start(task, problem)
        TutorService.apply_turn(task, turn)
        await self._append(task, MessageAuthor.tutor, _reply_with_solution(turn))
        await self._audit.record(
            "tutor.start",
            actor_user_id=user.id,
            entity_type="task",
            entity_id=str(task.id),
            meta={"phase": turn.phase, "subject": turn.subject.value},
        )
        return turn

    async def teacher_overview(self, grades: list[int] | None = None) -> list[GradeOverview]:
        grade_rows = await self._session.execute(
            select(User.grade, func.count(User.id))
            .where(User.role == "student", User.is_active.is_(True))
            .group_by(User.grade)
            .order_by(User.grade)
        )
        grade_map = {grade: count for grade, count in grade_rows.all() if grade is not None}
        if grades:
            grade_map = {grade: count for grade, count in grade_map.items() if grade in grades}

        overview: list[GradeOverview] = []
        for grade, students in grade_map.items():
            totals = await self._session.execute(
                select(Task.status, func.count(Task.id)).where(Task.grade == grade).group_by(Task.status)
            )
            status_map = {status.value: count for status, count in totals.all()}
            solved = status_map.get(TaskStatus.solved.value, 0)
            total = sum(status_map.values())

            topics_rows = await self._session.execute(
                select(
                    Task.topic,
                    func.count(Task.id),
                    func.sum(case((Task.status == TaskStatus.solved, 1), else_=0)),
                )
                .where(Task.grade == grade, Task.topic.is_not(None))
                .group_by(Task.topic)
                .order_by(func.count(Task.id).desc())
                .limit(8)
            )
            topics = [
                {
                    "topic": topic,
                    "total": int(count),
                    "solved": int(solved_count or 0),
                }
                for topic, count, solved_count in topics_rows.all()
            ]
            overview.append(
                GradeOverview(
                    grade=grade,
                    students=students,
                    tasks_total=total,
                    tasks_solved=solved,
                    topics=topics,
                )
            )
        return overview

    async def risk_students(self, grades: list[int] | None = None) -> list[RiskStudent]:
        week_ago = datetime.now(UTC) - timedelta(days=7)
        query = (
            select(User, func.count(Task.id))
            .join(Task, Task.user_id == User.id)
            .where(
                User.role == "student",
                Task.status == TaskStatus.active,
                Task.started_at >= week_ago,
            )
            .group_by(User.id)
        )
        if grades:
            query = query.where(User.grade.in_(grades))
        rows = (await self._session.execute(query)).all()

        result: list[RiskStudent] = []
        for user, unsolved in rows:
            if unsolved < RISK_UNSOLVED:
                continue
            topics_rows = await self._session.execute(
                select(Task.topic)
                .where(Task.user_id == user.id, Task.status == TaskStatus.active)
                .order_by(Task.started_at.desc())
                .limit(5)
            )
            result.append(
                RiskStudent(
                    user_id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    grade=user.grade or 0,
                    unsolved=int(unsolved),
                    stuck_topics=[t for t in topics_rows.scalars().all() if t],
                )
            )
        return sorted(result, key=lambda item: item.unsolved, reverse=True)

    async def issue_parent_code(self, student: User) -> str:
        code = f"{secrets.randbelow(900000) + 100000}"
        link = ParentLink(
            student_user_id=student.id,
            code_index=blind_index(self._settings.secret_key, "parent_code", code),
            created_at=datetime.now(UTC),
        )
        self._session.add(link)
        await self._audit.record(
            "parent_link.code_issued",
            actor_user_id=student.id,
            entity_type="user",
            entity_id=str(student.id),
        )
        return code

    async def redeem_parent_code(self, guardian: User, code: str) -> User:
        code_index = blind_index(self._settings.secret_key, "parent_code", code)
        result = await self._session.execute(
            select(ParentLink).where(ParentLink.code_index == code_index).limit(1)
        )
        link = result.scalar_one_or_none()
        if link is None:
            raise NotFoundError("Код не найден")
        if link.verified_at is not None:
            raise ForbiddenError("Код уже использован")
        if link.attempts >= CODE_MAX_ATTEMPTS:
            raise ForbiddenError("Код заблокирован, попросите у ребёнка новый")
        if as_utc(link.created_at) < datetime.now(UTC) - timedelta(minutes=CODE_TTL_MINUTES):
            raise ForbiddenError("Код устарел, попросите у ребёнка новый")

        if link.student_user_id == guardian.id:
            raise ForbiddenError("Нельзя привязать себя")
        link.guardian_user_id = guardian.id
        link.verified_at = datetime.now(UTC)
        link.code_index = None
        await self._audit.record(
            "parent_link.verified",
            actor_user_id=guardian.id,
            entity_type="user",
            entity_id=str(link.student_user_id),
        )
        student = await self._session.get(User, link.student_user_id)
        if student is None:
            raise NotFoundError("Ученик не найден")
        return student

    async def children_of(self, guardian_id: UUID) -> list[User]:
        result = await self._session.execute(
            select(User)
            .join(ParentLink, ParentLink.student_user_id == User.id)
            .where(ParentLink.guardian_user_id == guardian_id, User.is_active.is_(True))
            .order_by(User.last_name, User.first_name)
        )
        return list(result.scalars().all())

    async def assert_guardian(self, guardian_id: UUID, student_user_id: UUID) -> None:
        result = await self._session.execute(
            select(ParentLink)
            .where(
                ParentLink.guardian_user_id == guardian_id,
                ParentLink.student_user_id == student_user_id,
                ParentLink.verified_at.is_not(None),
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is None:
            raise ForbiddenError("Ребёнок не привязан к вашему кабинету")

    async def child_digest(self, student: User) -> ChildDigest:
        since = datetime.now(UTC) - timedelta(days=DIGEST_DAYS)
        rows = await self._session.execute(
            select(Task).where(Task.user_id == student.id, Task.started_at >= since).order_by(Task.started_at)
        )
        tasks = list(rows.scalars().all())
        topics: list[str] = []
        for task in tasks:
            if task.topic and task.topic not in topics:
                topics.append(task.topic)
        daily_map: dict[str, dict[str, int]] = {}
        for task in tasks:
            key = as_utc(task.started_at).strftime("%d.%m")
            bucket = daily_map.setdefault(key, {"started": 0, "solved": 0})
            bucket["started"] += 1
            if task.status == TaskStatus.solved:
                bucket["solved"] += 1
        last_activity = max((as_utc(task.last_activity_at) for task in tasks), default=None)
        return ChildDigest(
            student=student,
            started=len(tasks),
            solved=sum(1 for task in tasks if task.status == TaskStatus.solved),
            topics=topics[:6],
            daily=[{"day": day, **values} for day, values in sorted(daily_map.items())],
            last_activity_at=last_activity,
        )

    async def student_statistics(self, user_id: UUID) -> dict[str, object]:
        rows = await self._session.execute(
            select(Task.status, func.count(Task.id)).where(Task.user_id == user_id).group_by(Task.status)
        )
        status_map = {status.value: count for status, count in rows.all()}
        solved_rows = await self._session.execute(
            select(Task.topic)
            .where(Task.user_id == user_id, Task.status == TaskStatus.solved)
            .order_by(Task.solved_at.desc())
            .limit(6)
        )
        return {
            "total": sum(status_map.values()),
            "solved": status_map.get(TaskStatus.solved.value, 0),
            "active": status_map.get(TaskStatus.active.value, 0),
            "recent_topics": [t for t in solved_rows.scalars().all() if t],
        }


def _reply_with_solution(turn: TutorTurn) -> str:
    if turn.solution and turn.phase in {"solved", "stuck"}:
        return f"{turn.reply}\n\nРазбор:\n{turn.solution}"
    return turn.reply
