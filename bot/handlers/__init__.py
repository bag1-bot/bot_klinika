from aiogram import Router


def get_handlers_router() -> Router:
    from . import admin, appointment, appointment_catalog, free_text, menu, start

    router = Router()

    router.include_router(start.router)
    router.include_router(appointment.router)
    router.include_router(appointment_catalog.router)
    router.include_router(menu.router)
    router.include_router(admin.router)
    # free_text must be last — catches all remaining messages (StateFilter(None))
    router.include_router(free_text.router)

    return router
