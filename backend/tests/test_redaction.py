from __future__ import annotations

from app.integrations.gigachat.redaction import redactor


def test_phone_and_email_are_masked() -> None:
    result = redactor.redact("Свяжитесь со мной: +7 912 345-67-89 или parent@example.ru")
    assert "+7 912 345-67-89" not in result.text
    assert "parent@example.ru" not in result.text
    assert "ТЕЛЕФОН" in result.categories
    assert "EMAIL" in result.categories


def test_full_name_is_masked_and_restored() -> None:
    result = redactor.redact("Обращение касается Иванова Петра Сергеевича, ученика 5Б класса.")
    assert "Иванова Петра Сергеевича" not in result.text
    assert "ФИО" in result.categories
    restored = redactor.finalize("Ответ по обращению [ФИО_1].", result.mapping)
    assert "Иванова Петра Сергеевича" in restored


def test_documents_are_masked_and_removed() -> None:
    result = redactor.redact("СНИЛС 123-456-789 00, полис 1234567890123456")
    assert "123-456-789 00" not in result.text
    assert "1234567890123456" not in result.text
    finalized = redactor.finalize("Документы [СНИЛС_1] и [ПОЛИС_1] проверены.", result.mapping)
    assert "СНИЛС" not in finalized
    assert "ПОЛИС" not in finalized


def test_service_words_are_not_names() -> None:
    result = redactor.redact("Здравствуйте, уважаемый классный руководитель!")
    assert result.mapping == {}


def test_empty_text_passes_through() -> None:
    result = redactor.redact("")
    assert result.text == ""
    assert result.found_personal_data is False
