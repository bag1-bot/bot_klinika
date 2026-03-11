from __future__ import annotations

from typing import Any

from loguru import logger

from bot.services.interfaces import ICrmClient


class CrmStubClient(ICrmClient):
    """
    Заглушка для интеграции с CRM.

    Сейчас только пишет события в лог.
    В будущем здесь можно реализовать вызовы внешнего API / webhook.
    """

    async def create_appointment(self, payload: dict[str, Any]) -> None:
        logger.info(f"[CRM STUB] create_appointment: {payload}")

    async def notify_admin(self, payload: dict[str, Any]) -> None:
        logger.info(f"[CRM STUB] notify_admin: {payload}")

