# 🚀 Migration & Deployment Guide

## 📋 ไฟล์ที่ต้องอัพเดท (ลำดับสำคัญ)

| ลำดับ | ไฟล์ | ปลายทาง |
|---|---|---|
| 1 | `vlm_prompts.py` | `src/prompts/` |
| 2 | `vlm_service.py` | `src/services/` |
| 3 | `business_logic.py` | `src/services/` |
| 4 | `models.py` | `src/database/` |
| 5 | `db.py` | `src/database/` |
| 6 | `telegram_handlers.py` | `src/handlers/` |
| 7 | `.env.example` | root (และเพิ่ม `ENABLE_GILT_SELECTION` ลง `.env`) |

## ⚠️ Database Migration

Schema ใหม่ **เพิ่ม column หลายตัว**:
- `image_quality`, `visibility_issues`, `parity_adjustment`, `sow_id`
- `vulva_swelling`, `vulva_color`, `clitoris_state`, `mucus`, `tail_position`, `behavior` (เปลี่ยนเป็น string จาก boolean)
- `estrus_classification`, `confidence`, `reasoning_summary`, `recommended_action`
- `raw_vlm_response` เปลี่ยนเป็น JSONB

### ทางเลือกที่ 1: ลบตารางเก่าทิ้ง (เร็ว — เหมาะกับ dev)

```sql
DROP TABLE estrus_detections;
```
แล้ว start bot — `Base.metadata.create_all` จะสร้างตารางใหม่ให้

### ทางเลือกที่ 2: Backup ก่อนแล้ว migrate (production)

```sql
-- 1. backup
CREATE TABLE estrus_detections_backup AS SELECT * FROM estrus_detections;

-- 2. drop เก่า
DROP TABLE estrus_detections;

-- 3. start bot (สร้างตารางใหม่อัตโนมัติ)

-- 4. ถ้าต้องการ migrate ข้อมูลเก่า — เขียน script แยกต่างหาก
```

## 🔧 Configuration

### `.env` — เพิ่มบรรทัดนี้
```env
ENABLE_GILT_SELECTION=true
```
- `true` (default): แสดงปุ่มเลือกหมูสาว/หมูนาง (เหมือนเดิม)
- `false`: ข้ามขั้นตอนเลือก → วิเคราะห์เป็น sow อัตโนมัติ

## 🧪 Smoke Test

```powershell
# 1. ตรวจว่า import ได้ทุกไฟล์
uv run python -c "from src.services.vlm_service import get_vlm_service; print('vlm: OK')"
uv run python -c "from src.services.business_logic import generate_alert; print('biz: OK')"
uv run python -c "from src.database.models import EstrusDetection; print('models: OK')"
uv run python -c "from src.database.db import save_detection; print('db: OK')"
uv run python -c "from src.handlers.telegram_handlers import photo_handler; print('handlers: OK')"

# 2. ตรวจ ruff
uv run ruff check --fix .

# 3. รัน bot
uv run python main.py
```

## 📊 Query ที่ใช้ใน production

```sql
-- เคสที่เป็นสัด (Standing Estrus) ใน 7 วันล่าสุด
SELECT id, telegram_user_id, pig_type, confidence, created_at
FROM estrus_detections
WHERE estrus_classification = 'Standing Estrus'
  AND created_at >= NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;

-- สถิติประจำเดือนแยกตามคลาส
SELECT estrus_classification, confidence, COUNT(*) AS n
FROM estrus_detections
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY estrus_classification, confidence
ORDER BY estrus_classification;

-- เคสที่ confidence ต่ำ — เผื่อ retrain prompt
SELECT id, image_quality, visibility_issues, reasoning_summary
FROM estrus_detections
WHERE confidence = 'low'
ORDER BY created_at DESC
LIMIT 50;

-- ตรวจ payload เต็มจาก JSONB
SELECT raw_vlm_response -> 'observed_signs' AS signs
FROM estrus_detections
WHERE id = 123;
```

## 🎯 What's New (Summary)

| มิติ | ของเก่า | ของใหม่ |
|---|---|---|
| Classification | binary (estrus/not) | 5-class taxonomy |
| Output | `vulva_redness: true/false` | `vulva_color: pale\|pink\|red\|dark red` |
| Decision | hard-coded `if` | จาก VLM classification ตรงๆ |
| Message | Markdown (อาจ render เพี้ยน) | Plain text — ตัดมาร์คดาวน์ออก |
| Pig type selection | บังคับเสมอ | toggle ผ่าน `.env` |
| DB schema | 7 columns | 18+ columns + JSONB |
| Confidence | ไม่มี | `low/medium/high` พร้อม reasoning |
