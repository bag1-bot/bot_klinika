from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class StartCallbacks:
    APPOINTMENT = "start_appointment"
    PRICING = "start_pricing"
    QUESTION = "start_question"
    ADMIN = "start_admin"
    AI_CONSULT = "start_ai_consult"


def start_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="🩺 Записаться на приём",
            callback_data=StartCallbacks.APPOINTMENT,
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="💰 Узнать стоимость услуг",
            callback_data=StartCallbacks.PRICING,
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="❓ Задать вопрос",
            callback_data=StartCallbacks.QUESTION,
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="👨‍💼 Связаться с администратором",
            callback_data=StartCallbacks.ADMIN,
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="🤖 Подбор услуги (заглушка)",
            callback_data=StartCallbacks.AI_CONSULT,
        ),
    )
    return kb.as_markup()
