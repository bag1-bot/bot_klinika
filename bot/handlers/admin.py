# ruff: noqa: TD002, TD003
from __future__ import annotations

from aiogram import Bot, F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AppointmentModel, DialogModel
from bot.domain.models import DialogStatus, MessageAuthor
from bot.filters.admin import AdminFilter
from bot.keyboards.inline.admin import (
    AdminCallbacks,
    admin_back_keyboard,
    admin_menu_keyboard,
    dialog_list_keyboard,
)
from bot.services.appointments import AppointmentService
from bot.services.dialogs import DialogService

router = Router(name="admin")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


class AdminReplyStates(StatesGroup):
    ENTER_TEXT = State()


@router.message(F.text == "/admin")
async def admin_menu(message: types.Message, session: AsyncSession) -> None:
    await message.answer("Панель администратора:", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == AdminCallbacks.BACK_MENU)
async def admin_back(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Панель администратора:", reply_markup=admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == AdminCallbacks.DIALOGS)
async def admin_dialogs_list(callback: types.CallbackQuery, session: AsyncSession) -> None:
    dialog_svc = DialogService(session=session)
    dialogs = await dialog_svc.get_dialogs_by_status(DialogStatus.WAITING_ADMIN)
    ids = [d.id for d in dialogs]
    if not ids:
        await callback.message.edit_text(
            "Нет диалогов, ожидающих ответа.",
            reply_markup=admin_back_keyboard(),
        )
    else:
        await callback.message.edit_text(
            "Выберите диалог:",
            reply_markup=dialog_list_keyboard(ids),
        )
    await callback.answer()


@router.callback_query(F.data.startswith(AdminCallbacks.DIALOG))
async def admin_dialog_view(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    payload = callback.data.replace(AdminCallbacks.DIALOG, "", 1)
    if not payload.isdigit():
        await callback.answer("Ошибка")
        return
    dialog_id = int(payload)
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_dialog_by_id(dialog_id)
    if not dialog:
        await callback.answer("Диалог не найден")
        return
    messages = await dialog_svc.get_dialog_messages(dialog_id)
    lines = []
    for m in messages:
        author = "Пользователь" if m.author == MessageAuthor.USER else ("Бот" if m.author == MessageAuthor.BOT else "Админ")
        lines.append(f"{author}: {m.text[:200]}")
    text = f"Диалог #{dialog_id} (user_id={dialog.user_id})\n\n" + ("\n\n".join(lines) if lines else "Нет сообщений.")
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✏ Ответить",
            callback_data=f"admin_reply_{dialog_id}",
        ),
    )
    kb.row(InlineKeyboardButton(text="◀ К списку", callback_data=AdminCallbacks.DIALOGS))
    await callback.message.edit_text(text[:4000], reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reply_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    payload = callback.data.replace("admin_reply_", "", 1)
    if not payload.isdigit():
        await callback.answer("Ошибка")
        return
    await state.update_data(admin_reply_dialog_id=int(payload))
    await state.set_state(AdminReplyStates.ENTER_TEXT)
    await callback.message.edit_text("Введите текст ответа пользователю:")
    await callback.answer()


@router.message(AdminReplyStates.ENTER_TEXT, F.text)
async def admin_reply_send(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    data = await state.get_data()
    dialog_id = data.get("admin_reply_dialog_id")
    if not dialog_id:
        await message.answer("Сессия сброшена. Выберите диалог снова.")
        await state.clear()
        return
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_dialog_by_id(dialog_id)
    if not dialog:
        await message.answer("Диалог не найден.")
        await state.clear()
        return
    await dialog_svc.add_message(dialog_id, MessageAuthor.ADMIN, message.text or "")
    try:
        await bot.send_message(dialog.user_id, f"Ответ администратора:\n\n{message.text}")
    except Exception:
        await message.answer("Не удалось отправить сообщение пользователю (возможно, заблокировал бота).")
    else:
        await message.answer("Ответ отправлен.", reply_markup=admin_menu_keyboard())
    await state.clear()


@router.callback_query(F.data == AdminCallbacks.APPOINTMENTS)
async def admin_appointments_list(callback: types.CallbackQuery, session: AsyncSession) -> None:
    app_svc = AppointmentService(session=session)
    appointments = await app_svc.get_all_appointments(limit=20)
    if not appointments:
        await callback.message.edit_text("Заявок пока нет.", reply_markup=admin_back_keyboard())
    else:
        lines = []
        for a in appointments:
            lines.append(
                f"#{a.id} {a.client_name} | {a.phone} | {a.service} | {a.status.value} | {a.created_at}"
            )
        await callback.message.edit_text(
            "Заявки (последние 20):\n\n" + "\n".join(lines),
            reply_markup=admin_back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == AdminCallbacks.STATS)
async def admin_stats(callback: types.CallbackQuery, session: AsyncSession) -> None:
    from bot.database.models import MessageModel

    total_dialogs = await session.execute(select(func.count()).select_from(DialogModel))
    total_appointments = await session.execute(select(func.count()).select_from(AppointmentModel))
    waiting = await session.execute(
        select(func.count()).select_from(DialogModel).where(DialogModel.status == DialogStatus.WAITING_ADMIN),
    )
    d = total_dialogs.scalar() or 0
    a = total_appointments.scalar() or 0
    w = waiting.scalar() or 0
    text = (
        "Статистика:\n\n"
        f"Всего диалогов: {d}\n"
        f"Ожидают ответа админа: {w}\n"
        f"Всего заявок: {a}\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()