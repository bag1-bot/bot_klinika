"""Загрузчик документов для RAG.

Читает .docx и .doc файлы из директории RAG_DOCS_DIR,
очищает текст и разбивает на чанки с перекрытием.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from loguru import logger

# Подстроки в именах файлов, которые следует пропустить
# (не содержат полезной информации для клиентов / относятся к другим организациям)
_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "Договор оферты",         # договор такси-сервиса
    "ТРУДОВОЙ_ДОГОВОР",       # трудовой договор сторонней компании
    "ОСТРОВОК",               # сторонняя компания
    "Согласие_мед_работников",  # шаблон для сотрудников, не для клиентов
)

CHUNK_SIZE    = 900   # мягкий предел размера чанка (символов)
MAX_CHUNK     = 1800  # жёсткий предел — разбиваем даже длинные параграфы
CHUNK_OVERLAP = 120   # символов перекрытия между соседними чанками


def _should_skip(filename: str) -> bool:
    return any(pat in filename for pat in _EXCLUDE_PATTERNS)


# ── Читатели форматов ────────────────────────────────────────────────────────

def _read_docx(path: Path) -> str:
    import docx  # lazy import
    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _read_doc(path: Path) -> str:
    """Извлечь текст из .doc (старый Word) через системный catdoc."""
    try:
        res = subprocess.run(
            ["catdoc", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return res.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(f"[RAG loader] catdoc недоступен для {path.name}: {exc}")
        return ""


# ── Чанкинг ──────────────────────────────────────────────────────────────────

def _split_into_units(text: str) -> list[str]:
    """Разбить текст на единицы (абзацы / строки), подходящие для чанков."""
    # Нормализуем: убираем лишние пустые строки
    text = re.sub(r"\n{3,}", "\n\n", text.strip())

    # Сначала пробуем разбить по двойным переносам (реальные абзацы)
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    # Если остались слишком большие блоки — дробим по одиночным переносам
    units: list[str] = []
    for para in paras:
        if len(para) <= MAX_CHUNK:
            units.append(para)
        else:
            for line in para.splitlines():
                line = line.strip()
                if line:
                    units.append(line)
    return units


def _chunk_text(text: str, source: str) -> list[str]:
    """Разбить текст на чанки с учётом границ единиц текста."""
    units = _split_into_units(text)
    prefix = f"[{source}]"
    chunks: list[str] = []
    cur_parts: list[str] = [prefix]
    cur_len = len(prefix)

    for unit in units:
        unit_len = len(unit) + 2  # +2 за "\n\n"

        if cur_len + unit_len > CHUNK_SIZE and len(cur_parts) > 1:
            chunks.append("\n\n".join(cur_parts))
            # Перекрытие: оставляем последнюю единицу в новом чанке
            overlap = cur_parts[-1]
            cur_parts = [prefix, overlap]
            cur_len   = len(prefix) + len(overlap) + 2

        cur_parts.append(unit)
        cur_len += unit_len

    if len(cur_parts) > 1:
        chunks.append("\n\n".join(cur_parts))

    return chunks


# ── Публичный API ─────────────────────────────────────────────────────────────

def load_rag_chunks(docs_dir: str | Path) -> list[str]:
    """Загрузить документы из директории и вернуть список текстовых чанков."""
    root = Path(docs_dir)
    if not root.exists():
        logger.warning(f"[RAG loader] Директория не найдена: {root}")
        return []

    all_chunks: list[str] = []

    for path in sorted(root.iterdir()):
        if _should_skip(path.name):
            logger.debug(f"[RAG loader] Пропуск (исключение): {path.name}")
            continue

        ext = path.suffix.lower()
        try:
            if ext == ".docx":
                text = _read_docx(path)
            elif ext == ".doc":
                text = _read_doc(path)
            else:
                continue
        except Exception as exc:
            logger.warning(f"[RAG loader] Ошибка чтения {path.name}: {exc}")
            continue

        if not text.strip():
            logger.debug(f"[RAG loader] Пустой текст, пропуск: {path.name}")
            continue

        chunks = _chunk_text(text, path.stem)
        logger.info(f"[RAG loader] {path.name}: {len(text)} симв. → {len(chunks)} чанков")
        all_chunks.extend(chunks)

    logger.info(f"[RAG loader] Итого загружено чанков: {len(all_chunks)}")
    return all_chunks
