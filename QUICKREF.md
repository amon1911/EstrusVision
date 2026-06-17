# EstrusVision — Quick Reference

## โครงสร้างระบบ
- **Bot** — รันผ่าน systemd บน Jetson Orin Nano
- **Database** — PostgreSQL รันใน Docker
- **Storage** — รูป + JSON เก็บใน `~/EstrusVision/storage/YYYY-MM-DD/`
- **AI** — Gemini 2.5 Flash (Google Cloud API)

---

## คำสั่งที่ใช้บ่อย

### Bot Service
```bash
# ดูสถานะ
sudo systemctl status estrusvision-bot.service

# Start / Stop / Restart
sudo systemctl start estrusvision-bot.service
sudo systemctl stop estrusvision-bot.service
sudo systemctl restart estrusvision-bot.service

# ดู log แบบ real-time
journalctl -u estrusvision-bot.service -f

# ดู log 50 บรรทัดล่าสุด
journalctl -u estrusvision-bot.service -n 50 --no-pager
```

### Database (PostgreSQL)
```bash
# ดูสถานะ
docker compose ps

# Start / Stop
docker compose up -d db
docker compose down

# เข้า psql shell
docker exec -it estrus_db psql -U postgres -d swine_estrus

# ดูข้อมูลล่าสุด 10 รายการ
docker exec -it estrus_db psql -U postgres -d swine_estrus -c \
"SELECT id, pig_type, estrus_classification, confidence, created_at FROM estrus_detections ORDER BY id DESC LIMIT 10;"

# Backup
docker exec estrus_db pg_dump -U postgres swine_estrus > ~/backups/estrus_$(date +%Y%m%d).sql
```

---

## อัปเดตโค้ด

### บน Windows (แก้โค้ดเสร็จแล้ว)
```powershell
git add .
git commit -m "อธิบายสิ่งที่แก้"
git push
```

### บน Jetson (ดึงโค้ดใหม่)
```bash
cd ~/EstrusVision
git pull
sudo systemctl restart estrusvision-bot.service
```

---

## ตั้งค่า (.env)
ไฟล์อยู่ที่ `~/EstrusVision/.env`

```bash
nano ~/EstrusVision/.env
```

ค่าสำคัญ:
| ตัวแปร | ความหมาย |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token จาก BotFather |
| `GEMINI_API_KEY` | API Key จาก Google AI Studio |
| `ENABLE_GILT_SELECTION` | true = ให้เลือกหมูสาว/นาง, false = อัตโนมัติ |
| `ALLOWED_USER_IDS` | Telegram User ID ที่อนุญาต (คั่นด้วย ,) |
| `ALLOWED_GROUP_IDS` | Telegram Group ID ที่อนุญาต (คั่นด้วย ,) |
| `LANGUAGE` | TH / EN / THEN |

แก้ .env แล้วต้อง restart bot ทุกครั้ง:
```bash
sudo systemctl restart estrusvision-bot.service
```

---

## โครงสร้างไฟล์
```
EstrusVision/
  main.py                  — จุดเริ่มต้น bot
  src/
    config.py              — อ่านค่าจาก .env
    handlers/
      telegram_handlers.py — รับรูป, ส่งผล, whitelist
    services/
      vlm_service.py       — เรียก Gemini API
      vlm_prompts.py       — prompt สำหรับวิเคราะห์
      business_logic.py    — สร้างข้อความผลลัพธ์
    database/
      db.py                — บันทึก/ดึงข้อมูล DB
      models.py            — schema ตาราง
    utils/
      i18n.py              — ภาษา TH/EN/THEN
      rate_limiter.py      — จำกัดการส่งรูป
      session_manager.py   — จัดการ session ผู้ใช้
  storage/                 — รูป + JSON ถาวร (แยกตามวัน)
  temp_images/             — รูปชั่วคราว (ลบอัตโนมัติ)
  logs/                    — log ไฟล์
  .env                     — ค่า config (ห้าม commit)
```

---

## ดูข้อมูลใน DBeaver
เชื่อมต่อผ่าน Tailscale:
- Host: `IP Tailscale ของ Jetson`
- Port: `5432`
- Database: `swine_estrus`
- Username: `postgres`
- Password: ดูใน `.env` → `DB_PASSWORD`

---

## Troubleshooting

**Bot ไม่ตอบสนอง**
```bash
sudo systemctl status estrusvision-bot.service
journalctl -u estrusvision-bot.service -n 50 --no-pager
```

**DB เชื่อมต่อไม่ได้**
```bash
docker compose ps   # ต้องเห็น Up (healthy)
docker compose up -d db
```

**โค้ดใหม่ schema เปลี่ยน (เพิ่ม column)**
```bash
# ถ้าไม่มีข้อมูลสำคัญ — drop แล้วสร้างใหม่
uv run python -c "
from src.database.db import init_db, db
from sqlalchemy import text
init_db()
from src.database import db
c = db._engine.connect()
c.execute(text('DROP TABLE IF EXISTS estrus_detections'))
c.commit()
c.close()
print('Done')
"
sudo systemctl restart estrusvision-bot.service
```

**ดู storage รูป**
```bash
ls ~/EstrusVision/storage/
ls ~/EstrusVision/storage/YYYY-MM-DD/
```
