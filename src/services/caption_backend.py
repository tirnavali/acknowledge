"""Protocol defining the caption backend interface.

Two concrete backends:
- `CaptionService` (Qwen2.5-VL via transformers, local)
- `OllamaCaptionService` (Gemma4 via Ollama HTTP API)

`ApplicationService` picks one at startup based on settings.
"""
from __future__ import annotations
from typing import Protocol, runtime_checkable

from src.domain.entities.caption_result import CaptionResult


@runtime_checkable
class CaptionBackend(Protocol):
    """Single-image captioning backend.

    Implementations must be thread-safe for QThread workers
    (`CaptionTabWidget`, `BackgroundCaptionWorker`) that call analyse()
    from outside the main UI thread.
    """

    def analyse(self, img_path: str) -> CaptionResult:
        """Run inference on a single image. Blocking — call from QThread."""
        ...

    def is_ready(self) -> bool:
        """True if the model/connection is loaded and ready to serve."""
        ...
