from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

Rule = tuple[str, re.Pattern[str], Callable[[str], bool] | None]


def _is_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] in "78":
        return True
    return len(digits) == 10 and digits[0] == "9"


def _is_full_name(value: str) -> bool:
    parts = value.split()
    if len(parts) != 3 or any(part in SERVICE_WORDS for part in parts):
        return False
    return all(len(part) > 1 for part in parts)


def _is_name_pair(value: str) -> bool:
    parts = value.split()
    if len(parts) != 2 or any(part in SERVICE_WORDS for part in parts):
        return False
    return any(part.lower().endswith(SURNAME_ENDINGS) for part in parts)


RULES: tuple[Rule, ...] = (
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), None),
    ("СНИЛС", re.compile(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2}\b"), None),
    ("ПОЛИС", re.compile(r"\b\d{16}\b"), None),
    ("ИНН", re.compile(r"\b\d{10}\b|\b\d{12}\b"), None),
    ("ПАСПОРТ", re.compile(r"\b\d{4}\s?\d{6}\b"), None),
    ("ДАТА_РОЖДЕНИЯ", re.compile(r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"), None),
    ("ТЕЛЕФОН", re.compile(r"(?:\+7|8)?[\s(-]*9\d{2}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}"), _is_phone),
    ("ФИО", re.compile(r"\b[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\b"), _is_full_name),
    ("ИМЯ", re.compile(r"\b[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\b"), _is_name_pair),
)

RESTORABLE_LABELS = frozenset({"ФИО", "ИМЯ"})

SERVICE_WORDS = frozenset(
    {
        "Российская",
        "Федерация",
        "Москва",
        "Петербург",
        "Санкт",
        "Министерство",
        "Образования",
        "Здравствуйте",
        "Добрый",
        "Добрая",
        "Доброе",
        "Уважаемый",
        "Уважаемая",
        "Классный",
        "Руководитель",
        "Директор",
        "Школа",
        "Лицей",
        "Гимназия",
    }
)

SURNAME_ENDINGS = (
    "ов",
    "ев",
    "ёв",
    "ин",
    "ын",
    "ский",
    "цкий",
    "ова",
    "ева",
    "ёва",
    "ина",
    "ская",
    "цкая",
    "ко",
    "ук",
    "юк",
)


@dataclass(slots=True)
class RedactionResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)
    categories: tuple[str, ...] = ()

    @property
    def found_personal_data(self) -> bool:
        return bool(self.mapping)


class PersonalDataRedactor:
    def redact(self, text: str) -> RedactionResult:
        if not text:
            return RedactionResult(text=text)

        mapping: dict[str, str] = {}
        categories: list[str] = []
        working = text

        for label, pattern, predicate in RULES:
            counter = 0

            def _substitute(
                match: re.Match[str], label: str = label, predicate: Callable[[str], bool] | None = predicate
            ) -> str:
                nonlocal counter
                original = match.group(0)
                if predicate is not None and not predicate(original):
                    return original
                counter += 1
                placeholder = f"[{label}_{counter}]"
                mapping[placeholder] = original
                return placeholder

            replaced = pattern.sub(_substitute, working)
            if replaced != working:
                working = replaced
                categories.append(label)

        return RedactionResult(text=working, mapping=mapping, categories=tuple(categories))

    def finalize(self, text: str, mapping: dict[str, str]) -> str:
        if not mapping:
            return text
        result = text
        for placeholder, original in mapping.items():
            label = placeholder[1:].rsplit("_", 1)[0]
            if label in RESTORABLE_LABELS:
                result = result.replace(placeholder, original)
            else:
                result = result.replace(placeholder, "")
        return re.sub(r"[ \t]{2,}", " ", result).strip()


redactor = PersonalDataRedactor()
