from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AppointmentCatalogCallbacks:
    SECTION = "ap_cat_sec"          # ap_cat_sec|{section_idx}
    SERVICE = "ap_cat_srv"          # ap_cat_srv|{section_idx}|{service_idx}
    BACK_SECTIONS = "ap_cat_back_sections"
    COMPOSITION_YES = "ap_cat_comp_yes"
    COMPOSITION_NO = "ap_cat_comp_no"
    QA_YES = "ap_cat_qa_yes"
    QA_NO = "ap_cat_qa_no"
    QA_BACK = "ap_cat_qa_back"
    QA_NEW = "ap_cat_qa_new"
    BOOK = "ap_cat_book"
    MAIN_MENU = "ap_cat_main_menu"


def sections_keyboard(sections: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for idx, title in enumerate(sections):
        kb.row(
            InlineKeyboardButton(
                text=title,
                callback_data=f"{AppointmentCatalogCallbacks.SECTION}|{idx}",
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="🏠 В главное меню",
            callback_data=AppointmentCatalogCallbacks.MAIN_MENU,
        )
    )
    return kb.as_markup()


def services_keyboard(section_idx: int, services: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for sidx, title in enumerate(services):
        kb.row(
            InlineKeyboardButton(
                text=title,
                callback_data=f"{AppointmentCatalogCallbacks.SERVICE}|{section_idx}|{sidx}",
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ Назад к разделам",
            callback_data=AppointmentCatalogCallbacks.BACK_SECTIONS,
        )
    )
    return kb.as_markup()


def composition_question_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Да", callback_data=AppointmentCatalogCallbacks.COMPOSITION_YES),
        InlineKeyboardButton(text="Нет", callback_data=AppointmentCatalogCallbacks.COMPOSITION_NO),
    )
    return kb.as_markup()


def qa_question_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Да", callback_data=AppointmentCatalogCallbacks.QA_YES),
        InlineKeyboardButton(text="Нет", callback_data=AppointmentCatalogCallbacks.QA_NO),
    )
    return kb.as_markup()


def after_answer_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="↩️ Вернуться к услуге", callback_data=AppointmentCatalogCallbacks.QA_BACK),
        InlineKeyboardButton(text="❓ Задать новый вопрос", callback_data=AppointmentCatalogCallbacks.QA_NEW),
    )
    kb.row(
        InlineKeyboardButton(text="🏠 В главное меню", callback_data=AppointmentCatalogCallbacks.MAIN_MENU),
    )
    return kb.as_markup()


def summary_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🩺 Записаться на услугу", callback_data=AppointmentCatalogCallbacks.BOOK),
    )
    kb.row(
        InlineKeyboardButton(text="🏠 В главное меню", callback_data=AppointmentCatalogCallbacks.MAIN_MENU),
    )
    return kb.as_markup()

