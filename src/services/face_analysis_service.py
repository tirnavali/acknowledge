"""
FaceAnalysisService — wraps insightface for face detection and embedding extraction.

Design decisions:
- Model is loaded lazily on first call (heavy ~200 MB, downloaded once by insightface)
- Returns a list of FaceResult dataclasses with normalised bbox and numpy embedding
- Runs synchronously; callers should use QThread to avoid UI blocking
- A threading.Lock serialises concurrent detect() calls so rapid event-switching
  cannot corrupt the singleton insightface model state.
"""
from __future__ import annotations
import logging
import threading
import ssl
from dataclasses import dataclass
import numpy as np

# Bypass SSL verification for corporate networks with MITM proxies
ssl._create_default_https_context = ssl._create_unverified_context
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
_orig_request = requests.Session.request
def _no_verify_request(self, method, url, **kwargs):
    kwargs.setdefault("verify", False)
    return _orig_request(self, method, url, **kwargs)
requests.Session.request = _no_verify_request
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BLUR_THRESHOLD = 5.0  # Variance of Laplacian; lowered from 20.0 to allow close-ups with smooth skin.


def _variance_of_laplacian(gray_img) -> float:
    """Return the Laplacian variance of a grayscale image crop (blur metric)."""
    import cv2
    return cv2.Laplacian(gray_img, cv2.CV_64F).var()


@dataclass
class FaceResult:
    """Single detected face from an image."""
    # Normalised bounding box (0.0–1.0 relative to original image)
    x1: float
    y1: float
    x2: float
    y2: float
    # 512-dim ArcFace embedding
    embedding: np.ndarray  # shape (512,)
    # Confidence score
    score: float


class FaceAnalysisService:
    """
    Singleton-style service for face detection and embedding.
    Uses insightface buffalo_l model (ArcFace, 512-dim embeddings).
    """

    _instance = None
    _app = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        """Lazy load the insightface model (only once)."""
        if self._app is not None:
            return
        try:
            from insightface.app import FaceAnalysis
            self._app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            self._app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("✅ InsightFace model loaded (buffalo_l)")
        except Exception as e:
            logger.error(f"❌ InsightFace model load failed: {e}")
            self._app = None
            raise

    def detect(self, img_path: str) -> list[FaceResult]:
        """
        Detect all faces in an image and return normalised results.

        Args:
            img_path: Absolute path to the image file.

        Returns:
            List of FaceResult sorted by face area (largest first).
        """
        import cv2

        with self._lock:
            self._load_model()
            if self._app is None:
                return []

            img = cv2.imread(img_path)
            if img is None:
                logger.warning(f"Could not read image: {img_path}")
                return []

            h, w = img.shape[:2]
            faces = self._app.get(img)

        results = []
        for face in faces:
            import cv2
            bbox = face.bbox.astype(float)
            x1, y1, x2, y2 = bbox

            # Guard: clamp to image bounds and skip empty/degenerate crops
            ix1 = max(0, int(x1))
            iy1 = max(0, int(y1))
            ix2 = min(w, int(x2))
            iy2 = min(h, int(y2))
            if ix2 <= ix1 or iy2 <= iy1:
                logger.debug("Skipping face: empty crop after clamping bbox to image bounds.")
                continue

            # Blur gatekeeper: skip faces with no discernible structure (very low threshold)
            crop = img[iy1:iy2, ix1:ix2]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            blur_score = _variance_of_laplacian(gray)
            if blur_score < BLUR_THRESHOLD:
                logger.info(f"Skipping face: too blurry. Score: {blur_score:.2f} (threshold={BLUR_THRESHOLD})")
                continue

            results.append(FaceResult(
                x1=max(0.0, x1 / w),
                y1=max(0.0, y1 / h),
                x2=min(1.0, x2 / w),
                y2=min(1.0, y2 / h),
                embedding=face.embedding,
                score=float(face.det_score),
            ))

        results.sort(key=lambda f: (f.x2 - f.x1) * (f.y2 - f.y1), reverse=True)
        return results

    def is_ready(self) -> bool:
        return self._app is not None
