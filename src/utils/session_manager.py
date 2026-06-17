"""
session_manager.py — จัดการ session ของแต่ละ user

🆕 เพิ่ม sow_id (optional) — user ระบุได้จาก:
   1. caption ของรูปที่ส่ง (เช่น "S001")
   2. หรือพิมพ์ message ถัดมาเป็น sow_id ก่อนกดเลือกหมูสาว/นาง

ใช้ in-memory dict (เพียงพอสำหรับ single instance)
ถ้าจะ scale หลาย instance ให้เปลี่ยนเป็น Redis
"""
import logging
import os
import re
import time
from dataclasses import dataclass, field

from src.config import Config

logger = logging.getLogger(__name__)


# sow_id อนุญาตเฉพาะ alphanumeric + dash + underscore (1-64 chars)
SOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def is_valid_sow_id(s: str | None) -> bool:
    """ตรวจว่า sow_id ที่ user ส่งมาถูกต้อง"""
    return bool(s and SOW_ID_PATTERN.match(s.strip()))


@dataclass
class UserSession:
    """Session ของ user ที่กำลังรอเลือกประเภทหมู"""
    user_id: int
    username: str | None
    first_name: str | None
    image_path: str
    image_file_id: str
    sow_id: str | None = None  # 🆕 optional sow ID จาก user
    created_at: float = field(default_factory=time.time)

    def is_expired(self, timeout_seconds: int) -> bool:
        return (time.time() - self.created_at) > timeout_seconds


class SessionManager:
    """In-memory session storage"""

    def __init__(self) -> None:
        self._sessions: dict[int, UserSession] = {}
        self._timeout = Config.SESSION_TIMEOUT_MINUTES * 60

    def create(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        image_path: str,
        image_file_id: str,
        sow_id: str | None = None,
    ) -> UserSession:
        """สร้าง session ใหม่ (ถ้ามี session เก่าให้ลบทิ้ง)"""
        self.clear(user_id)

        # validate / sanitize sow_id
        if sow_id and not is_valid_sow_id(sow_id):
            logger.warning(f"Invalid sow_id '{sow_id}' ignored for user {user_id}")
            sow_id = None
        elif sow_id:
            sow_id = sow_id.strip()

        session = UserSession(
            user_id=user_id,
            username=username,
            first_name=first_name,
            image_path=image_path,
            image_file_id=image_file_id,
            sow_id=sow_id,
        )
        self._sessions[user_id] = session
        logger.debug(f"📝 Session created for user {user_id} (sow_id={sow_id})")
        return session

    def get(self, user_id: int) -> UserSession | None:
        """ดึง session — ถ้า expired ให้ลบทิ้งและ return None"""
        session = self._sessions.get(user_id)
        if session is None:
            return None

        if session.is_expired(self._timeout):
            logger.debug(f"⏰ Session expired for user {user_id}")
            self.clear(user_id)
            return None

        return session

    def set_sow_id(self, user_id: int, sow_id: str) -> bool:
        """อัพเดท sow_id ของ session (ใช้ตอน user ส่ง sow_id หลังส่งรูปแล้ว)"""
        session = self.get(user_id)
        if session is None:
            return False
        if not is_valid_sow_id(sow_id):
            return False
        session.sow_id = sow_id.strip()
        logger.debug(f"📝 sow_id={sow_id} set for user {user_id}")
        return True

    def clear(self, user_id: int) -> None:
        """ลบ session + ลบไฟล์รูป temp"""
        session = self._sessions.pop(user_id, None)
        if session and session.image_path:
            try:
                if os.path.exists(session.image_path):
                    os.remove(session.image_path)
                    logger.debug(f"🗑️ Removed temp image: {session.image_path}")
            except Exception as e:
                logger.warning(f"Could not remove temp image: {e}")

    def cleanup_expired(self) -> None:
        """เคลียร์ session ที่หมดอายุทั้งหมด"""
        expired_users = [
            uid for uid, s in self._sessions.items()
            if s.is_expired(self._timeout)
        ]
        for uid in expired_users:
            self.clear(uid)

        if expired_users:
            logger.info(f"🧹 Cleaned up {len(expired_users)} expired sessions")


# Singleton
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
