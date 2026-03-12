"""AI-сервис: intent recognition, entity extraction, FAQ responder.

Все LLM-вызовы идут через OpenRouter (OpenAI SDK) с моделью
google/gemini-flash-lite-preview. Каждая функция — отдельный
сфокусированный запрос с минимальным количеством токенов.
"""
from __future__ import annotations

import json
from typing import Any

from cachetools import TTLCache
from loguru import logger
from openai import AsyncOpenAI

from bot.core.config import settings
from bot.services.interfaces import (
    ExtractedEntities,
    IEntityExtractor,
    IIntentRecognizer,
    IntentResult,
)

# ── Модель и клиент ──────────────────────────────────────────────────────────
MODEL = "google/gemini-3.1-flash-lite-preview"

# Rate-limit: не более 1 AI-вызова на пользователя за 2 секунды
_ai_rate_cache: TTLCache[int, bool] = TTLCache(maxsize=10_000, ttl=2)

VALID_INTENTS = frozenset(
    {"appointment_create", "pricing_question", "general_question", "admin_request", "unknown"}
)


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.OPENROUTE_API_KEY or "no-key",
        base_url="https://openrouter.ai/api/v1",
    )


def _strip_code_block(raw: str) -> str:
    """Remove markdown ```...``` wrapper if the model adds it."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        # drop first line (```json / ```) and last line (```)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def check_ai_rate_limit(user_id: int) -> bool:
    """Return True if user may proceed; False if rate-limited."""
    if user_id in _ai_rate_cache:
        logger.debug(f"[AI rate-limit] user_id={user_id} — заблокирован (TTL 2s)")
        return False
    _ai_rate_cache[user_id] = True
    logger.debug(f"[AI rate-limit] user_id={user_id} — разрешён")
    return True


# ── Intent Recognition ───────────────────────────────────────────────────────
class AIIntentRecognizer(IIntentRecognizer):
    """Classify the user's intent with a single compact LLM call."""

    _PROMPT = (
        "Classify the intent of a clinic patient's message into exactly one of: "
        "appointment_create, pricing_question, general_question, admin_request, unknown.\n"
        "appointment_create — wants to book an appointment\n"
        "pricing_question — asking about prices / costs\n"
        "general_question — general info (address, hours, doctors, etc.)\n"
        "admin_request — wants human operator / admin\n"
        "unknown — unclear\n\n"
        "Message: {text}\n\n"
        'Reply ONLY with JSON (no extra text): {{"intent": "...", "confidence": 0.0}}'
    )

    async def detect_intent(
        self, text: str, context: dict[str, Any] | None = None
    ) -> IntentResult:
        if not settings.OPENROUTE_API_KEY:
            logger.debug("[AI intent] OPENROUTE_API_KEY не задан — возвращаю unknown")
            return IntentResult(intent="unknown", confidence=0.0)

        logger.debug(f"[AI intent] → запрос | текст: {text[:120]!r}")
        try:
            resp = await _client().chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "user", "content": self._PROMPT.format(text=text[:500])}
                ],
                max_tokens=64,
                temperature=0,
            )
            raw = _strip_code_block(resp.choices[0].message.content or "")
            logger.debug(f"[AI intent] ← ответ модели: {raw!r}")
            data = json.loads(raw)
            intent = str(data.get("intent", "unknown"))
            if intent not in VALID_INTENTS:
                logger.debug(f"[AI intent] неизвестный intent {intent!r} → unknown")
                intent = "unknown"
            result = IntentResult(
                intent=intent,
                confidence=float(data.get("confidence", 0.5)),
            )
            logger.debug(f"[AI intent] результат: intent={result.intent!r}  confidence={result.confidence:.2f}")
            return result
        except Exception as exc:
            logger.warning(f"[AI intent] ошибка: {exc}")
            return IntentResult(intent="unknown", confidence=0.0)


# ── Entity Extraction ────────────────────────────────────────────────────────
class AIEntityExtractor(IEntityExtractor):
    """Extract structured entities (name, phone, service, date, time) via LLM."""

    _PROMPT = (
        "Extract entities from a clinic patient's message.\n"
        "Fields: name (full name), phone (phone number), "
        "service (medical service/specialty), date (visit date), time (visit time).\n"
        "Use null for fields that are not present.\n\n"
        "Message: {text}\n\n"
        'Reply ONLY with JSON: {{"name": null, "phone": null, "service": null, "date": null, "time": null}}'
    )

    async def extract(
        self, text: str, context: dict[str, Any] | None = None
    ) -> ExtractedEntities:
        if not settings.OPENROUTE_API_KEY:
            logger.debug("[AI entities] OPENROUTE_API_KEY не задан — пустые сущности")
            return ExtractedEntities()

        logger.debug(f"[AI entities] → запрос | текст: {text[:120]!r}")
        try:
            resp = await _client().chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "user", "content": self._PROMPT.format(text=text[:500])}
                ],
                max_tokens=128,
                temperature=0,
            )
            raw = _strip_code_block(resp.choices[0].message.content or "")
            logger.debug(f"[AI entities] ← ответ модели: {raw!r}")
            data = json.loads(raw)
            result = ExtractedEntities(
                name=data.get("name"),
                phone=data.get("phone"),
                service=data.get("service"),
                date=data.get("date"),
                time=data.get("time"),
            )
            logger.debug(
                f"[AI entities] результат: name={result.name!r}  phone={result.phone!r}"
                f"  service={result.service!r}  date={result.date!r}  time={result.time!r}"
            )
            return result
        except Exception as exc:
            logger.warning(f"[AI entities] ошибка: {exc}")
            return ExtractedEntities()


# ── History Summarization ────────────────────────────────────────────────────
_SUMMARIZE_PROMPT = (
    "Summarize the following conversation between a clinic bot and a patient "
    "in 2-3 sentences. Focus on what the patient wants, any shared information "
    "(name, phone, service, date), and the current status of their request.\n\n"
    "Conversation:\n{history}"
)


async def summarize_history(messages: list[dict[str, str]]) -> str:
    """Compress a list of chat messages into a short summary string."""
    if not settings.OPENROUTE_API_KEY or not messages:
        return ""
    formatted = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )
    try:
        resp = await _client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "user", "content": _SUMMARIZE_PROMPT.format(history=formatted[:3000])}
            ],
            max_tokens=150,
            temperature=0,
        )
        summary = (resp.choices[0].message.content or "").strip()
        logger.debug(f"[AI summary] сжато {len(messages)} сообщ. → {len(summary)} симв.: {summary[:80]!r}")
        return summary
    except Exception as exc:
        logger.warning(f"[AI summary] ошибка: {exc}")
        return ""


# ── FAQ / General Questions ──────────────────────────────────────────────────
# Информация о клинике — отредактируйте под реальные данные
_CLINIC_INFO = """
Клиника: МедЦентр «Здоровье»
Адрес: г. Москва, ул. Примерная, 10
Телефон: +7 (999) 123-45-67
Часы работы: пн–пт 8:00–20:00, сб 9:00–17:00, вс — выходной

Услуги и примерные цены:
- Терапевт: от 1 500 руб.
- Педиатр: от 1 500 руб.
- Кардиолог: от 2 000 руб.
- Невролог: от 2 000 руб.
- УЗИ (брюшная полость): от 1 800 руб.
- УЗИ сердца (ЭхоКГ): от 2 200 руб.
- ЭКГ: от 800 руб.
- Анализ крови (общий): от 500 руб.
- Стоматолог (консультация): от 1 000 руб.
- Гинеколог: от 2 000 руб.
- Хирург: от 1 800 руб.

Запись: через бота, по телефону или лично в регистратуре.
""".strip()

_FAQ_SYSTEM = (
    "Ты вежливый ИИ-ассистент медицинской клиники. "
    "Отвечай кратко, только на основе информации о клинике. "
    "Не ставь диагнозы, не давай медицинских советов — "
    "для этого приглашай клиента на очный приём. "
    "Если вопрос выходит за рамки — скажи, что уточнит администратор.\n\n"
    f"Информация о клинике:\n{_CLINIC_INFO}"
)


class AIFaqResponder:
    """Answer FAQ / pricing questions with conversation context."""

    async def answer(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        if not settings.OPENROUTE_API_KEY:
            logger.debug("[AI faq] OPENROUTE_API_KEY не задан — fallback-текст")
            return "Для уточнения информации обратитесь к администратору."

        history_len = len(history) if history else 0
        logger.debug(f"[AI faq] → запрос | вопрос: {question[:120]!r}  история: {history_len} сообщ.")
        messages: list[dict[str, str]] = [{"role": "system", "content": _FAQ_SYSTEM}]
        if history:
            messages.extend(history)  # размер контролируется на уровне вызывающего кода
        messages.append({"role": "user", "content": question[:1000]})
        try:
            resp = await _client().chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=300,
                temperature=0.3,
            )
            answer = (resp.choices[0].message.content or "").strip()
            logger.debug(f"[AI faq] ← ответ ({len(answer)} симв.): {answer[:120]!r}")
            return answer
        except Exception as exc:
            logger.warning(f"[AI faq] ошибка: {exc}")
            return "Произошла ошибка. Попробуйте позже или обратитесь к администратору."
