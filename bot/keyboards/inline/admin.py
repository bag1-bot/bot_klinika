# ruff: noqa: TD002
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AdminCallbacks:
    MENU = "admin_menu"
    DIALOGS = "admin_dialogs"
    DIALOG = "admin_dialog_"  # + dialog_id
    APPOINTMENTS = "admin_appointments"
    STATS = "admin_stats"
    BACK_MENU = "admin_back"


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📩 Диалоги (ожидают)", callback_data=AdminCallbacks.DIALOGS),
    )
    kb.row(
        InlineKeyboardButton(text="📋 Заявки", callback_data=AdminCallbacks.APPOINTMENTS),
    )
    kb.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data=AdminCallbacks.STATS),
    )
    return kb.as_markup()


def admin_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀ В меню админа", callback_data=AdminCallbacks.BACK_MENU))
    return kb.as_markup()


def dialog_list_keyboard(dialog_ids: list[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for did in dialog_ids[:15]:
        kb.row(
            InlineKeyboardButton(
                text=f"Диалог #{did}",
                callback_data=f"{AdminCallbacks.DIALOG}{did}",
            ),
        )
    kb.row(InlineKeyboardButton(text="◀ В меню админа", callback_data=AdminCallbacks.BACK_MENU))
    return kb.as_markup()
