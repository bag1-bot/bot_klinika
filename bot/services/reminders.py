# ruff: noqa: TD002
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from bot.domain.models import AppointmentStatus
from bot.services.appointments import AppointmentService

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

REMINDER_TEXT = (
    "Напоминаем о вашей записи в клинику.\n\n"
    "Пожалуйста, подтвердите визит или отмените запись."
)


async def send_reminders(
    bot: Bot,
    session: AsyncSession,
    *,
    hours_before: float = 24.0,
    window_hours: float = 2.0,
) -> int:
    """
    Находит записи, до которых осталось около hours_before часов,
    отправляет напоминание и помечает статус REMINDER_SENT.
    Возвращает количество отправленных напоминаний.
    """
    now = datetime.utcnow()
    after = now + timedelta(hours=hours_before - window_hours / 2)
    before = now + timedelta(hours=hours_before + window_hours / 2)
    app_svc = AppointmentService(session=session)
    appointments = await app_svc.get_upcoming_for_reminders(before=before, after=after)
    sent = 0
    for app in appointments:
        try:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            kb = InlineKeyboardBuilder()
            kb.row(
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"reminder_confirm_{app.id}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"reminder_cancel_{app.id}"),
            )
            await bot.send_message(
                app.user_id,
                REMINDER_TEXT,
                reply_markup=kb.as_markup(),
            )
            await app_svc.set_status(app.id, AppointmentStatus.REMINDER_SENT)
            sent += 1
        except Exception:
            continue
    return sent
