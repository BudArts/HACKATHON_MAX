from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, get_session
from app.db.models import Task, TaskMessage, TaskStatus, User, UserRole
from tests.test_initdata import build_init_data

STUDENT_MAX_ID = 9_111_222
GUARDIAN_MAX_ID = 9_444_333


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def app(sessions: async_sessionmaker[AsyncSession]) -> Iterator[FastAPI]:
    from app.main import create_app

    application = create_app()

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    application.dependency_overrides[get_session] = session_override
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as http_client:
        yield http_client


async def add_user(
    sessions: async_sessionmaker[AsyncSession],
    max_user_id: int,
    role: UserRole,
    *,
    grade: int | None = None,
    first_name: str = "Тест",
    last_name: str = "Тестов",
) -> User:
    async with sessions() as session:
        user = User(
            id=uuid4(),
            max_user_id=max_user_id,
            first_name=first_name,
            last_name=last_name,
            role=role,
            grade=grade,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        return user


async def login(client: httpx.AsyncClient, max_user_id: int) -> dict[str, object]:
    response = await client.post(
        "/api/v1/auth/max",
        json={"init_data": build_init_data(user_id=max_user_id)},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def authorize(
    client: httpx.AsyncClient, max_user_id: int, *, purpose: str | None = "service"
) -> dict[str, str]:
    payload = await login(client, max_user_id)
    tokens = payload["tokens"]
    assert isinstance(tokens, dict)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    if purpose:
        granted = await client.post(f"/api/v1/consents/{purpose}", json={"accept": True}, headers=headers)
        assert granted.status_code == 200, granted.text
    return headers


async def test_login_registers_student(client: httpx.AsyncClient) -> None:
    payload = await login(client, STUDENT_MAX_ID)
    assert payload["onboarding_required"] is True
    user = payload["user"]
    assert isinstance(user, dict)
    assert user["role"] == "student"


async def test_profile_is_closed_until_service_consent(client: httpx.AsyncClient) -> None:
    headers = await authorize(client, STUDENT_MAX_ID, purpose=None)
    response = await client.get("/api/v1/tasks", headers=headers)
    assert response.status_code == 403


async def test_tasks_history_is_empty_for_new_student(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await add_user(sessions, STUDENT_MAX_ID, UserRole.student, grade=7)
    headers = await authorize(client, STUDENT_MAX_ID)
    response = await client.get("/api/v1/tasks", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == []

    stats = await client.get("/api/v1/tasks/statistics", headers=headers)
    assert stats.status_code == 200
    assert stats.json() == {"total": 0, "solved": 0, "active": 0, "recent_topics": []}


async def test_parent_link_flow(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await add_user(
        sessions, STUDENT_MAX_ID, UserRole.student, grade=8, first_name="Пётр", last_name="Смирнов"
    )
    await add_user(sessions, GUARDIAN_MAX_ID, UserRole.parent, first_name="Анна", last_name="Смирнова")

    student_headers = await authorize(client, STUDENT_MAX_ID)
    code_response = await client.post("/api/v1/tutor/link-code", headers=student_headers)
    assert code_response.status_code == 201, code_response.text
    code = code_response.json()["code"]
    assert len(str(code)) == 6

    parent_headers = await authorize(client, GUARDIAN_MAX_ID)
    link_response = await client.post("/api/v1/parent/link", json={"code": str(code)}, headers=parent_headers)
    assert link_response.status_code == 200, link_response.text
    child = link_response.json()
    assert child["name"] == "Мария Иванова"
    assert child["grade"] == 8

    children = await client.get("/api/v1/parent/children", headers=parent_headers)
    assert children.status_code == 200
    assert [item["user_id"] for item in children.json()] == [child["user_id"]]

    digest = await client.get(f"/api/v1/parent/children/{child['user_id']}/digest", headers=parent_headers)
    assert digest.status_code == 200, digest.text
    assert digest.json()["started"] == 0

    reused = await client.post("/api/v1/parent/link", json={"code": str(code)}, headers=parent_headers)
    assert reused.status_code in {403, 404}


async def test_parent_link_requires_parent_role(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await add_user(sessions, STUDENT_MAX_ID, UserRole.student, grade=7)
    stranger_headers = await authorize(client, STUDENT_MAX_ID)
    response = await client.post("/api/v1/parent/link", json={"code": "123456"}, headers=stranger_headers)
    assert response.status_code == 403


async def test_teacher_overview_access(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await add_user(sessions, 9_000_777, UserRole.teacher, first_name="Зоя", last_name="Учительнова")
    await add_user(
        sessions, STUDENT_MAX_ID, UserRole.student, grade=7, first_name="Пётр", last_name="Смирнов"
    )

    async with sessions() as session:
        student = (await session.execute(select(User).where(User.max_user_id == STUDENT_MAX_ID))).scalar_one()
        moment = datetime.now(UTC)
        session.add(
            Task(
                id=uuid4(),
                user_id=student.id,
                grade=7,
                topic="Теорема Пифагора",
                status=TaskStatus.solved,
                steps=4,
                started_at=moment - timedelta(days=2),
                last_activity_at=moment - timedelta(days=2),
                solved_at=moment - timedelta(days=2),
            )
        )
        session.add(
            Task(
                id=uuid4(),
                user_id=student.id,
                grade=7,
                topic="Теорема Пифагора",
                status=TaskStatus.active,
                steps=2,
                started_at=moment - timedelta(days=1),
                last_activity_at=moment - timedelta(days=1),
            )
        )
        await session.commit()

    headers = await authorize(client, 9_000_777)
    overview = await client.get("/api/v1/tutor/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    grades = overview.json()["grades"]
    assert len(grades) == 1
    assert grades[0]["grade"] == 7
    assert grades[0]["students"] == 1
    assert grades[0]["tasks_total"] == 2
    assert grades[0]["tasks_solved"] == 1
    assert grades[0]["topics"][0]["topic"] == "Теорема Пифагора"

    risk = await client.get("/api/v1/tutor/risk", headers=headers)
    assert risk.status_code == 200
    assert risk.json()["students"] == []


async def test_teacher_overview_closed_for_student(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await add_user(sessions, STUDENT_MAX_ID, UserRole.student, grade=7)
    headers = await authorize(client, STUDENT_MAX_ID)
    response = await client.get("/api/v1/tutor/overview", headers=headers)
    assert response.status_code == 403


async def test_task_thread_view(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await add_user(sessions, STUDENT_MAX_ID, UserRole.student, grade=7)
    async with sessions() as session:
        student = (await session.execute(select(User).where(User.max_user_id == STUDENT_MAX_ID))).scalar_one()
        moment = datetime.now(UTC)
        task = Task(
            id=uuid4(),
            user_id=student.id,
            grade=7,
            topic="Пропорции",
            status=TaskStatus.active,
            steps=1,
            started_at=moment,
            last_activity_at=moment,
        )
        session.add(task)
        await session.flush()
        session.add(
            TaskMessage(
                id=uuid4(),
                task_id=task.id,
                author="student",
                content="В треугольнике даны два катета",
                created_at=moment,
            )
        )
        session.add(
            TaskMessage(
                id=uuid4(),
                task_id=task.id,
                author="tutor",
                content="Что нужно найти?",
                created_at=moment,
            )
        )
        await session.commit()
        task_id = task.id

    headers = await authorize(client, STUDENT_MAX_ID)
    listing = await client.get("/api/v1/tasks", headers=headers)
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["messages"] == 2

    detail = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert detail.status_code == 200
    thread = detail.json()["thread"]
    assert [item["author"] for item in thread] == ["student", "tutor"]


async def test_dev_login_closed_by_default(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/dev/users")).status_code == 404


async def test_dev_login_issues_signed_init_data(
    app: FastAPI,
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await add_user(
        sessions, STUDENT_MAX_ID, UserRole.student, grade=7, first_name="Пётр", last_name="Смирнов"
    )
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"dev_login_enabled": True}
    )

    signed = await client.get("/api/v1/dev/init-data", params={"max_user_id": STUDENT_MAX_ID})
    assert signed.status_code == 200, signed.text
    init_data = signed.json()["init_data"]

    response = await client.post("/api/v1/auth/max", json={"init_data": init_data})
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["role"] == "student"
