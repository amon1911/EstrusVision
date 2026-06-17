"""
config.py — โหลดค่า config ทั้งหมดจาก .env
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    # ─── Telegram ────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    MODE = os.getenv("MODE", "polling").lower()
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
    WEBHOOK_LISTEN = os.getenv("WEBHOOK_LISTEN", "0.0.0.0")

    # ─── Gemini ──────────────────────────────────────────────────────────────
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # ─── Database ────────────────────────────────────────────────────────────
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "swine_estrus")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # ─── General ─────────────────────────────────────────────────────────────
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    TEMP_IMAGE_DIR = os.getenv("TEMP_IMAGE_DIR", "./temp_images")
    SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "10"))

    # ─── Feature Flags ───────────────────────────────────────────────────────
    ENABLE_GILT_SELECTION: bool = (
        os.getenv("ENABLE_GILT_SELECTION", "true").lower() not in ("false", "0", "no")
    )

    # ─── Daily Image Limit ───────────────────────────────────────────────────
    # จำนวนรูปสูงสุดที่รับได้ต่อวัน (รวมทุกคนในกลุ่ม) รีเซ็ตทุก 23:59 PH time
    # 0 = ไม่จำกัด
    DAILY_IMAGE_LIMIT: int = int(os.getenv("DAILY_IMAGE_LIMIT", "0"))

    @classmethod
    def validate(cls) -> bool:
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        if not cls.DB_PASSWORD:
            missing.append("DB_PASSWORD")

        if missing:
            raise ValueError(
                f"❌ Missing required environment variables: {', '.join(missing)}\n"
                f"   กรุณาคัดลอก .env.example เป็น .env แล้วกรอกค่า"
            )

        os.makedirs(cls.TEMP_IMAGE_DIR, exist_ok=True)
        return True
