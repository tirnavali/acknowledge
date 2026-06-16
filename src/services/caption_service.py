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
import time
import torch
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
from src.services.caption_parsing import get_combined_prompt, parse_combined_response

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
            try:
                from transformers import Qwen2_5_VLForConditionalGeneration, Qwen2_5_VLProcessor
            except ImportError:
                # Direct import fallback for environments where top-level exports might be missing
                from transformers.models.qwen2_5_vl import Qwen2_5_VLForConditionalGeneration, Qwen2_5_VLProcessor

            import transformers
            logger.info(f"Loaded transformers from: {transformers.__file__} (version: {transformers.__version__})")
            logger.info(f"Loaded torch from: {torch.__file__} (version: {torch.__version__})")

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
                # Load on CPU first to avoid accelerate meta-tensor errors with
                # Qwen2.5-VL (lm_head is not weight-tied, which confuses
                # device_map="auto" / infer_auto_device), then move to CUDA.
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.bfloat16,
                )
                self._model.to("cuda")
            elif mps_available:
                # Use bfloat16: PyTorch 2.5+ / 2.11.0 on MPS has native bfloat16 support.
                # bfloat16 prevents numerical overflow/NaN attention loops (which caused !!! repetition bugs).
                torch.set_num_threads(max(2, (os.cpu_count() or 4) // 2))
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.bfloat16,
                )
                self._model.to("mps")
            else:
                # No device_map on CPU — avoids "cannot copy out of meta tensor" from accelerate.
                # Limit threads so captioning doesn't saturate all cores on low-end machines.
                torch.set_num_threads(max(2, (os.cpu_count() or 4) // 2))
                self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_id,
                    torch_dtype=torch.float32,
                )

            self._processor = Qwen2_5_VLProcessor.from_pretrained(model_id)
            logger.info("✅ CaptionService: Qwen2.5-VL-3B-Instruct loaded", extra={"event": "MODEL_LOAD"})
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

    def _run_prompt(self, image_input, prompt_text: str) -> str:
        """Run a single vision prompt and return stripped output text.

        image_input may be a PIL.Image.Image (in-memory) or a file path string.
        """
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image_input,
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
        # Single fused copy: move to device and cast dtype in one operation
        inputs = inputs.to(device=self._device, dtype=self._model.dtype)

        start_time = time.perf_counter()
        with torch.no_grad():
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=400,  # 400 provides extra headroom to prevent JSON truncation with detailed captions
                do_sample=False,
                repetition_penalty=1.15,   # kills token-loop bug ("göğüslerindeki sakallar" repeating)
                no_repeat_ngram_size=4,    # blocks any 4-gram from repeating verbatim
            )
        generation_time = time.perf_counter() - start_time
        logger.info(
            f"CaptionService: generation took {generation_time:.2f}s",
            extra={"event": "CAPTION_RESULT", "duration_ms": int(generation_time * 1000)},
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
    # 1024 preserves enough detail for color/tie/badge identification while
    # staying under MAX_PIXELS (1280²) cap after Qwen2.5-VL's internal tiling.
    MAX_SIDE_PX = 1024

    @staticmethod
    def _prepare_image(img_path: str, max_side: int):
        """Return a PIL Image resized to fit within max_side, entirely in memory.

        Eliminates the temp-file round-trip (disk write + disk read + JPEG decode)
        that previously ran before every inference call.
        """
        from PIL import Image as _Image, ImageOps as _ImageOps

        im = _Image.open(img_path)
        im = _ImageOps.exif_transpose(im)
        im.load()
        w, h = im.size
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if im.mode != "RGB":
            im = im.convert("RGB")
        if max(w, h) <= max_side:
            return im
        ratio = max_side / max(w, h)
        new_w, new_h = max(1, int(w * ratio)), max(1, int(h * ratio))
        resized = im.resize((new_w, new_h), _Image.LANCZOS)
        im.close()
        logger.debug(f"_prepare_image: {w}×{h} → {new_w}×{new_h} (in-memory)")
        return resized

    def _correct_grammar_if_enabled(self, text: str) -> str:
        """Runs Ollama-based grammar correction if enabled in settings and Ollama is ready."""
        from src.utils import config_util
        if not config_util.get_setting("grammar_correction_enabled", True):
            return text

        try:
            from src.services.grammar_service import OllamaGrammarService
            grammar_svc = OllamaGrammarService(
                model=config_util.get_setting("grammar_correction_model", "gemma4:latest"),
                url=os.environ.get("OLLAMA_URL", "http://localhost:11434")
            )
            if grammar_svc.is_ready():
                return grammar_svc.correct_text(text)
            else:
                logger.warning("OllamaGrammarService is not ready or reachable. Skipping correction.")
        except Exception as e:
            logger.error(f"Failed to run grammar correction: {e}")
        return text

    def analyse(self, img_path: str, person_names: list[str] = None) -> CaptionResult:
        """
        Run a single combined Turkish JSON prompt and return a CaptionResult.
        Blocking — must be called from a QThread worker.
        The image is pre-resized to MAX_SIDE_PX before being passed to the model
        so that full-resolution press photos never exhaust GPU/system memory.
        caption_en and tags_en are left empty (Turkish-only output).
        """
        result = CaptionResult(img_path=img_path)

        # Pre-resize outside the lock: returns a PIL Image in memory, no temp files
        try:
            pil_image = self._prepare_image(img_path, self.MAX_SIDE_PX)
        except Exception as e:
            result.error = f"Resim hazırlanamadı: {e}"
            return result

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
                full_start = time.perf_counter()

                prompt = get_combined_prompt(person_names)
                raw = self._run_prompt(pil_image, prompt)
                caption_tr, tags_tr = parse_combined_response(raw, person_names)

                if caption_tr:
                    result.caption_tr = self._correct_grammar_if_enabled(caption_tr)
                    result.tags_tr = tags_tr
                else:
                    # Fallback: JSON parse failed but model produced text output.
                    # Save raw text directly so the caption is not silently lost.
                    raw_stripped = raw.strip()
                    if len(raw_stripped) > 20:
                        result.caption_tr = self._correct_grammar_if_enabled(raw_stripped)
                        logger.warning(
                            "CaptionService: JSON parse failed, saving raw text as "
                            "caption_tr for %s",
                            os.path.basename(img_path),
                        )

                total_duration = time.perf_counter() - full_start
                result.duration = total_duration
                saved = "yes" if result.caption_tr else "no"
                logger.info(
                    f"CaptionService: analysis done {os.path.basename(img_path)} "
                    f"{total_duration:.2f}s | saved={saved}"
                )
            except Exception as e:
                logger.error(f"CaptionService.analyse error for {img_path}: {e}")
                result.error = str(e)

        return result
