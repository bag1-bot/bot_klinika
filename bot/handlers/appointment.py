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
from bot.utils.validators import validate_date, validate_name, validate_phone, validate_service


router = Router(name="appointment")


class AppointmentStates(StatesGroup):
    ASK_NAME = State()
    ASK_PHONE = State()
    ASK_SERVICE = State()
    ASK_DATE = State()
    CONFIRM = State()


@router.callback_query(F.data == StartCallbacks.APPOINTMENT)
async def start_appointment(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Давайте запишем вас на приём.\n\nКак вас зовут?",
    )
    await state.set_state(AppointmentStates.ASK_NAME)


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
    await state.update_data(raw_date=cleaned)

    data = await state.get_data()
    text = (
        "Проверьте, пожалуйста, данные записи:\n\n"
        f"Имя: {data.get('client_name')}\n"
        f"Телефон: {data.get('phone')}\n"
        f"Услуга: {data.get('service')}\n"
        f"Желаемая дата/время: {data.get('raw_date')}\n\n"
        "Если всё верно — напишите «Да».\n"
        "Если нужно что-то изменить — напишите, что именно."
    )
    await message.answer(text)
    await state.set_state(AppointmentStates.CONFIRM)


@router.message(AppointmentStates.CONFIRM)
async def finalize_appointment(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    text = (message.text or "").strip().lower()
    if text not in {"да", "ок", "хорошо", "подтверждаю"}:
        await message.answer("Я сохранил ваши данные. Администратор уточнит детали и свяжется с вами.")
        await state.clear()
        return

    data = await state.get_data()

    dialog_service = DialogService(session=session)
    dialog = await dialog_service.get_or_create_active_dialog(user_id=message.from_user.id)

    appointment_service = AppointmentService(session=session)

    # Пока дата сохраняется как текущий момент — позже можно добавить полноценный парсинг
    start_at = datetime.utcnow()

    appointment = await appointment_service.create_appointment(
        user_id=message.from_user.id,
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
            "user_id": message.from_user.id,
            "client_name": appointment.client_name,
            "phone": appointment.phone,
            "service": appointment.service,
            "raw_date": data.get("raw_date"),
            "source": appointment.source,
        },
    )

    await message.answer(
        "Спасибо! Ваша заявка на запись отправлена администратору.\n"
        "Мы свяжемся с вами для подтверждения времени приёма.",
    )
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

