from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.profile import BotProfile, load_profile
from app.core.config import get_settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.db.models import ConsentPurpose, ConsentSource, User, UserConsent, UserRole
from app.integrations.max.initdata import verify_contact_hash
from app.integrations.max.keyboard import (
    callback_button,
    deeplink,
    inline_keyboard,
    link_button,
    open_app_button,
)
from app.integrations.max.updates import IncomingEvent, contact_from_attachments
from app.runtime import Runtime, get_runtime
from app.services.audit import AuditService
from app.services.consents import ConsentService
from app.services.ocr import image_to_text
from app.services.tasks import TaskService
from app.services.users import UserService

log = get_logger(__name__)

GREETING = (
    "Привет! Это «УчусьИИ» — ИИ-наставник по математике и физике.\n\n"
    "Пришли фото задачи или напиши её текстом. Я не даю готовых ответов: наводящими вопросами "
    "помогу дойти до решения самому. Родители и учителя видят аналитику в личном кабинете."
)

CONSENT_PROMPT = (
    "Для работы нужна ваша согласие на обработку персональных данных.\n\n"
    "Какие данные обрабатываются: идентификатор профиля MAX, имя и фамилия, класс, содержание "
    "задач и диалогов с наставником.\n"
    "Цель: работа ИИ-наставника, аналитика для ученика, родителей и учителя.\n"
    "Данные хранятся в Российской Федерации. Согласие можно отозвать в любой момент."
)

AI_CONSENT_PROMPT = (
    "Отдельное согласие нужно на обработку текста задачи нейросетью.\n\n"
    "Как это устроено: перед отправкой в GigaChat из текста автоматически удаляются фамилии, "
    "имена, телефоны и другие персональные данные, вместо них остаются служебные метки. "
    "Без этого согласия ИИ-наставник работать не может."
)

CONSENT_ACCEPTED = "Согласие зафиксировано. Теперь можно работать: пришлите фото или текст задачи."

CONSENT_DECLINED = (
    "Понятно. Без согласия на обработку данных наставник не работает.\n\n"
    "Если измените решение — отправьте /start."
)

MENU_TITLE = "Выберите раздел"

HELP_TEXT = (
    "Как работает «УчусьИИ»\n\n"
    "1. Пришлите фото задачи или напишите её текстом.\n"
    "2. Наставник не даёт готовый ответ, а задаёт наводящие вопросы.\n"
    "3. Отвечайте шаг за шагом — обычно хватает 3-5 шагов.\n"
    "4. Когда дойдёте до решения, наставник подтвердит его и покажет разбор.\n"
    "5. Учитель видит темы класса, родитель — недельный дайджест ребёнка.\n\n"
    "Команды:\n"
    "/stats — моя статистика\n"
    "/code — код для привязки родителя (ученикам)\n"
    "/consent — согласия и данные\n"
    "/stop — прекратить обработку данных\n\n"
    "Наставник не заменяет учителя и не помогает на контрольных и экзаменах."
)

NO_CONSENT_REMINDER = (
    "Сначала нужно согласие на обработку персональных данных — без него наставник не работает."
)

NEED_GRADE = "Выберите свой класс — так наставник объясняет на подходящем уровне:"

AI_CONSENT_REQUIRED = (
    "Для диалога с наставником нужно согласие на обработку текста нейросетью. Текст перед "
    "отправкой обезличивается."
)

NO_TEXT = "Не понял сообщение. Пришлите фото задачи или напишите её текстом."

OCR_FAILED = (
    "Не смог разобрать текст с картинки. Попробуйте сфотографировать ярче и ровнее "
    "или просто напечатайте условие сообщением."
)

TASK_ERROR = "Наставник временно недоступен, задача сохранена. Попробуйте написать ещё раз позже."

TASK_SAVED_NO_AI = "Задача сохранена, но наставник недоступен. Попробуйте позже."

STUDENT_ONLY_HINT = (
    "Кабинет ученика — для школьников. Родителям и учителям открыт раздел аналитики в мини-приложении."
)

PARENT_CODE_TEXT = (
    "Код для привязки родителя (действует 30 минут): {code}\n\nРодитель вводит его в своём кабинете."
)

PARENT_ROLE_HINT = "Код привязки выдаёт ученик со своего аккаунта: команда /code."

STATS_TEMPLATE = "Ваша статистика:\nЗадач всего: {total}\nРешено: {solved}\nВ работе: {active}\n\n{topics}"

ERASURE_ACCEPTED = (
    "Заявление о прекращении обработки зарегистрировано.\n\n"
    "Персональные данные обезличены, журнал действий сохраняется три года в силу требований "
    "законодательства."
)

CONTACT_SAVED = "Номер телефона сохранён."

CONTACT_REJECTED = "Не удалось подтвердить номер телефона. Попробуйте ещё раз."

STOPPED_BY_USER = "Хорошо, уведомления прекращены. Вернуться можно командой /start."

GRADE_DONE = "Класс записан: {grade}. Теперь пришлите фото или текст задачи!"

BOT_COMMANDS = [
    {"name": "start", "description": "Начать работу"},
    {"name": "stats", "description": "Моя статистика"},
    {"name": "code", "description": "Код для привязки родителя"},
    {"name": "consent", "description": "Согласия и персональные данные"},
    {"name": "help", "description": "Как работает наставник"},
    {"name": "stop", "description": "Прекратить обработку данных"},
]


async def handle_event(session: AsyncSession, event: IncomingEvent) -> None:
    settings = get_settings()
    runtime = get_runtime()
    users = UserService(session, settings)
    consents = ConsentService(session, settings)
    audit = AuditService(session, settings)
    profile = await load_profile(runtime.max_client)

    if event.update_type in {"bot_stopped", "dialog_removed"}:
        await _on_bot_stopped(session, event, users, audit)
        return

    if event.update_type in {"bot_added", "bot_removed", "user_added", "user_removed"}:
        log.info("chat_membership_event", update_type=event.update_type, chat_id=event.chat_id)
        return

    if event.actor is None:
        log.info("event_without_actor", update_type=event.update_type)
        return

    user = await users.ensure(
        event.actor.user_id,
        first_name=event.actor.first_name,
        last_name=event.actor.last_name,
        username=event.actor.username,
        locale=event.actor.language_code,
    )

    if event.update_type == "bot_started":
        user.bot_stopped_at = None
        await _welcome(runtime, session, event, user, consents, profile)
        return

    if event.update_type == "message_callback":
        await _on_callback(runtime, session, event, user, consents, audit, profile)
        return

    if event.update_type in {"message_created", "message_edited"}:
        await _on_message(runtime, session, event, user, users, consents, audit, profile)
        return

    if event.update_type == "dialog_cleared":
        await _welcome(runtime, session, event, user, consents, profile)


async def _welcome(
    runtime: Runtime,
    session: AsyncSession,
    event: IncomingEvent,
    user: User,
    consents: ConsentService,
    profile: BotProfile,
) -> None:
    if not await consents.is_granted(user.id, ConsentPurpose.service):
        await _send(
            runtime,
            event,
            f"{GREETING}\n\n{CONSENT_PROMPT}",
            keyboard=[
                [callback_button("Согласен", "consent:service:accept")],
                [callback_button("Не согласен", "consent:service:decline")],
                [link_button("Открыть документы", deeplink(profile.username or "", "legal"))]
                if profile.username
                else [],
            ],
        )
        return

    if user.role == UserRole.student and user.grade is None:
        await _ask_grade(runtime, event)
        return

    if not await consents.is_granted(user.id, ConsentPurpose.ai_processing):
        await _send(
            runtime,
            event,
            f"{GREETING}\n\n{AI_CONSENT_PROMPT}",
            keyboard=[
                [callback_button("Разрешаю", "consent:ai:accept")],
                [callback_button("Не разрешаю", "consent:ai:decline")],
            ],
        )
        return

    await _send(runtime, event, f"{GREETING}\n\n{CONSENT_ACCEPTED}", keyboard=_main_keyboard(profile))


def _main_keyboard(profile: BotProfile) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    if profile.ready and profile.username:
        rows.append([open_app_button("Личный кабинет", profile.username, profile.user_id or 0, "cabinet")])
    rows.append([callback_button("Моя статистика", "stats")])
    rows.append([callback_button("Код для родителя", "parentcode")])
    rows.append([callback_button("Согласия и данные", "consent:show")])
    rows.append([callback_button("Как это работает", "help")])
    return rows


def _student_menu(profile: BotProfile) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    if profile.ready and profile.username:
        rows.append([open_app_button("Личный кабинет", profile.username, profile.user_id or 0, "cabinet")])
    rows.append([callback_button("Согласия и данные", "consent:show")])
    rows.append([callback_button("Как это работает", "help")])
    return rows


async def _ask_grade(runtime: Runtime, event: IncomingEvent) -> None:
    rows = [
        [callback_button("5 класс", "grade:5"), callback_button("6 класс", "grade:6")],
        [callback_button("7 класс", "grade:7"), callback_button("8 класс", "grade:8")],
        [callback_button("9 класс", "grade:9"), callback_button("10 класс", "grade:10")],
        [callback_button("11 класс", "grade:11")],
    ]
    await _send(runtime, event, NEED_GRADE, rows)


async def _on_callback(
    runtime: Runtime,
    session: AsyncSession,
    event: IncomingEvent,
    user: User,
    consents: ConsentService,
    audit: AuditService,
    profile: BotProfile,
) -> None:
    payload = (event.callback_payload or "").strip()
    notification: str | None = None

    parts = payload.split(":")
    if parts[0] == "consent" and len(parts) == 3:
        purpose = _purpose(parts[1])
        if purpose is None:
            notification = "Неизвестный раздел"
        elif parts[2] == "accept":
            await consents.grant(user, purpose, source=ConsentSource.bot)
            notification = "Согласие зафиксировано"
            if purpose == ConsentPurpose.service and user.role == UserRole.student and user.grade is None:
                await _ask_grade(runtime, event)
            else:
                await _send(runtime, event, CONSENT_ACCEPTED, keyboard=_student_menu(profile))
        else:
            if await consents.is_granted(user.id, purpose):
                await consents.revoke(user, purpose)
            notification = "Согласие не предоставлено"
            await _send(runtime, event, CONSENT_DECLINED, keyboard=[])
    elif payload.startswith("grade:") and parts[1].isdigit():
        grade = int(parts[1])
        if 5 <= grade <= 11:
            user.grade = grade
            notification = f"Класс {grade}"
            await _send(
                runtime,
                event,
                GRADE_DONE.format(grade=grade),
                keyboard=[
                    [
                        callback_button("Разрешаю ИИ", "consent:ai:accept"),
                        callback_button("Не разрешаю", "consent:ai:decline"),
                    ]
                ],
            )
        else:
            notification = "Некорректный класс"
    elif payload == "consent:show":
        await _send(
            runtime,
            event,
            _consent_summary(user, await consents.active(user.id)),
            keyboard=_student_menu(profile),
        )
    elif payload == "parentcode":
        await _send(runtime, event, PARENT_ROLE_HINT, keyboard=_student_menu(profile))
    elif payload == "stats":
        await _send(runtime, event, await _statistics_text(session, user), keyboard=_student_menu(profile))
    elif payload == "help":
        await _send(runtime, event, HELP_TEXT, keyboard=_student_menu(profile))
    elif payload == "menu":
        await _send(runtime, event, MENU_TITLE, keyboard=_student_menu(profile))
    else:
        notification = "Действие недоступно"

    await audit.record(
        "bot.callback",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        meta={"payload": payload[:128]},
    )

    if event.callback_id:
        await _answer_callback(runtime, event.callback_id, notification)


async def _statistics_text(session: AsyncSession, user: User) -> str:
    tasks = TaskService(session, get_settings())
    stats = await tasks.student_statistics(user.id)
    topics_raw = stats.get("recent_topics")
    topics = [str(item) for item in topics_raw] if isinstance(topics_raw, list) else []
    topics_text = (
        "Недавние темы: " + ", ".join(str(t) for t in topics) if topics else "Решённых задач пока нет."
    )
    return STATS_TEMPLATE.format(
        total=stats.get("total", 0),
        solved=stats.get("solved", 0),
        active=stats.get("active", 0),
        topics=topics_text,
    )


def _consent_summary(user: User, consents: list[UserConsent]) -> str:
    granted = {item.purpose.value for item in consents}
    lines = [
        "Согласия и данные",
        "",
        f"Роль: {_role_label(user.role)}",
        f"Класс: {user.grade if user.grade else 'не указан'}",
        f"Обработка персональных данных: {'предоставлено' if 'service' in granted else 'не предоставлено'}",
        f"Обработка текста нейросетью: {'разрешена' if 'ai_processing' in granted else 'не разрешена'}",
        f"Телефон: {'сохранён' if user.phone_index else 'не указан'}",
        "",
        "Отозвать согласие можно командой /stop или в мини-приложении.",
    ]
    return "\n".join(lines)


def _role_label(role: UserRole) -> str:
    return {
        UserRole.student: "ученик",
        UserRole.parent: "родитель",
        UserRole.teacher: "учитель",
        UserRole.administrator: "администратор",
    }[role]


def _image_from_attachments(attachments: list[dict[str, Any]]) -> str | None:
    for attachment in attachments:
        if attachment.get("type") != "image":
            continue
        payload = attachment.get("payload") or {}
        token = payload.get("token") or payload.get("url")
        if token:
            return str(token)
    return None


async def _on_message(
    runtime: Runtime,
    session: AsyncSession,
    event: IncomingEvent,
    user: User,
    users: UserService,
    consents: ConsentService,
    audit: AuditService,
    profile: BotProfile,
) -> None:
    phone, _name, contact_hash = contact_from_attachments(event.attachments)
    if phone:
        settings = get_settings()
        verified = bool(contact_hash) and _verify_contact_hash(
            contact_hash or "", _contact_payload(event), settings.max_bot_token
        )
        if (verified or not contact_hash) and await users.store_phone(user, phone, source="bot"):
            await audit.record(
                "bot.phone_shared",
                actor_user_id=user.id,
                entity_type="user",
                entity_id=str(user.id),
                meta={"verified": verified},
            )
            await _send(runtime, event, CONTACT_SAVED, keyboard=_student_menu(profile))
            return
        await _send(runtime, event, CONTACT_REJECTED, keyboard=_student_menu(profile))
        return

    text = (event.text or "").strip()
    if event.is_command:
        await _on_command(runtime, session, event, user, users, consents, audit, profile, event.command or "")
        return

    if not text and not event.attachments:
        await _send(runtime, event, NO_TEXT, keyboard=_student_menu(profile))
        return

    if not await consents.is_granted(user.id, ConsentPurpose.service):
        await _send(
            runtime,
            event,
            NO_CONSENT_REMINDER,
            keyboard=[
                [callback_button("Согласен", "consent:service:accept")],
                [callback_button("Не согласен", "consent:service:decline")],
            ],
        )
        return

    if user.role in {UserRole.parent, UserRole.teacher, UserRole.administrator}:
        await _send(runtime, event, STUDENT_ONLY_HINT, keyboard=_main_keyboard(profile))
        return

    if user.role == UserRole.student and user.grade is None:
        await _ask_grade(runtime, event)
        return

    if not await consents.is_granted(user.id, ConsentPurpose.ai_processing):
        await _send(
            runtime,
            event,
            AI_CONSENT_REQUIRED,
            keyboard=[
                [callback_button("Разрешаю", "consent:ai:accept")],
                [callback_button("Не разрешаю", "consent:ai:decline")],
            ],
        )
        return

    problem = text
    image_token = _image_from_attachments(event.attachments)
    if image_token and not problem:
        problem = await _recognize_image(runtime, image_token) or ""
        if not problem:
            await _send(runtime, event, OCR_FAILED, keyboard=_student_menu(profile))
            return

    tasks = TaskService(session, get_settings(), runtime.tutor)
    active = await tasks.active_task(user.id)
    try:
        if active is None:
            task, source = await tasks.create_task(user, problem)
            turn = await tasks.start_with_tutor(user, task, source)
        else:
            turn = await tasks.student_reply(user, active, problem)
    except DependencyUnavailableError:
        await _send(runtime, event, TASK_ERROR, keyboard=_student_menu(profile))
        return

    keyboard = None
    if turn.phase in {"solved", "stuck"}:
        keyboard = [[callback_button("Моя статистика", "stats")]]
    await _send(runtime, event, turn.reply, keyboard=keyboard)


async def _recognize_image(runtime: Runtime, token: str) -> str | None:
    try:
        data = await runtime.max_client.download_file(token)
    except Exception as exc:
        log.warning("image_download_failed", error=str(exc))
        return None
    return image_to_text(data)


async def _on_command(
    runtime: Runtime,
    session: AsyncSession,
    event: IncomingEvent,
    user: User,
    users: UserService,
    consents: ConsentService,
    audit: AuditService,
    profile: BotProfile,
    command: str,
) -> None:
    if command in {"start", "начать"}:
        user.bot_stopped_at = None
        await _welcome(runtime, session, event, user, consents, profile)
    elif command in {"help", "помощь"}:
        await _send(runtime, event, HELP_TEXT, keyboard=_student_menu(profile))
    elif command in {"stats", "статистика"}:
        await _send(runtime, event, await _statistics_text(session, user), keyboard=_student_menu(profile))
    elif command in {"code", "код"}:
        if user.role != UserRole.student:
            await _send(runtime, event, PARENT_ROLE_HINT, keyboard=_student_menu(profile))
            return
        tasks = TaskService(session, get_settings())
        code = await tasks.issue_parent_code(user)
        await session.commit()
        await _send(runtime, event, PARENT_CODE_TEXT.format(code=code), keyboard=_student_menu(profile))
    elif command in {"consent", "согласие", "согласия"}:
        await _send(
            runtime,
            event,
            _consent_summary(user, await consents.active(user.id)),
            keyboard=_student_menu(profile),
        )
    elif command in {"stop", "стоп"}:
        await _erasure(session, event, user, users, consents, audit, runtime)
    else:
        await _send(runtime, event, HELP_TEXT, keyboard=_student_menu(profile))


async def _erasure(
    session: AsyncSession,
    event: IncomingEvent,
    user: User,
    users: UserService,
    consents: ConsentService,
    audit: AuditService,
    runtime: Runtime,
) -> None:
    for purpose in ConsentPurpose:
        await consents.revoke(user, purpose)
    user.phone_encrypted = None
    user.phone_index = None
    user.email_encrypted = None
    user.email_index = None
    user.first_name = None
    user.last_name = None
    user.username = None
    user.is_active = False
    await audit.record(
        "personal_data.erasure_requested",
        actor_user_id=user.id,
        actor_kind="user",
        entity_type="user",
        entity_id=str(user.id),
        meta={"source": "bot"},
    )
    await _send(runtime, event, ERASURE_ACCEPTED, keyboard=[])


async def _on_bot_stopped(
    session: AsyncSession,
    event: IncomingEvent,
    users: UserService,
    audit: AuditService,
) -> None:
    if event.actor is None:
        return
    user = await users.by_max_id(event.actor.user_id)
    if user is None:
        return
    user.bot_stopped_at = datetime.now(UTC)
    await audit.record(
        "bot.stopped",
        actor_user_id=user.id,
        actor_kind="system",
        entity_type="user",
        entity_id=str(user.id),
    )


def _purpose(value: str) -> ConsentPurpose | None:
    mapping = {
        "service": ConsentPurpose.service,
        "personal": ConsentPurpose.service,
        "ai": ConsentPurpose.ai_processing,
        "notifications": ConsentPurpose.notifications,
    }
    return mapping.get(value)


def _contact_payload(event: IncomingEvent) -> str:
    for attachment in event.attachments:
        if attachment.get("type") == "contact":
            return str((attachment.get("payload") or {}).get("vcf_info") or "")
    return ""


def _verify_contact_hash(provided: str, vcf_info: str, bot_token: str) -> bool:
    if not vcf_info or not bot_token:
        return False
    return verify_contact_hash(vcf_info, provided, bot_token)


async def _send(
    runtime: Runtime,
    event: IncomingEvent,
    text: str,
    keyboard: list[list[dict[str, Any]]] | None = None,
) -> None:
    attachments = [inline_keyboard([row for row in keyboard if row])] if keyboard else None
    if event.chat_id is not None:
        kwargs: dict[str, Any] = {"chat_id": event.chat_id}
    elif event.actor is not None:
        kwargs = {"user_id": event.actor.user_id}
    else:
        return
    try:
        await runtime.max_client.send_message(text, attachments=attachments, **kwargs)
    except Exception as exc:
        log.warning("bot_send_failed", error=str(exc))


async def _answer_callback(runtime: Runtime, callback_id: str, notification: str | None) -> None:
    try:
        await runtime.max_client.answer_callback(callback_id, notification=notification)
    except Exception as exc:
        log.info("callback_answer_failed", error=str(exc))


async def register_commands(profile: BotProfile) -> None:
    runtime = get_runtime()
    if not profile.ready:
        return
    try:
        await runtime.max_client.set_commands(BOT_COMMANDS)
    except Exception as exc:
        log.info("commands_registration_failed", error=str(exc))
