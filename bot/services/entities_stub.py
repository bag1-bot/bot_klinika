from __future__ import annotations

import re
from typing import Any

from bot.services.interfaces import ExtractedEntities, IEntityExtractor


PHONE_REGEX = re.compile(r"(?:\+?\d[\d\-\s]{7,}\d)")


class SimpleEntityExtractor(IEntityExtractor):
    """
    Заглушка для извлечения сущностей.

    Сейчас извлекает только телефон по regex.
    Остальные поля будут дорабатываться по мере развития AI-модуля.
    """

    async def extract(self, text: str, context: dict[str, Any] | None = None) -> ExtractedEntities:
        entities = ExtractedEntities()

        if not text:
            return entities

        if match := PHONE_REGEX.search(text):
            entities.phone = match.group(0)

        # Остальные сущности (имя, услуга, врач, дата, время) будут добавлены позже.
        return entities

