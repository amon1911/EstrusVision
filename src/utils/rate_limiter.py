"""
rate_limiter.py — Token-bucket rate limiter (in-memory)

🔑 Design:
- Sliding window: นับ request ภายใน X วินาทีล่าสุด
- คอนฟิกผ่าน .env:
    RATE_LIMIT_MAX_REQUESTS  (default 5)
    RATE_LIMIT_WINDOW_SECONDS (default 60)
- Singleton — instantiate ครั้งเดียวต่อ process
- Thread-safe พอใช้ใน asyncio (เพราะ Python GIL + dict operations atomic)
- Memory-bounded — auto-clean user ที่ไม่ใช้เกิน window x 2

หมายเหตุ:
- ถ้า scale หลาย instance ให้เปลี่ยนไปใช้ Redis
- Sliding window แม่นกว่า fixed window (ไม่มี burst ตอนเปลี่ยน window)
"""
import logging
import os
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """ผลการ check rate limit"""
    allowed: bool
    remaining: int            # request ที่เหลือใน window
    retry_after_seconds: int  # ถ้า denied → รออีกกี่วินาที


class RateLimiter:
    """In-memory sliding window rate limiter"""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, deque[float]] = {}
        logger.info(
            f"🚦 RateLimiter initialized: "
            f"{max_requests} requests / {window_seconds}s"
        )

    def check(self, user_id: int) -> RateLimitResult:
        """
        ตรวจว่า user_id ขอ request ได้ไหม

        Returns:
            RateLimitResult — ถ้า allowed=False → ห้าม + ระบุ retry_after
        """
        now = time.time()
        window_start = now - self.window_seconds

        # ดึง / สร้าง queue
        queue = self._requests.setdefault(user_id, deque())

        # ลบ request เก่าที่หลุด window
        while queue and queue[0] < window_start:
            queue.popleft()

        # เช็คว่าเกิน limit ไหม
        if len(queue) >= self.max_requests:
            oldest = queue[0]
            retry_after = max(1, int(self.window_seconds - (now - oldest)))
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=retry_after,
            )

        # อนุญาต — บันทึก request นี้
        queue.append(now)
        return RateLimitResult(
            allowed=True,
            remaining=self.max_requests - len(queue),
            retry_after_seconds=0,
        )

    def cleanup_inactive(self) -> int:
        """ลบ user ที่ไม่มี request ใน window x 2 — ประหยัด memory"""
        now = time.time()
        threshold = now - (self.window_seconds * 2)
        inactive = [
            uid for uid, q in self._requests.items()
            if not q or q[-1] < threshold
        ]
        for uid in inactive:
            del self._requests[uid]
        return len(inactive)


# =============================================================================
# Singleton
# =============================================================================
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create singleton RateLimiter from env config."""
    global _rate_limiter
    if _rate_limiter is None:
        max_req = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "5"))
        window = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        _rate_limiter = RateLimiter(max_requests=max_req, window_seconds=window)
    return _rate_limiter
