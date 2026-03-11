from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.users import is_admin


def _user_id_from_event(event: Message | CallbackQuery) -> int | None:
    if isinstance(event, Message):
        return event.from_user.id if event.from_user else None
    return event.from_user.id if event.from_user else None


class AdminFilter(BaseFilter):
    """Allows only administrators (whose database column is_admin=True)."""

    async def __call__(
        self,
        event: Message | CallbackQuery,
        session: AsyncSession,
    ) -> bool:
        user_id = _user_id_from_event(event)
        if user_id is None:
            return False
        return await is_admin(session=session, user_id=user_id)
