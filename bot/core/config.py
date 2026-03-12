from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from sqlalchemy.engine.url import URL

DIR = Path(__file__).absolute().parent.parent.parent
BOT_DIR = Path(__file__).absolute().parent.parent

class EnvBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class BotSettings(EnvBaseSettings):
    BOT_TOKEN: str
    SUPPORT_URL: str | None = None
    RATE_LIMIT: int | float = 0.5


class DBSettings(EnvBaseSettings):
    DB_PATH: str = "database.db"

    @property
    def database_url(self) -> str:
        # Для асинхронного доступа с aiosqlite
        db_path = Path(self.DB_PATH).absolute()
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def database_url_sync(self) -> str:
        # Для синхронного доступа с sqlite3
        db_path = Path(self.DB_PATH).absolute()
        return f"sqlite:///{db_path}"


class Settings(BotSettings, DBSettings):
    DEBUG: bool = False

    SENTRY_DSN: str | None = None

    OPENROUTE_API_KEY: str | None = None


settings = Settings()
