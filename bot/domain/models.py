from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DialogStatus(str, Enum):
    ACTIVE = "active"
    WAITING_ADMIN = "waiting_admin"
    CLOSED = "closed"


class MessageAuthor(str, Enum):
    USER = "user"
    BOT = "bot"
    ADMIN = "admin"


class AppointmentStatus(str, Enum):
    CREATED = "created"
    REMINDER_SENT = "reminder_sent"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    UNCONFIRMED = "unconfirmed"


@dataclass(slots=True)
class Dialog:
    id: int
    user_id: int
    status: DialogStatus
    channel: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Message:
    id: int
    dialog_id: int
    author: MessageAuthor
    text: str
    created_at: datetime


@dataclass(slots=True)
class Appointment:
    id: int
    user_id: int
    dialog_id: int | None
    client_name: str
    phone: str
    service: str
    doctor: str | None
    start_at: datetime
    source: str
    status: AppointmentStatus
    created_at: datetime
    updated_at: datetime

