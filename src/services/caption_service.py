"""
CaptionService — wraps Qwen2.5-VL-3B-Instruct for image captioning and tagging.

Design:
- Singleton with threading.Lock (mirrors FaceAnalysisService)
- Model loads lazily on first analyse() call
- Runs synchronously; callers must use QThread to avoid UI blocking
- CUDA used automatically when available; CPU fallback without device_map="auto"
"""
from __future__ import annotations
import logging
import os
import ssl
import threading
from pathlib import Path

# Bypass SSL verification for corporate networks with MITM proxies.
ssl._create_default_https_context = ssl._create_unverified_context

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Patch Session.__init__ so EVERY session created by ANY library starts with verify=False.
# This covers huggingface_hub regardless of version (no configure_http_backend needed).
_orig_session_init = requests.Session.__init__
def _patched_session_init(self, *args, **kwargs):
    _orig_session_init(self, *args, **kwargs)
    self.verify = False
requests.Session.__init__ = _patched_session_init


from src.domain.entities.caption_result import CaptionResult

logger = logging.getLogger(__name__)


class CaptionService:
    _instance = None
    _model = None
    _processor = None
    _lock = threading.Lock()
    _device: str = "cpu"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self) -> None:
        """Lazy-load Qwen2.5-VL-3B-Instruct (only once per process).

        Prefers a locally downloaded copy at ./models/Qwen2.5-VL-3B-Instruct
        (created by download_model.py) to avoid corporate SSL issues at runtime.
        Falls back to the HuggingFace hub ID if the local copy is absent.
        """
        if self._model is not None:
            return
        try:
            import torch
            from transformers import Qwen2_5_VLForConditionalGeneration, Qwen2_5_VLProcessor

            cuda_available = torch.cuda.is_available()
            self._device = "cuda" if cuda_available else "cpu"
            logger.info(f"CaptionService: loading model on {self._device}")

            _candidates = [
                Path("./src/models/Qwen2.5-VL-3B-Instruct"),
                Path("./models/Qwen2.5-VL-3B-Instruct"),
            ]
            _local = next((p for p in _candidates if (p / "config.json").exists()), None)
            model_id = str(_local) if _local else "Qwen/Qwen2.5-VL-3B-Instruct"
            logger.info(f"CaptionService: model source → {model_id}")
            if cuda_available:
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.bfloat16,
                    device_map="auto",
                )
            else:
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.float32,
                )
                self._model.to("cpu")

            self._processor = Qwen2_5_VLProcessor.from_pretrained(model_id)
            logger.info("✅ CaptionService: Qwen2.5-VL-3B-Instruct loaded")
        except Exception as e:
            logger.error(f"❌ CaptionService model load failed: {e}")
            self._model = None
            self._processor = None
            raise

    def is_ready(self) -> bool:
        return self._model is not None and self._processor is not None

    def _run_prompt(self, image_uri: str, prompt_text: str) -> str:
        """Run a single vision prompt and return stripped output text."""
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_uri},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]

        text_input = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self._processor(
            text=[text_input],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self._device)

        import torch
        with torch.no_grad():
            generated_ids = self._model.generate(**inputs, max_new_tokens=256)

        # Strip input tokens — Qwen canonical pattern
        trimmed = [
            out[len(inp):]
            for inp, out in zip(inputs.input_ids, generated_ids)
        ]
        decoded = self._processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        return decoded[0].strip() if decoded else ""

    def analyse(self, img_path: str) -> CaptionResult:
        """
        Run 4 sequential prompts on the image and return a CaptionResult.
        Blocking — must be called from a QThread worker.
        """
        result = CaptionResult(img_path=img_path)
        image_uri = str(Path(img_path).resolve())  # absolute path, qwen-vl-utils handles Windows paths directly

        with self._lock:
            try:
                self._load_model()
            except Exception as e:
                result.error = f"Model yüklenemedi: {e}"
                return result

            try:
                result.caption_en = self._run_prompt(image_uri, "Describe this image in detail.")
                result.caption_tr = self._run_prompt(image_uri, "Bu resmi detaylı bir şekilde Türkçe açıkla.")
                result.tags_en = self._run_prompt(image_uri, "List objects in this image as comma-separated values.")
                result.tags_tr = self._run_prompt(image_uri, "Bu resimdeki nesneleri virgülle ayrılmış değerler olarak listele.")
            except Exception as e:
                logger.error(f"CaptionService.analyse error for {img_path}: {e}")
                result.error = str(e)

        return result
