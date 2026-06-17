"""
images.py — API endpoint สำหรับเสิร์ฟรูปภาพของแต่ละ detection

GET /api/detections/{detection_id}/image

Flow:
1. หา record จาก DB ด้วย detection_id
2. ถ้า image_path มีไฟล์อยู่จริงในเครื่อง → ส่งไฟล์กลับตรงๆ
3. ถ้าไฟล์ไม่มี (ถูก cleanup ไปแล้ว) แต่มี image_file_id →
   proxy/redirect ไป Telegram file URL (ชั่วคราว ~1 ชม.)
4. ถ้าไม่มีทั้งคู่ → 404
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from src.database.db import get_detection_by_id
from src.services.telegram_file import get_telegram_file_url

router = APIRouter()


@router.get("/api/detections/{detection_id}/image")
async def get_detection_image(detection_id: int):
    detection = get_detection_by_id(detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Detection not found")

    # 1) ไฟล์ local ยังอยู่ → เสิร์ฟตรง
    if detection.image_path and os.path.exists(detection.image_path):
        return FileResponse(detection.image_path, media_type="image/jpeg")

    # 2) fallback → proxy ไป Telegram ด้วย image_file_id
    if detection.image_file_id:
        url = await get_telegram_file_url(detection.image_file_id)
        if url:
            return RedirectResponse(url)

    raise HTTPException(status_code=404, detail="Image not available")
