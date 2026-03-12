# ruff: noqa: TD002, TD003
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.domain.models import DialogStatus, MessageAuthor
from bot.keyboards.inline.start import StartCallbacks, start_keyboard
from bot.services.ai_service import AIFaqResponder, check_ai_rate_limit
from bot.services.crm_stub import CrmStubClient
from bot.services.dialogs import DialogService
from bot.utils.render_md import send_md

router = Router(name="menu")


@router.callback_query(F.data == StartCallbacks.PRICING)
async def pricing(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Узнать стоимость услуг — AI отвечает по прайсу клиники."""
    user_id = callback.from_user.id
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=user_id)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Узнать стоимость услуг")

    if check_ai_rate_limit(user_id):
        answer = await AIFaqResponder().answer(
            "Перечисли основные услуги клиники с примерными ценами кратко."
        )
    else:
        answer = (
            "Стоимость услуг уточните у администратора или нажмите кнопку "
            "«Связаться с администратором»."
        )

    # Убираем кнопки с исходного сообщения, затем отправляем отформатированный ответ
    await callback.message.edit_reply_markup(reply_markup=None)
    await send_md(callback.message, answer, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, answer)
    await callback.answer()


@router.callback_query(F.data == StartCallbacks.QUESTION)
async def question(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Задать вопрос — просим написать вопрос, free_text handler обработает его."""
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=callback.from_user.id)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Задать вопрос")

    text = (
        "Напишите ваш вопрос следующим сообщением, и я постараюсь помочь.\n\n"
        "Если потребуется, переключу вас на администратора."
    )
    await callback.message.edit_text(text, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, text)
    await callback.answer()


@router.callback_query(F.data == StartCallbacks.ADMIN)
async def request_admin(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Передача диалога администратору."""
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=callback.from_user.id)
    await dialog_svc.change_status(dialog.id, DialogStatus.WAITING_ADMIN)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Связаться с администратором")

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
        "Ваш запрос передан администратору. Ожидайте ответа в этом чате — "
        "с вами свяжутся в ближайшее время."
    )
    await callback.message.edit_text(text, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, text)
    await callback.answer()


@router.callback_query(F.data == StartCallbacks.AI_CONSULT)
async def ai_consult(callback: types.CallbackQuery, session: AsyncSession) -> None:
    """Подбор услуги — AI помогает по описанию симптомов/запроса."""
    dialog_svc = DialogService(session=session)
    dialog = await dialog_svc.get_or_create_active_dialog(user_id=callback.from_user.id)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, "Подбор услуги (консультация)")

    text = (
        "Опишите вашу ситуацию или симптомы следующим сообщением.\n\n"
        "Я подскажу, к какому специалисту лучше обратиться. "
        "Если потребуется — переключу на администратора."
    )
    await callback.message.edit_text(text, reply_markup=start_keyboard())
    await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, text)
    await callback.answer()
