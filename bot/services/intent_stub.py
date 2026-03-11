from __future__ import annotations

from typing import Any

from bot.services.interfaces import IIntentRecognizer, IntentResult


class KeywordIntentRecognizer(IIntentRecognizer):
    """
    Простая заглушка для определения намерений по ключевым словам.

    В будущем можно заменить на реальный NLP-модуль,
    реализующий тот же интерфейс IIntentRecognizer.
    """

    async def detect_intent(self, text: str, context: dict[str, Any] | None = None) -> IntentResult:
        normalized = (text or "").lower()

        # Минимальный набор намерений по ТЗ
        mapping: dict[str, str] = {
            "запис": "appointment_create",
            "прием": "appointment_create",
            "стоим": "pricing_question",
            "цена": "pricing_question",
            "сколько": "pricing_question",
            "админ": "admin_request",
            "оператор": "admin_request",
            "отмен": "appointment_cancel",
            "перенес": "appointment_change",
            "спасибо": "thanks",
            "благодар": "thanks",
            "привет": "greeting",
            "здравств": "greeting",
        }

        for key, intent in mapping.items():
            if key in normalized:
                # Заглушка: фиксированная высокая уверенность
                return IntentResult(intent=intent, confidence=0.9)

        # Непонятный запрос
        return IntentResult(intent="unknown", confidence=0.5)

