from __future__ import annotations

import datetime

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.models.base import Base, auto_int_pk, created_at
from bot.domain.models import DialogStatus


class DialogModel(Base):
    __tablename__ = "dialogs"

    id: Mapped[auto_int_pk]
    user_id: Mapped[int] = mapped_column(index=True)
    status: Mapped[DialogStatus] = mapped_column(
        Enum(DialogStatus, name="dialog_status"),
        default=DialogStatus.ACTIVE,
    )
    channel: Mapped[str] = mapped_column(String(length=32), default="telegram")
    created_at: Mapped[created_at]
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

