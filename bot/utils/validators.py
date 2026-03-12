"""Валидаторы полей записи на приём.

Каждая функция возвращает (ok, cleaned_value, error_message).
При ok=True error_message=None, cleaned_value содержит нормализованное значение.
При ok=False cleaned_value=None, error_message — текст для пользователя.
"""
from __future__ import annotations

import re
import unicodedata

# ── Имя ─────────────────────────────────────────────────────────────────────
_NAME_MIN = 2
_NAME_MAX = 60
# Допустимы буквы любого языка, пробел, дефис, апостроф
_NAME_ALLOWED = re.compile(r"^[\w\s\-'.]+$", re.UNICODE)


def validate_name(raw: str) -> tuple[bool, str | None, str | None]:
    text = raw.strip()

    if not text:
        return False, None, "Имя не может быть пустым. Пожалуйста, введите ваше имя."

    if len(text) < _NAME_MIN:
        return False, None, f"Имя слишком короткое (минимум {_NAME_MIN} символа). Попробуйте ещё раз."

    if len(text) > _NAME_MAX:
        return False, None, f"Имя слишком длинное (максимум {_NAME_MAX} символов). Сократите, пожалуйста."

    # Считаем буквы (любой язык)
    letter_count = sum(1 for c in text if unicodedata.category(c).startswith("L"))
    if letter_count < 2:
        return False, None, "Имя должно содержать хотя бы 2 буквы. Введите полное имя."

    # Недопустимые символы: цифры и спецсимволы кроме пробела, дефиса, апострофа, точки
    bad = [c for c in text if not (
        unicodedata.category(c).startswith("L")  # буква
        or c in " -'."                           # допустимые разделители
    )]
    if bad:
        chars = "".join(dict.fromkeys(bad))  # уникальные без повторов
        return False, None, f"Имя содержит недопустимые символы: «{chars}». Введите только буквы."

    # Нормализация: capitalize каждое слово
    cleaned = " ".join(part.capitalize() for part in text.split())
    return True, cleaned, None


# ── Телефон ──────────────────────────────────────────────────────────────────
_DIGITS_ONLY = re.compile(r"\D")
_PHONE_MIN_DIGITS = 10
_PHONE_MAX_DIGITS = 15


def validate_phone(raw: str) -> tuple[bool, str | None, str | None]:
    text = raw.strip()

    if not text:
        return False, None, "Номер телефона не может быть пустым. Введите ваш номер."

    if len(text) > 25:
        return False, None, "Слишком длинный номер. Проверьте и введите снова."

    digits = _DIGITS_ONLY.sub("", text)

    if len(digits) < _PHONE_MIN_DIGITS:
        return False, None, (
            f"Номер слишком короткий — нужно минимум {_PHONE_MIN_DIGITS} цифр. "
            "Введите номер в формате +7 999 123-45-67 или 89991234567."
        )

    if len(digits) > _PHONE_MAX_DIGITS:
        return False, None, (
            "Номер слишком длинный. Проверьте и введите снова — "
            "например: +7 999 123-45-67 или 89991234567."
        )

    # Нормализация: приводим к +7XXXXXXXXXX для российских номеров
    if len(digits) == 11 and digits[0] in ("7", "8"):
        cleaned = "+7" + digits[1:]
    elif len(digits) == 10:
        cleaned = "+7" + digits
    else:
        # Международный формат — оставляем как есть, только цифры с +
        cleaned = "+" + digits if not text.startswith("+") else text

    return True, cleaned, None


# ── Услуга ───────────────────────────────────────────────────────────────────
_SERVICE_MIN = 2
_SERVICE_MAX = 100


def validate_service(raw: str) -> tuple[bool, str | None, str | None]:
    text = raw.strip()

    if not text:
        return False, None, "Пожалуйста, укажите интересующую услугу или специальность врача."

    if len(text) < _SERVICE_MIN:
        return False, None, "Название услуги слишком короткое. Уточните, что вас интересует."

    if len(text) > _SERVICE_MAX:
        return False, None, (
            f"Слишком длинное описание услуги (максимум {_SERVICE_MAX} символов). "
            "Укажите кратко: например «Терапевт» или «УЗИ»."
        )

    # Хотя бы одна буква должна быть
    if not any(unicodedata.category(c).startswith("L") for c in text):
        return False, None, "Укажите название услуги буквами, например «Терапевт» или «УЗИ»."

    return True, text, None


# ── Дата/время ───────────────────────────────────────────────────────────────
_DATE_MIN = 3
_DATE_MAX = 50
_DATE_HAS_DIGIT = re.compile(r"\d")


def validate_date(raw: str) -> tuple[bool, str | None, str | None]:
    text = raw.strip()

    if not text:
        return False, None, (
            "Пожалуйста, укажите желаемую дату и время.\n"
            "Например: «25.03 в 15:00» или «завтра в 10 утра»."
        )

    if len(text) < _DATE_MIN:
        return False, None, (
            "Слишком короткое значение. Укажите дату и время, "
            "например: «25.03 в 15:00»."
        )

    if len(text) > _DATE_MAX:
        return False, None, (
            "Слишком длинное значение. Укажите дату и время кратко, "
            "например: «25.03 в 15:00»."
        )

    # Должна быть хотя бы одна цифра (дата/время) или слово-маркер
    time_words = {"завтра", "сегодня", "послезавтра", "понедельник", "вторник",
                  "среду", "четверг", "пятницу", "субботу", "воскресенье",
                  "утра", "утром", "вечера", "вечером", "дня", "после", "через"}
    lower = text.lower()
    has_digit = bool(_DATE_HAS_DIGIT.search(text))
    has_word = any(w in lower for w in time_words)

    if not has_digit and not has_word:
        return False, None, (
            "Не могу распознать дату. Укажите, пожалуйста, например:\n"
            "«25.03 в 15:00», «завтра в 10:00» или «в следующий вторник»."
        )

    return True, text, None
