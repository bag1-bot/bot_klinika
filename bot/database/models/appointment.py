from __future__ import annotations

import datetime

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.models.base import Base, auto_int_pk, created_at
from bot.domain.models import AppointmentStatus


class AppointmentModel(Base):
    __tablename__ = "appointments"

    id: Mapped[auto_int_pk]
    user_id: Mapped[int] = mapped_column(index=True)
    dialog_id: Mapped[int | None] = mapped_column(
        ForeignKey("dialogs.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_name: Mapped[str]
    phone: Mapped[str]
    service: Mapped[str]
    doctor: Mapped[str | None]
    start_at: Mapped[datetime.datetime]
    source: Mapped[str] = mapped_column(String(length=32), default="telegram")
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"),
        default=AppointmentStatus.CREATED,
    )
    created_at: Mapped[created_at]
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

