"""Handler for free-text messages when no FSM state is active.

Classifies user intent via AI and routes to:
- Appointment booking flow
- FAQ / pricing answer
- Admin transfer
- Fallback (after 3 failed attempts → auto-transfer to admin)
"""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.domain.models import DialogStatus, MessageAuthor
from bot.keyboards.inline.start import start_keyboard
from bot.services.ai_service import (
    AIFaqResponder,
    AIIntentRecognizer,
    check_ai_rate_limit,
    summarize_history,
)
from bot.services.crm_stub import CrmStubClient
from bot.services.dialogs import DialogService
from bot.utils.render_md import send_md

router = Router(name="free_text")

_MAX_FALLBACKS = 3
_HISTORY_SUMMARIZE_THRESHOLD = 10  # сообщений до суммаризации
_HISTORY_RECENT_KEEP = 4           # свежих сообщений оставляем без изменений


@router.message(StateFilter(None), F.text)
async def free_text_handler(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Intercept messages when user is not in any FSM flow."""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    dialog_svc = DialogService(session=session)

    # Читаем FSM до получения диалога, чтобы обнаружить сброс контекста
    fsm_data = await state.get_data()
    prev_dialog_id: int | None = fsm_data.get("active_dialog_id")

    dialog = await dialog_svc.get_or_create_active_dialog(user_id=user_id)

    # Если диалог заменился (TTL истёк) — сбрасываем FSM-состояние тоже
    if prev_dialog_id is not None and prev_dialog_id != dialog.id:
        await state.clear()
        fsm_data = {}
        await message.answer(
            "Прошло некоторое время — начинаем заново. Чем могу помочь?",
            reply_markup=start_keyboard(),
        )

    await state.update_data(active_dialog_id=dialog.id)
    await dialog_svc.add_message(dialog.id, MessageAuthor.USER, text)

    # Dialog already waiting for human — just acknowledge
    if dialog.status == DialogStatus.WAITING_ADMIN:
        await message.answer("Ваше сообщение получено. Ожидайте ответа администратора.")
        return

    # Per-user AI rate limit (2 sec between calls)
    if not check_ai_rate_limit(user_id):
        await message.answer("Подождите немного перед следующим сообщением.")
        return

    recognizer = AIIntentRecognizer()
    intent_result = await recognizer.detect_intent(text)

    fallback_count = int(fsm_data.get("fallback_count", 0))

    # ── Route by intent ──────────────────────────────────────────────────────
    if intent_result.intent == "appointment_create" and intent_result.confidence >= 0.5:
        await state.update_data(fallback_count=0)
        from bot.handlers.appointment import AppointmentStates

        await state.set_state(AppointmentStates.ASK_NAME)
        bot_text = "Давайте запишем вас на приём.\n\nКак вас зовут?"
        await message.answer(bot_text)
        await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, bot_text)

    elif (
        intent_result.intent in ("pricing_question", "general_question")
        and intent_result.confidence >= 0.5
    ):
        await state.update_data(fallback_count=0)
        # Build history with optional summarization for long dialogs
        msgs = await dialog_svc.get_dialog_messages(dialog.id)
        all_history = [
            {
                "role": "user" if m.author == MessageAuthor.USER else "assistant",
                "content": m.text,
            }
            for m in msgs
            if m.author in (MessageAuthor.USER, MessageAuthor.BOT)
        ]
        if len(all_history) > _HISTORY_SUMMARIZE_THRESHOLD:
            old_msgs = all_history[:-_HISTORY_RECENT_KEEP]
            recent_msgs = all_history[-_HISTORY_RECENT_KEEP:]
            summary = await summarize_history(old_msgs)
            history: list[dict[str, str]] = []
            if summary:
                history.append(
                    {"role": "system", "content": f"Краткое содержание предыдущего диалога: {summary}"}
                )
            history.extend(recent_msgs)
        else:
            history = all_history
        answer = await AIFaqResponder().answer(text, history)
        await send_md(message, answer, reply_markup=start_keyboard())
        await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, answer)

    elif intent_result.intent == "admin_request" and intent_result.confidence >= 0.5:
        await state.update_data(fallback_count=0)
        await dialog_svc.change_status(dialog.id, DialogStatus.WAITING_ADMIN)
        await CrmStubClient().notify_admin(
            {
                "event": "dialog_transferred",
                "dialog_id": dialog.id,
                "user_id": user_id,
                "user_name": message.from_user.full_name or "",
            }
        )
        bot_text = "Ваш запрос передан администратору. Ожидайте ответа в этом чате."
        await message.answer(bot_text, reply_markup=start_keyboard())
        await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, bot_text)

    else:
        # Fallback — unclear intent
        new_count = fallback_count + 1
        await state.update_data(fallback_count=new_count)

        if new_count >= _MAX_FALLBACKS:
            await state.update_data(fallback_count=0)
            await dialog_svc.change_status(dialog.id, DialogStatus.WAITING_ADMIN)
            await CrmStubClient().notify_admin(
                {
                    "event": "dialog_transferred_auto_fallback",
                    "dialog_id": dialog.id,
                    "user_id": user_id,
                }
            )
            bot_text = (
                "Перевожу вас на администратора. "
                "Ожидайте — с вами свяжутся в ближайшее время."
            )
        elif new_count >= 2:
            bot_text = (
                "Извините, я не совсем понял запрос. "
                "Вы хотите записаться на приём, узнать цены или задать вопрос?"
            )
        else:
            bot_text = (
                "Извините, не совсем понял. "
                "Пожалуйста, выберите действие из меню или уточните запрос."
            )
        await message.answer(bot_text, reply_markup=start_keyboard())
        await dialog_svc.add_message(dialog.id, MessageAuthor.BOT, bot_text)
