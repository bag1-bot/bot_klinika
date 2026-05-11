"""Валидаторы полей записи на приём.

Каждая функция возвращает (ok, cleaned_value, error_message).
При ok=True error_message=None, cleaned_value содержит нормализованное значение.
При ok=False cleaned_value=None, error_message — текст для пользователя.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
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


# ── Парсинг даты/времени для проверки "не в прошлом" ─────────────────────────
_RE_DDMMYYYY = re.compile(r"(?P<d>\d{1,2})[./-](?P<m>\d{1,2})(?:[./-](?P<y>\d{2,4}))?")
_RE_HHMM = re.compile(r"(?P<h>\d{1,2})\s*[:.]\s*(?P<min>\d{2})")


@dataclass(frozen=True)
class ParsedDateTime:
    dt: datetime
    has_time: bool


def parse_requested_datetime(raw: str, *, now: datetime | None = None) -> ParsedDateTime | None:
    """Пытается распарсить дату/время из текста пользователя.

    Поддерживаем базовые форматы:
    - 25.03 15:00 / 25.03.2026 15:00 / 25/03 в 15:00
    - сегодня/завтра/послезавтра + HH:MM

    Возвращает datetime в локальном времени сервера (naive) и флаг наличия времени.
    """
    text = raw.strip().lower()
    now = now or datetime.now()

    has_time = False
    t_match = _RE_HHMM.search(text)
    parsed_time = time(0, 0)
    if t_match:
        h = int(t_match.group("h"))
        mi = int(t_match.group("min"))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            parsed_time = time(h, mi)
            has_time = True

    # относительные слова
    base_day: date | None = None
    if "сегодня" in text:
        base_day = now.date()
    elif "завтра" in text:
        base_day = (now + timedelta(days=1)).date()
    elif "послезавтра" in text:
        base_day = (now + timedelta(days=2)).date()

    if base_day is not None:
        return ParsedDateTime(dt=datetime.combine(base_day, parsed_time), has_time=has_time)

    # явная дата
    d_match = _RE_DDMMYYYY.search(text)
    if not d_match:
        return None

    d = int(d_match.group("d"))
    m = int(d_match.group("m"))
    y_raw = d_match.group("y")
    if y_raw:
        y = int(y_raw)
        if y < 100:
            y += 2000
    else:
        y = now.year

    try:
        return ParsedDateTime(dt=datetime(y, m, d, parsed_time.hour, parsed_time.minute), has_time=has_time)
    except ValueError:
        return None


def validate_not_past_datetime(raw: str, *, now: datetime | None = None) -> tuple[bool, datetime | None, str | None]:
    """Проверяет, что дата/время не в прошлом.

    Если время не указано, проверяем только дату (дата должна быть сегодня или позже).
    Если дата == сегодня и время не указано — просим указать время.
    """
    now = now or datetime.now()
    parsed = parse_requested_datetime(raw, now=now)
    if parsed is None:
        # Не можем проверить строго — пусть основной валидатор решит формат,
        # а здесь просто не блокируем.
        return True, None, None

    if not parsed.has_time:
        # Только дата
        if parsed.dt.date() < now.date():
            return False, None, "На прошедшую дату записаться нельзя. Укажите, пожалуйста, дату в будущем."
        if parsed.dt.date() == now.date():
            return False, None, "На сегодня нужно указать время. Например: «сегодня в 16:30»."
        return True, parsed.dt, None

    if parsed.dt < now:
        return False, None, "На прошедшее время записаться нельзя. Укажите, пожалуйста, дату/время в будущем."

    return True, parsed.dt, None
