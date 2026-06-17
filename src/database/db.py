"""
db.py — Database connection + persistence layer

🆕 v3 changes:
- save_detection() **ไม่ save** ถ้า result_status == 'error'
- รองรับ sow_id parameter (ของ user > VLM > None)
- เพิ่ม helper get_recent_by_sow() สำหรับ query ประวัติ
"""
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import Config
from src.database.models import Base, EstrusDetection

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None

# Status ที่จะไม่บันทึก DB
SKIP_SAVE_STATUSES = {"error"}


# =============================================================================
# Bootstrap
# =============================================================================
def init_db() -> None:
    """Initialize engine + sessionmaker + create tables."""
    global _engine, _SessionFactory

    _engine = create_engine(
        Config.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    logger.info("✅ Database initialized")


@contextmanager
def get_session():
    """Context-managed SQLAlchemy session."""
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =============================================================================
# Persistence
# =============================================================================
def save_detection(
    telegram_user_id: int,
    telegram_username: str | None,
    telegram_first_name: str | None,
    pig_type: str,
    image_file_id: str | None,
    image_path: str | None,
    vlm_result: dict,
    result_status: str,
    alert_message: str,
    sow_id: str | None = None,
) -> int | None:
    """
    Persist one estrus inspection record.

    🆕 ไม่ save ถ้า result_status เป็น error (กัน DB เต็มไปด้วย noise)

    Returns: id ของ record ที่บันทึก หรือ None ถ้า skip / error
    """
    # === Skip — error case ===
    if result_status in SKIP_SAVE_STATUSES:
        logger.info(
            f"⏭️ Skip saving record (status={result_status}, user={telegram_user_id})"
        )
        return None

    try:
        observed = vlm_result.get("observed_signs", {}) or {}
        issues = vlm_result.get("visibility_issues") or []

        # ใช้ sow_id จาก user > VLM > None
        final_sow_id = sow_id or vlm_result.get("sow_id") or None

        # 🆕 Quality flags — คำนวณจาก vlm_result ตรงๆ (ไม่ต้อง parse alert_message)
        confidence = vlm_result.get("confidence")
        image_quality = vlm_result.get("image_quality")
        low_confidence_flag = confidence == "low"
        poor_image_flag = image_quality == "poor"

        detection = EstrusDetection(
            # user
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            telegram_first_name=telegram_first_name,
            # input
            pig_type=pig_type,
            image_file_id=image_file_id,
            image_path=image_path,
            # meta
            image_quality=image_quality,
            visibility_issues=", ".join(str(x) for x in issues) if issues else None,
            parity_adjustment=vlm_result.get("parity_adjustment"),
            sow_id=final_sow_id,
            # observed signs
            vulva_swelling=observed.get("vulva_swelling"),
            vulva_color=observed.get("vulva_color"),
            clitoris_state=observed.get("clitoris_state"),
            mucus=observed.get("mucus"),
            tail_position=observed.get("tail_position"),
            behavior=observed.get("behavior"),
            # classification
            estrus_classification=vlm_result.get("estrus_classification", "Non-Estrus"),
            confidence=confidence,
            reasoning_summary=vlm_result.get("reasoning_summary"),
            recommended_action=vlm_result.get("recommended_action"),
            # 🆕 quality flags
            low_confidence_flag=low_confidence_flag,
            poor_image_flag=poor_image_flag,
            # raw backup
            raw_vlm_response=vlm_result,
            # pipeline
            result_status=result_status,
            alert_message=alert_message,
        )

        with get_session() as session:
            session.add(detection)
            session.flush()
            detection_id = detection.id

        logger.info(
            f"💾 Saved detection id={detection_id} "
            f"class={vlm_result.get('estrus_classification')} "
            f"sow_id={final_sow_id} "
            f"low_conf={low_confidence_flag} poor_img={poor_image_flag}"
        )
        return detection_id

    except Exception as e:
        logger.error(f"❌ Failed to save detection: {e}", exc_info=True)
        return None


# =============================================================================
# Query helpers
# =============================================================================
def get_recent_by_sow(sow_id: str, limit: int = 10) -> list[EstrusDetection]:
    """ดึงประวัติของ sow ตาม sow_id"""
    with get_session() as session:
        return (
            session.query(EstrusDetection)
            .filter(EstrusDetection.sow_id == sow_id)
            .order_by(EstrusDetection.created_at.desc())
            .limit(limit)
            .all()
        )


def get_detection_by_id(detection_id: int) -> EstrusDetection | None:
    """ดึง 1 record ตาม id — ใช้สำหรับ API serve รูป/รายละเอียด"""
    with get_session() as session:
        return (
            session.query(EstrusDetection)
            .filter(EstrusDetection.id == detection_id)
            .first()
        )
