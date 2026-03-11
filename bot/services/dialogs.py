from __future__ import annotations

from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DialogModel, MessageModel
from bot.domain.models import DialogStatus, MessageAuthor


class DialogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_active_dialog(self, user_id: int, channel: str = "telegram") -> DialogModel:
        query = (
            select(DialogModel)
            .where(
                DialogModel.user_id == user_id,
                DialogModel.status == DialogStatus.ACTIVE,
            )
            .limit(1)
        )
        result = await self._session.execute(query)
        dialog = result.scalar_one_or_none()

        if dialog:
            return dialog

        dialog = DialogModel(user_id=user_id, status=DialogStatus.ACTIVE, channel=channel)
        self._session.add(dialog)
        await self._session.commit()
        await self._session.refresh(dialog)
        return dialog

    async def change_status(self, dialog_id: int, status: DialogStatus) -> None:
        stmt = (
            update(DialogModel)
            .where(DialogModel.id == dialog_id)
            .values(status=status)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def add_message(self, dialog_id: int, author: MessageAuthor, text: str) -> MessageModel:
        message = MessageModel(dialog_id=dialog_id, author=author, text=text)
        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def get_dialog_messages(self, dialog_id: int) -> list[MessageModel]:
        query = select(MessageModel).where(MessageModel.dialog_id == dialog_id).order_by(MessageModel.created_at)
        result = await self._session.execute(query)
        messages: Iterable[MessageModel] = result.scalars()
        return list(messages)

    async def get_dialogs_by_status(self, status: DialogStatus) -> list[DialogModel]:
        query = select(DialogModel).where(DialogModel.status == status).order_by(DialogModel.updated_at.desc())
        result = await self._session.execute(query)
        dialogs: Iterable[DialogModel] = result.scalars()
        return list(dialogs)

    async def get_dialog_by_id(self, dialog_id: int) -> DialogModel | None:
        result = await self._session.execute(select(DialogModel).where(DialogModel.id == dialog_id).limit(1))
        return result.scalar_one_or_none()

