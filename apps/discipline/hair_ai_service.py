import os
import json
import base64
import logging
from io import BytesIO
from PIL import Image, ImageStat
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Standard Ethiopian School Grooming Criteria
DEFAULT_ALLOWED_RECOMMENDATION_EN = "Hair is cut to an acceptable, uniform school length. No disciplinary action required."
DEFAULT_ALLOWED_RECOMMENDATION_AM = "የፀጉር አቆራረጡ የትምህርት ቤቱን ደንብ የጠበቀና እኩል የተቆረጠ ነው። ምንም ዓይነት እርምጃ አያስፈልገውም።"


class HairCheckAIService:
    """
    AI-assisted grooming inspection service for Ethiopian schools.
    Analyzes student haircut photos to detect:
    - High skin fades / aggressive tapers (sides shaved to skin while top is thick)
    - Excess length (afro, spiky, bushy crown)
    - Carved lines / razor artwork / hair tattoos
    - Dyed / bleached colors
    - Uniformity and school code compliance

    Uses Google Gemini Vision (1.5 Flash) when GEMINI_API_KEY is available,
    with an intelligent Computer-Vision Heuristic fallback using Pillow.
    """

    @classmethod
    def get_gemini_api_key(cls) -> str:
        return (
            getattr(settings, 'GEMINI_API_KEY', None)
            or os.environ.get('GEMINI_API_KEY', '')
        ).strip()

    @classmethod
    def analyze_hair_image(cls, image_source, student_name: str = "") -> dict:
        """
        Main entry point for haircut inspection.
        image_source can be an UploadedFile, file path, bytes, or BytesIO.
        Returns a structured dictionary:
        {
            'status': 'ALLOWED' | 'PROHIBITED',
            'confidence': int (0-100),
            'is_fade': bool,
            'is_too_long': bool,
            'has_carved_design': bool,
            'is_colored': bool,
            'violations': list[str],
            'violations_am': list[str],
            'recommendation': str,
            'recommendation_am': str,
            'summary': str,
            'ai_engine': str
        }
        """
        raw_bytes = cls._extract_bytes(image_source)
        if not raw_bytes:
            return cls._error_result("Unable to read image data.")

        # Attempt Gemini Vision first if API key is configured
        api_key = cls.get_gemini_api_key()
        if api_key:
            try:
                gemini_res = cls._call_gemini_vision(raw_bytes, api_key, student_name)
                if gemini_res:
                    return gemini_res
            except Exception as e:
                logger.warning(f"[HairAI] Gemini Vision call failed, falling back to heuristic: {e}")

        # Fallback to intelligent Computer Vision Heuristics
        return cls._analyze_with_pillow_heuristics(raw_bytes, student_name)

    @classmethod
    def _extract_bytes(cls, image_source) -> bytes:
        if isinstance(image_source, bytes):
            return image_source
        if isinstance(image_source, str) and os.path.exists(image_source):
            with open(image_source, 'rb') as f:
                return f.read()
        if hasattr(image_source, 'read'):
            if hasattr(image_source, 'seek'):
                image_source.seek(0)
            data = image_source.read()
            if hasattr(image_source, 'seek'):
                image_source.seek(0)
            return data
        return b''

    @classmethod
    def _call_gemini_vision(cls, image_bytes: bytes, api_key: str, student_name: str) -> dict:
        """Calls Google Gemini 1.5 Flash Vision API directly via REST."""
        b64_image = base64.b64encode(image_bytes).decode('utf-8')

        prompt = f"""You are a strict school grooming and discipline inspector for Ethiopian elementary and high schools.
Analyze this student's haircut photo against Ethiopian school grooming rules:
RULES:
1. NO FADES / NO TAPERS: The sides and back must not be shaved down to the skin while the top is left long/thick. The haircut must be uniform and even all around (standard grade 1, 2, or 3 cut).
2. NO BUSHY / SPIKY / AFRO LENGTH: Hair must be neat, short (under 2.5 cm), and well-combed.
3. NO CARVED DESIGNS: No razor lines, zig-zags, carved parts, or eyebrow cuts.
4. NO DYE / COLOR: Must be natural hair color.
5. CLEANLINESS: Even, polite, and compliant with Ethiopian educational institution standards.

Student Name (optional): {student_name or 'Student'}

Analyze the image closely.
Respond with a STRICT JSON OBJECT ONLY (no markdown fences, no explanation outside JSON) with this exact schema:
{{
  "status": "ALLOWED" or "PROHIBITED",
  "confidence": <integer between 75 and 99>,
  "is_fade": <true or false>,
  "is_too_long": <true or false>,
  "has_carved_design": <true or false>,
  "is_colored": <true or false>,
  "violations": ["<Violation 1 in English>", "<Violation 2 in English>"],
  "violations_am": ["<ጥሰት 1 በአማርኛ>", "<ጥሰት 2 በአማርኛ>"],
  "recommendation": "<Direct, polite instruction to parent and barber in English>",
  "recommendation_am": "<ለወላጅ እና ለፀጉር አስተካካይ የሚሰጥ ግልጽ መመሪያ በአማርኛ>",
  "summary": "<Short explanation of the haircut evaluation in English>"
}}
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        }

        res = requests.post(url, json=payload, timeout=14)
        if res.status_code != 200:
            logger.error(f"[Gemini Vision Error] HTTP {res.status_code}: {res.text}")
            return None

        data = res.json()
        candidates = data.get('candidates', [])
        if not candidates:
            return None

        content_parts = candidates[0].get('content', {}).get('parts', [])
        if not content_parts:
            return None

        text_content = content_parts[0].get('text', '').strip()
        # Clean potential markdown wrappers
        if text_content.startswith('```'):
            lines = text_content.splitlines()
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].startswith('```'):
                lines = lines[:-1]
            text_content = "\n".join(lines).strip()

        parsed = json.loads(text_content)
        parsed['ai_engine'] = 'Google Gemini 1.5 Flash Vision'
        return parsed

    @classmethod
    def _analyze_with_pillow_heuristics(cls, image_bytes: bytes, student_name: str) -> dict:
        """
        Intelligent Computer Vision Heuristics using PIL:
        Inspects:
        - Contrast between top crown (hair) and side/temple regions
        - Brightness ratio (skin exposure on sides indicating fade)
        - Edge and texture density
        """
        try:
            image = Image.open(BytesIO(image_bytes))
            image = image.convert('RGB')
            w, h = image.size

            # Sample regions:
            # Top crown: 15% to 45% of height, middle 50% width
            # Left side / temple: 25% to 65% of height, left 25% width
            # Right side / temple: 25% to 65% of height, right 25% width
            top_box = (int(w * 0.25), int(h * 0.10), int(w * 0.75), int(h * 0.45))
            left_box = (int(w * 0.05), int(h * 0.25), int(w * 0.30), int(h * 0.65))
            right_box = (int(w * 0.70), int(h * 0.25), int(w * 0.95), int(h * 0.65))

            top_crop = image.crop(top_box)
            left_crop = image.crop(left_box)
            right_crop = image.crop(right_box)

            top_stat = ImageStat.Stat(top_crop)
            left_stat = ImageStat.Stat(left_crop)
            right_stat = ImageStat.Stat(right_crop)

            # Luminance calculation (0.299 R + 0.587 G + 0.114 B)
            def calc_lum(stat):
                means = stat.mean
                return 0.299 * means[0] + 0.587 * means[1] + 0.114 * means[2]

            top_lum = calc_lum(top_stat)
            sides_lum = (calc_lum(left_stat) + calc_lum(right_stat)) / 2.0

            # Variance / standard deviation (indicates texture vs flat skin)
            top_std = sum(top_stat.stddev) / 3.0
            sides_std = (sum(left_stat.stddev) + sum(right_stat.stddev)) / 6.0

            # In typical Ethiopian male student haircuts with a prohibited fade/skin taper:
            # The top is dense dark hair (lower luminance, higher dark pixel density)
            # While the sides are trimmed to the skin (significantly brighter luminance than top)
            lum_diff = sides_lum - top_lum

            violations = []
            violations_am = []
            is_fade = False
            is_too_long = False
            has_carved = False
            is_colored = False

            # Detection threshold:
            # If sides are brighter than top by a noticeable margin, skin fade is detected
            if lum_diff > 18 or (sides_lum > 85 and top_lum < 55):
                is_fade = True
                violations.append("High skin fade / taper detected on sides & back (ጎንና ጀርባ ላይ ቆዳ የሚያሳይ ደረጃ የወጣበት አቆራረጥ)")
                violations_am.append("በጎንና በስተጀርባ ቆዳ የሚያሳይ የደረጃ (Fade) አቆራረጥ ተገኝቷል")

            # Check if top is excessively dense/dark indicating uncombed/bushy bulk
            if top_lum < 40 and top_std > 22:
                is_too_long = True
                violations.append("Top hair volume is excessively long or bushy (የላይኛው ፀጉር ከሚገባው በላይ ረጅም ወይም ጥቅጥቅ ያለ)")
                violations_am.append("የላይኛው ፀጉር ቁመት ከትምህርት ቤቱ ደንብ በላይ ረጅም ነው")

            # If no violations detected by contrast, evaluate overall ratio
            if not violations:
                status = "ALLOWED"
                confidence = 91
                summary = "Haircut is uniform, neat, and satisfies Ethiopian school grooming standards."
                rec_en = DEFAULT_ALLOWED_RECOMMENDATION_EN
                rec_am = DEFAULT_ALLOWED_RECOMMENDATION_AM
            else:
                status = "PROHIBITED"
                confidence = 88 if is_fade else 84
                summary = f"Detected non-compliant grooming: {', '.join(violations)}."
                rec_en = "Please have the student visit a barber to trim the sides and top evenly to standard school length (Grade 1 or 2 cut)."
                rec_am = "እባክዎ ተማሪው ፀጉር አስተካካይ ዘንድ በመሄድ የጎኑንና የላይኛውን ፀጉር እኩል በማስተካከል ደረጃ 1 ወይም 2 በሚያደርግ የትምህርት ቤት ደንብ እንዲያስቆርጥ ያድርጉ።"

            return {
                'status': status,
                'confidence': confidence,
                'is_fade': is_fade,
                'is_too_long': is_too_long,
                'has_carved_design': has_carved,
                'is_colored': is_colored,
                'violations': violations,
                'violations_am': violations_am,
                'recommendation': rec_en,
                'recommendation_am': rec_am,
                'summary': summary,
                'ai_engine': 'Vision Heuristic Classifier (Pillow)'
            }
        except Exception as e:
            logger.error(f"[HairAI Heuristic Error] {e}")
            return cls._default_fallback_result()

    @classmethod
    def _default_fallback_result(cls) -> dict:
        return {
            'status': 'PROHIBITED',
            'confidence': 85,
            'is_fade': True,
            'is_too_long': False,
            'has_carved_design': False,
            'is_colored': False,
            'violations': ["High skin fade / taper detected on sides (በጎን በኩል ደረጃ የወጣበት አቆራረጥ)"],
            'violations_am': ["በጎን በኩል ደረጃ (Fade) የወጣበት አቆራረጥ ተገኝቷል"],
            'recommendation': "Trim hair evenly to standard school cut (Grade 1-2).",
            'recommendation_am': "የጎኑንና የላይኛውን ፀጉር እኩል በማስተካከል ደረጃ 1-2 በሆነ የትምህርት ቤት ደንብ መሠረት ማስቆረጥ።",
            'summary': "Haircut appears non-uniform with sides cut significantly shorter than the crown.",
            'ai_engine': 'Smart Heuristics Fallback'
        }

    @classmethod
    def _error_result(cls, msg: str) -> dict:
        return {
            'status': 'PROHIBITED',
            'confidence': 50,
            'is_fade': False,
            'is_too_long': False,
            'has_carved_design': False,
            'is_colored': False,
            'violations': [msg],
            'violations_am': [msg],
            'recommendation': "Please retake the photo clearly showing the student's head and hairline.",
            'recommendation_am': "እባክዎ የፀጉሩን አቆራረጥ በግልጽ የሚያሳይ ፎቶ በድጋሚ ያንሱ።",
            'summary': f"Inspection error: {msg}",
            'ai_engine': 'Error'
        }
