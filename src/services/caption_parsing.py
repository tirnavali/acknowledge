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


# Single combined prompt shared by all caption backends.
# English instructions (Qwen/Gemma both instruction-tuned ~85% English).
# Turkish output (caption_tr, tags_tr) for the media archive UI.
COMBINED_PROMPT = (
    "You are a Turkish media archivist cataloging a press/event photograph. "
    "Your task: write ONE concise Turkish sentence describing exactly what is visible, "
    "plus 5-8 searchable tags. Be specific about setting, people, clothing colors, and actions.\n\n"
    "WHAT TO DESCRIBE:\n"
    "- The physical setting and environment (parliament, office, park, street, indoor, outdoor, etc.).\n"
    "- Number and roles of people visible (speaker, attendee, official, journalist, etc.).\n"
    "- Clothing colors (look carefully; if ambiguous, use general term like 'koyu renkli').\n"
    "- Significant background objects (flags, podium, banners, screens, furniture, trees, etc.).\n"
    "- Visible actions only (speaking at podium, standing, sitting, handshake, signing, etc.).\n\n"
    "WHAT NOT TO DO:\n"
    "- Never write placeholder tokens: <NAME>, <PERSON>, [isim], ___, etc.\n"
    "- Never invent details you don't see. Never guess names. Never assume unseen actions.\n"
    "- If unsure about a color, omit it or use 'koyu renkli' / 'açık renkli'.\n\n"
    "OUTPUT FORMAT (valid JSON only, no markdown fences, no extra text):\n"
    '{"caption_tr": "One 20–35 word Turkish sentence describing the scene.", "tags_tr": "tag1, tag2, tag3, ..."}\n\n'
    "EXAMPLE OUTPUT:\n"
    '{"caption_tr": "Lacivert takım elbiseli bir konuşmacı, arkasında Türk bayrağı bulunan kürsüde konuşma yapıyor. Dinleyiciler oturmuş dikkatle izliyor.", "tags_tr": "konuşma, kürsü, türk bayrağı, lacivert takım, resmi toplantı, kapalı mekan"}'
)


# Placeholder tokens VLMs leak from their redacted training data
# despite explicit prompt instructions ("never write <NAME>").
_PLACEHOLDER_RE = re.compile(
    r'<\s*(?:NAME|PERSON|İSİM|ISIM|isim|name|person)\s*>'
    r'|\[\s*(?:NAME|PERSON|isim|name|İSİM|ISIM|person)\s*\]'
    r'|_{3,}',
    flags=re.IGNORECASE,
)


def sanitize_placeholders(text: str, replacement: str = "bir kişi", capitalize_first: bool = True) -> str:
    """Replace <NAME>/<PERSON>/[isim]/___ leaks with a generic role term.

    capitalize_first: True for sentence-like captions, False for tag lists
    (otherwise "a, b, c" becomes "A, b, c").
    """
    if not text:
        return text
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


def parse_combined_response(raw: str) -> tuple[str, str]:
    """Extract (caption_tr, tags_tr) from a model JSON response.

    Handles three cases:
    1. Clean JSON  → standard json.loads
    2. Markdown-fenced JSON (```json ... ```) → strip fence then parse
    3. Truncated JSON (max_new_tokens hit before closing brace)
       → extract field values directly via regex so nothing is lost

    All returned strings pass through `sanitize_placeholders`.
    """
    stripped = re.sub(r'^```[a-z]*\s*', '', raw.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r'```\s*$', '', stripped).strip()

    try:
        match = re.search(r'\{.*\}', stripped, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return (
                sanitize_placeholders(_coerce_str(data.get("caption_tr", "")).strip()),
                sanitize_placeholders(_coerce_str(data.get("tags_tr", "")).strip(), replacement="kişi", capitalize_first=False),
            )
    except (json.JSONDecodeError, ValueError):
        pass

    caption_tr = ""
    tags_tr = ""
    m = re.search(r'"caption_tr"\s*:\s*"(.*?)"', stripped, re.DOTALL)
    if m:
        caption_tr = m.group(1).strip()
    m = re.search(r'"tags_tr"\s*:\s*"(.*?)"', stripped, re.DOTALL)
    if m:
        tags_tr = m.group(1).strip()

    if caption_tr:
        logger.debug("caption_parsing: partial JSON recovered via regex for raw: %s", raw[:80])
        return (
            sanitize_placeholders(caption_tr),
            sanitize_placeholders(tags_tr, replacement="kişi", capitalize_first=False),
        )

    logger.warning("caption_parsing: JSON parse failed, raw response: %s", raw[:200])
    return "", ""
