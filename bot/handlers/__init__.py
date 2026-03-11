from aiogram import Router


def get_handlers_router() -> Router:
    from . import admin, appointment, menu, start
    router = Router()

    router.include_router(start.router)
    router.include_router(appointment.router)
    router.include_router(menu.router)
    router.include_router(admin.router)

    return router
