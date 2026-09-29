from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.db.models import Task, TaskMessage, TaskStatus, TaskSubject
from app.integrations.gigachat.client import ChatMessage, GigaChatClient, GigaChatError
from app.integrations.gigachat.redaction import redactor
from app.services.prompts import SYSTEM_GRADE_HINT, SYSTEM_TUTOR

log = get_logger(__name__)

MAX_INPUT_CHARS = 4000
MAX_REPLY_CHARS = 2500
HISTORY_WINDOW = 14
MAX_STEPS_TO_SOLVED = 8

PHASES = {"start", "guide", "solved", "stuck", "offtopic"}


@dataclass(slots=True)
class TutorTurn:
    reply: str
    phase: str
    subject: TaskSubject
    topic: str | None = None
    solution: str | None = None
    steps_done: int = 0
    model: str = ""
    total_tokens: int = 0
    redaction_categories: tuple[str, ...] = field(default_factory=tuple)
    refused: bool = False


def _truncate(text: str) -> str:
    return text[:MAX_INPUT_CHARS]


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("answer without json object")
    return dict(json.loads(cleaned[start : end + 1]))


class TutorService:
    def __init__(self, client: GigaChatClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.enabled

    async def start(self, task: Task, problem: str) -> TutorTurn:
        return await self._ask(task, problem, is_first=True)

    async def advance(self, task: Task, history: list[TaskMessage], answer: str) -> TutorTurn:
        return await self._ask(task, answer, is_first=False, history=history)

    async def _ask(
        self,
        task: Task,
        student_text: str,
        *,
        is_first: bool,
        history: list[TaskMessage] | None = None,
    ) -> TutorTurn:
        if not self.available:
            raise DependencyUnavailableError(
                "ИИ-наставник временно недоступен. Задача сохранена, попробуйте позже."
            )

        redacted = redactor.redact(_truncate(student_text))
        messages = [
            ChatMessage(role="system", content=SYSTEM_TUTOR),
            ChatMessage(role="system", content=SYSTEM_GRADE_HINT),
        ]
        if history:
            for item in history[-HISTORY_WINDOW:]:
                role = "user" if item.author.value == "student" else "assistant"
                messages.append(ChatMessage(role=role, content=item.content[:MAX_INPUT_CHARS]))

        prefix = f"Класс ученика: {task.grade}."
        if is_first:
            prefix += " Первое сообщение ученика с задачей:"
        else:
            prefix += " Очередной ответ ученика:"
        messages.append(ChatMessage(role="user", content=f"{prefix}\n{redacted.text}"))

        try:
            completion = await self._client.complete(
                messages,
                temperature=0.3,
                max_tokens=900,
            )
        except GigaChatError as exc:
            log.warning("tutor_turn_failed", error=str(exc))
            raise DependencyUnavailableError(
                "ИИ-наставник временно недоступен. Задача сохранена, попробуйте позже."
            ) from exc

        if completion.refused or not completion.text:
            return TutorTurn(
                reply=(
                    "Я не смог разобрать это сообщение. Попробуйте сформулировать задачу "
                    "по-другому или отправьте её текстом."
                ),
                phase="guide",
                subject=task.subject,
                model=completion.model,
                total_tokens=completion.total_tokens,
                redaction_categories=redacted.categories,
                refused=True,
            )

        try:
            parsed = _parse_json_object(completion.text)
        except ValueError:
            return TutorTurn(
                reply=completion.text[:MAX_REPLY_CHARS],
                phase="guide",
                subject=task.subject,
                model=completion.model,
                total_tokens=completion.total_tokens,
                redaction_categories=redacted.categories,
                refused=True,
            )

        phase = str(parsed.get("phase") or "guide")
        if phase not in PHASES:
            phase = "guide"
        if is_first and phase == "guide":
            phase = "start"

        subject_value = str(parsed.get("subject") or task.subject.value)
        try:
            subject = TaskSubject(subject_value)
        except ValueError:
            subject = task.subject

        topic = parsed.get("topic")
        topic = str(topic)[:160] if topic else task.topic

        solution = parsed.get("solution")
        solution = str(solution)[:MAX_REPLY_CHARS] if solution else None

        try:
            steps_done = int(parsed.get("steps_done") or 0)
        except (TypeError, ValueError):
            steps_done = 0

        reply = str(parsed.get("reply") or "").strip()[:MAX_REPLY_CHARS]
        if not reply:
            reply = "Давайте продолжим: с чего начинается решение этой задачи?"

        solved = phase in {"solved", "stuck"} and bool(solution)
        if solved and not topic:
            topic = task.topic or "Задача"

        return TutorTurn(
            reply=reply,
            phase=phase,
            subject=subject,
            topic=topic,
            solution=solution,
            steps_done=max(steps_done, 0),
            model=completion.model,
            total_tokens=completion.total_tokens,
            redaction_categories=redacted.categories,
        )

    @staticmethod
    def apply_turn(task: Task, turn: TutorTurn, now: datetime | None = None) -> None:
        moment = now or datetime.now(UTC)
        task.subject = turn.subject
        task.topic = turn.topic or task.topic
        task.steps = max(task.steps, turn.steps_done)
        task.last_activity_at = moment
        if turn.phase in {"solved", "stuck"} and turn.solution:
            task.status = TaskStatus.solved
            task.solved_at = moment
            task.summary = turn.solution
