from __future__ import annotations

import datetime

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.models.base import Base, auto_int_pk, created_at
from bot.domain.models import MessageAuthor


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[auto_int_pk]
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id", ondelete="CASCADE"), index=True)
    author: Mapped[MessageAuthor] = mapped_column(Enum(MessageAuthor, name="message_author"))
    text: Mapped[str]
    created_at: Mapped[created_at]

