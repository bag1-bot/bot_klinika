from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart

from bot.keyboards.inline.start import start_keyboard

router = Router(name="start")


def _main_menu_text(intro: str | None = None) -> str:
    base = (
        "Я бот клиники. Могу помочь с записью на приём, подсказать по услугам "
        "или переключить вас на администратора.\n\n"
        "Выберите действие:"
    )
    if intro:
        return f"{intro}\n\n{base}"
    return (
        "<b>Здравствуйте!</b>\n\n"
        f"{base}"
    )


@router.message(CommandStart())
async def start_handler(message: types.Message) -> None:
    """Приветствие и главное меню."""
    await message.answer(text=_main_menu_text(), reply_markup=start_keyboard())
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.message(Command("help"))
async def help_handler(message: types.Message) -> None:
    """Помощь по боту — главное меню."""
    text = (
        "<b>Помощь</b>\n\n"
        "Используйте кнопки ниже для записи на приём, просмотра услуг, "
        "вопросов или связи с администратором."
    )
    await message.answer(text=text, reply_markup=start_keyboard())


@router.message(Command("zapis"))
async def zapis_handler(message: types.Message) -> None:
    """Команда /zapis — запись на приём."""
    await message.answer(
        text=_main_menu_text("🩺 Нажмите кнопку «Записаться на приём» ниже."),
        reply_markup=start_keyboard(),
    )


@router.message(Command("uslugi"))
async def uslugi_handler(message: types.Message) -> None:
    """Команда /uslugi — услуги и цены."""
    await message.answer(
        text=_main_menu_text("💰 Нажмите «Узнать стоимость услуг» ниже."),
        reply_markup=start_keyboard(),
    )


@router.message(Command("vopros"))
async def vopros_handler(message: types.Message) -> None:
    """Команда /vopros — задать вопрос."""
    await message.answer(
        text=_main_menu_text("❓ Нажмите «Задать вопрос» ниже."),
        reply_markup=start_keyboard(),
    )


@router.message(Command("consult"))
async def consult_handler(message: types.Message) -> None:
    """Команда /consult — подбор услуги (ИИ)."""
    await message.answer(
        text=_main_menu_text("🤖 Нажмите «Подбор услуги» ниже."),
        reply_markup=start_keyboard(),
    )
