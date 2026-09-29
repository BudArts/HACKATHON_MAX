from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app.db.models import Task, TaskStatus, TaskSubject
from app.integrations.gigachat.client import ChatMessage, Completion
from app.services.tutor import TutorService


@dataclass
class FakeClient:
    enabled: bool = True
    answer: str = "{}"

    async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> Completion:
        return Completion(
            text=self.answer,
            model="test",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            finish_reason="stop",
        )


def make_task() -> Task:
    moment = datetime.now(UTC)
    return Task(
        grade=8,
        subject=TaskSubject.math,
        status=TaskStatus.active,
        steps=0,
        started_at=moment,
        last_activity_at=moment,
    )


async def test_start_parses_first_question() -> None:
    client = FakeClient(
        answer=(
            '{"phase": "start", "reply": "Что дано в задаче?", "subject": "physics", '
            '"topic": "Кинематика", "steps_done": 1}'
        )
    )
    task = make_task()
    turn = await TutorService(client).start(task, "Тело движется со скоростью 20 метров в секунду")
    assert turn.phase == "start"
    assert turn.subject == TaskSubject.physics
    assert turn.topic == "Кинематика"
    assert "Что дано" in turn.reply


async def test_solved_phase_closes_task() -> None:
    client = FakeClient(
        answer=(
            '{"phase": "solved", "reply": "Верно!", "topic": "Теорема Пифагора", '
            '"solution": "1. Гипотенуза в квадрате равна сумме катетов.", "steps_done": 4}'
        )
    )
    service = TutorService(client)
    task = make_task()
    turn = await service.start(task, "Катеты 3 и 4, найдите гипотенузу")
    TutorService.apply_turn(task, turn)
    assert task.status == TaskStatus.solved
    assert task.solved_at is not None
    assert task.topic == "Теорема Пифагора"
    assert task.summary and "Гипотенуза" in task.summary


async def test_answer_without_json_is_used_as_reply() -> None:
    client = FakeClient(answer="С какого числа начинается условие?")
    task = make_task()
    turn = await TutorService(client).start(task, "Простая задача про проценты")
    assert turn.refused is True
    assert "проценты" in turn.reply or "С какого" in turn.reply


async def test_unavailable_client_raises_stub_text() -> None:
    service = TutorService(FakeClient(enabled=False))
    task = make_task()
    with pytest.raises(Exception):
        await service.start(task, "задача")
