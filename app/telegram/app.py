from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from app.telegram.handlers import callback, start


def build_telegram_application(settings, provider, prediction_service) -> Application:
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data.update(
        {"settings": settings, "provider": provider, "prediction_service": prediction_service}
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback))
    return application
