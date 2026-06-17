"""
i18n.py — Internationalization helper

🔑 Design:
- Single source of truth สำหรับข้อความทุก locale
- รองรับ 3 โหมดจาก .env LANGUAGE:
    TH    → ภาษาไทยอย่างเดียว
    EN    → ภาษาอังกฤษอย่างเดียว
    THEN  → ไทย\nอังกฤษ (2 บรรทัด)
- Default = TH
- ใช้ฟังก์ชัน t(key) ที่ไหนก็ได้ในโค้ด

Usage:
    from src.utils.i18n import t
    msg = t("disclaimer")
"""
from __future__ import annotations

import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

LanguageMode = Literal["TH", "EN", "THEN"]


def _read_language() -> LanguageMode:
    """อ่านโหมดภาษาจาก .env LANGUAGE (default = TH)"""
    raw = os.getenv("LANGUAGE", "TH").strip().upper()
    if raw not in {"TH", "EN", "THEN"}:
        logger.warning(f"⚠️ Unknown LANGUAGE='{raw}' — fallback to TH")
        return "TH"
    return raw  # type: ignore[return-value]


LANGUAGE: LanguageMode = _read_language()


# =============================================================================
# Translation dictionary
#   key → {"th": "...", "en": "..."}
# =============================================================================
TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- Disclaimer (fixed text — ไม่ดึงจากผลวิเคราะห์) ---
    "disclaimer": {
        "th": "ℹ️ หมายเหตุ: ผลนี้เป็นเครื่องมือคัดกรองเบื้องต้น ไม่ใช่การวินิจฉัยขั้นสุดท้าย",
        "en": "ℹ️ Disclaimer: This is a preliminary screening tool, not a final diagnosis.",
    },

    # --- Headers (5-class) ---
    "header_standing_estrus": {
        "th": "ตรวจพบการเป็นสัด (Standing Estrus)",
        "en": "Standing Estrus Detected",
    },
    "header_pre_estrus": {
        "th": "ระยะก่อนเป็นสัด (Pre-Estrus)",
        "en": "Pre-Estrus Phase",
    },
    "header_post_estrus": {
        "th": "ระยะหลังเป็นสัด (Post-Estrus)",
        "en": "Post-Estrus Phase",
    },
    "header_non_estrus": {
        "th": "ยังไม่พบสัญญาณการเป็นสัด (Non-Estrus)",
        "en": "No Estrus Signs Detected",
    },
    "header_false_estrus": {
        "th": "สงสัยเป็นสัดเทียม / ความผิดปกติ",
        "en": "False Estrus or Pathology Suspected",
    },

    # --- Pig type labels ---
    "pig_type_label": {
        "th": "ประเภทที่เลือก",
        "en": "Selected pig type",
    },
    "pig_type_gilt": {
        "th": "หมูสาว (Gilt)",
        "en": "Gilt",
    },
    "pig_type_sow": {
        "th": "หมูนาง (Sow)",
        "en": "Sow",
    },

    # --- Section titles ---
    "section_signs": {
        "th": "📋 ผลการประเมินอาการ",
        "en": "📋 Observed Signs",
    },
    "section_action": {
        "th": "🎯 คำแนะนำ",
        "en": "🎯 Recommended Action",
    },
    "section_meta": {
        "th": "🔬 รายละเอียดเชิงเทคนิค",
        "en": "🔬 Technical Details",
    },

    # --- Sign field labels ---
    "label_swelling": {"th": "บวมที่อวัยวะเพศ", "en": "Vulva swelling"},
    "label_color": {"th": "สีของอวัยวะเพศ", "en": "Vulva color"},
    "label_clitoris": {"th": "อาการที่คลิตอริส", "en": "Clitoris"},
    "label_mucus": {"th": "เมือก / สิ่งคัดหลั่ง", "en": "Mucus / discharge"},
    "label_tail": {"th": "ลักษณะของหาง", "en": "Tail position"},
    "label_behavior": {"th": "พฤติกรรม", "en": "Behavior"},
    "label_image_quality": {"th": "คุณภาพภาพ", "en": "Image quality"},
    "label_visibility": {"th": "อุปสรรคในการมองเห็น", "en": "Visibility issues"},
    "label_confidence": {"th": "ความเชื่อมั่น", "en": "Confidence"},
    "label_reasoning": {"th": "เหตุผลโดยสรุป", "en": "Reasoning"},

    # --- Action templates ---
    "action_standing_estrus": {
        "th": (
            "  • แจ้งทีมผสมพันธุ์ทันที\n"
            "  • ทำ Back-pressure test (BPT) ยืนยัน\n"
            "  • ใช้พ่อพันธุ์เทียบ (boar exposure)\n"
            "  • หากยืนยันได้ → ผสมตามโปรโตคอลของฟาร์ม"
        ),
        "en": (
            "  • Alert breeding technician immediately\n"
            "  • Perform Back-pressure test (BPT) for confirmation\n"
            "  • Use boar exposure for verification\n"
            "  • If confirmed → inseminate per farm protocol"
        ),
    },
    # --- Standing Estrus: Gilt (ผสมเลย) ---
    "action_standing_estrus_gilt": {
        "th": "  • ผสมพันธุ์ได้เลย",
        "en": "  • Inseminate immediately.",
    },
    # --- Standing Estrus: Sow เช้า (ผสมบ่าย) ---
    "action_standing_estrus_sow_morning": {
        "th": "  • ตรวจพบช่วงเช้า → ผสมช่วงบ่าย",
        "en": "  • Detected in morning → Inseminate in the afternoon.",
    },
    # --- Standing Estrus: Sow บ่าย (ผสมพรุ่งนี้เช้า) ---
    "action_standing_estrus_sow_afternoon": {
        "th": "  • ตรวจพบช่วงบ่าย → ผสมพรุ่งนี้เช้า",
        "en": "  • Detected in afternoon → Inseminate tomorrow morning.",
    },
    "action_pre_estrus": {
        "th": (
            "  • เฝ้าสังเกตอย่างใกล้ชิด\n"
            "  • ตรวจซ้ำใน 6-12 ชั่วโมง\n"
            "  • เตรียมพ่อพันธุ์ / อุปกรณ์ให้พร้อม"
        ),
        "en": (
            "  • Monitor closely\n"
            "  • Recheck within 6-12 hours\n"
            "  • Prepare boar and equipment"
        ),
    },
    "action_post_estrus": {
        "th": (
            "  • บันทึกว่าอาจพลาดช่วงเป็นสัดไปแล้ว\n"
            "  • ติดตามรอบการเป็นสัดต่อไป"
        ),
        "en": (
            "  • Record likely missed estrus window\n"
            "  • Continue cycle tracking"
        ),
    },
    "action_non_estrus": {
        "th": (
            "  • ไม่ต้องผสมในรอบนี้\n"
            "  • ติดตามการเปลี่ยนแปลงในวันถัดไป"
        ),
        "en": (
            "  • No breeding action required\n"
            "  • Continue routine monitoring"
        ),
    },
    "action_false_estrus": {
        "th": (
            "  • ห้ามผสมโดยอาศัยภาพเพียงอย่างเดียว\n"
            "  • ขอการยืนยันด้วยมือจากทีมงาน\n"
            "  • ปรึกษาสัตวแพทย์\n"
            "  • ตรวจคุณภาพอาหาร / ความเสี่ยง mycotoxin"
        ),
        "en": (
            "  • Do NOT inseminate based on image alone\n"
            "  • Request manual confirmation\n"
            "  • Consult veterinarian\n"
            "  • Check feed quality / mycotoxin risk"
        ),
    },

    # --- Misc ---
    "no_issues": {"th": "ไม่มี", "en": "None"},
    "record_id": {"th": "Record ID", "en": "Record ID"},
    "low_confidence_warning": {
        "th": "⚠️ ความเชื่อมั่นต่ำ — ภาพอาจไม่ชัดเจนพอ กรุณาถ่ายรูปใหม่หรือยืนยันด้วยการตรวจด้วยมือ",
        "en": "⚠️ Low confidence — Image may not be clear enough. Please retake or confirm manually.",
    },
    "poor_image_warning": {
        "th": "⚠️ คุณภาพภาพต่ำ — ผลอาจคลาดเคลื่อน กรุณาถ่ายรูปใหม่เพื่อยืนยัน",
        "en": "⚠️ Poor image quality — Results may be inaccurate. Please retake photo to confirm.",
    },
    "error_analysis": {
        "th": "❌ เกิดข้อผิดพลาดในการวิเคราะห์\n",
        "en": "❌ Analysis error\n",
    },
    "error_retry": {
        "th": "กรุณาลองส่งรูปใหม่อีกครั้ง",
        "en": "Please send a new image and try again.",
    },
    "bad_image_header": {
        "th": "⚠️ ภาพไม่ชัดเจนพอจะวิเคราะห์ได้",
        "en": "⚠️ Image quality insufficient for analysis",
    },
    "bad_image_tips": {
        "th": (
            "กรุณาถ่ายรูปใหม่โดยให้:\n"
            "  • เห็นบริเวณอวัยวะเพศชัดเจน\n"
            "  • แสงเพียงพอ ไม่มืดเกินไป\n"
            "  • ระยะใกล้พอ ไม่เบลอ"
        ),
        "en": (
            "Please retake the photo ensuring:\n"
            "  • Clear view of the genital area\n"
            "  • Adequate lighting\n"
            "  • Close enough, not blurred"
        ),
    },
}


# =============================================================================
# Enum value translations (ค่า observed_signs)
# =============================================================================
ENUM_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "swelling": {
        "none":     {"th": "ปกติ / ไม่บวม", "en": "Normal / no swelling"},
        "mild":     {"th": "บวมเล็กน้อย", "en": "Mild swelling"},
        "moderate": {"th": "บวมปานกลาง", "en": "Moderate swelling"},
        "severe":   {"th": "บวมมาก / เต่งตึง", "en": "Severe / turgid"},
        "unclear":  {"th": "ไม่ชัดเจน", "en": "Unclear"},
    },
    "color": {
        "pale":     {"th": "ชมพูซีด / สีปกติ", "en": "Pale / normal"},
        "pink":     {"th": "ชมพูสด", "en": "Bright pink"},
        "red":      {"th": "แดง", "en": "Red"},
        "dark red": {"th": "แดงเข้ม", "en": "Dark red"},
        "unclear":  {"th": "ไม่ชัดเจน", "en": "Unclear"},
    },
    "clitoris": {
        "hidden":              {"th": "ปกติ ไม่เห็น", "en": "Hidden / normal"},
        "mildly swollen":      {"th": "บวมเล็กน้อย", "en": "Mildly swollen"},
        "engorged protruding": {"th": "บวมแดง โผล่ชัด", "en": "Engorged, protruding"},
        "unclear":             {"th": "ไม่ชัดเจน", "en": "Unclear"},
    },
    "mucus": {
        "none":               {"th": "ไม่มี", "en": "None"},
        "clear watery":       {"th": "ใส คล้ายน้ำ", "en": "Clear, watery"},
        "cloudy sticky":      {"th": "ขุ่น เหนียว", "en": "Cloudy, sticky"},
        "dry residue":        {"th": "แห้ง คราบขาว", "en": "Dry residue"},
        "abnormal discharge": {"th": "ผิดปกติ (อาจมีการอักเสบ)", "en": "Abnormal discharge (possible inflammation)"},
        "unclear":            {"th": "ไม่ชัดเจน", "en": "Unclear"},
    },
    "tail": {
        "clamped":            {"th": "แนบลำตัว", "en": "Clamped"},
        "slightly raised":    {"th": "ยกขึ้นเล็กน้อย", "en": "Slightly raised"},
        "lifted":             {"th": "ยกขึ้น", "en": "Lifted"},
        "flicking-quivering": {"th": "ยกขึ้น สะบัด / สั่น", "en": "Lifted, flicking / quivering"},
        "unclear":            {"th": "ไม่ชัดเจน", "en": "Unclear"},
    },
    "behavior": {
        "calm":                       {"th": "สงบ ปกติ", "en": "Calm"},
        "restless":                   {"th": "กระสับกระส่าย", "en": "Restless"},
        "boar-seeking":               {"th": "หาพ่อพันธุ์", "en": "Boar-seeking"},
        "standing reflex observed":   {"th": "ยืนนิ่ง (Standing reflex)", "en": "Standing reflex observed"},
        "not available":              {"th": "ไม่สามารถประเมินจากภาพ", "en": "Not available"},
    },
    "confidence": {
        "low":    {"th": "ต่ำ", "en": "Low"},
        "medium": {"th": "ปานกลาง", "en": "Medium"},
        "high":   {"th": "สูง", "en": "High"},
    },
    "image_quality": {
        "good": {"th": "ดี", "en": "Good"},
        "fair": {"th": "พอใช้", "en": "Fair"},
        "poor": {"th": "ไม่ชัดเจน", "en": "Poor"},
    },
}


# =============================================================================
# Public API
# =============================================================================
def _render(th: str, en: str, *, inline: bool = False) -> str:
    """
    Combine TH/EN per current LANGUAGE mode.

    Args:
        inline: True = inline format (`TH | EN`) สำหรับ label/value สั้นๆ
                False = multi-line (`TH\\nEN`) สำหรับข้อความยาว
    """
    if LANGUAGE == "TH":
        return th
    if LANGUAGE == "EN":
        return en
    # THEN
    if inline:
        return f"{th} | {en}"
    return f"{th}\n{en}"


def t(key: str, *, inline: bool = False) -> str:
    """Translate a top-level key."""
    entry = TRANSLATIONS.get(key)
    if entry is None:
        logger.warning(f"⚠️ Missing translation key: {key}")
        return f"[{key}]"
    return _render(entry["th"], entry["en"], inline=inline)


def te(category: str, value: str) -> str:
    """
    Translate an enum value within a category (always inline format for THEN).

    Args:
        category: 'swelling' | 'color' | 'clitoris' | 'mucus' | 'tail' |
                  'behavior' | 'confidence' | 'image_quality'
        value:    enum value จาก VLM
    """
    cat = ENUM_TRANSLATIONS.get(category)
    if cat is None:
        return value or "-"
    entry = cat.get(value)
    if entry is None:
        return value or "-"
    return _render(entry["th"], entry["en"], inline=True)


def current_language() -> LanguageMode:
    """ใช้ตอน debug / unit test"""
    return LANGUAGE
