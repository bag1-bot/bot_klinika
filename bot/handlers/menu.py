# ruff: noqa: TD002, TD003
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.domain.models import DialogStatus, MessageAuthor
from bot.keyboards.inline.start import StartCallbacks, start_keyboard
from bot.services.crm_stub import CrmStubClient
from bot.services.dialogs import DialogService

router = Router(name="menu")


@router.callback_query(F.data == StartCallbacks.PRICING)
async def pricing(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Узнать стоимость услуг — данные позже из БД."""
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=callback.from_user.id)
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, "Узнать стоимость услуг")
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Узнать стоимость услуг")

    text = (
        "Стоимость услуг вы можете уточнить у администратора или в разделе «Услуги» на нашем сайте. "
        "Список услуг и цен мы заполним позже."
    )
    await callback.message.edit_text(text, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, text)


@router.callback_query(F.data == StartCallbacks.QUESTION)
async def question(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Задать вопрос — предлагаем написать текст или связаться с админом."""
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=callback.from_user.id)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Задать вопрос")
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, "Задать вопрос")

    text = (
        "Напишите ваш вопрос в следующем сообщении — мы передадим его администратору и ответим в ближайшее время. "
        "Либо нажмите «Связаться с администратором» для быстрой связи."
    )
    await callback.message.edit_text(text, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, text)


@router.callback_query(F.data == StartCallbacks.ADMIN)
async def request_admin(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Передача диалога администратору."""
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=callback.from_user.id)
    await dialog_svc.change_status(dialog.id, DialogStatus.WAITING_ADMIN)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Связаться с администратором")
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, "Диалог передан администратору.")

    crm = CrmStubClient()
    await crm.notify_admin(
        {
            "event": "dialog_transferred",
            "dialog_id": dialog.id,
            "user_id": callback.from_user.id,
            "user_name": callback.from_user.full_name or "",
        },
    )

    text = (
        "Ваш запрос передан администратору. Ожидайте ответа в этом чате — с вами свяжутся в ближайшее время."
    )
    await callback.message.edit_text(text, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, text)


@router.callback_query(F.data == StartCallbacks.AI_CONSULT)
async def ai_consult_stub(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Подбор услуги (консультация) — заглушка."""
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=callback.from_user.id)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Подбор услуги (консультация)")
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, "Подбор услуги (заглушка)")

    text = (
        "Функция подбора услуги по описанию будет доступна позже. "
        "Пока вы можете записаться на приём или связаться с администратором."
    )
    await callback.message.edit_text(text, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, text)
