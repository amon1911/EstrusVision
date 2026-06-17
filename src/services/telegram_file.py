"""
telegram_file.py — Helper สำหรับดึง URL ไฟล์รูปจาก Telegram

ใช้เป็น fallback เมื่อไฟล์ในเครื่อง (image_path) ถูกลบไปแล้ว
แต่ยังมี image_file_id เก็บอยู่ใน DB

⚠️ ข้อจำกัด: Telegram file URL จะหมดอายุภายใน ~1 ชั่วโมง
ดังนั้นไม่ควร cache URL นี้ไว้นาน — เรียกขอใหม่ทุกครั้งที่ request
"""
import logging

from telegram import Bot

from src.config import Config

logger = logging.getLogger(__name__)

_bot: Bot | None = None


def _get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    return _bot


async def get_telegram_file_url(file_id: str) -> str | None:
    """
    ขอ URL ชั่วคราวจาก Telegram สำหรับ file_id ที่ระบุ

    Returns:
        URL string หรือ None ถ้าดึงไม่สำเร็จ (เช่น file_id หมดอายุ/ไม่ถูกต้อง)
    """
    try:
        bot = _get_bot()
        tg_file = await bot.get_file(file_id)
        return tg_file.file_path  # python-telegram-bot คืน full URL ให้แล้ว
    except Exception as e:
        logger.warning(f"⚠️ Could not resolve telegram file_id={file_id}: {e}")
        return None
