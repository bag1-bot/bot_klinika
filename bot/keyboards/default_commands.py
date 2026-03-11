from __future__ import annotations
from typing import TYPE_CHECKING

from aiogram.types import BotCommand, BotCommandScopeDefault

if TYPE_CHECKING:
    from aiogram import Bot

users_commands: dict[str, dict[str, str]] = {
    "ru": {
        "start": "Главное меню",
        "help": "Помощь по боту",
        "zapis": "Записаться на приём",
        "uslugi": "Услуги и цены",
        "vopros": "Задать вопрос",
        "consult": "Подбор услуги (ИИ)",
    },
}

admins_commands: dict[str, dict[str, str]] = {
    "ru": {
        "admin": "Админ-панель клиники",
        "stats": "Статистика бота",
        "ping": "Проверка работы бота",
    },
}


async def set_default_commands(bot: Bot) -> None:
    await remove_default_commands(bot)

    for language_code, commands in users_commands.items():
        await bot.set_my_commands(
            [BotCommand(command=command, description=description) for command, description in commands.items()],
            scope=BotCommandScopeDefault(),
            language_code=language_code,
        )

        """ Commands for admins
        for admin_id in await admin_ids():
            await bot.set_my_commands(
                [
                    BotCommand(command=command, description=description)
                    for command, description in admins_commands[language_code].items()
                ],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        """


async def remove_default_commands(bot: Bot) -> None:
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
