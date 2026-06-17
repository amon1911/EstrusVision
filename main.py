"""
main.py — Entry point ของ Swine Estrus Detection Bot
รันด้วย: python main.py
"""
import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.config import Config
from src.database import init_db
from src.handlers import (
    cancel_command,
    error_handler,
    help_command,
    photo_handler,
    pig_type_callback,
    start_command,
    stats_command,
    text_handler,
)
from src.handlers.telegram_handlers import periodic_cleanup
from src.utils import setup_logging

# Cleanup ทุกกี่วินาที (5 นาที)
CLEANUP_INTERVAL_SECONDS = 5 * 60


def build_application() -> Application:
    """สร้างและ register handlers ทั้งหมด"""
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # === Commands ===
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # === Photo ===
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    # === Callback Queries (ปุ่มเลือกประเภทหมู) ===
    app.add_handler(
        CallbackQueryHandler(pig_type_callback, pattern=r"^pig_type:(gilt|sow)$")
    )

    # === Fallback: ข้อความอื่นๆ ===
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )

    # === Global error handler ===
    app.add_error_handler(error_handler)

    # === Periodic cleanup (ทุก 5 นาที) ===
    app.job_queue.run_repeating(
        periodic_cleanup,
        interval=CLEANUP_INTERVAL_SECONDS,
        first=CLEANUP_INTERVAL_SECONDS,
        name="periodic_cleanup",
    )

    return app


def main():
    """Main entry point"""
    # 1. Setup
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("🐷 Swine Estrus Detection Bot Starting...")
    logger.info("=" * 60)

    # 2. Validate config
    Config.validate()
    logger.info(f"✅ Config loaded (mode={Config.MODE})")

    # 3. Init DB
    init_db()

    # 4. Build application
    app = build_application()
    logger.info("✅ Telegram handlers registered")
    logger.info(f"🧹 Cleanup job scheduled every {CLEANUP_INTERVAL_SECONDS}s")

    # 5. Run
    if Config.MODE == "webhook":
        logger.info(f"🌐 Running in WEBHOOK mode at {Config.WEBHOOK_URL}")
        app.run_webhook(
            listen=Config.WEBHOOK_LISTEN,
            port=Config.WEBHOOK_PORT,
            url_path=Config.TELEGRAM_BOT_TOKEN,
            webhook_url=f"{Config.WEBHOOK_URL}/{Config.TELEGRAM_BOT_TOKEN}",
        )
    else:
        logger.info("🔄 Running in POLLING mode")
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
