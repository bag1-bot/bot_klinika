from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AppointmentModel
from bot.domain.models import AppointmentStatus


class AppointmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_appointment(
        self,
        *,
        user_id: int,
        dialog_id: int | None,
        client_name: str,
        phone: str,
        service: str,
        doctor: str | None,
        start_at: datetime,
        source: str = "telegram",
    ) -> AppointmentModel:
        appointment = AppointmentModel(
            user_id=user_id,
            dialog_id=dialog_id,
            client_name=client_name,
            phone=phone,
            service=service,
            doctor=doctor,
            start_at=start_at,
            source=source,
        )
        self._session.add(appointment)
        await self._session.commit()
        await self._session.refresh(appointment)
        return appointment

    async def set_status(self, appointment_id: int, status: AppointmentStatus) -> None:
        stmt = (
            update(AppointmentModel)
            .where(AppointmentModel.id == appointment_id)
            .values(status=status)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_upcoming_for_reminders(self, before: datetime, after: datetime) -> list[AppointmentModel]:
        query = (
            select(AppointmentModel)
            .where(
                AppointmentModel.start_at >= after,
                AppointmentModel.start_at <= before,
                AppointmentModel.status == AppointmentStatus.CREATED,
            )
        )
        result = await self._session.execute(query)
        appointments: Iterable[AppointmentModel] = result.scalars()
        return list(appointments)

    async def get_all_appointments(self, limit: int = 50) -> list[AppointmentModel]:
        query = select(AppointmentModel).order_by(AppointmentModel.created_at.desc()).limit(limit)
        result = await self._session.execute(query)
        appointments: Iterable[AppointmentModel] = result.scalars()
        return list(appointments)

    async def get_appointment_by_id(self, appointment_id: int) -> AppointmentModel | None:
        result = await self._session.execute(
            select(AppointmentModel).where(AppointmentModel.id == appointment_id).limit(1),
        )
        return result.scalar_one_or_none()

