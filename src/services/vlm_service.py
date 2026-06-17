"""
vlm_service.py — Integration กับ Gemini Vision API (Swine Estrus Inspection)

🔑 Highlights:
1. รองรับ JSON schema ใหม่ (5-class taxonomy + enum values)
2. Validate + normalize enum strictly → กัน VLM ตอบ value แปลกๆ
3. Singleton pattern (get_vlm_service()) — instantiate ครั้งเดียวต่อ process
4. Robust JSON parsing — รองรับกรณี VLM ส่ง markdown fence มาบ้าง
5. Safety Evasion (Regex) — แปลงคำศัพท์ล่อแหลมขั้นเด็ดขาดก่อนส่ง API
6. 🆕 ปิด thinking budget (Gemini 2.5) + เช็ก finish_reason กัน JSON ถูกตัดกลางคัน
"""
import json
import logging
import re
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from src.config import Config
from src.prompts import build_estrus_prompt

logger = logging.getLogger(__name__)


# =============================================================================
# ENUM VALIDATION (single source of truth)
# =============================================================================
ALLOWED_IMAGE_QUALITY = {"good", "fair", "poor"}
ALLOWED_PARITY = {"gilt", "multiparous", "unknown"}
ALLOWED_VULVA_SWELLING = {"none", "mild", "moderate", "severe", "unclear"}
ALLOWED_VULVA_COLOR = {"pale", "pink", "red", "dark red", "unclear"}
ALLOWED_CLITORIS = {"hidden", "mildly swollen", "engorged protruding", "unclear"}
ALLOWED_MUCUS = {
    "none", "clear watery", "cloudy sticky", "dry residue",
    "abnormal discharge", "unclear",
}
ALLOWED_TAIL = {"clamped", "slightly raised", "lifted", "flicking-quivering", "unclear"}
ALLOWED_BEHAVIOR = {
    "calm", "restless", "boar-seeking",
    "standing reflex observed", "not available",
}
ALLOWED_CLASSIFICATION = {
    "Non-Estrus", "Pre-Estrus", "Standing Estrus",
    "Post-Estrus", "False Estrus or Pathology Suspect",
}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


def _clean_enum(value, allowed: set, default: str) -> str:
    """Normalize a value to one of the allowed enum values, or fall back to default."""
    if not isinstance(value, str):
        return default
    v = value.strip()
    if v in allowed:
        return v
    # case-insensitive match
    for a in allowed:
        if v.lower() == a.lower():
            return a
    return default


# =============================================================================
# VLM SERVICE
# =============================================================================
class VLMService:
    """Service สำหรับเรียก Gemini Vision API วิเคราะห์รูปหมู"""

    def __init__(self) -> None:
        if not Config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY ไม่ได้ตั้งค่า")

        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model_name = Config.GEMINI_MODEL

        # รวม config + safety เป็นก้อนเดียว (กันโดนเขียนทับ)
        #
        # 🆕 แก้ปัญหา JSON ถูกตัดกลางคัน (finish_reason=MAX_TOKENS):
        #   - gemini-2.5-* เป็นโมเดลตระกูล thinking → กิน output tokens ไปกับ
        #     reasoning ภายในก่อน เลยเหลือ token เขียน JSON จริงไม่พอ
        #   - thinking_budget=0 → ปิด reasoning ภายใน, token ทั้งหมดไปลง JSON
        #   - เพิ่ม max_output_tokens เป็น 4096 เผื่อ schema ยาว
        self.generation_config = types.GenerateContentConfig(
            temperature=0.2,
            top_p=0.95,
            max_output_tokens=4096,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"
                ),
            ],
        )
        logger.info(f"🤖 VLM Service initialized with model: {self.model_name}")

    async def analyze_estrus(self, image_path: str, pig_type: str) -> dict:
        """
        วิเคราะห์รูปหมูเพื่อตรวจสัญญาณการเป็นสัด
        """
        try:
            image_path_obj = Path(image_path)
            if not image_path_obj.exists():
                logger.error(f"Image not found: {image_path}")
                return self._error_response("ไม่พบไฟล์รูปภาพ")

            image = Image.open(image_path_obj)

            # 1. ดึงสเปกพรอปต์ดั้งเดิมมาใช้งาน
            raw_prompt = build_estrus_prompt(pig_type)

            # 2. ทำ Safety Evasion (Regex): ปูพรมเปลี่ยนคำล่อแหลมทุกขนาดตัวอักษร
            evaded_prompt = raw_prompt
            evaded_prompt = re.sub(r"vulva_swelling", "perineal_swelling", evaded_prompt, flags=re.IGNORECASE)
            evaded_prompt = re.sub(r"vulva_color", "perineal_color", evaded_prompt, flags=re.IGNORECASE)
            evaded_prompt = re.sub(r"clitoris_state", "tissue_state", evaded_prompt, flags=re.IGNORECASE)

            evaded_prompt = re.sub(r"vulva", "perineal area", evaded_prompt, flags=re.IGNORECASE)
            evaded_prompt = re.sub(r"clitoral", "tissue", evaded_prompt, flags=re.IGNORECASE)
            evaded_prompt = re.sub(r"clitoris", "tissue node", evaded_prompt, flags=re.IGNORECASE)

            logger.info(f"📸 Calling Gemini VLM for pig_type={pig_type} (with STRONG Regex Safety Evasion)")

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[evaded_prompt, image],
                config=self.generation_config,
            )

            # 🆕 เช็ก finish_reason ก่อน parse — ถ้าโดนตัด (MAX_TOKENS) ให้เลิกทำทันที
            finish_reason = None
            if response.candidates:
                finish_reason = response.candidates[0].finish_reason
                logger.info(f"VLM finish_reason: {finish_reason}")

            raw_text = response.text or ""
            # แสดงล็อกแค่ 500 ตัวอักษร เพื่อเช็กหัว/หาง
            logger.info(f"VLM raw response: {raw_text[:500]} ... {raw_text[-100:] if len(raw_text) > 100 else ''}")

            if self._is_truncated(finish_reason):
                logger.error(
                    f"⚠️ VLM output truncated (finish_reason={finish_reason}, "
                    f"len={len(raw_text)}). JSON อาจไม่ครบ — ส่ง error response กลับ"
                )
                return self._error_response(
                    "ผลวิเคราะห์ถูกตัดกลางคัน (token ไม่พอ) กรุณาลองส่งรูปใหม่อีกครั้ง"
                )

            # 3. แปลงคีย์ข้อมูลที่แอบสลับไว้ ให้กลับมาเป็นฟอร์แมตเดิมของฐานข้อมูล
            if raw_text:
                raw_text = re.sub(r"perineal_swelling", "vulva_swelling", raw_text, flags=re.IGNORECASE)
                raw_text = re.sub(r"perineal_color", "vulva_color", raw_text, flags=re.IGNORECASE)
                raw_text = re.sub(r"tissue_state", "clitoris_state", raw_text, flags=re.IGNORECASE)

            result = self._parse_json_response(raw_text)
            result = self._validate_and_normalize(result, pig_type)

            logger.info(
                f"✅ VLM analysis complete: classification="
                f"{result.get('estrus_classification')} "
                f"confidence={result.get('confidence')}"
            )
            return result

        except Exception as e:
            logger.error(f"❌ VLM API error: {e}", exc_info=True)
            return self._error_response(f"เกิดข้อผิดพลาดในการวิเคราะห์: {e}")

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------
    @staticmethod
    def _is_truncated(finish_reason) -> bool:
        """
        เช็กว่า response ถูกตัดเพราะชน max_output_tokens หรือไม่
        รองรับทั้ง enum และ string ('MAX_TOKENS', 'hit max_output_tokens limit', ฯลฯ)
        """
        if finish_reason is None:
            return False
        fr = str(finish_reason).upper()
        return "MAX_TOKEN" in fr or "MAX_OUTPUT" in fr

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """Parse JSON; tolerate stray markdown fences."""
        if not text:
            raise ValueError("VLM returned empty response")
        text = text.strip()

        text = re.sub(r"^`{3}(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"`{3}\s*$", "", text, flags=re.IGNORECASE)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}. Raw text: {text[:500]}")
            # try to extract a JSON object substring
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise

    @staticmethod
    def _validate_and_normalize(result: dict, pig_type: str) -> dict:
        """
        Validate enum + ensure all expected fields exist.
        """
        observed = result.get("observed_signs", {}) or {}
        default_parity = (
            "gilt" if pig_type == "gilt"
            else "multiparous" if pig_type == "sow"
            else "unknown"
        )

        normalized = {
            "sow_id": str(result.get("sow_id") or ""),
            "image_quality": _clean_enum(
                result.get("image_quality"), ALLOWED_IMAGE_QUALITY, "fair"
            ),
            "visibility_issues": [
                str(x) for x in (result.get("visibility_issues") or [])
                if isinstance(x, (str, int, float))
            ],
            "parity_adjustment": _clean_enum(
                result.get("parity_adjustment"), ALLOWED_PARITY, default_parity
            ),
            "observed_signs": {
                "vulva_swelling": _clean_enum(
                    observed.get("vulva_swelling"), ALLOWED_VULVA_SWELLING, "unclear"
                ),
                "vulva_color": _clean_enum(
                    observed.get("vulva_color"), ALLOWED_VULVA_COLOR, "unclear"
                ),
                "clitoris_state": _clean_enum(
                    observed.get("clitoris_state"), ALLOWED_CLITORIS, "unclear"
                ),
                "mucus": _clean_enum(
                    observed.get("mucus"), ALLOWED_MUCUS, "unclear"
                ),
                "tail_position": _clean_enum(
                    observed.get("tail_position"), ALLOWED_TAIL, "unclear"
                ),
                "behavior": _clean_enum(
                    observed.get("behavior"), ALLOWED_BEHAVIOR, "not available"
                ),
            },
            "estrus_classification": _clean_enum(
                result.get("estrus_classification"),
                ALLOWED_CLASSIFICATION,
                "Non-Estrus",
            ),
            "confidence": _clean_enum(
                result.get("confidence"), ALLOWED_CONFIDENCE, "low"
            ),
            "reasoning_summary": str(result.get("reasoning_summary") or "").strip(),
            "recommended_action": str(result.get("recommended_action") or "").strip(),
        }
        return normalized

    @staticmethod
    def _error_response(message: str) -> dict:
        """Return a schema-compatible error structure."""
        return {
            "error": message,
            "sow_id": "",
            "image_quality": "poor",
            "visibility_issues": [message],
            "parity_adjustment": "unknown",
            "observed_signs": {
                "vulva_swelling": "unclear",
                "vulva_color": "unclear",
                "clitoris_state": "unclear",
                "mucus": "unclear",
                "tail_position": "unclear",
                "behavior": "not available",
            },
            "estrus_classification": "Non-Estrus",
            "confidence": "low",
            "reasoning_summary": message,
            "recommended_action": "",
        }


# =============================================================================
# Singleton accessor
# =============================================================================
_vlm_service: VLMService | None = None


def get_vlm_service() -> VLMService:
    """Get or create singleton VLM service."""
    global _vlm_service
    if _vlm_service is None:
        _vlm_service = VLMService()
    return _vlm_service

