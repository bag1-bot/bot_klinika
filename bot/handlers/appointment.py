from __future__ import annotations

from datetime import datetime

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger

from bot.domain.models import AppointmentStatus, MessageAuthor
from bot.keyboards.inline.start import StartCallbacks
from bot.services.ai_service import AIEntityExtractor
from bot.services.appointments import AppointmentService
from bot.services.crm_stub import CrmStubClient
from bot.services.dialogs import DialogService
from bot.utils.validators import (
    validate_date,
    validate_name,
    validate_not_past_datetime,
    validate_phone,
    validate_service,
)
from bot.keyboards.inline.appointment_catalog import sections_keyboard
from bot.services.price_catalog import list_sections


router = Router(name="appointment")


class AppointmentStates(StatesGroup):
    ASK_NAME = State()
    ASK_PHONE = State()
    ASK_SERVICE = State()
    ASK_DATE = State()
    CONFIRM = State()
    EDIT_CHOICE = State()
    EDIT_NAME = State()
    EDIT_PHONE = State()
    EDIT_DATE = State()


class AppointmentConfirmCallbacks:
    SUBMIT = "appt_confirm_submit"
    EDIT = "appt_confirm_edit"
    EDIT_NAME = "appt_edit_name"
    EDIT_PHONE = "appt_edit_phone"
    EDIT_DATE = "appt_edit_date"
    BACK_TO_SUMMARY = "appt_edit_back"


def _confirm_keyboard() -> types.InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🩺 Записаться", callback_data=AppointmentConfirmCallbacks.SUBMIT),
        InlineKeyboardButton(text="✏️ Изменить данные", callback_data=AppointmentConfirmCallbacks.EDIT),
    )
    return kb.as_markup()


def _edit_keyboard() -> types.InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Имя", callback_data=AppointmentConfirmCallbacks.EDIT_NAME))
    kb.row(InlineKeyboardButton(text="Телефон", callback_data=AppointmentConfirmCallbacks.EDIT_PHONE))
    kb.row(InlineKeyboardButton(text="Дата/время", callback_data=AppointmentConfirmCallbacks.EDIT_DATE))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=AppointmentConfirmCallbacks.BACK_TO_SUMMARY))
    return kb.as_markup()


def _summary_text(data: dict) -> str:
    return (
        "<b>Проверьте, пожалуйста, данные записи:</b>\n\n"
        f"Имя: <b>{data.get('client_name')}</b>\n"
        f"Телефон: <b>{data.get('phone')}</b>\n"
        f"Услуга: <b>{data.get('service')}</b>\n"
        f"Желаемая дата/время: <b>{data.get('raw_date')}</b>\n"
    )


@router.callback_query(F.data == StartCallbacks.APPOINTMENT)
async def start_appointment(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Выберите раздел услуг:",
        reply_markup=sections_keyboard(list_sections()),
    )
    await callback.answer()


@router.message(AppointmentStates.ASK_NAME)
async def ask_phone(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    ok, cleaned, error = validate_name(raw)
    logger.debug(f"[validate name] raw={raw!r}  ok={ok}  cleaned={cleaned!r}  error={error!r}")
    if not ok:
        await message.answer(f"{error}\n\nКак вас зовут?")
        return  # остаёмся в ASK_NAME
    await state.update_data(client_name=cleaned)
    await message.answer("Укажите, пожалуйста, ваш номер телефона.\n\nНапример: +7 999 123-45-67 или 89991234567.")
    await state.set_state(AppointmentStates.ASK_PHONE)


@router.message(AppointmentStates.ASK_PHONE)
async def ask_service(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    # Сначала пробуем AI-извлечение — вдруг пользователь написал фразой
    extractor = AIEntityExtractor()
    entities = await extractor.extract(raw)
    candidate = entities.phone or raw

    ok, cleaned, error = validate_phone(candidate)
    logger.debug(f"[validate phone] raw={raw!r}  ai_extracted={entities.phone!r}  ok={ok}  cleaned={cleaned!r}  error={error!r}")
    if not ok:
        await message.answer(f"{error}")
        return  # остаёмся в ASK_PHONE
    await state.update_data(phone=cleaned)
    data = await state.get_data()
    # Если услуга уже выбрана через каталог — пропускаем вопрос про услугу
    if data.get("service"):
        await message.answer("На какую дату и время вы хотите записаться?\n\nНапример: «25.03 в 15:00» или «завтра в 10:00».")
        await state.set_state(AppointmentStates.ASK_DATE)
        return

    await message.answer("Какую услугу вы рассматриваете?\n\nНапример: «Терапевт», «УЗИ», «Стоматолог».")
    await state.set_state(AppointmentStates.ASK_SERVICE)


@router.message(AppointmentStates.ASK_SERVICE)
async def ask_date(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    ok, cleaned, error = validate_service(raw)
    logger.debug(f"[validate service] raw={raw!r}  ok={ok}  cleaned={cleaned!r}  error={error!r}")
    if not ok:
        await message.answer(f"{error}")
        return  # остаёмся в ASK_SERVICE
    await state.update_data(service=cleaned)
    await message.answer("На какую дату и время вы хотите записаться?\n\nНапример: «25.03 в 15:00» или «завтра в 10:00».")
    await state.set_state(AppointmentStates.ASK_DATE)


@router.message(AppointmentStates.ASK_DATE)
async def confirm(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    ok, cleaned, error = validate_date(raw)
    logger.debug(f"[validate date] raw={raw!r}  ok={ok}  cleaned={cleaned!r}  error={error!r}")
    if not ok:
        await message.answer(f"{error}")
        return  # остаёмся в ASK_DATE

    ok2, parsed_dt, err2 = validate_not_past_datetime(cleaned)
    if not ok2:
        await message.answer(err2 or "Укажите, пожалуйста, дату/время в будущем.")
        return  # остаёмся в ASK_DATE
    await state.update_data(raw_date=cleaned)
    if parsed_dt is not None:
        await state.update_data(requested_dt=parsed_dt.isoformat(timespec="minutes"))

    data = await state.get_data()
    await message.answer(_summary_text(data), reply_markup=_confirm_keyboard())
    await state.set_state(AppointmentStates.CONFIRM)


@router.callback_query(F.data == AppointmentConfirmCallbacks.EDIT)
async def edit_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AppointmentStates.EDIT_CHOICE)
    await callback.message.edit_text("Что вы хотите изменить?", reply_markup=_edit_keyboard())
    await callback.answer()


@router.callback_query(F.data == AppointmentConfirmCallbacks.BACK_TO_SUMMARY)
async def back_to_summary(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AppointmentStates.CONFIRM)
    await callback.message.edit_text(_summary_text(data), reply_markup=_confirm_keyboard())
    await callback.answer()


@router.callback_query(F.data == AppointmentConfirmCallbacks.EDIT_NAME)
async def edit_name(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AppointmentStates.EDIT_NAME)
    await callback.message.edit_text("Введите имя заново:")
    await callback.answer()


@router.callback_query(F.data == AppointmentConfirmCallbacks.EDIT_PHONE)
async def edit_phone(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AppointmentStates.EDIT_PHONE)
    await callback.message.edit_text("Введите номер телефона заново:\n\nНапример: +7 999 123-45-67")
    await callback.answer()


@router.callback_query(F.data == AppointmentConfirmCallbacks.EDIT_DATE)
async def edit_date(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AppointmentStates.EDIT_DATE)
    await callback.message.edit_text("Введите желаемую дату и время заново:\n\nНапример: «25.03 в 15:00» или «завтра в 10:00».")
    await callback.answer()


@router.message(AppointmentStates.EDIT_NAME)
async def apply_edit_name(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    ok, cleaned, error = validate_name(raw)
    if not ok:
        await message.answer(f"{error}\n\nВведите имя заново:")
        return
    await state.update_data(client_name=cleaned)
    data = await state.get_data()
    await message.answer(_summary_text(data), reply_markup=_confirm_keyboard())
    await state.set_state(AppointmentStates.CONFIRM)


@router.message(AppointmentStates.EDIT_PHONE)
async def apply_edit_phone(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    extractor = AIEntityExtractor()
    entities = await extractor.extract(raw)
    candidate = entities.phone or raw
    ok, cleaned, error = validate_phone(candidate)
    if not ok:
        await message.answer(f"{error}")
        return
    await state.update_data(phone=cleaned)
    data = await state.get_data()
    await message.answer(_summary_text(data), reply_markup=_confirm_keyboard())
    await state.set_state(AppointmentStates.CONFIRM)


@router.message(AppointmentStates.EDIT_DATE)
async def apply_edit_date(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    ok, cleaned, error = validate_date(raw)
    if not ok:
        await message.answer(f"{error}")
        return
    ok2, parsed_dt, err2 = validate_not_past_datetime(cleaned)
    if not ok2:
        await message.answer(err2 or "Укажите, пожалуйста, дату/время в будущем.")
        return
    await state.update_data(raw_date=cleaned)
    if parsed_dt is not None:
        await state.update_data(requested_dt=parsed_dt.isoformat(timespec="minutes"))
    data = await state.get_data()
    await message.answer(_summary_text(data), reply_markup=_confirm_keyboard())
    await state.set_state(AppointmentStates.CONFIRM)


@router.callback_query(F.data == AppointmentConfirmCallbacks.SUBMIT)
async def finalize_appointment(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:

    data = await state.get_data()

    dialog_service = DialogService(session=session)
    dialog = await dialog_service.get_or_create_active_dialog(user_id=callback.from_user.id)

    appointment_service = AppointmentService(session=session)

    # Пока дата сохраняется как текущий момент — позже можно добавить полноценный парсинг
    start_at = datetime.utcnow()

    appointment = await appointment_service.create_appointment(
        user_id=callback.from_user.id,
        dialog_id=dialog.id,
        client_name=str(data.get("client_name")),
        phone=str(data.get("phone")),
        service=str(data.get("service")),
        doctor=None,
        start_at=start_at,
    )

    await appointment_service.set_status(appointment.id, AppointmentStatus.CREATED)

    await dialog_service.add_message(
        dialog_id=dialog.id,
        author=MessageAuthor.USER,
        text=f"Запись подтверждена пользователем. ID заявки: {appointment.id}",
    )

    crm = CrmStubClient()
    await crm.create_appointment(
        {
            "appointment_id": appointment.id,
            "user_id": callback.from_user.id,
            "client_name": appointment.client_name,
            "phone": appointment.phone,
            "service": appointment.service,
            "raw_date": data.get("raw_date"),
            "source": appointment.source,
        },
    )

    await callback.message.edit_text(
        "Спасибо! Ваша заявка на запись отправлена администратору.\n"
        "Мы свяжемся с вами для подтверждения времени приёма.",
    )
    await callback.answer()
    await state.clear()


@router.callback_query(F.data.startswith("reminder_confirm_"))
async def reminder_confirm(callback: types.CallbackQuery, session: AsyncSession) -> None:
    payload = callback.data.replace("reminder_confirm_", "", 1)
    if not payload.isdigit():
        await callback.answer("Ошибка")
        return
    aid = int(payload)
    app_svc = AppointmentService(session=session)
    appointment = await app_svc.get_appointment_by_id(aid)
    if not appointment or appointment.user_id != callback.from_user.id:
        await callback.answer("Запись не найдена.")
        return
    await app_svc.set_status(aid, AppointmentStatus.CONFIRMED)
    await callback.message.edit_text("Запись подтверждена. Ждём вас!")
    await callback.answer()


@router.callback_query(F.data.startswith("reminder_cancel_"))
async def reminder_cancel(callback: types.CallbackQuery, session: AsyncSession) -> None:
    payload = callback.data.replace("reminder_cancel_", "", 1)
    if not payload.isdigit():
        await callback.answer("Ошибка")
        return
    aid = int(payload)
    app_svc = AppointmentService(session=session)
    appointment = await app_svc.get_appointment_by_id(aid)
    if not appointment or appointment.user_id != callback.from_user.id:
        await callback.answer("Запись не найдена.")
        return
    await app_svc.set_status(aid, AppointmentStatus.CANCELLED)
    crm = CrmStubClient()
    await crm.notify_admin({"event": "appointment_cancelled", "appointment_id": aid})
    await callback.message.edit_text("Запись отменена. Вы можете записаться на другое время через меню.")
    await callback.answer()

