"""AI-сервис: intent recognition, entity extraction, FAQ responder + RAG.

Все LLM-вызовы идут через Yandex AI Studio SDK с моделью
deepseek-r1-distill-llama-70b. RAG реализован на основе
текстовых эмбеддингов Яндекса (text-search-query / text-search-doc).
Знания загружаются из реальных документов клиники (RAG_DOCS_DIR).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from cachetools import TTLCache
from loguru import logger
from yandex_ai_studio_sdk import AsyncAIStudio

from bot.core.config import settings
from bot.services.interfaces import (
    ExtractedEntities,
    IEntityExtractor,
    IIntentRecognizer,
    IntentResult,
)

# ── Параметры модели ─────────────────────────────────────────────────────────
MODEL_URI        = "yandexgpt"
EMBED_DOC_MODEL  = "doc"    # text-search-doc — для индексации документов
EMBED_QRY_MODEL  = "query"  # text-search-query — для запросов пользователя
RAG_TOP_K        = 4        # количество чанков, возвращаемых при поиске

# Rate-limit: не более 1 AI-вызова на пользователя за 2 секунды
_ai_rate_cache: TTLCache[int, bool] = TTLCache(maxsize=10_000, ttl=2)

VALID_INTENTS = frozenset(
    {"appointment_create", "pricing_question", "general_question", "admin_request", "unknown"}
)

# ── Singleton SDK ────────────────────────────────────────────────────────────
_sdk_instance: AsyncAIStudio | None = None


def _get_sdk() -> AsyncAIStudio:
    """Вернуть (или создать) singleton-клиент Yandex AI Studio."""
    global _sdk_instance
    if _sdk_instance is None:
        kwargs: dict[str, Any] = {}
        if settings.YANDEX_FOLDER_ID:
            kwargs["folder_id"] = settings.YANDEX_FOLDER_ID
        if settings.YANDEX_API_KEY:
            kwargs["auth"] = settings.YANDEX_API_KEY
        _sdk_instance = AsyncAIStudio(**kwargs)
    return _sdk_instance


# ── Вспомогательные функции ──────────────────────────────────────────────────

def _strip_code_block(raw: str) -> str:
    """Убирает обёртку ```...``` если модель добавила её."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def _strip_think_tags(text: str) -> str:
    """Убирает блоки <think>...</think> (рассуждения DeepSeek)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_text(result: Any) -> str:
    """Извлекает текст из результата SDK-вызова completions."""
    try:
        text = result[0].text or ""
    except (IndexError, AttributeError):
        text = str(result)
    return _strip_think_tags(text)


def _to_yandex_msg(msg: dict[str, str]) -> dict[str, str]:
    """Конвертирует OpenAI-формат {'role','content'} в Yandex-формат {'role','text'}."""
    if "text" in msg:
        return msg
    return {"role": msg["role"], "text": msg.get("content", "")}


def check_ai_rate_limit(user_id: int) -> bool:
    """Вернуть True если пользователь может сделать запрос; False если rate-limited."""
    if user_id in _ai_rate_cache:
        logger.debug(f"[AI rate-limit] user_id={user_id} — заблокирован (TTL 2s)")
        return False
    _ai_rate_cache[user_id] = True
    logger.debug(f"[AI rate-limit] user_id={user_id} — разрешён")
    return True


# ── RAG: векторное хранилище ─────────────────────────────────────────────────

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 1e-10 else 0.0


class _VectorStore:
    """In-memory RAG-хранилище на основе текстовых эмбеддингов Яндекса.

    Документы загружаются лениво при первом обращении к retrieve().
    """

    def __init__(self, docs_dir: str | Path | None = None) -> None:
        self._docs_dir  = docs_dir
        self._chunks: list[str] = []
        self._embeddings: list[np.ndarray] | None = None
        self._lock = asyncio.Lock()
        self._docs_loaded = False

    def _load_docs(self) -> None:
        """Синхронно загрузить документы из папки (вызывается один раз)."""
        if self._docs_loaded:
            return
        self._docs_loaded = True
        if self._docs_dir and Path(self._docs_dir).exists():
            from bot.services.rag_loader import load_rag_chunks
            self._chunks = load_rag_chunks(self._docs_dir)
        else:
            logger.warning(
                f"[RAG] RAG_DOCS_DIR не найден или не задан: {self._docs_dir!r}"
            )

    async def _build(self, sdk: AsyncAIStudio) -> None:
        """Вычислить и закэшировать эмбеддинги (один раз при старте)."""
        async with self._lock:
            if self._embeddings is not None:
                return
            self._load_docs()
            if not self._chunks:
                logger.warning("[RAG] Нет чанков — индекс пуст, RAG отключён")
                self._embeddings = []
                return
            doc_model = sdk.models.text_embeddings(EMBED_DOC_MODEL)
            batch_size = 8  # лимит Яндекса — 10 req/s, берём с запасом
            results = []
            for i in range(0, len(self._chunks), batch_size):
                batch = self._chunks[i:i + batch_size]
                batch_results = await asyncio.gather(
                    *(doc_model.run(chunk[:2000]) for chunk in batch)
                )
                results.extend(batch_results)
                if i + batch_size < len(self._chunks):
                    await asyncio.sleep(1.1)
            self._embeddings = [np.array(r.embedding) for r in results]
            logger.info(f"[RAG] Индекс построен: {len(self._chunks)} чанков")

    async def retrieve(self, query: str, sdk: AsyncAIStudio, top_k: int = RAG_TOP_K) -> str:
        """Найти top_k наиболее релевантных чанков для запроса."""
        await self._build(sdk)
        if not self._embeddings:
            return ""

        qry_model = sdk.models.text_embeddings(EMBED_QRY_MODEL)
        q_result = await qry_model.run(query[:500])
        q_vec = np.array(q_result.embedding)

        scores: list[tuple[float, int]] = [
            (_cosine_sim(q_vec, doc_vec), idx)
            for idx, doc_vec in enumerate(self._embeddings)
        ]
        scores.sort(reverse=True)

        top_indices = sorted(i for _, i in scores[:top_k])
        return "\n\n---\n\n".join(self._chunks[i] for i in top_indices)


# Инициализируем хранилище — чанки будут загружены при первом обращении
_store = _VectorStore(docs_dir=settings.RAG_DOCS_DIR if hasattr(settings, "RAG_DOCS_DIR") else None)


def init_rag_store(docs_dir: str | Path) -> None:
    """Переинициализировать RAG-хранилище с указанной директорией.

    Вызывается из main.py при старте бота:
        from bot.services.ai_service import init_rag_store
        init_rag_store(settings.RAG_DOCS_DIR)
    """
    global _store
    _store = _VectorStore(docs_dir=docs_dir)
    logger.info(f"[RAG] Хранилище будет загружено из: {docs_dir}")


# ── Intent Recognition ───────────────────────────────────────────────────────
class AIIntentRecognizer(IIntentRecognizer):
    """Определяет намерение пользователя одним вызовом LLM."""

    _SYSTEM = (
        "Classify the intent of a reproductive medicine clinic patient's message "
        "into exactly one of: "
        "appointment_create, pricing_question, general_question, admin_request, unknown.\n"
        "appointment_create — wants to book an appointment / consultation\n"
        "pricing_question — asking about prices, costs, programs\n"
        "general_question — general info (address, hours, doctors, services, procedures, etc.)\n"
        "admin_request — wants human operator / admin / coordinator\n"
        "unknown — unclear\n\n"
        "Reply ONLY with valid JSON, no extra text, no markdown: "
        '{"intent": "...", "confidence": 0.0}'
    )

    async def detect_intent(
        self, text: str, context: dict[str, Any] | None = None
    ) -> IntentResult:
        if not settings.YANDEX_API_KEY:
            logger.debug("[AI intent] YANDEX_API_KEY не задан — возвращаю unknown")
            return IntentResult(intent="unknown", confidence=0.0)

        logger.debug(f"[AI intent] → {text[:120]!r}")
        try:
            sdk = _get_sdk()
            model = sdk.models.completions(MODEL_URI).configure(
                temperature=0,

            )
            result = await model.run([
                {"role": "system", "text": self._SYSTEM},
                {"role": "user",   "text": f"Message: {text[:500]}"},
            ])
            raw = _strip_code_block(_extract_text(result))
            logger.debug(f"[AI intent] ← {raw!r}")
            data = json.loads(raw)
            intent = str(data.get("intent", "unknown"))
            if intent not in VALID_INTENTS:
                intent = "unknown"
            res = IntentResult(
                intent=intent,
                confidence=float(data.get("confidence", 0.5)),
            )
            logger.debug(f"[AI intent] {res.intent!r}  conf={res.confidence:.2f}")
            return res
        except Exception as exc:
            logger.warning(f"[AI intent] ошибка: {exc}")
            return IntentResult(intent="unknown", confidence=0.0)


# ── Entity Extraction ────────────────────────────────────────────────────────
class AIEntityExtractor(IEntityExtractor):
    """Извлекает структурированные сущности из сообщения пользователя."""

    _SYSTEM = (
        "Extract entities from a clinic patient's message.\n"
        "Fields: name (full name), phone (phone number), "
        "service (medical service or program name), date (visit date), time (visit time).\n"
        "Use null for fields that are not present.\n\n"
        "Reply ONLY with valid JSON, no extra text, no markdown: "
        '{"name": null, "phone": null, "service": null, "date": null, "time": null}'
    )

    async def extract(
        self, text: str, context: dict[str, Any] | None = None
    ) -> ExtractedEntities:
        if not settings.YANDEX_API_KEY:
            return ExtractedEntities()

        logger.debug(f"[AI entities] → {text[:120]!r}")
        try:
            sdk = _get_sdk()
            model = sdk.models.completions(MODEL_URI).configure(
                temperature=0,

            )
            result = await model.run([
                {"role": "system", "text": self._SYSTEM},
                {"role": "user",   "text": f"Message: {text[:500]}"},
            ])
            raw = _strip_code_block(_extract_text(result))
            logger.debug(f"[AI entities] ← {raw!r}")
            data = json.loads(raw)
            res = ExtractedEntities(
                name=data.get("name"),
                phone=data.get("phone"),
                service=data.get("service"),
                date=data.get("date"),
                time=data.get("time"),
            )
            logger.debug(
                f"[AI entities] name={res.name!r}  phone={res.phone!r}"
                f"  service={res.service!r}  date={res.date!r}  time={res.time!r}"
            )
            return res
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
    """Сжимает список сообщений чата в короткую сводку."""
    if not settings.YANDEX_API_KEY or not messages:
        return ""
    formatted = "\n".join(
        f"{m['role'].upper()}: {m.get('content') or m.get('text', '')}"
        for m in messages
    )
    try:
        sdk = _get_sdk()
        model = sdk.models.completions(MODEL_URI).configure(
            temperature=0,
            reasoning_mode="medium",
        )
        result = await model.run([
            {"role": "user", "text": _SUMMARIZE_PROMPT.format(history=formatted[:3000])}
        ])
        summary = _extract_text(result)
        logger.debug(
            f"[AI summary] сжато {len(messages)} сообщ. → {len(summary)} симв.: {summary[:80]!r}"
        )
        return summary
    except Exception as exc:
        logger.warning(f"[AI summary] ошибка: {exc}")
        return ""


# ── FAQ / General Questions (RAG) ────────────────────────────────────────────
_FAQ_SYSTEM_TMPL = (
    "Ты консультант Репробанка (АО «Репролаб») — репродуктивного банка в Москве.\n"
    "Специализация клиники: криоконсервация яйцеклеток и спермы, донорство репродуктивного материала,\n"
    "программа «Сохрани для себя, помогая другим».\n"
    "Контакты: тел. +7 (499) 112-14-34, 8-800-775-61-49 (бесплатно), email info@reprobank.ru.\n"
    "Режим работы: ежедневно 9:00–21:00, приём строго по предварительной записи.\n"
    "Адрес: г. Москва, ул. Ивана Бабушкина, 9 (вход — большое белое крыльцо), м. Академическая.\n\n"
    "Правила:\n"
    "— Отвечай развёрнуто и по делу, опираясь на предоставленную информацию из базы знаний.\n"
    "— Ты консультант: объясняй процедуры, программы, условия, требования и что нужно сделать.\n"
    "— Давай конкретные советы и рекомендации на основе информации из базы знаний.\n"
    "— НИКОГДА не говори «я не могу дать медицинских рекомендаций» и не перенаправляй к врачу без причины.\n"
    "— Если в базе знаний нет ответа на вопрос — НЕ придумывай и не догадывайся. Честно скажи, что не знаешь, и предложи обратиться в клинику: позвонить +7 (499) 112-14-34 или написать на info@reprobank.ru.\n\n"
    "Информация из базы знаний клиники:\n"
    "─────────────────────────────────────\n"
    "{context}\n"
    "─────────────────────────────────────"
)


class AIFaqResponder:
    """Отвечает на вопросы FAQ / о ценах / об услугах с помощью RAG + Yandex LLM."""

    async def answer(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        if not settings.YANDEX_API_KEY:
            return "Для уточнения информации обратитесь к администратору или позвоните: +7 (499) 112-14-34."

        history_len = len(history) if history else 0
        logger.debug(f"[AI faq] → {question[:120]!r}  история: {history_len} сообщ.")
        try:
            sdk = _get_sdk()

            # RAG: найти релевантные чанки
            context = await _store.retrieve(question, sdk)
            if not context:
                context = "Информация не найдена. Рекомендуй обратиться по телефону."
            logger.debug(f"[RAG] контекст {len(context)} симв.")

            system_text = _FAQ_SYSTEM_TMPL.format(context=context[:3500])
            yandex_messages: list[dict[str, str]] = [
                {"role": "system", "text": system_text}
            ]
            if history:
                yandex_messages.extend(_to_yandex_msg(m) for m in history)
            yandex_messages.append({"role": "user", "text": question[:1000]})

            model = sdk.models.completions(MODEL_URI).configure(temperature=0.3)
            result = await model.run(yandex_messages)
            answer_text = _extract_text(result)
            logger.debug(f"[AI faq] ← {answer_text[:120]!r}")
            return (
                answer_text
                or "Произошла ошибка. Попробуйте позже или позвоните нам: +7 (499) 112-14-34."
            )
        except Exception as exc:
            logger.warning(f"[AI faq] ошибка: {exc}")
            return "Произошла ошибка. Попробуйте позже или позвоните нам: +7 (499) 112-14-34."
