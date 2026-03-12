"""Утилита для отправки Markdown-ответов от ИИ через telegramify_markdown.

telegramify() конвертирует Markdown → plain text + MessageEntity,
автоматически разбивает длинные сообщения и умеет отправлять
код-блоки как файлы, а mermaid-диаграммы — как изображения.
"""
from __future__ import annotations

from io import BytesIO

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, MessageEntity
from loguru import logger
from telegramify_markdown import telegramify
from telegramify_markdown.content import ContentType


def _to_aiogram_entities(raw_entities: list) -> list[MessageEntity]:
    """Convert telegramify MessageEntity → aiogram MessageEntity."""
    result = []
    for e in raw_entities:
        d = e.to_dict()
        try:
            result.append(MessageEntity(**d))
        except Exception as exc:
            logger.debug(f"[render_md] entity skip: {d}  ({exc})")
    return result


async def send_md(
    message: types.Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправить Markdown-текст с правильным рендерингом.

    - Разбивает длинные сообщения на части.
    - Форматирует bold, italic, code, списки и т.д. через MessageEntity.
    - Код-блоки отправляет как файлы, mermaid-диаграммы — как фото.
    - reply_markup прикрепляется к последнему сообщению.
    """
    items = await telegramify(text, max_message_length=4090)

    for idx, item in enumerate(items):
        is_last = idx == len(items) - 1
        kb = reply_markup if is_last else None

        if item.content_type == ContentType.TEXT:
            entities = _to_aiogram_entities(item.entities)
            await message.answer(
                item.text,
                entities=entities if entities else None,
                reply_markup=kb,
            )

        elif item.content_type == ContentType.PHOTO:
            caption_entities = _to_aiogram_entities(item.caption_entities or [])
            await message.answer_photo(
                types.BufferedInputFile(
                    file=item.file_data,
                    filename=item.file_name or "image.png",
                ),
                caption=item.caption_text or None,
                caption_entities=caption_entities or None,
                reply_markup=kb,
            )

        elif item.content_type == ContentType.FILE:
            caption_entities = _to_aiogram_entities(item.caption_entities or [])
            await message.answer_document(
                types.BufferedInputFile(
                    file=item.file_data,
                    filename=item.file_name or "code.txt",
                ),
                caption=item.caption_text or None,
                caption_entities=caption_entities or None,
                reply_markup=kb,
            )
