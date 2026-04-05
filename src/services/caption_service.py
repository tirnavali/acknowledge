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

# Pass HF_TOKEN to huggingface_hub if set in environment / .env
def _apply_hf_token() -> None:
    import os
    token = os.environ.get("HF_TOKEN", "").strip()
    if token:
        try:
            from huggingface_hub import login
            login(token=token, add_to_git_credential=False)
        except Exception:
            pass  # non-fatal — anonymous access still works

_apply_hf_token()


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
        if self._model is not None and self._processor is not None:
            return
        try:
            import torch
            from transformers import Qwen2_5_VLForConditionalGeneration, Qwen2_5_VLProcessor

            cuda_available = torch.cuda.is_available()
            mps_available  = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()

            if cuda_available:
                self._device = "cuda"
            elif mps_available:
                self._device = "mps"
            else:
                self._device = "cpu"
            logger.info(f"CaptionService: loading model on {self._device}")

            _candidates = [
                Path("./src/models/Qwen2.5-VL-3B-Instruct"),
                Path("./models/Qwen2.5-VL-3B-Instruct"),
            ]
            _local = next((p for p in _candidates if (p / "config.json").exists()), None)
            model_id = str(_local) if _local else "Qwen/Qwen2.5-VL-3B-Instruct"
            logger.info(f"CaptionService: model source → {model_id}")

            if cuda_available:
                # device_map="auto" lets transformers shard across GPUs
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.bfloat16,
                    device_map="auto",
                )
            elif mps_available:
                # device_map={"": "mps"} places weights on MPS during loading.
                # Calling .to("mps") after from_pretrained fails on newer transformers
                # because lazy-loaded meta tensors cannot be copied with .to().
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.bfloat16,
                    device_map={"": "mps"},
                )
            else:
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.float32,
                    device_map={"": "cpu"},
                )

            self._processor = Qwen2_5_VLProcessor.from_pretrained(model_id)
            logger.info("✅ CaptionService: Qwen2.5-VL-3B-Instruct loaded")
        except Exception as e:
            logger.error(f"❌ CaptionService model load failed: {e}")
            self._model = None
            self._processor = None
            raise

    def is_ready(self) -> bool:
        return self._model is not None and self._processor is not None

    # Max pixels fed to the model per prompt.
    # Qwen2.5-VL tiles images dynamically; very large press photos (50 MP+)
    # can exceed available VRAM/RAM without this cap.
    # 1280×1280 = ~1.6 M pixels — safe for RTX 3060 (12 GB) and M4 Pro (24 GB).
    MAX_PIXELS = 1280 * 1280
    MIN_PIXELS = 224 * 224

    def _run_prompt(self, image_uri: str, prompt_text: str) -> str:
        """Run a single vision prompt and return stripped output text."""
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image_uri,
                        "min_pixels": self.MIN_PIXELS,
                        "max_pixels": self.MAX_PIXELS,
                    },
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
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=256,
                repetition_penalty=1.15,
            )

        # Strip input tokens — Qwen canonical pattern
        trimmed = [
            out[len(inp):]
            for inp, out in zip(inputs.input_ids, generated_ids)
        ]
        decoded = self._processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        return decoded[0].strip() if decoded else ""

    # Longest side of the pre-resized image fed to the model.
    # Keeps PIL memory and model input small regardless of original resolution.
    MAX_SIDE_PX = 768

    @staticmethod
    def _prepare_image(img_path: str, max_side: int) -> str:
        """
        Return a path to a downscaled copy of the image.
        If the image already fits within max_side × max_side it is returned as-is.
        The resized copy is written to a temp file that the caller must delete.
        Returns (path, is_temp) tuple.
        """
        import tempfile
        from PIL import Image as _Image

        with _Image.open(img_path) as im:
            w, h = im.size
            if max(w, h) <= max_side:
                return img_path, False          # already small enough

            # Resize keeping aspect ratio
            ratio = max_side / max(w, h)
            new_w, new_h = max(1, int(w * ratio)), max(1, int(h * ratio))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            resized = im.resize((new_w, new_h), _Image.LANCZOS)
            if resized.mode != "RGB":
                resized = resized.convert("RGB")

            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            resized.save(tmp.name, "JPEG", quality=88)
            logger.debug(f"_prepare_image: {w}×{h} → {new_w}×{new_h}, tmp={tmp.name}")
            return tmp.name, True

    def _parse_combined_response(self, raw: str) -> tuple[str, str]:
        """Extract caption_tr and tags_tr from a JSON model response.

        Falls back to using the raw text as caption with no tags if JSON parsing fails.
        """
        import json
        import re

        def _coerce_str(val) -> str:
            if isinstance(val, list):
                return ", ".join(str(v) for v in val)
            return str(val) if val is not None else ""

        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return _coerce_str(data.get("caption_tr", "")).strip(), _coerce_str(data.get("tags_tr", "")).strip()
        except (json.JSONDecodeError, ValueError):
            pass
        logger.warning("CaptionService: JSON parse failed, raw response: %s", raw[:200])
        return "", ""

    def analyse(self, img_path: str) -> CaptionResult:
        """
        Run a single combined Turkish JSON prompt and return a CaptionResult.
        Blocking — must be called from a QThread worker.
        The image is pre-resized to MAX_SIDE_PX before being passed to the model
        so that full-resolution press photos never exhaust GPU/system memory.
        caption_en and tags_en are left empty (Turkish-only output).
        """
        import os as _os
        result = CaptionResult(img_path=img_path)

        # Pre-resize outside the lock so PIL work doesn't block other threads
        try:
            tmp_path, is_temp = self._prepare_image(img_path, self.MAX_SIDE_PX)
        except Exception as e:
            result.error = f"Resim hazırlanamadı: {e}"
            return result

        image_uri = str(Path(tmp_path).resolve())

        with self._lock:
            try:
                self._load_model()
            except Exception as e:
                result.error = f"Model yüklenemedi: {e}"
                return result

            if not self.is_ready():
                result.error = "Model yüklenemedi (processor eksik)"
                return result

            try:
                combined_prompt = (
                    "Bu fotoğrafı Türkçe analiz et ve aşağıdaki JSON formatında yanıt ver "
                    "(başka hiçbir şey yazma):\n"
                    '{"caption_tr": "Detaylı Türkçe açıklama", "tags_tr": "nesne1, nesne2, nesne3"}'
                )
                raw = self._run_prompt(image_uri, combined_prompt)
                result.caption_tr, result.tags_tr = self._parse_combined_response(raw)
            except Exception as e:
                logger.error(f"CaptionService.analyse error for {img_path}: {e}")
                result.error = str(e)
            finally:
                if is_temp:
                    try:
                        _os.unlink(tmp_path)
                    except OSError:
                        pass

        return result
