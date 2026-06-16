"""OllamaCaptionService — Gemma4 (or any vision model) via Ollama HTTP API.

Drop-in alternative to `CaptionService` (Qwen2.5-VL transformers backend).
Both implement the `CaptionBackend` protocol so `ApplicationService` can
pick one at startup via `caption_backend` setting.

Why Ollama:
- No transformers/torch import — leaner runtime, no CUDA dtype quirks.
- Native vision support in Gemma3/Gemma4 family.
- `think` parameter enables silent chain-of-thought reasoning; the final
  `response` field stays a clean JSON object while internal reasoning is
  returned separately (and dropped).
"""
from __future__ import annotations
import base64
import io
import logging
import os
import time

import requests

from src.domain.entities.caption_result import CaptionResult
from src.services.caption_parsing import COMBINED_PROMPT, parse_combined_response
from src.services.caption_service import CaptionService  # reuse _prepare_image staticmethod

logger = logging.getLogger(__name__)


class OllamaCaptionService:
    """Vision captioning via an Ollama-hosted multimodal model.

    Tested with `gemma4:latest` (8B, vision + thinking). Should also work
    with `gemma3:4b`, `gemma3:12b`, `qwen2.5vl`, `llava` and similar.
    """

    # Same pre-resize cap as Qwen path — keeps payload small and inference fast.
    # Lower this (e.g. 768) on 8GB GPUs to avoid OOM when thinking mode is on.
    MAX_SIDE_PX = 1024

    # NOTE on `thinking`: Gemma4 in Ollama think-mode treats structured-output
    # prompts (with explicit OUTPUT FORMAT examples) as a "thinking task" and
    # never emits the final answer in the `response` field. It produces good
    # chain-of-thought naturally WITHOUT the think flag, so we default it off
    # and parse the JSON straight from `response`. If callers force think=True
    # we fall back to extracting JSON from the `thinking` blob.
    def __init__(
        self,
        model: str = "gemma4:latest",
        url: str = "http://localhost:11434",
        thinking: bool = False,
        timeout: int = 300,
    ):
        self._model = model
        self._url = url.rstrip("/")
        self._thinking = thinking
        self._timeout = timeout
        self._session = requests.Session()
        self._session.verify = False  # match project-wide SSL bypass policy
        logger.info(
            f"OllamaCaptionService init model={model} url={url} thinking={thinking}"
        )

    def is_ready(self) -> bool:
        """Probe Ollama for the model. Returns True if reachable AND model present."""
        try:
            r = self._session.get(f"{self._url}/api/tags", timeout=5)
            r.raise_for_status()
            installed = {m.get("name") for m in r.json().get("models", [])}
            # Ollama returns names like "gemma4:latest"; allow bare "gemma4" match too.
            base_name = self._model.split(":")[0]
            return self._model in installed or any(n.startswith(base_name + ":") for n in installed)
        except Exception as e:
            logger.warning(f"OllamaCaptionService.is_ready probe failed: {e}")
            return False

    def _load_model(self) -> None:
        """Probe the server to verify the model is loaded/installed.
        Raises an exception if Ollama is unreachable or the model is missing.
        """
        if not self.is_ready():
            raise RuntimeError(
                f"Ollama sunucusuna erişilemiyor veya '{self._model}' modeli yüklü değil.\n"
                "Lütfen Ollama'nın çalıştığından ve modelin indirildiğinden (ollama pull) emin olun."
            )

    def _image_to_b64(self, img_path: str) -> str:
        """Pre-resize image and encode as base64 JPEG for Ollama's images field."""
        pil = CaptionService._prepare_image(img_path, self.MAX_SIDE_PX)
        buf = io.BytesIO()
        pil.save(buf, "JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def analyse(self, img_path: str) -> CaptionResult:
        """Single-image captioning. Blocking — call from a QThread worker.

        Returns a CaptionResult with caption_tr / tags_tr / duration / error
        populated. caption_en and tags_en stay empty (Turkish-only output,
        matching the Qwen backend's behavior).
        """
        result = CaptionResult(img_path=img_path)
        full_start = time.perf_counter()

        try:
            b64 = self._image_to_b64(img_path)
        except Exception as e:
            result.error = f"Resim hazırlanamadı: {e}"
            return result

        payload = {
            "model": self._model,
            "prompt": COMBINED_PROMPT,
            "images": [b64],
            "stream": False,
            "think": self._thinking,
            "options": {
                "temperature": 0.3,           # low temp for deterministic JSON
                "num_predict": 400,           # cap output tokens (caption + tags)
                "repeat_penalty": 1.15,       # mirror Qwen path's loop guard
            },
        }

        try:
            gen_start = time.perf_counter()
            r = self._session.post(
                f"{self._url}/api/generate", json=payload, timeout=self._timeout
            )
            r.raise_for_status()
            data = r.json()
            gen_ms = int((time.perf_counter() - gen_start) * 1000)
        except Exception as e:
            logger.error(f"OllamaCaptionService HTTP error for {img_path}: {e}")
            result.error = f"Ollama hatası: {e}"
            return result

        raw = (data.get("response") or "").strip()
        thinking_blob = (data.get("thinking") or "").strip()
        # Thinking-mode fallback: Gemma4 sometimes emits the JSON inside the
        # `thinking` field and leaves `response` empty. Use thinking text only
        # when response itself is empty so we never throw away a clean answer.
        if not raw and thinking_blob:
            raw = thinking_blob
            logger.info("OllamaCaptionService: response empty, falling back to thinking blob")
        logger.info(
            f"OllamaCaptionService: gen {gen_ms}ms model={self._model} "
            f"thinking_len={len(thinking_blob)} response_len={len(raw)}",
            extra={"event": "CAPTION_RESULT", "duration_ms": gen_ms},
        )

        caption_tr, tags_tr = parse_combined_response(raw)
        if caption_tr:
            result.caption_tr = caption_tr
            result.tags_tr = tags_tr
        elif len(raw) > 20:
            # Fallback: JSON parse failed but model produced text. Save raw so
            # the caption is not silently lost (mirrors Qwen path fallback).
            result.caption_tr = raw
            logger.warning(
                "OllamaCaptionService: JSON parse failed, saving raw text as "
                "caption_tr for %s",
                os.path.basename(img_path),
            )

        result.duration = time.perf_counter() - full_start
        saved = "yes" if result.caption_tr else "no"
        logger.info(
            f"OllamaCaptionService: analysis done {os.path.basename(img_path)} "
            f"{result.duration:.2f}s | saved={saved}"
        )
        return result
