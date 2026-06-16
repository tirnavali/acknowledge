"""Shared caption prompt, JSON parser, and placeholder sanitizer.

Used by both `CaptionService` (Qwen2.5-VL via transformers) and
`OllamaCaptionService` (Gemma4 via Ollama HTTP) so prompt + output
contract stays identical across backends.
"""
from __future__ import annotations
import json
import logging
import re

logger = logging.getLogger(__name__)


# JSON schema sent to Ollama's `format` parameter for structured output.
# Equivalent to what pydantic would generate — kept as a plain dict to avoid
# the PySide6/shiboken ↔ pydantic v2 circular-import conflict at module load time.
CAPTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "caption_tr": {"type": "string", "description": "20-40 kelimelik Türkçe sahne betimleme cümlesi"},
        "tags_tr": {"type": "string", "description": "Virgülle ayrılmış 5-8 aranabilir etiket"},
    },
    "required": ["caption_tr", "tags_tr"],
}


def get_combined_prompt(person_names: list[str] = None) -> str:
    names_instruction = ""
    if person_names:
        names_str = ", ".join(person_names)
        names_instruction = (
            "Fotoğrafdaki kişiler: " + names_str + ". "
            "Bu isimleri Türkçe açıklamada doğal bir şekilde kullan. "
        )

    example = json.dumps({
        "caption_tr": "Bir konuşmacı arkasında Türk bayrağı bulunan kürsüde konuşma yapıyor, önde oturan dinleyiciler izliyor.",
        "tags_tr": "konuşma, kürsü, türk bayrağı, dinleyiciler, resmi toplantı, kapalı mekan",
    }, ensure_ascii=False)

    return (
        "Aşağıdaki fotoğrafı Türkçe olarak belgele. "
        "Sadece aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma. "
        + names_instruction
        + "Kurallar: "
        "- Yalnızca açıkça görünen şeyleri yaz; tahmin etme, çıkarım yapma. "
        "- Giysi veya kravat rengini ancak kesinlikle emin olduğunda belirt; emin değilsen rengi hiç yazma. "
        "- ‘bu fotoğrafta’, ‘fotoğrafta görülen’, ‘yer aldığı’, ‘vurgulanıyor’, ‘dikkat çekiyor’ "
        "gibi meta ifadeler kullanma; sahneyi doğrudan betimle. "
        "- ‘ihtişamlı’, ‘etkileyici’, ‘şık’, ‘görkemli’ gibi öznel/süslü sıfatlar kullanma; "
        "yalnızca gözlemlenebilir olgular. "
        "- Mekanı (parlamento salonu, ofis, bahçe vb.), kişi sayısını, rollerini "
        "(konuşmacı, milletvekili, dinleyici vb.) ve öne çıkan nesneleri (kürsü, bayrak, masa vb.) yaz. "
        "- Arka planı ve ortamı mutlaka betimle: duvarlar, perdeler, avize, mobilya, bayraklar, "
        "tablo/çerçeveler ve genel mekan karakteri (büyük salon, küçük oda, açık alan vb.) dahil. "
        "- Kişilerin kıyafetlerini betimle: takım elbise, gömlek, ceket, kravat, resmi/spor vb. "
        "(rengi yalnızca kesinlikle eminsen yaz; emin değilsen rengi hiç yazma). "
        "- Ortam bir meclis veya parlamento salonu ise, mümkünse bunu belirt. "
        "- İsimler verilmemişse ‘bir konuşmacı’, ‘bir yetkili’ gibi genel ifadeler kullan. "
        "- caption_tr: 25-45 kelimelik, gerektiğinde birden fazla cümle, doğrudan betimleme. "
        "- tags_tr: en fazla 8 adet virgülle ayrılmış kısa etiket (mekan, rol, nesne vb.). "
        "JSON dışında hiçbir metin yazma.\n"
        + example
    )



# Placeholder tokens VLMs leak from their redacted training data
# despite explicit prompt instructions ("never write <NAME>").
_PLACEHOLDER_RE = re.compile(
    r'<\s*(?:NAME|PERSON|İSİM|ISIM|isim|name|person)\s*>'
    r'|\[\s*(?:NAME|PERSON|isim|name|İSİM|ISIM|person)\s*\]'
    r'|_{3,}',
    flags=re.IGNORECASE,
)


def sanitize_placeholders(text: str, person_names: list[str] = None, replacement: str = "bir kişi", capitalize_first: bool = True) -> str:
    """Replace <NAME>/<PERSON>/[isim]/___ leaks with generic roles or actual names.

    capitalize_first: True for sentence-like captions, False for tag lists
    (otherwise "a, b, c" becomes "A, b, c").
    """
    if not text:
        return text

    if person_names:
        # Resolve placeholders with detected name list in order
        matches = list(_PLACEHOLDER_RE.finditer(text))
        if matches:
            new_text = text
            # Replace in reverse order so string indices do not shift
            for i, match in reversed(list(enumerate(matches))):
                if i < len(person_names):
                    rep = person_names[i]
                else:
                    rep = replacement
                start, end = match.span()
                new_text = new_text[:start] + rep + new_text[end:]
            text = new_text

    cleaned = _PLACEHOLDER_RE.sub(replacement, text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\s+([.,;:!?])', r'\1', cleaned)
    if capitalize_first and cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _coerce_str(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val) if val is not None else ""


def parse_combined_response(raw: str, person_names: list[str] = None) -> tuple[str, str]:
    """Extract (caption_tr, tags_tr) from a model JSON response.

    Handles four cases:
    1. Clean JSON  → standard json.loads + Pydantic validation
    2. Markdown-fenced JSON (```json ... ```) → strip fence then parse
    3. Truncated JSON (max_new_tokens hit before closing brace or quote)
       → extract field values directly via regex so nothing is lost

    All returned strings pass through `sanitize_placeholders`.
    """
    stripped = re.sub(r'^```[a-z]*\s*', '', raw.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r'```\s*$', '', stripped).strip()

    try:
        # Pre-clean trailing commas commonly generated by LLMs in objects and arrays
        cleaned = re.sub(r',\s*\}', '}', stripped)
        cleaned = re.sub(r',\s*\]', ']', cleaned)
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group())
            
            # Map alternative keys from model generation
            caption_val = data.get("caption_tr") or data.get("caption") or ""
            tags_val = data.get("tags_tr") or data.get("tags_tr_") or data.get("tags") or ""
            
            # Coerce list/array values to comma-separated string
            caption_str = _coerce_str(caption_val).strip()
            tags_str = _coerce_str(tags_val).strip()
            
            if caption_str or tags_str:
                return (
                    sanitize_placeholders(caption_str, person_names),
                    sanitize_placeholders(tags_str, person_names, replacement="kişi", capitalize_first=False),
                )
    except Exception:
        pass

    # Fallback to regex parsing for malformed or truncated JSON
    caption_tr = ""
    tags_tr = ""

    # Try to extract caption_tr or alternate keys
    for key in ["caption_tr", "caption"]:
        m = re.search(rf'"{key}"\s*:\s*"(.*?)"', stripped, re.DOTALL)
        if m:
            caption_tr = m.group(1).strip()
            break
        else:
            m = re.search(rf'"{key}"\s*:\s*"(.*)', stripped, re.DOTALL)
            if m:
                val = m.group(1).strip()
                for alt_key in ["tags_tr", "tags_tr_", "tags"]:
                    if f'"{alt_key}"' in val:
                        val = val.split(f'"{alt_key}"')[0].strip()
                val = re.sub(r'["\s,]+$', '', val)
                caption_tr = val
                break

    # Try to extract tags_tr or alternate keys
    for key in ["tags_tr", "tags_tr_", "tags"]:
        m = re.search(rf'"{key}"\s*:\s*"(.*?)"', stripped, re.DOTALL)
        if m:
            tags_tr = m.group(1).strip()
            break
        else:
            m = re.search(rf'"{key}"\s*:\s*"(.*)', stripped, re.DOTALL)
            if m:
                val = m.group(1).strip()
                val = re.sub(r'["\}\s,]+$', '', val)
                tags_tr = val
                break

    if caption_tr:
        logger.debug("caption_parsing: partial JSON recovered via regex for raw: %s", raw[:80])
        return (
            sanitize_placeholders(caption_tr, person_names),
            sanitize_placeholders(tags_tr, person_names, replacement="kişi", capitalize_first=False),
        )

    logger.warning("caption_parsing: JSON parse failed, raw response: %s", raw[:200])
    return "", ""
