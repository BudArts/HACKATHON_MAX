from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import pathlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.security import blind_index
from app.db.base import get_engine, init_engine, is_sqlite
from app.db.models import (
    ClassGroup,
    Organization,
    ParentLink,
    Task,
    TaskMessage,
    TaskStatus,
    TaskSubject,
    User,
    UserRole,
)
from app.integrations.max.client import UPDATE_TYPES
from app.integrations.max.initdata import build_init_data
from app.runtime import get_runtime, init_runtime
from app.services.consents import ConsentService

log = get_logger(__name__)


async def _prepare() -> None:
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    init_runtime(settings)


async def _dispose() -> None:
    await get_runtime().close()
    await get_engine().dispose()


async def _create_sqlite_schema() -> None:
    from app.db import models  # noqa: F401
    from app.db.base import Base

    async with get_engine().raw.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def cmd_dev_init_data(args: argparse.Namespace) -> int:
    settings = get_settings()
    if settings.is_production:
        print("Команда отключена в production", file=sys.stderr)
        return 1
    if not settings.max_bot_token:
        print("Не задан MAX_BOT_TOKEN", file=sys.stderr)
        return 1
    print(
        build_init_data(
            settings.max_bot_token,
            user_id=args.max_user_id,
            first_name=args.first_name,
            last_name=args.last_name,
            start_param=args.start_param,
        )
    )
    return 0


def cmd_openapi(args: argparse.Namespace) -> int:
    from app.main import create_app

    spec = create_app().openapi()
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix in {".yaml", ".yml"}:
        import yaml

        target.write_text(yaml.dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    else:
        target.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Спецификация OpenAPI сохранена: {target}")
    return 0


def cmd_init_db(_: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings)
    if is_sqlite(settings.database_url):
        init_engine(settings)
        asyncio.run(_create_sqlite_schema())
        asyncio.run(get_engine().dispose())
        print(f"Схема создана: {settings.database_url}")
        return 0

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    print("Миграции применены")
    return 0


async def cmd_me(_: argparse.Namespace) -> int:
    await _prepare()
    info = await get_runtime().max_client.get_me()
    print(f"user_id={info.get('user_id')} username={info.get('username')} name={info.get('name')}")
    await _dispose()
    return 0


async def cmd_webhook(args: argparse.Namespace) -> int:
    await _prepare()
    client = get_runtime().max_client
    settings = get_settings()
    if args.action == "info":
        payload = await client.list_subscriptions()
        for item in payload.get("subscriptions") or []:
            print(item)
    elif args.action == "set":
        url = args.url or settings.max_webhook_url
        if not url:
            print("Укажите --url или задайте MAX_WEBHOOK_URL", file=sys.stderr)
            return 2
        result = await client.subscribe(url, args.secret or settings.max_webhook_secret, UPDATE_TYPES)
        print(result)
    elif args.action == "remove":
        url = args.url or settings.max_webhook_url
        print(await client.unsubscribe(url))
    await _dispose()
    return 0


async def cmd_commands(_: argparse.Namespace) -> int:
    await _prepare()
    from app.bot.handlers import register_commands
    from app.bot.profile import load_profile

    profile = await load_profile(get_runtime().max_client)
    if not profile.ready:
        print("Не удалось получить профиль бота", file=sys.stderr)
        await _dispose()
        return 1
    await register_commands(profile)
    print(f"Команды зарегистрированы для @{profile.username}")
    await _dispose()
    return 0


async def cmd_policies(_: argparse.Namespace) -> int:
    await _prepare()
    async for session in get_engine().open_session():
        documents = await ConsentService(session, get_settings()).sync_policies()
        await session.commit()
        for document in documents:
            print(f"{document.code} {document.version}")
        await session.close()
        break
    await _dispose()
    return 0


async def cmd_retention(_: argparse.Namespace) -> int:
    await _prepare()
    from app.worker import run_retention

    await run_retention()
    await _dispose()
    return 0


async def cmd_grant_role(args: argparse.Namespace) -> int:
    await _prepare()
    settings = get_settings()
    async for session in get_engine().open_session():
        index = blind_index(settings.secret_key, "phone", args.phone)
        result = await session.execute(select(User).where(User.phone_index == index))
        user = result.scalar_one_or_none()
        if user is None:
            result = await session.execute(select(User).where(User.max_user_id == args.max_user_id))
            user = result.scalar_one_or_none()
        if user is None:
            print("Пользователь не найден", file=sys.stderr)
            await session.close()
            await _dispose()
            return 1
        user.role = UserRole(args.role)
        session.add(user)
        await session.commit()
        print(f"{user.id} -> {user.role.value}")
        await session.close()
        break
    await _dispose()
    return 0


DEMO_SCHOOL = {
    "name": "Средняя общеобразовательная школа № 12",
    "short_name": "СОШ № 12",
    "address": "г. Чита, ул. Ленина, 12",
}


@dataclass(frozen=True, slots=True)
class DemoClass:
    grade: int
    teacher_max_id: int
    teacher_first_name: str
    teacher_last_name: str
    students: tuple[tuple[int, str, str], ...]


DEMO_CLASSES = (
    DemoClass(
        grade=7,
        teacher_max_id=9_000_000,
        teacher_first_name="Ольга",
        teacher_last_name="Лебедева",
        students=(
            (9_100_101, "Артём", "Ковалёв"),
            (9_100_102, "Софья", "Маркова"),
            (9_100_103, "Илья", "Дёмин"),
        ),
    ),
    DemoClass(
        grade=8,
        teacher_max_id=9_000_001,
        teacher_first_name="Сергей",
        teacher_last_name="Панкратов",
        students=(
            (9_100_201, "Вера", "Носова"),
            (9_100_202, "Матвей", "Ершов"),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class DemoParent:
    max_user_id: int
    first_name: str
    last_name: str
    student_max_id: int


DEMO_PARENTS = (
    DemoParent(9_100_001, "Мария", "Ковалёва", 9_100_101),
    DemoParent(9_100_002, "Игорь", "Носов", 9_100_201),
)


@dataclass(frozen=True, slots=True)
class DemoTask:
    student_max_id: int
    subject: TaskSubject
    topic: str
    status: TaskStatus
    steps: int
    age_days: int
    problem: str
    first_question: str


DEMO_TASKS = (
    DemoTask(
        9_100_101,
        TaskSubject.math,
        "Теорема Пифагора",
        TaskStatus.solved,
        4,
        3,
        "Катеты прямоугольного треугольника 3 и 4, найдите гипотенузу",
        "Что дано в задаче и что нужно найти?",
    ),
    DemoTask(
        9_100_101,
        TaskSubject.math,
        "Проценты",
        TaskStatus.active,
        2,
        0,
        "Куртка стоит 4000 рублей, скидка 15 процентов, сколько заплатим",
        "Сколько процентов от первоначальной цены останется заплатить?",
    ),
    DemoTask(
        9_100_102,
        TaskSubject.math,
        "Теорема Пифагора",
        TaskStatus.solved,
        5,
        2,
        "Диагональ прямоугольника 13, одна сторона 5, найдите вторую сторону",
        "Какая формула связывает диагональ прямоугольника с его сторонами?",
    ),
    DemoTask(
        9_100_103,
        TaskSubject.physics,
        "Равномерное движение",
        TaskStatus.abandoned,
        1,
        1,
        "Поезд едет 72 километра в час, какой путь он пройдёт за 30 минут",
        "Как связаны скорость, время и расстояние?",
    ),
    DemoTask(
        9_100_201,
        TaskSubject.physics,
        "Плотность",
        TaskStatus.solved,
        3,
        1,
        "Масса кирпича 3.6 кг, объём 2 дм3, найдите плотность",
        "По какой формуле плотность связана с массой и объёмом?",
    ),
    DemoTask(
        9_100_202,
        TaskSubject.math,
        "Квадратные уравнения",
        TaskStatus.active,
        2,
        0,
        "Решите уравнение x2 минус 5x плюс 6 равно 0",
        "Что такое дискриминант квадратного уравнения?",
    ),
)


async def cmd_seed(args: argparse.Namespace) -> int:
    await _prepare()
    async for session in get_engine().open_session():
        existing = await session.execute(select(Organization).limit(1))
        if existing.scalar_one_or_none() is not None and not args.force:
            print("Данные уже заполнены. Используйте --force для повторного заполнения.", file=sys.stderr)
            await session.close()
            await _dispose()
            return 1

        organization = Organization(id=uuid4(), is_active=True, **DEMO_SCHOOL)
        session.add(organization)

        now = datetime.now(UTC)
        year = f"{now.year}/{now.year + 1}"
        teachers: dict[int, User] = {}
        student_users: dict[int, User] = {}
        grade_of_student: dict[int, int] = {}

        for item in DEMO_CLASSES:
            teacher = User(
                id=uuid4(),
                max_user_id=item.teacher_max_id,
                first_name=item.teacher_first_name,
                last_name=item.teacher_last_name,
                locale="ru",
                role=UserRole.teacher,
                is_active=True,
            )
            session.add(teacher)
            await session.flush()
            teachers[item.grade] = teacher

            class_group = ClassGroup(
                id=uuid4(),
                organization_id=organization.id,
                name=f"{item.grade}А",
                grade=item.grade,
                academic_year=year,
                homeroom_teacher_id=teacher.id,
            )
            session.add(class_group)
            await session.flush()

            for max_user_id, first_name, last_name in item.students:
                student = User(
                    id=uuid4(),
                    max_user_id=max_user_id,
                    first_name=first_name,
                    last_name=last_name,
                    locale="ru",
                    role=UserRole.student,
                    grade=item.grade,
                    is_active=True,
                )
                session.add(student)
                await session.flush()
                student_users[max_user_id] = student
                grade_of_student[max_user_id] = item.grade

        parents: dict[int, User] = {}
        for person in DEMO_PARENTS:
            parent = User(
                id=uuid4(),
                max_user_id=person.max_user_id,
                first_name=person.first_name,
                last_name=person.last_name,
                locale="ru",
                role=UserRole.parent,
                is_active=True,
            )
            session.add(parent)
            await session.flush()
            parents[person.max_user_id] = parent
            session.add(
                ParentLink(
                    id=uuid4(),
                    student_user_id=student_users[person.student_max_id].id,
                    guardian_user_id=parent.id,
                    created_at=now,
                    verified_at=now,
                )
            )

        for demo in DEMO_TASKS:
            student = student_users[demo.student_max_id]
            started_at = now - timedelta(days=demo.age_days, hours=3)
            last_activity = started_at + timedelta(minutes=15 * demo.steps)
            solved_at = last_activity if demo.status == TaskStatus.solved else None
            task = Task(
                id=uuid4(),
                user_id=student.id,
                subject=demo.subject,
                grade=grade_of_student[demo.student_max_id],
                topic=demo.topic,
                status=demo.status,
                steps=demo.steps,
                summary="Задача решена с подсказками наставника."
                if demo.status == TaskStatus.solved
                else None,
                redaction_categories={},
                started_at=started_at,
                last_activity_at=last_activity,
                solved_at=solved_at,
            )
            session.add(task)
            await session.flush()
            session.add(
                TaskMessage(
                    id=uuid4(),
                    task_id=task.id,
                    author="student",
                    content=demo.problem,
                    created_at=started_at,
                )
            )
            session.add(
                TaskMessage(
                    id=uuid4(),
                    task_id=task.id,
                    author="tutor",
                    content=demo.first_question,
                    created_at=started_at + timedelta(minutes=1),
                )
            )

        await session.commit()
        print(
            f"Заполнено: {organization.short_name}, классов {len(DEMO_CLASSES)}, "
            f"педагогов {len(teachers)}, учеников {len(student_users)}, "
            f"родителей {len(parents)}, задач {len(DEMO_TASKS)}"
        )
        await session.close()
        break
    await _dispose()
    return 0


async def cmd_expire_sessions(_: argparse.Namespace) -> int:
    await _prepare()
    from sqlalchemy import update

    from app.db.models import AuthSession

    cutoff = datetime.now(UTC) - timedelta(days=get_settings().refresh_token_ttl_days)
    async for session in get_engine().open_session():
        await session.execute(
            update(AuthSession).where(AuthSession.expires_at < cutoff).values(revoked_at=cutoff)
        )
        await session.commit()
        await session.close()
        break
    await _dispose()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uchusai", description="Служебные операции сервиса")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Создать схему БД (миграции или SQLite)").set_defaults(func=cmd_init_db)

    dev = sub.add_parser(
        "dev-init-data",
        help="Подписать стартовые данные мини-приложения для локальной проверки (вне production)",
    )
    dev.add_argument("--max-user-id", type=int, required=True, dest="max_user_id")
    dev.add_argument("--first-name", default="Пользователь", dest="first_name")
    dev.add_argument("--last-name", default=None, dest="last_name")
    dev.add_argument("--start-param", default=None, dest="start_param")
    dev.set_defaults(func=cmd_dev_init_data)
    sub.add_parser("me", help="Проверить токен бота MAX").set_defaults(func=cmd_me)

    openapi = sub.add_parser("openapi", help="Сохранить спецификацию OpenAPI в файл (.yaml или .json)")
    openapi.add_argument("--out", default="openapi.yaml")
    openapi.set_defaults(func=cmd_openapi)

    webhook = sub.add_parser("webhook", help="Управление подпиской на события MAX")
    webhook.add_argument("action", choices=["set", "info", "remove"])
    webhook.add_argument("--url")
    webhook.add_argument("--secret")
    webhook.set_defaults(func=cmd_webhook)

    sub.add_parser("commands", help="Зарегистрировать команды меню бота").set_defaults(func=cmd_commands)
    sub.add_parser("policies", help="Синхронизировать редакции юридических документов").set_defaults(
        func=cmd_policies
    )
    sub.add_parser("retention", help="Выполнить очистку по срокам хранения").set_defaults(func=cmd_retention)
    sub.add_parser("expire-sessions", help="Отозвать просроченные сессии").set_defaults(
        func=cmd_expire_sessions
    )

    role = sub.add_parser("grant-role", help="Назначить роль пользователю")
    role.add_argument("role", choices=[item.value for item in UserRole])
    role.add_argument("--phone")
    role.add_argument("--max-user-id", type=int, default=0, dest="max_user_id")
    role.set_defaults(func=cmd_grant_role)

    seed = sub.add_parser("seed", help="Заполнить демонстрационные данные")
    seed.add_argument("--force", action="store_true")
    seed.set_defaults(func=cmd_seed)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    handler = args.func
    try:
        if inspect.iscoroutinefunction(handler):
            return int(asyncio.run(handler(args)))
        return int(handler(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
