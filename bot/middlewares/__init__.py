from aiogram import Dispatcher


def register_middlewares(dp: Dispatcher) -> None:
    from .auth import AuthMiddleware
    from .database import DatabaseMiddleware
    from .throttling import ThrottlingMiddleware
    from .logging import LoggingMiddleware

    dp.message.outer_middleware(ThrottlingMiddleware())

    dp.update.outer_middleware(LoggingMiddleware())

    dp.update.outer_middleware(DatabaseMiddleware())

    dp.message.middleware(AuthMiddleware())