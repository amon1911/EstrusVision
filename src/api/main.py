"""
api/main.py — FastAPI app สำหรับ Dashboard API

รันแยกจาก Telegram bot (main.py):
    uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI

from src.api.images import router as images_router
from src.database.db import init_db

app = FastAPI(title="EstrusVision Dashboard API")

app.include_router(images_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
