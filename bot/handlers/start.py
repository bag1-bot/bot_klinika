from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart

from bot.keyboards.inline.start import start_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def start_handler(message: types.Message) -> None:
    """Приветствие и главное меню."""
    start = (
        "<b>Здравствуйте!</b>\n\n"
        "Я бот клиники. Могу помочь с записью на приём, подсказать по услугам "
        "или переключить вас на администратора.\n\n"
        "Выберите действие:"
    )
    await message.answer(text=start, reply_markup=start_keyboard())
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
