"""
telegram_handlers.py — Telegram Bot Handlers v6

🆕 changes:
1. Rate limiting — ป้องกัน user spam
2. Daily image limit — จำกัดรูปรวมทั้งกลุ่มต่อวัน (DAILY_IMAGE_LIMIT)
3. เมื่อเกิน limit → เก็บรูปใน storage/YYYY-MM-DD/overlimit/ ไม่วิเคราะห์
4. image_path ใน DB ชี้ไปที่ storage/ ถาวร
5. รองรับ ALLOWED_USER_IDS + ALLOWED_GROUP_IDS
6. Raw storage — copy รูป + JSON ไปเก็บใน storage/YYYY-MM-DD/ ถาวร
7. รีเซ็ต daily count ทุก 23:59 PH time
"""
import glob
import json
import logging
import os
import shutil
import uuid
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from src.config import Config
from src.database import save_detection
from src.database.models import PH_TZ
from src.services import generate_alert, get_vlm_service
from src.services.business_logic import append_record_id
from src.utils import get_session_manager
from src.utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================
CALLBACK_GILT = "pig_type:gilt"
CALLBACK_SOW = "pig_type:sow"
DEFAULT_PIG_TYPE_WHEN_DISABLED = "gilt"
TG_MAX_CHARS = 4096
STORAGE_DIR = "./storage"

# =============================================================================
# Daily limit counter (in-memory, รีเซ็ตตามวัน PH)
# =============================================================================
_daily_count: int = 0
_daily_date: str = ""  # YYYY-MM-DD ของ PH


def _get_today_ph() -> str:
    return datetime.now(PH_TZ).strftime("%Y-%m-%d")


def _check_daily_limit() -> tuple[bool, int]:
    """
    ตรวจว่ายังไม่เกิน limit ไหม
    Return: (allowed, current_count)
    - allowed=True  → ยังส่งได้
    - allowed=False → เกิน limit แล้ว
    """
    global _daily_count, _daily_date

    today = _get_today_ph()
    if _daily_date != today:
        # วันใหม่ — รีเซ็ต
        _daily_count = 0
        _daily_date = today
        logger.info(f"🔄 Daily limit reset for {today}")

    limit = Config.DAILY_IMAGE_LIMIT
    if limit <= 0:
        # ไม่จำกัด
        return True, _daily_count

    if _daily_count >= limit:
        return False, _daily_count

    return True, _daily_count


def _increment_daily_count() -> int:
    global _daily_count
    _daily_count += 1
    return _daily_count


# =============================================================================
# Whitelist
# =============================================================================
_ALLOWED_IDS: set[int] = set()
_raw_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
if _raw_ids:
    for _id in _raw_ids.split(","):
        _id = _id.strip()
        if _id.lstrip("-").isdigit():
            _ALLOWED_IDS.add(int(_id))
    logger.info(f"🔒 User whitelist: {len(_ALLOWED_IDS)} user(s)")

_ALLOWED_GROUP_IDS: set[int] = set()
_raw_groups = os.getenv("ALLOWED_GROUP_IDS", "").strip()
if _raw_groups:
    for _gid in _raw_groups.split(","):
        _gid = _gid.strip()
        if _gid.lstrip("-").isdigit():
            _ALLOWED_GROUP_IDS.add(int(_gid))
    logger.info(f"🔒 Group whitelist: {len(_ALLOWED_GROUP_IDS)} group(s)")


# =============================================================================
# Helpers
# =============================================================================
def _is_allowed(user_id: int, chat_id: int | None = None) -> bool:
    no_user_list = not _ALLOWED_IDS
    no_group_list = not _ALLOWED_GROUP_IDS
    if no_user_list and no_group_list:
        return True
    if user_id in _ALLOWED_IDS:
        return True
    if chat_id and chat_id in _ALLOWED_GROUP_IDS:
        return True
    return False


def _truncate(text: str, limit: int = TG_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n\n⚠️ [ข้อความถูกตัดเพราะยาวเกินขีดจำกัด / Message truncated]"
    return text[: limit - len(suffix)] + suffix


async def _check_rate_limit(update: Update) -> bool:
    user_id = update.effective_user.id
    limiter = get_rate_limiter()
    result = limiter.check(user_id)
    if not result.allowed:
        logger.warning(
            f"🚦 Rate limit blocked user={user_id} "
            f"retry_after={result.retry_after_seconds}s"
        )
        await update.message.reply_text(
            f"⏳ ส่งบ่อยเกินไป กรุณารออีก {result.retry_after_seconds} วินาที\n"
            f"⏳ Too many requests. Please wait {result.retry_after_seconds} seconds.\n"
            f"(จำกัด {limiter.max_requests} ครั้ง / {limiter.window_seconds} วินาที | "
            f"Limit: {limiter.max_requests} requests / {limiter.window_seconds}s)"
        )
        return False
    return True


def _save_overlimit_image(image_path: str, user_id: int) -> None:
    """เก็บรูปที่เกิน limit ไว้ใน overlimit/ โดยไม่สร้าง JSON"""
    try:
        date_str = _get_today_ph()
        overlimit_dir = os.path.join(STORAGE_DIR, date_str, "overlimit")
        os.makedirs(overlimit_dir, exist_ok=True)

        timestamp = datetime.now(PH_TZ).strftime("%H%M%S")
        img_ext = os.path.splitext(image_path)[1] or ".jpg"
        dest = os.path.join(overlimit_dir, f"{timestamp}_{user_id}{img_ext}")
        shutil.copy2(image_path, dest)
        logger.info(f"📦 Overlimit image saved: {dest}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to save overlimit image: {e}")


def _copy_to_storage(
    image_path: str,
    detection_id: int | None,
    vlm_result: dict,
    alert_status: str,
    alert_message: str,
    pig_type: str,
    user_id: int,
    username: str | None,
    sow_id: str | None,
) -> str | None:
    try:
        date_str = _get_today_ph()
        day_dir = os.path.join(STORAGE_DIR, date_str)
        os.makedirs(day_dir, exist_ok=True)

        timestamp = datetime.now(PH_TZ).strftime("%H%M%S")
        base_name = f"{timestamp}_id{detection_id or 'err'}_{user_id}"

        img_ext = os.path.splitext(image_path)[1] or ".jpg"
        dest_image = os.path.join(day_dir, f"{base_name}{img_ext}")
        shutil.copy2(image_path, dest_image)

        payload = {
            "detection_id": detection_id,
            "timestamp_ph": datetime.now(PH_TZ).isoformat(),
            "user_id": user_id,
            "username": username,
            "pig_type": pig_type,
            "sow_id": sow_id,
            "result_status": alert_status,
            "estrus_classification": vlm_result.get("estrus_classification"),
            "confidence": vlm_result.get("confidence"),
            "observed_signs": vlm_result.get("observed_signs", {}),
            "reasoning_summary": vlm_result.get("reasoning_summary"),
            "recommended_action": vlm_result.get("recommended_action"),
            "image_quality": vlm_result.get("image_quality"),
            "visibility_issues": vlm_result.get("visibility_issues", []),
            "alert_message": alert_message,
            "image_file": os.path.basename(dest_image),
            "vlm_raw": vlm_result,
        }
        dest_json = os.path.join(day_dir, f"{base_name}.json")
        with open(dest_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info(f"📦 Stored: {dest_image} + {dest_json}")
        return dest_image

    except Exception as e:
        logger.warning(f"⚠️ Failed to save storage: {e}")
        return None


def _cleanup_stale_temp_images() -> int:
    threshold = Config.SESSION_TIMEOUT_MINUTES * 60 * 2
    now = datetime.now().timestamp()
    removed = 0
    pattern = os.path.join(Config.TEMP_IMAGE_DIR, "*.jpg")
    for filepath in glob.glob(pattern):
        try:
            if now - os.path.getmtime(filepath) > threshold:
                os.remove(filepath)
                removed += 1
        except Exception as e:
            logger.warning(f"Could not remove stale temp image {filepath}: {e}")
    if removed:
        logger.info(f"🧹 Removed {removed} stale temp image(s)")
    return removed


# =============================================================================
# Periodic cleanup job
# =============================================================================
async def periodic_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    session_mgr = get_session_manager()
    session_mgr.cleanup_expired()

    limiter = get_rate_limiter()
    cleaned = limiter.cleanup_inactive()
    if cleaned:
        logger.info(f"🧹 Rate limiter: removed {cleaned} inactive user(s)")

    _cleanup_stale_temp_images()


# =============================================================================
# Command handlers
# =============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not _is_allowed(user.id, chat_id):
        await update.message.reply_text(
            "⛔ ขออภัย คุณไม่มีสิทธิ์ใช้งานระบบนี้\n"
            "⛔ Sorry, you are not authorized to use this system."
        )
        return
    msg = (
        f"สวัสดีครับ คุณ {user.first_name} 👋\n"
        "🐷 ระบบตรวจจับการเป็นสัดของสุกร\n\n"
        "📸 วิธีใช้งาน:\n"
        "  1. ถ่ายรูปก้นของหมูให้ชัดเจน\n"
        "  2. ส่งรูปเข้ามาที่บอทนี้\n"
    )
    if Config.ENABLE_GILT_SELECTION:
        msg += (
            "  3. เลือกประเภทหมู (หมูสาว / หมูนาง)\n"
            "  4. รอผลภายในไม่กี่วินาที\n\n"
        )
    else:
        msg += "  3. รอผลภายในไม่กี่วินาที\n\n"
    msg += "💡 ถ่ายในที่แสงเพียงพอ ระยะใกล้พอเห็นรายละเอียด\n\n"
    msg += "---\n"
    msg += (
        f"Hello, {user.first_name} 👋\n"
        "🐷 Swine Estrus Detection System\n\n"
        "📸 How to use:\n"
        "  1. Take a clear photo of the pig's rear\n"
        "  2. Send the photo to this bot\n"
    )
    if Config.ENABLE_GILT_SELECTION:
        msg += (
            "  3. Select pig type (Gilt / Sow)\n"
            "  4. Wait a few seconds for results\n\n"
        )
    else:
        msg += "  3. Wait a few seconds for results\n\n"
    msg += "💡 Good lighting and close-up shots give better results"
    await update.message.reply_text(msg)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not _is_allowed(user.id, chat_id):
        await update.message.reply_text(
            "⛔ ขออภัย คุณไม่มีสิทธิ์ใช้งานระบบนี้\n"
            "⛔ Sorry, you are not authorized to use this system."
        )
        return
    limit = Config.DAILY_IMAGE_LIMIT
    limit_text = f"{limit} รูป/วัน" if limit > 0 else "ไม่จำกัด"
    limit_text_en = f"{limit} photos/day" if limit > 0 else "Unlimited"
    msg = (
        "📖 คู่มือการใช้งาน\n\n"
        "• ส่งรูป → บอทวิเคราะห์ → ส่งผลกลับ\n\n"
        f"• จำนวนรูปต่อวัน: {limit_text}\n\n"
        "คำสั่ง:\n"
        "/start  - เริ่มต้น\n"
        "/help   - คู่มือ\n"
        "/cancel - ยกเลิก session\n"
        "/stats  - สถิติการใช้งาน\n\n"
        "ผลที่จะได้:\n"
        "🚨 Standing Estrus - เป็นสัด พร้อมผสม\n"
        "⚠️ Pre-Estrus      - ก่อนเป็นสัด\n"
        "ℹ️ Post-Estrus     - หลังเป็นสัด\n"
        "✅ Non-Estrus      - ยังไม่เป็นสัด\n"
        "🛑 False Estrus    - สงสัยเป็นสัดเทียม\n\n"
        "---\n"
        "📖 User Guide\n\n"
        "• Send photo → Bot analyzes → Results returned\n\n"
        f"• Daily limit: {limit_text_en}\n\n"
        "Commands:\n"
        "/start  - Start\n"
        "/help   - Help\n"
        "/cancel - Cancel session\n"
        "/stats  - Usage statistics\n\n"
        "Results:\n"
        "🚨 Standing Estrus - In heat, ready to breed\n"
        "⚠️ Pre-Estrus      - Approaching heat\n"
        "ℹ️ Post-Estrus     - Heat has passed\n"
        "✅ Non-Estrus      - Not in heat\n"
        "🛑 False Estrus    - Suspected false heat"
    )
    await update.message.reply_text(msg)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _is_allowed(user_id, chat_id):
        await update.message.reply_text(
            "⛔ ขออภัย คุณไม่มีสิทธิ์ใช้งานระบบนี้\n"
            "⛔ Sorry, you are not authorized to use this system."
        )
        return
    session_mgr = get_session_manager()
    if session_mgr.get(user_id):
        session_mgr.clear(user_id)
        await update.message.reply_text(
            "✅ ยกเลิกแล้ว ส่งรูปใหม่ได้เลยครับ\n"
            "✅ Cancelled. You can send a new photo now."
        )
    else:
        await update.message.reply_text(
            "ไม่มี session ที่ค้างอยู่\n"
            "No active session found."
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not _is_allowed(user.id, chat_id):
        await update.message.reply_text(
            "⛔ ขออภัย คุณไม่มีสิทธิ์ใช้งานระบบนี้\n"
            "⛔ Sorry, you are not authorized to use this system."
        )
        return

    try:
        from sqlalchemy import func

        from src.database.db import get_session as db_session
        from src.database.models import EstrusDetection

        with db_session() as session:
            total = session.query(func.count(EstrusDetection.id)).scalar() or 0
            today_start = datetime.now(PH_TZ).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today = (
                session.query(func.count(EstrusDetection.id))
                .filter(EstrusDetection.created_at >= today_start)
                .scalar() or 0
            )
            by_class = (
                session.query(
                    EstrusDetection.estrus_classification,
                    func.count(EstrusDetection.id),
                )
                .group_by(EstrusDetection.estrus_classification)
                .all()
            )

        emoji_map = {
            "Standing Estrus": "🚨",
            "Pre-Estrus": "⚠️",
            "Post-Estrus": "ℹ️",
            "Non-Estrus": "✅",
            "False Estrus or Pathology Suspect": "🛑",
        }

        limit = Config.DAILY_IMAGE_LIMIT
        remaining = max(0, limit - _daily_count) if limit > 0 else "ไม่จำกัด / Unlimited"

        lines = [
            "📊 สถิติการวิเคราะห์\n",
            f"  • ทั้งหมด    : {total} ครั้ง",
            f"  • วันนี้      : {today} ครั้ง",
            f"  • คงเหลือวันนี้: {remaining} รูป\n",
            "แยกตาม Classification:",
        ]
        for cls, cnt in sorted(by_class, key=lambda x: -x[1]):
            emoji = emoji_map.get(cls, "•")
            lines.append(f"  {emoji} {cls}: {cnt}")

        lines += [
            "\n---",
            "📊 Analysis Statistics\n",
            f"  • Total   : {total} records",
            f"  • Today   : {today} records",
            f"  • Remaining today: {remaining} photos\n",
            "By Classification:",
        ]
        for cls, cnt in sorted(by_class, key=lambda x: -x[1]):
            emoji = emoji_map.get(cls, "•")
            lines.append(f"  {emoji} {cls}: {cnt}")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Stats command error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ ไม่สามารถดึงสถิติได้ในขณะนี้\n"
            "❌ Unable to retrieve statistics at this time."
        )


# =============================================================================
# Photo handler
# =============================================================================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    chat_id = update.effective_chat.id

    if not _is_allowed(user.id, chat_id):
        await message.reply_text(
            "⛔ ขออภัย คุณไม่มีสิทธิ์ใช้งานระบบนี้\n"
            "⛔ Sorry, you are not authorized to use this system."
        )
        return

    if not await _check_rate_limit(update):
        return

    await context.bot.send_chat_action(
        chat_id=message.chat_id, action=ChatAction.TYPING
    )

    try:
        photo = message.photo[-1]
        file_id = photo.file_id
        photo_file = await context.bot.get_file(file_id)

        timestamp = datetime.now(PH_TZ).strftime("%Y%m%d_%H%M%S")
        filename = f"{user.id}_{timestamp}_{uuid.uuid4().hex[:4]}.jpg"
        image_path = os.path.join(Config.TEMP_IMAGE_DIR, filename)
        await photo_file.download_to_drive(image_path)
        logger.info(f"📥 Image downloaded: {image_path}")

        # === เช็ค Daily Limit ===
        allowed, current_count = _check_daily_limit()
        if not allowed:
            limit = Config.DAILY_IMAGE_LIMIT
            _save_overlimit_image(image_path, user.id)
            await message.reply_text(
                f"🚫 ครบจำนวนการวิเคราะห์รายวันแล้ว ({current_count}/{limit} รูป)\n"
                "โปรดลองใหม่ในวันถัดไป (รีเซ็ตทุกเที่ยงคืน)\n\n"
                f"🚫 Daily analysis limit reached ({current_count}/{limit} photos)\n"
                "Please try again tomorrow (resets at midnight)."
            )
            return

        # === เพิ่ม counter ===
        _increment_daily_count()

        session_mgr = get_session_manager()
        session_mgr.create(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            image_path=image_path,
            image_file_id=file_id,
        )

        if Config.ENABLE_GILT_SELECTION:
            keyboard = [
                [
                    InlineKeyboardButton("🐷 หมูสาว (Gilt)", callback_data=CALLBACK_GILT),
                    InlineKeyboardButton("🐖 หมูนาง (Sow)", callback_data=CALLBACK_SOW),
                ]
            ]
            await message.reply_text(
                "✅ ได้รับรูปแล้ว / Photo received\n"
                "🐷 กรุณาเลือกประเภทของหมู / Please select pig type:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        sent = await message.reply_text(
            "🔍 กำลังวิเคราะห์ภาพ (หมูสาว) / Analyzing (Gilt)...\n"
            "⏱️ กรุณารอสักครู่... / Please wait..."
        )
        await _run_analysis_pipeline(
            update=update,
            context=context,
            pig_type=DEFAULT_PIG_TYPE_WHEN_DISABLED,
            edit_target=sent,
        )

    except Exception:
        logger.error("❌ Photo handler error", exc_info=True)
        await message.reply_text(
            "❌ เกิดข้อผิดพลาดในการรับรูปภาพ กรุณาลองใหม่อีกครั้ง\n"
            "❌ Error receiving photo. Please try again."
        )


# =============================================================================
# Callback handler
# =============================================================================
async def pig_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    callback_data = query.data or ""
    if not callback_data.startswith("pig_type:"):
        return

    pig_type = callback_data.split(":", 1)[1]
    pig_label = "หมูสาว (Gilt)" if pig_type == "gilt" else "หมูนาง (Sow)"

    await query.edit_message_text(
        f"🔍 กำลังวิเคราะห์ภาพ ({pig_label}) / Analyzing ({pig_label})...\n"
        "⏱️ กรุณารอสักครู่... / Please wait..."
    )
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id, action=ChatAction.TYPING
    )
    await _run_analysis_pipeline(
        update=update,
        context=context,
        pig_type=pig_type,
        edit_target=query.message,
        use_edit=True,
    )


# =============================================================================
# Text handler
# =============================================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not _is_allowed(user_id, chat_id):
        await update.message.reply_text(
            "⛔ ขออภัย คุณไม่มีสิทธิ์ใช้งานระบบนี้\n"
            "⛔ Sorry, you are not authorized to use this system."
        )
        return

    await update.message.reply_text(
        "📸 กรุณาส่งรูปภาพของหมูเข้ามาเพื่อวิเคราะห์\n"
        "📸 Please send a pig photo to analyze.\n\n"
        "พิมพ์ /help เพื่อดูคู่มือ / Type /help for instructions."
    )


# =============================================================================
# Core pipeline
# =============================================================================
async def _run_analysis_pipeline(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    pig_type: str,
    edit_target,
    use_edit: bool = False,
) -> None:
    user = update.effective_user
    session_mgr = get_session_manager()
    session = session_mgr.get(user.id)

    if session is None:
        text = (
            "⏰ ไม่พบรูปที่ส่งไว้ / Photo not found\n"
            "อาจเป็นเพราะ / Possible reasons:\n"
            "  • กดปุ่มเลือกซ้ำ / Button pressed twice\n"
            f"  • ส่งรูปไว้นานเกิน {Config.SESSION_TIMEOUT_MINUTES} นาที / "
            f"Photo expired after {Config.SESSION_TIMEOUT_MINUTES} min\n\n"
            "📸 กรุณาส่งรูปใหม่อีกครั้ง / Please send a new photo."
        )
        if use_edit:
            await edit_target.edit_text(text)
        else:
            await edit_target.reply_text(text)
        return

    sow_id = getattr(session, "sow_id", None)
    temp_image_path = session.image_path

    try:
        # === VLM ===
        vlm = get_vlm_service()
        vlm_result = await vlm.analyze_estrus(
            image_path=temp_image_path, pig_type=pig_type
        )

        # === Business logic ===
        alert = generate_alert(vlm_result, pig_type)

        # === Save DB ===
        detection_id = save_detection(
            telegram_user_id=user.id,
            telegram_username=user.username,
            telegram_first_name=user.first_name,
            pig_type=pig_type,
            image_file_id=session.image_file_id,
            image_path=temp_image_path,
            vlm_result=vlm_result,
            result_status=alert.status,
            alert_message=alert.message,
            sow_id=sow_id,
        )

        # === Copy ไปเก็บใน storage/ ถาวร ===
        storage_image_path = _copy_to_storage(
            image_path=temp_image_path,
            detection_id=detection_id,
            vlm_result=vlm_result if isinstance(vlm_result, dict) else vars(vlm_result),
            alert_status=alert.status,
            alert_message=alert.message,
            pig_type=pig_type,
            user_id=user.id,
            username=user.username,
            sow_id=sow_id,
        )

        # === อัปเดต image_path ใน DB → storage ===
        if storage_image_path and detection_id:
            try:
                from src.database.db import get_session as db_session
                from src.database.models import EstrusDetection
                with db_session() as db_sess:
                    record = db_sess.query(EstrusDetection).filter(
                        EstrusDetection.id == detection_id
                    ).first()
                    if record:
                        record.image_path = storage_image_path
                logger.info(f"📝 Updated image_path → {storage_image_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to update image_path: {e}")

        # === Compose final ===
        final_text = alert.message
        if sow_id:
            final_text = f"📌 รหัสหมู / Pig ID: {sow_id}\n\n{final_text}"
        final_text = append_record_id(final_text, detection_id)
        final_text = _truncate(final_text)

        if use_edit:
            await edit_target.edit_text(final_text)
        else:
            await edit_target.reply_text(final_text)

        logger.info(
            f"✅ Pipeline done user={user.id} pig_type={pig_type} "
            f"class={alert.classification} status={alert.status} "
            f"record_id={detection_id} daily_count={_daily_count}"
        )

    except Exception:
        logger.error("❌ Pipeline error", exc_info=True)
        text = (
            "❌ เกิดข้อผิดพลาดในการวิเคราะห์ กรุณาลองส่งรูปใหม่อีกครั้ง\n"
            "❌ Analysis error. Please try sending a new photo."
        )
        if use_edit:
            await edit_target.edit_text(text)
        else:
            await edit_target.reply_text(text)
    finally:
        session_mgr.clear(user.id)


# =============================================================================
# Error handler
# =============================================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("⚠️ Update caused error:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ เกิดข้อผิดพลาดในระบบ กรุณาลองใหม่อีกครั้ง\n"
                "❌ System error. Please try again."
            )
        except Exception:
            pass
