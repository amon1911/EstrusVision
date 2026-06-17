"""
models.py — SQLAlchemy ORM Models

ตาราง estrus_detections ออกแบบให้:
1. Map ตรงกับ JSON schema ของ VLM (1 field = 1 column)
2. Query ง่าย: filter ตาม classification / confidence / pig_type
3. มี raw_vlm_response (JSONB) สำรองไว้เผื่อเปลี่ยน schema ในอนาคต
4. Index ที่ใช้บ่อย — telegram_user_id, created_at, estrus_classification, sow_id

🆕 v3 changes:
- created_at ใช้เวลาฟิลิปปินส์ (Asia/Manila, UTC+8) แทน UTC
  เพื่อให้ตรงกับ business logic (เช้า/บ่าย) — query ดูประวัติไม่ต้องแปลง timezone
- เพิ่ม low_confidence_flag, poor_image_flag (Boolean) — query/stats ง่ายขึ้น
  ไม่ต้อง parse alert_message text
- เพิ่ม index บน sow_id — get_recent_by_sow() เร็วขึ้นเมื่อข้อมูลมาก

⚠️ Migration: ถ้า DB เก่ามีตารางนี้อยู่แล้ว ให้รัน:
    DROP TABLE estrus_detections;
หรือใช้ Alembic migration เพิ่ม column ใหม่
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# ฟิลิปปินส์ = UTC+8 ตลอดปี (ไม่มี DST) — ใช้ fixed offset กันปัญหา tzdata บน Windows
PH_TZ = timezone(timedelta(hours=8))


def _now_ph() -> datetime:
    """เวลาปัจจุบันแบบ Asia/Manila (เก็บเป็น naive datetime ใน DB)"""
    return datetime.now(PH_TZ).replace(tzinfo=None)


class EstrusDetection(Base):
    """บันทึกผลการตรวจการเป็นสัด — รุ่นที่ 3 (5-class taxonomy + flags)"""

    __tablename__ = "estrus_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Telegram user ---
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    telegram_username = Column(String(255), nullable=True)
    telegram_first_name = Column(String(255), nullable=True)

    # --- Input ---
    pig_type = Column(String(20), nullable=False)  # 'gilt' | 'sow'
    image_file_id = Column(String(255), nullable=True)
    image_path = Column(String(500), nullable=True)

    # --- VLM result: image meta ---
    image_quality = Column(String(20), nullable=True)        # good | fair | poor
    visibility_issues = Column(Text, nullable=True)          # CSV
    parity_adjustment = Column(String(20), nullable=True)    # gilt | multiparous | unknown
    sow_id = Column(String(64), nullable=True, index=True)   # 🆕 index เพิ่ม

    # --- VLM result: observed_signs (enum values) ---
    vulva_swelling = Column(String(20), nullable=True)
    vulva_color = Column(String(20), nullable=True)
    clitoris_state = Column(String(40), nullable=True)
    mucus = Column(String(40), nullable=True)
    tail_position = Column(String(30), nullable=True)
    behavior = Column(String(40), nullable=True)

    # --- VLM result: classification ---
    estrus_classification = Column(String(50), nullable=False, index=True)
    confidence = Column(String(10), nullable=True)
    reasoning_summary = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)

    # 🆕 --- Quality flags (สำหรับ stats/filter โดยไม่ต้อง parse text) ---
    low_confidence_flag = Column(Boolean, nullable=False, default=False, index=True)
    poor_image_flag = Column(Boolean, nullable=False, default=False, index=True)

    # --- Raw backup (JSONB ใน PostgreSQL — query ได้แบบ structured) ---
    raw_vlm_response = Column(JSONB, nullable=True)

    # --- Pipeline result ---
    result_status = Column(String(30), nullable=False, index=True)
    # 'standing_estrus' | 'pre_estrus' | 'post_estrus' | 'non_estrus'
    # | 'false_estrus' | 'bad_image' | 'error'
    alert_message = Column(Text, nullable=True)

    # --- Timestamps ---
    # 🆕 ใช้เวลาฟิลิปปินส์ (PH_TZ) แทน UTC — ตรงกับ business logic เช้า/บ่าย
    created_at = Column(
        DateTime, default=_now_ph, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<EstrusDetection id={self.id} user={self.telegram_user_id} "
            f"type={self.pig_type} class={self.estrus_classification} "
            f"status={self.result_status}>"
        )
