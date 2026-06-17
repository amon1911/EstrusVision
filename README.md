# 🐷 Swine Estrus Detection Telegram Bot

Telegram bot ตรวจจับการเป็นสัดของสุกร ด้วย Vision-Language Model (Gemini 2.5 Flash)

## โครงสร้างโปรเจกต์

```
swine_estrus_bot/
├── main.py                         # Entry point
├── pyproject.toml                  # Dependencies + project config (uv)
├── uv.lock                         # Lock file (pin exact versions)
├── .python-version                 # Python version (uv อ่านอัตโนมัติ)
├── Dockerfile                      # Multi-stage build ใช้ uv
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
│
├── src/
│   ├── __init__.py
│   ├── config.py                   # โหลด env vars
│   │
│   ├── handlers/                   # Telegram handlers
│   │   ├── __init__.py
│   │   └── telegram_handlers.py
│   │
│   ├── services/                   # Business services
│   │   ├── __init__.py
│   │   ├── vlm_service.py         # Gemini API integration
│   │   └── business_logic.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── db.py
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── vlm_prompts.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── session_manager.py
│
├── temp_images/                    # รูปชั่วคราว (auto-cleanup)
└── logs/                           # Log files
```

## ⚡ Prerequisites

ติดตั้ง **uv** (Python package manager ที่เร็วกว่า pip มาก) ก่อน:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# หรือถ้ามี pipx
pipx install uv
```

ตรวจสอบ: `uv --version`

## วิธีติดตั้ง

### Option A: รันแบบ Local (แนะนำสำหรับ Dev)

```bash
# 1. Clone repo
git clone <repo-url> && cd swine_estrus_bot

# 2. ติดตั้ง dependencies (uv จะสร้าง .venv และติดตั้งทุกอย่างให้)
uv sync

# 3. ตั้งค่า env
cp .env.example .env
nano .env  # กรอก TOKEN, API KEY, DB password

# 4. ติดตั้ง PostgreSQL (ถ้ายังไม่มี)
# macOS:  brew install postgresql && brew services start postgresql
# Ubuntu: sudo apt install postgresql && sudo systemctl start postgresql
createdb swine_estrus

# 5. รัน bot
uv run python main.py
```

### Option B: ใช้ Docker (แนะนำสำหรับ Production)

```bash
# 1. ตั้งค่า env
cp .env.example .env
nano .env

# 2. Build + run (Dockerfile ใช้ uv ภายในด้วย)
docker-compose up -d

# ดู log
docker-compose logs -f bot
```

## 🛠️ uv Commands ที่ใช้บ่อย

```bash
# ติดตั้ง/sync dependencies จาก pyproject.toml + uv.lock
uv sync

# เพิ่ม dependency ใหม่
uv add requests
uv add --dev pytest  # dev dependency

# ลบ dependency
uv remove requests

# รันคำสั่งใน venv (ไม่ต้อง activate)
uv run python main.py
uv run pytest

# Activate venv แบบเก่า (ถ้าชอบ)
source .venv/bin/activate

# อัปเดต lock file
uv lock --upgrade

# Update เฉพาะ package
uv lock --upgrade-package google-genai
```

## วิธีขอ API Keys

### Telegram Bot Token
1. ไปคุยกับ [@BotFather](https://t.me/BotFather) ใน Telegram
2. พิมพ์ `/newbot` และทำตามขั้นตอน
3. คัดลอก token ใส่ใน `.env`

### Gemini API Key
1. ไปที่ https://aistudio.google.com/apikey
2. สร้าง API Key ใหม่
3. คัดลอกใส่ใน `.env`

## การใช้งาน

1. เปิด Telegram → ค้นหาบอทที่สร้าง
2. กด `/start`
3. ส่งรูปก้นหมูเข้ามา
4. เลือกประเภท: **หมูสาว** หรือ **หมูนาง**
5. รอผลวิเคราะห์

## คำสั่งที่รองรับ

| คำสั่ง | คำอธิบาย |
|--------|----------|
| `/start` | เริ่มต้นใช้งาน |
| `/help` | คู่มือการใช้งาน |
| `/cancel` | ยกเลิก session ปัจจุบัน |

## Database Schema

ตาราง `estrus_detections` เก็บข้อมูล:
- ข้อมูล user (telegram_user_id, username)
- ประเภทหมู, รูป
- ผล VLM (อาการแต่ละข้อ, reflex_score)
- ผลการประเมิน + ข้อความที่ส่ง
- timestamp

### Query ตัวอย่าง

```sql
-- ดูประวัติของ user คนหนึ่ง
SELECT * FROM estrus_detections
WHERE telegram_user_id = 123456
ORDER BY created_at DESC;

-- สถิติประจำเดือน
SELECT result_status, COUNT(*)
FROM estrus_detections
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY result_status;

-- หาเคสที่ปัญหา (เผื่อต้อง review รูป)
SELECT * FROM estrus_detections
WHERE result_status = 'estrus_detected'
  AND reflex_score >= 3
ORDER BY created_at DESC;
```

## การเปลี่ยนจาก Polling → Webhook (ตอน Production)

แก้ใน `.env`:
```
MODE=webhook
WEBHOOK_URL=https://yourdomain.com
WEBHOOK_PORT=8443
```

ต้องมี:
- Domain + SSL Certificate (Let's Encrypt)
- Nginx reverse proxy หรือ port forwarding
- เปิด port 8443 (หรือ 443/80/88)

## Business Rules Summary

| เงื่อนไข   | ผลลัพธ์   | คำสั่ง  |
|--------- |---------|--------|
| `reflex_score≥2` OR (`swelling`+`redness`) + Gilt | 🚨 เป็นสัด | ผสมทันที |
| `reflex_score≥2` OR (`swelling`+`redness`) + Sow | 🚨 เป็นสัด | ดูช่วงเวลา (เช้า/บ่าย) |
| `reflex_score<2` + `swelling`=true | ⚠️ เฝ้าระวัง | Back-pressure test |
| อื่นๆ | ℹ️ ไม่พบ | สังเกตอาการอื่น |

## License

MIT