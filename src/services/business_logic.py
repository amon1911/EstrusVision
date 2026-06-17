"""
business_logic.py — Decision rules + Multi-language message composition

🔑 Design (v2):
1. ใช้ i18n.t() / i18n.te() ทุกข้อความ → รองรับ TH / EN / THEN
2. Disclaimer เป็น fixed text จาก i18n (ไม่ดึงจากผลวิเคราะห์)
3. ข้อความ output เป็น plain text — ไม่มี markdown
4. ไม่มี short-circuit bad_image ที่ส่งข้อความ generic ทับผลจริง
   (ถ้า VLM ตอบมาแล้ว ให้แสดงผล + เตือนคุณภาพภาพแทน)
5. คืน AlertResult (dataclass) — typed, immutable, easy to test
"""
import logging
from dataclasses import dataclass
from datetime import datetime

from src.database.models import PH_TZ
from src.utils.i18n import t, te

logger = logging.getLogger(__name__)


# =============================================================================
# Result type
# =============================================================================
@dataclass(frozen=True)
class AlertResult:
    """ผลลัพธ์การประเมิน (immutable)"""
    status: str
    classification: str
    is_estrus: bool
    message: str


# =============================================================================
# Classification → (status_key, emoji, header_i18n_key, action_i18n_key)
# =============================================================================
CLASSIFICATION_MAP: dict[str, tuple[str, str, str, str]] = {
    "Standing Estrus": (
        "standing_estrus", "🚨",
        "header_standing_estrus", "action_standing_estrus",
    ),
    "Pre-Estrus": (
        "pre_estrus", "⚠️",
        "header_pre_estrus", "action_pre_estrus",
    ),
    "Post-Estrus": (
        "post_estrus", "ℹ️",
        "header_post_estrus", "action_post_estrus",
    ),
    "Non-Estrus": (
        "non_estrus", "✅",
        "header_non_estrus", "action_non_estrus",
    ),
    "False Estrus or Pathology Suspect": (
        "false_estrus", "🛑",
        "header_false_estrus", "action_false_estrus",
    ),
}


# =============================================================================
# Section builders
# =============================================================================
def _build_signs_section(signs: dict) -> str:
    """แสดงผลการประเมินอาการ"""
    return (
        f"{t('section_signs')}\n"
        f"  • {t('label_swelling', inline=True)}: {te('swelling', signs.get('vulva_swelling', ''))}\n"
        f"  • {t('label_color', inline=True)}: {te('color', signs.get('vulva_color', ''))}\n"
        f"  • {t('label_clitoris', inline=True)}: {te('clitoris', signs.get('clitoris_state', ''))}\n"
        f"  • {t('label_mucus', inline=True)}: {te('mucus', signs.get('mucus', ''))}\n"
        f"  • {t('label_tail', inline=True)}: {te('tail', signs.get('tail_position', ''))}\n"
        f"  • {t('label_behavior', inline=True)}: {te('behavior', signs.get('behavior', ''))}"
    )


def _build_action_section(action_key: str, pig_type: str = "", classification: str = "") -> str:
    """คำแนะนำตาม classification — แยก gilt/sow สำหรับ Standing Estrus"""
    if classification == "Standing Estrus":
        if pig_type == "gilt":
            action_text = t("action_standing_estrus_gilt")
        else:
            hour = datetime.now(PH_TZ).hour
            if hour < 12:
                action_text = t("action_standing_estrus_sow_morning")
            else:
                action_text = t("action_standing_estrus_sow_afternoon")
    else:
        action_text = t(action_key)
    return f"{t('section_action')}\n{action_text}"


def _build_meta_section(vlm_result: dict) -> str:
    """ข้อมูลคุณภาพภาพ / confidence / reasoning"""
    img_q = te("image_quality", vlm_result.get("image_quality", ""))
    conf = te("confidence", vlm_result.get("confidence", ""))
    issues = vlm_result.get("visibility_issues") or []
    issues_txt = ", ".join(str(x) for x in issues) if issues else t("no_issues", inline=True)
    reasoning = vlm_result.get("reasoning_summary") or "-"

    return (
        f"{t('section_meta')}\n"
        f"  • {t('label_image_quality', inline=True)}: {img_q}\n"
        f"  • {t('label_visibility', inline=True)}: {issues_txt}\n"
        f"  • {t('label_confidence', inline=True)}: {conf}\n"
        f"  • {t('label_reasoning', inline=True)}: {reasoning}"
    )


# =============================================================================
# Public API
# =============================================================================
def generate_alert(vlm_result: dict, pig_type: str) -> AlertResult:
    """สร้างข้อความแจ้งเตือนตามภาษาที่ตั้งไว้ใน .env"""

    # === Error case ===
    if vlm_result.get("error"):
        return AlertResult(
            status="error",
            classification="Non-Estrus",
            is_estrus=False,
            message=(
                f"{t('error_analysis')}"
                f"{vlm_result['error']}\n\n"
                f"{t('error_retry')}"
            ),
        )

    classification = vlm_result.get("estrus_classification", "Non-Estrus")
    signs = vlm_result.get("observed_signs", {}) or {}
    image_quality = vlm_result.get("image_quality", "fair")

    # === Bad image short-circuit (poor + Non-Estrus) ===
    if image_quality == "poor" and classification == "Non-Estrus":
        return AlertResult(
            status="bad_image",
            classification=classification,
            is_estrus=False,
            message=f"{t('bad_image_header')}\n\n{t('bad_image_tips')}",
        )

    # === Map classification ===
    status_key, emoji, header_key, action_key = CLASSIFICATION_MAP.get(
        classification, ("non_estrus", "ℹ️", "header_non_estrus", "action_non_estrus")
    )
    pig_label_key = "pig_type_gilt" if pig_type == "gilt" else "pig_type_sow"

    # === Compose message ===
    parts = [
        f"{emoji} {t(header_key)}",
        f"{t('pig_type_label', inline=True)}: {t(pig_label_key, inline=True)}",
        "",
        _build_signs_section(signs),
        "",
        _build_action_section(action_key, pig_type=pig_type, classification=classification),
        "",
        _build_meta_section(vlm_result),
        "",
        t("disclaimer"),
    ]

    # === เตือน poor image (ไม่ว่า classification จะเป็นอะไร) ===
    if image_quality == "poor":
        parts.append("")
        parts.append(t("poor_image_warning"))

    # === เตือน low confidence ===
    confidence = vlm_result.get("confidence", "")
    if confidence == "low":
        parts.append("")
        parts.append(t("low_confidence_warning"))

    message = "\n".join(parts)

    return AlertResult(
        status=status_key,
        classification=classification,
        is_estrus=(classification == "Standing Estrus"),
        message=message,
    )


def append_record_id(message: str, detection_id: int | None) -> str:
    """ต่อ record id ท้ายข้อความ"""
    if detection_id is None:
        return message
    return f"{message}\n\n📌 {t('record_id')}: #{detection_id}"
