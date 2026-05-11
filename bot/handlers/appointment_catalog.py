from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

from bot.handlers.start import _main_menu_text
from bot.keyboards.inline.appointment_catalog import (
    AppointmentCatalogCallbacks as Cb,
    after_answer_keyboard,
    composition_question_keyboard,
    qa_question_keyboard,
    sections_keyboard,
    services_keyboard,
    summary_keyboard,
)
from bot.keyboards.inline.start import start_keyboard
from bot.services.ai_service import check_ai_rate_limit
from bot.services.price_catalog import CatalogServiceItem, get_service, list_sections, list_services


router = Router(name="appointment_catalog")


class AppointmentCatalogStates(StatesGroup):
    ASK_QUESTION = State()


def _summary_text(item: CatalogServiceItem) -> str:
    return (
        "<b>Вы выбрали:</b>\n\n"
        f"Раздел: <b>{item.section}</b>\n"
        f"Услуга: <b>{item.service}</b>\n"
        f"Цена: <b>{item.price}</b>\n"
    )


def _composition_text(item: CatalogServiceItem) -> str:
    if not item.consists_of:
        return "В прайсе нет расшифровки состава этой услуги."
    lines = "\n".join(f"— {x}" for x in item.consists_of)
    return f"<b>Состав услуги:</b>\n{lines}"


async def _show_sections(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Выберите раздел услуг:",
        reply_markup=sections_keyboard(list_sections()),
    )


async def _show_sections_from_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Выберите раздел услуг:",
        reply_markup=sections_keyboard(list_sections()),
    )
    await callback.answer()


async def _render_summary(
    callback: types.CallbackQuery,
    state: FSMContext,
    *,
    item: CatalogServiceItem,
    ask_questions: bool = True,
) -> None:
    await state.update_data(
        selected_section=item.section,
        selected_service=item.service,
        selected_price=item.price,
        selected_consists_of=item.consists_of,
        selected_nomenclature=item.nomenclature,
    )

    text = _summary_text(item)
    if ask_questions:
        text += "\n<b>Есть ли у вас вопросы по услуге?</b>"
        await callback.message.edit_text(text, reply_markup=qa_question_keyboard())
    else:
        await callback.message.edit_text(text, reply_markup=summary_keyboard())
    await callback.answer()


@router.callback_query(F.data == Cb.MAIN_MENU)
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(_main_menu_text(), reply_markup=start_keyboard())
    await callback.answer()


@router.callback_query(F.data == Cb.BACK_SECTIONS)
async def back_to_sections(callback: types.CallbackQuery, state: FSMContext) -> None:
    # Остаёмся в сценарии выбора услуг (не “главное меню”)
    await state.clear()
    await callback.message.edit_text(
        "Выберите раздел услуг:",
        reply_markup=sections_keyboard(list_sections()),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{Cb.SECTION}|"))
async def pick_section(callback: types.CallbackQuery, state: FSMContext) -> None:
    payload = callback.data.split("|", 1)[1]
    if not payload.isdigit():
        await callback.answer("Ошибка")
        return
    section_idx = int(payload)
    sections = list_sections()
    if section_idx < 0 or section_idx >= len(sections):
        await callback.answer("Раздел не найден")
        return
    section = sections[section_idx]
    services = list_services(section)
    await state.update_data(section_idx=section_idx)
    await callback.message.edit_text(
        f"<b>{section}</b>\n\nВыберите услугу:",
        reply_markup=services_keyboard(section_idx, [s.service for s in services]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{Cb.SERVICE}|"))
async def pick_service(callback: types.CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split("|")
    if len(parts) != 3:
        await callback.answer("Ошибка")
        return
    _, sec_str, srv_str = parts
    if not (sec_str.isdigit() and srv_str.isdigit()):
        await callback.answer("Ошибка")
        return
    section_idx = int(sec_str)
    service_idx = int(srv_str)
    sections = list_sections()
    if section_idx < 0 or section_idx >= len(sections):
        await callback.answer("Раздел не найден")
        return
    section = sections[section_idx]
    item = get_service(section, service_idx)
    if not item:
        await callback.answer("Услуга не найдена")
        return
    await state.update_data(section_idx=section_idx, service_idx=service_idx)

    text = _summary_text(item)
    text += "\n<b>Хотите узнать из чего состоит услуга?</b>"
    await callback.message.edit_text(text, reply_markup=composition_question_keyboard())
    await callback.answer()


@router.callback_query(F.data.in_({Cb.COMPOSITION_YES, Cb.COMPOSITION_NO}))
async def composition_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    section_idx = int(data.get("section_idx", -1))
    service_idx = int(data.get("service_idx", -1))
    sections = list_sections()
    if section_idx < 0 or section_idx >= len(sections):
        await callback.answer("Ошибка")
        return
    item = get_service(sections[section_idx], service_idx)
    if not item:
        await callback.answer("Ошибка")
        return

    if callback.data == Cb.COMPOSITION_YES:
        await state.update_data(
            selected_section=item.section,
            selected_service=item.service,
            selected_price=item.price,
            selected_consists_of=item.consists_of,
            selected_nomenclature=item.nomenclature,
        )
        text = _summary_text(item) + "\n" + _composition_text(item) + "\n\n<b>Есть ли у вас вопросы по услуге?</b>"
        await callback.message.edit_text(text, reply_markup=qa_question_keyboard())
        await callback.answer()
        return

    # NO → просто саммэри + вопрос про вопросы
    await _render_summary(callback, state, item=item, ask_questions=True)


@router.callback_query(F.data.in_({Cb.QA_YES, Cb.QA_NO}))
async def qa_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    section = str(data.get("selected_section") or "")
    service = str(data.get("selected_service") or "")
    price = str(data.get("selected_price") or "")
    if not section or not service:
        await callback.answer("Сначала выберите услугу")
        return

    if callback.data == Cb.QA_NO:
        text = (
            "<b>Итог:</b>\n\n"
            f"Раздел: <b>{section}</b>\n"
            f"Услуга: <b>{service}</b>\n"
            f"Цена: <b>{price}</b>\n"
        )
        await callback.message.edit_text(text, reply_markup=summary_keyboard())
        await callback.answer()
        return

    await state.set_state(AppointmentCatalogStates.ASK_QUESTION)
    await callback.message.edit_text(
        "Задайте ваш вопрос по выбранной услуге следующим сообщением.\n\n"
        f"Раздел: <b>{section}</b>\n"
        f"Услуга: <b>{service}</b>",
        reply_markup=after_answer_keyboard(),
    )
    await callback.answer()


def _build_price_only_context(data: dict) -> str:
    section = str(data.get("selected_section") or "")
    service = str(data.get("selected_service") or "")
    price = str(data.get("selected_price") or "")
    consists = data.get("selected_consists_of") or []
    nomen = data.get("selected_nomenclature") or []
    consists_lines = "\n".join(f"- {x}" for x in consists) if consists else "— (нет данных)"
    nomen_lines = "\n".join(f"- {x}" for x in nomen) if nomen else "— (нет данных)"
    return (
        "ДАННЫЕ ПРАЙСА (ЕДИНСТВЕННЫЙ ИСТОЧНИК):\n"
        f"Раздел: {section}\n"
        f"Услуга: {service}\n"
        f"Цена: {price}\n\n"
        "СОСТАВ УСЛУГИ:\n"
        f"{consists_lines}\n\n"
        "НОМЕНКЛАТУРА МЕД. УСЛУГ:\n"
        f"{nomen_lines}\n"
    )


async def _answer_price_only(question: str, data: dict) -> str:
    # Локальный “price-only” промпт: отвечать только по переданным данным, не добавлять фантазий
    from bot.services.ai_service import _get_sdk, _extract_text  # noqa: PLC0415

    from bot.services.ai_service import MODEL_URI  # noqa: PLC0415
    from bot.core.config import settings  # noqa: PLC0415

    if not settings.YANDEX_API_KEY:
        return "Сейчас я не могу ответить автоматически. Напишите, пожалуйста, администратору."

    ctx = _build_price_only_context(data)
    system = (
        "Ты консультант клиники.\n"
        "ВАЖНО: отвечай только на основе данных прайса, приведённых ниже. "
        "Если в данных нет ответа — скажи, что в прайсе нет информации.\n\n"
        f"{ctx}"
    )
    sdk = _get_sdk()
    model = sdk.models.completions(MODEL_URI).configure(temperature=0.1)
    result = await model.run(
        [
            {"role": "system", "text": system[:7000]},
            {"role": "user", "text": question[:1200]},
        ]
    )
    return _extract_text(result) or "В прайсе нет информации по этому вопросу."


@router.message(StateFilter(AppointmentCatalogStates.ASK_QUESTION), F.text)
async def handle_service_question(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not check_ai_rate_limit(user_id):
        await message.answer("Подождите немного перед следующим сообщением.")
        return

    data = await state.get_data()
    question = (message.text or "").strip()
    answer = await _answer_price_only(question, data)
    await message.answer(answer, reply_markup=after_answer_keyboard())


@router.callback_query(F.data.in_({Cb.QA_BACK, Cb.QA_NEW}))
async def qa_nav(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    section = str(data.get("selected_section") or "")
    service = str(data.get("selected_service") or "")
    price = str(data.get("selected_price") or "")

    if callback.data == Cb.QA_NEW:
        if not section or not service:
            await callback.answer("Сначала выберите услугу")
            return
        await state.set_state(AppointmentCatalogStates.ASK_QUESTION)
        await callback.message.edit_text(
            "Задайте новый вопрос следующим сообщением.\n\n"
            f"Раздел: <b>{section}</b>\n"
            f"Услуга: <b>{service}</b>",
            reply_markup=after_answer_keyboard(),
        )
        await callback.answer()
        return

    # BACK → сводка + кнопки записи
    await state.set_state(None)
    text = (
        "<b>Итог:</b>\n\n"
        f"Раздел: <b>{section}</b>\n"
        f"Услуга: <b>{service}</b>\n"
        f"Цена: <b>{price}</b>\n"
    )
    await callback.message.edit_text(text, reply_markup=summary_keyboard())
    await callback.answer()


@router.callback_query(F.data == Cb.BOOK)
async def start_booking_from_catalog(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    section = str(data.get("selected_section") or "")
    service = str(data.get("selected_service") or "")
    if not service:
        await callback.answer("Сначала выберите услугу")
        return

    # Запускаем существующую запись, но “услугу” уже знаем
    from bot.handlers.appointment import AppointmentStates  # noqa: PLC0415

    await state.update_data(service=service, service_section=section)
    await state.set_state(AppointmentStates.ASK_NAME)
    await callback.message.edit_text(
        f"Записываю вас на услугу:\n<b>{service}</b>\n\nКак вас зовут?"
    )
    await callback.answer()

