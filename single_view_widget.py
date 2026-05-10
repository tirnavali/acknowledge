"""
SingleViewWidget — full-screen image display with integrated face detection overlay.

Architecture:
- QThread (FaceDetectionWorker) runs insightface off the UI thread
- FaceOverlayWidget is layered on top of the image label
- DB-first: if face_detections exist for this media, skip re-detection
"""
from __future__ import annotations
import os
import logging
import time
from uuid import UUID
from PySide6 import QtCore, QtWidgets, QtGui

from face_overlay_widget import FaceOverlayWidget
from src.utils import path_util

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background worker — keeps UI responsive during detection
# ---------------------------------------------------------------------------

class ImageLoaderWorker(QtCore.QThread):
    """Loads a QImage from disk in a background thread (QImage is thread-safe; QPixmap is not)."""

    loaded = QtCore.Signal(str, QtGui.QImage)  # (path, image)

    def __init__(self, img_path: str, parent=None):
        super().__init__(parent)
        self._img_path = img_path

    def run(self):
        try:
            from PIL import Image, ImageOps
            import numpy as np
            with Image.open(self._img_path) as pil_img:
                pil_img = ImageOps.exif_transpose(pil_img)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
            
            # Convert PIL to QImage
            width, height = pil_img.size
            bytes_per_line = 3 * width
            data = pil_img.tobytes("raw", "RGB")
            image = QtGui.QImage(data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888)
            image = image.copy()
        except Exception:
            # Fallback for videos: use OpenCV to extract the first frame
            try:
                import cv2
                cap = cv2.VideoCapture(self._img_path)
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    image = QtGui.QImage()
                else:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame_rgb.shape
                    bytes_per_line = ch * w
                    image = QtGui.QImage(frame_rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                    image = image.copy()
            except Exception as e:
                logger.error(f"Failed to load image/video via Pillow/CV2: {e}")
                image = QtGui.QImage()
        self.loaded.emit(self._img_path, image)


class FaceDetectionWorker(QtCore.QThread):
    """Runs FaceAnalysisService.detect() in a worker thread."""

    detected = QtCore.Signal(list)   # list[FaceResult]
    error    = QtCore.Signal(str)

    def __init__(self, face_service, img_path: str, parent=None):
        super().__init__(parent)
        self._service = face_service
        self._img_path = img_path

    def run(self):
        try:
            results = self._service.detect_faces(self._img_path)
            self.detected.emit(results)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class _VideoFaceThumb(QtWidgets.QFrame):
    """Small thumbnail for a face detected in a video, with name and timestamp."""
    def __init__(self, face: dict, parent=None):
        super().__init__(parent)
        self.setFixedSize(90, 110)
        self.setStyleSheet("""
            QFrame {
                background: #2a2a2e;
                border-radius: 6px;
                border: 1px solid #3a3a3e;
            }
            QFrame:hover { background: #35353a; border-color: #50C8FF; }
        """)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        # Crop logic (similar to EventPersonsDialog but faster/smaller)
        self.thumb_label = QtWidgets.QLabel()
        self.thumb_label.setFixedSize(82, 70)
        self.thumb_label.setAlignment(QtCore.Qt.AlignCenter)
        self.thumb_label.setStyleSheet("border-radius: 3px; background: #1a1a1a;")
        layout.addWidget(self.thumb_label)
        
        name = face.get("person_name") or "Bilinmiyor"
        name_lbl = QtWidgets.QLabel(name)
        name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        name_lbl.setStyleSheet("color: #ddd; font-size: 10px; font-weight: bold;")
        layout.addWidget(name_lbl)
        
        tms = face.get("timestamp_ms") or 0
        total_seconds = tms / 1000.0
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        time_str = f"{minutes:02d}:{seconds:05.2f}"
        time_lbl = QtWidgets.QLabel(time_str)
        time_lbl.setAlignment(QtCore.Qt.AlignCenter)
        time_lbl.setStyleSheet("color: #888; font-size: 9px;")
        layout.addWidget(time_lbl)
        
        self.face_data = face
        self.setCursor(QtCore.Qt.PointingHandCursor)

    clicked = QtCore.Signal(dict)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.face_data)
        super().mousePressEvent(event)

    def set_pixmap(self, pix):
        if pix and not pix.isNull():
            self.thumb_label.setPixmap(pix.scaled(
                82, 70, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation
            ).copy(QtCore.QRect(0, 0, 82, 70)))
        else:
            self.thumb_label.setText("👤")
            self.thumb_label.setStyleSheet("color: #444; font-size: 24px;")

class SingleViewWidget(QtWidgets.QWidget):
    """
    Displays a single image with:
    - Filename label
    - Scrollable, aspect-ratio-correct image
    - Transparent face bounding-box overlay (face_overlay_widget)
    - Background face detection via FaceDetectionWorker

    Dependencies injected at construction:
        face_service    — FaceAnalysisService (optional, can be None to disable)
        face_service    — FaceService (optional, can be None to disable)
        person_service  — PersonService (optional, can be None to disable)
        media_service   — MediaService (optional, can be None to disable)
    """

    doubleClicked   = QtCore.Signal()
    nextRequested   = QtCore.Signal()
    prevRequested   = QtCore.Signal()
    facesChanged    = QtCore.Signal()

    def __init__(
        self,
        face_service=None,
        person_service=None,
        media_service=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self._face_service      = face_service
        self._face_service      = face_service  # Use the actual service
        self._person_service    = person_service
        self._media_service     = media_service

        self.current_img_path   = None
        self._current_media_id  = None
        self._current_event_id  = None
        self._face_detected_at  = None
        self._is_batch_pending  = False
        self._detection_worker: FaceDetectionWorker | None = None
        self._detection_img_path: str | None = None   # path sent to current worker
        self._image_loader: ImageLoaderWorker | None = None
        self._source_pixmap: QtGui.QPixmap | None = None
        # Raw FaceResult list from last detection (needed to save to DB)
        self._pending_results: list = []
        self._skip_similarity = False  # set by reset to skip auto-matching
        self._zoom_factor = 1.0        # 1.0 = fit to container; >1.0 = zoom in; <1.0 = zoom out

        self._init_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Top bar: back button + filename label
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(8)

        self.back_btn = QtWidgets.QPushButton("← Geri")
        self.back_btn.setFixedHeight(32)
        self.back_btn.setFixedWidth(80)
        self.back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #222;
                border: 1px solid #bbb;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #c8c8c8;
            }
            QPushButton:pressed {
                background-color: #b0b0b0;
            }
        """)
        self.back_btn.clicked.connect(self.doubleClicked.emit)
        top_bar.addWidget(self.back_btn)

        self.filename_label = QtWidgets.QLabel("Dosya adı")
        self.filename_label.setAlignment(QtCore.Qt.AlignCenter)
        self.filename_label.setStyleSheet("""
            font-weight: bold;
            color: #444;
            font-size: 14px;
            padding: 5px;
        """)
        top_bar.addWidget(self.filename_label, stretch=1)

        layout.addLayout(top_bar)

        # Container that stacks image + overlay
        self._image_container = QtWidgets.QWidget()
        self._image_container.setStyleSheet("background-color: #1e1e1e;")
        container_layout = QtWidgets.QVBoxLayout(self._image_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setFocusPolicy(QtCore.Qt.NoFocus)
        self.image_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        container_layout.addWidget(self.image_label)

        # Overlay lives inside the container, anchored via resizeEvent
        self.face_overlay = FaceOverlayWidget(self._image_container)
        self.face_overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.face_overlay.face_named.connect(self._on_face_named)
        self.face_overlay.face_reset.connect(self._on_face_reset)
        self.face_overlay.face_cleared.connect(self._on_face_cleared)
        self.face_overlay.face_note_saved.connect(self._on_face_note_saved)
        self.face_overlay.hide()

        # Scroll area wraps the container
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self.scroll_area.setWidget(self._image_container)
        layout.addWidget(self.scroll_area)

        self._status_label = QtWidgets.QLabel("")
        self._status_label.setAlignment(QtCore.Qt.AlignCenter)
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_label)

        # NEW: Face list area (hidden by default, used for videos)
        self.face_list_scroll = QtWidgets.QScrollArea()
        self.face_list_scroll.setFixedHeight(130)
        self.face_list_scroll.setWidgetResizable(True)
        self.face_list_scroll.setVisible(False)
        self.face_list_scroll.setStyleSheet("""
            QScrollArea {
                background-color: #1e1e1e;
                border: none;
                border-top: 1px solid #333;
            }
        """)
        
        self.face_list_content = QtWidgets.QWidget()
        self.face_list_content.setStyleSheet("background: transparent;")
        self.face_list_layout = QtWidgets.QHBoxLayout(self.face_list_content)
        self.face_list_layout.setContentsMargins(10, 5, 10, 10)
        self.face_list_layout.setSpacing(12)
        
        self.face_list_scroll.setWidget(self.face_list_content)
        layout.addWidget(self.face_list_scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_context(self, event_id, media_id=None, face_detected_at=None, is_batch_pending=False):
        """Call from MainWindow to provide DB context for this image."""
        self._current_event_id = event_id
        self._current_media_id = media_id
        self._face_detected_at = face_detected_at
        self._is_batch_pending = is_batch_pending
        self.face_overlay.set_media_id(media_id)

    def show_context_menu(self, pos):
        """Show context menu for single view"""
        if not self.current_img_path or not os.path.exists(self.current_img_path):
            return
            
        menu = QtWidgets.QMenu(self)
        reveal_action = menu.addAction("📁 Dosya Konumunu Aç")
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == reveal_action:
            from src.utils import path_util
            path_util.reveal_in_explorer(self.current_img_path)

    def set_image(self, img_path: str):
        """Load image asynchronously, clear overlay, trigger face detection."""
        self.current_img_path = img_path
        self.face_overlay.clear_faces()
        self._pending_results = []
        self._source_pixmap = None
        self._zoom_factor = 1.0  # Reset zoom on new image load

        if not img_path or not os.path.exists(img_path):
            self.image_label.setText("Resim yüklenemedi.")
            self.filename_label.setText("")
            self._status_label.setText("")
            return

        self.filename_label.setText(os.path.basename(img_path))
        self._image_load_start = time.monotonic()

        # Stop any in-flight loader for a previous image
        if self._image_loader and self._image_loader.isRunning():
            self._image_loader.quit()
            self._image_loader.wait(200)

        # Show placeholder immediately so the UI feels responsive
        self.image_label.setText("⏳ Yükleniyor…")
        self._status_label.setText("")

        from src.utils.video_util import VIDEO_EXTS
        self._is_video = os.path.splitext(img_path)[1].lower() in VIDEO_EXTS
        
        # For videos, we don't show the interactive overlay boxes on top of a static frame
        self.face_overlay.setVisible(not self._is_video)
        self.face_list_scroll.setVisible(self._is_video)
        self._clear_face_list()

        self._image_loader = ImageLoaderWorker(img_path, self)
        self._image_loader.loaded.connect(self._on_image_loaded)
        self._image_loader.start()

    def _on_image_loaded(self, path: str, image: QtGui.QImage):
        """Called on the UI thread once the background loader finishes."""
        if path != self.current_img_path:
            return  # user switched image before this one finished loading

        if image.isNull():
            self.image_label.setText("Geçersiz resim dosyası.")
            return

        # Convert QImage → QPixmap on the UI thread (the only safe place)
        pixmap = QtGui.QPixmap.fromImage(image)
        self._source_pixmap = pixmap
        self._scale_and_show(pixmap, smooth=True)
        
        # If video, load and show faces at bottom
        if self._is_video and self._current_media_id:
            self._populate_face_list()
        
        # If it's a photo, trigger face detection overlay
        if not self._is_video:
            self.face_overlay.set_source_pixmap(pixmap)
            _load_ms = int((time.monotonic() - getattr(self, '_image_load_start', time.monotonic())) * 1000)
            logger.info(
                f"Image loaded in {_load_ms}ms: {os.path.basename(path)}",
                extra={"event": "IMAGE_LOAD", "duration_ms": _load_ms, "media_id": str(self._current_media_id) if self._current_media_id else None},
            )

            # Now trigger face detection logic
            if self._face_service is None:
                return  # face detection disabled

            # DB-first: if background worker already processed this media, load from DB and skip re-detection
            if self._current_media_id and self._face_detected_at and self._face_service:
                try:
                    db_faces = self._face_service.get_faces_for_media(self._current_media_id)
                    if db_faces:
                        self._auto_match_db_faces(db_faces)
                        self._show_db_faces(db_faces)
                        self._status_label.setText(f"🗃️ {len(db_faces)} yüz veritabanından yüklendi")
                        logger.info(
                            f"Faces loaded from DB: {len(db_faces)} faces",
                            extra={"event": "FACE_DB_HIT", "media_id": str(self._current_media_id)},
                        )
                    else:
                        self._status_label.setText("Yüz algılanamadı.")
                    return
                except Exception as e:
                    logger.warning(f"Could not get faces from DB: {e}")

            # Batch worker is still running for this image → wait, don't duplicate detection
            if self._is_batch_pending and not self._face_detected_at:
                self._status_label.setText("⏳ Yüz tanıma bekleniyor…")
                logger.info("Face detection deferred: batch worker still running", extra={"event": "FACE_BATCH_WAIT"})
                return

            # Fallback: check for named detections (older records without face_detected_at)
            if self._current_media_id and self._face_service:
                try:
                    db_faces = self._face_service.get_faces_for_media(self._current_media_id)
                    has_named = any(f.get("person_name") for f in db_faces)
                    if db_faces and has_named:
                        self._auto_match_db_faces(db_faces)
                        self._show_db_faces(db_faces)
                        self._status_label.setText(f"🗃️ {len(db_faces)} yüz veritabanından yüklendi")
                        return
                except Exception as e:
                    logger.warning(f"Could not get faces from DB: {e}")

            # No DB data → run detector
            self._status_label.setText("🔍 Yüzler algılanıyor…")
            self._start_detection(path)

    def refresh_faces_from_db(self):
        """Re-fetch face detections from DB and update the overlay. Called after batch worker finishes."""
        if not self._current_media_id or not self._face_service:
            return
        try:
            db_faces = self._face_service.get_faces_for_media(self._current_media_id)
            if db_faces:
                self._auto_match_db_faces(db_faces)
                self._show_db_faces(db_faces)
                self._status_label.setText(f"🗃️ {len(db_faces)} yüz veritabanından yüklendi")
            else:
                self._status_label.setText("Yüz algılanamadı.")
            self._is_batch_pending = False
        except Exception as e:
            logger.warning(f"refresh_faces_from_db failed: {e}")

    # ------------------------------------------------------------------
    # Detection pipeline
    # ------------------------------------------------------------------

    def _start_detection(self, img_path: str):
        if self._detection_worker and self._detection_worker.isRunning():
            self._detection_worker.quit()
            self._detection_worker.wait(500)

        self._detection_start = time.monotonic()
        self._detection_img_path = img_path
        self._detection_worker = FaceDetectionWorker(self._face_service, img_path, self)
        self._detection_worker.detected.connect(self._on_detection_finished)
        self._detection_worker.error.connect(self._on_detection_error)
        self._detection_worker.start()

    def _on_detection_finished(self, results: list):
        # Guard: discard stale results if user switched image/event before detection finished
        if self.current_img_path != self._detection_img_path:
            logger.debug("Discarding stale detection results (image changed during detection)")
            return

        _detect_ms = int((time.monotonic() - getattr(self, '_detection_start', time.monotonic())) * 1000)
        if not results:
            self._status_label.setText("Yüz algılanamadı.")
            logger.info(
                f"Face detection: 0 faces in {_detect_ms}ms",
                extra={"event": "FACE_DETECT", "duration_ms": _detect_ms, "media_id": str(self._current_media_id) if self._current_media_id else None},
            )
            return

        self._pending_results = results
        n = len(results)
        self._status_label.setText(f"✅ {n} yüz algılandı — isimleri girin ve Enter'a basın")

        # Try auto-matching via similarity search (unless reset was triggered)
        face_dicts = []
        skip_sim = self._skip_similarity
        self._skip_similarity = False  # reset flag
        for i, face in enumerate(results):
            person_id, person_name = None, None
            if not skip_sim and self._face_service and face.embedding is not None:
                person_id, person_name = self._face_service.find_similar_person(face.embedding)
            pid_str = str(person_id) if person_id else None
            face_dicts.append({
                "bbox"        : {"x1": face.x1, "y1": face.y1, "x2": face.x2, "y2": face.y2},
                "face_id"     : None,
                "person_name" : person_name,
                "face_index"  : i,
                "person_id"   : pid_str,
                "note"        : self._load_note(pid_str, self._current_media_id),
            })

        # Ensure media record exists in DB (create it if needed)
        if self._media_service and self._face_service and self.current_img_path:
            if not self._current_media_id and self._current_event_id:
                try:
                    self._current_media_id = self._media_service.ensure_media_exists(
                        self._current_event_id, self.current_img_path, "photo"
                    )
                except Exception as e:
                    logger.warning(f"Could not ensure media exists: {e}")

        # Save detections to DB (always save so we don't wipe them on refresh)
        if self._current_media_id and self._face_service:
            try:
                saved_ids = self._face_service.save_faces(self._current_media_id, results)
                for i, fid in enumerate(saved_ids):
                    face_dicts[i]["face_id"] = str(fid)
                    # If auto-matched, assign immediately
                    if not skip_sim and face_dicts[i]["person_name"] and self._person_service:
                        pid, _ = self._face_service.find_similar_person(results[i].embedding)
                        if pid:
                            self._face_service.assign_person(fid, pid)
                            self._person_service.link_to_media(pid, self._current_media_id)
            except Exception as e:
                logger.warning(f"Failed to save faces: {e}")

        auto_matched = sum(1 for fd in face_dicts if fd.get("person_name"))
        logger.info(
            f"Face detection: {n} faces ({auto_matched} auto-matched) in {_detect_ms}ms",
            extra={"event": "FACE_DETECT", "duration_ms": _detect_ms, "media_id": str(self._current_media_id) if self._current_media_id else None},
        )
        self._refresh_person_names()
        img_rect = self._get_image_display_rect()
        self.face_overlay.set_faces(face_dicts, img_rect)
        self.face_overlay.setGeometry(self._image_container.rect())
        self.face_overlay.show()
        self.face_overlay.raise_()

        # Mark so batch worker skips this image later
        if self._current_media_id and self._media_service:
            try:
                self._media_service.mark_face_detected(self._current_media_id)
            except Exception as e:
                logger.warning(f"mark_face_detected failed: {e}")

        # Emit signal to inform main app that automatic matches might have updated the persons in this media
        if any(fd["person_name"] for fd in face_dicts):
            self.facesChanged.emit()

    def _on_detection_error(self, msg: str):
        logger.error(f"Face detection error: {msg}", extra={"event": "FACE_DETECT_ERROR"})
        self._status_label.setText(f"⚠️ Yüz algılama hatası: {msg[:60]}")

    def _refresh_person_names(self) -> None:
        """Fetch all person names from DB and push to the face overlay for autocomplete."""
        if not self._person_service:
            return
        try:
            persons = self._person_service.get_all()
            names = [p["name"] for p in persons if p.get("name")]
            self.face_overlay.set_person_names(names)
        except Exception as e:
            logger.warning(f"Could not refresh person names: {e}")

    def _auto_match_db_faces(self, db_faces: list[dict]) -> None:
        """For each DB face with no person assigned, attempt similarity match and persist."""
        if not self._face_service:
            return
        import numpy as np
        import json as _json
        matched = 0
        for face in db_faces:
            if face.get("person_name") or face.get("person_id"):
                continue  # already assigned
            if face.get("person_cleared"):
                continue  # user intentionally cleared this face — do not re-match
            raw_emb = face.get("embedding")
            if not raw_emb:
                continue
            try:
                arr = np.array(_json.loads(str(raw_emb)), dtype=np.float32)
                pid, pname = self._face_service.find_similar_person(arr)
                if pid and pname:
                    face["person_name"] = pname
                    face_id = face.get("id")
                    if face_id:
                        self._face_service.assign_person(UUID(str(face_id)), pid)
                    if self._current_media_id and self._person_service:
                        self._person_service.link_to_media(pid, self._current_media_id)
                    matched += 1
            except Exception as e:
                logger.warning(f"_auto_match_db_faces: failed for face {face.get('id')}: {e}")
        if matched:
            self._status_label.setText(
                f"🗃️ {len(db_faces)} yüz yüklendi, {matched} kişi eşleşti"
            )
            self.facesChanged.emit()

    def _show_db_faces(self, db_faces: list[dict]):
        """Render faces loaded from the database (skip detection)."""
        face_dicts = []
        for i, row in enumerate(db_faces):
            bbox = row.get("bbox")
            if isinstance(bbox, str):
                import json
                bbox = json.loads(bbox)
            person_id = str(row["person_id"]) if row.get("person_id") else None
            face_dicts.append({
                "bbox"        : bbox,
                "face_id"     : str(row["id"]) if row.get("id") else None,
                "person_name" : row.get("person_name"),
                "face_index"  : i,
                "person_id"   : person_id,
                "note"        : self._load_note(person_id, self._current_media_id),
            })

        self._refresh_person_names()
        img_rect = self._get_image_display_rect()
        self.face_overlay.set_faces(face_dicts, img_rect)
        self.face_overlay.setGeometry(self._image_container.rect())
        self.face_overlay.show()
        self.face_overlay.raise_()

    # ------------------------------------------------------------------
    # Note helpers
    # ------------------------------------------------------------------

    def _load_note(self, person_id, media_id) -> str:
        if not person_id or not media_id or not self._person_service:
            return ""
        try:
            from uuid import UUID
            return self._person_service.get_note(UUID(str(person_id)), media_id)
        except Exception as e:
            logger.warning(f"_load_note failed: {e}")
            return ""

    def _on_face_note_saved(self, face_index: int, note: str):
        face = next((f for f in self.face_overlay._faces if f["face_index"] == face_index), None)
        person_id = face.get("person_id") if face else None
        if not person_id or not self._current_media_id or not self._person_service:
            return
        try:
            from uuid import UUID
            self._person_service.save_note(UUID(str(person_id)), self._current_media_id, note)
            # Keep the cached note in the face dict so re-opening the popup shows it
            if face is not None:
                face["note"] = note
        except Exception as e:
            logger.warning(f"_on_face_note_saved failed: {e}")

    # ------------------------------------------------------------------
    # Name assignment
    # ------------------------------------------------------------------

    def _clear_face_list(self):
        while self.face_list_layout.count() > 0:
            item = self.face_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.face_list_layout.addStretch()

    def _populate_face_list(self):
        """Fetch faces from DB and show as thumbnails at the bottom."""
        self._clear_face_list()
        if not self._current_media_id:
            return

        try:
            from src.database import get_db
            from src.repositories.face_repository import FaceRepository
            repo = FaceRepository()
            faces = repo.get_faces_for_media(self._current_media_id)
            if not faces:
                self._status_label.setText("Bu videoda henüz yüz tespiti yapılmadı.")
                return

            self._status_label.setText(f"📹 Videoda {len(faces)} yüz tespit edildi.")
            
            # Remove the stretch we added in _clear_face_list
            self.face_list_layout.takeAt(self.face_list_layout.count()-1)

            from event_persons_dialog import _crop_face
            for f in faces:
                thumb = _VideoFaceThumb(f)
                thumb.clicked.connect(self._on_face_thumb_clicked)
                self.face_list_layout.addWidget(thumb)
                
                crop = _crop_face(self.current_img_path, f["bbox"], f.get("timestamp_ms"))
                thumb.set_pixmap(crop)
            
            self.face_list_layout.addStretch()
        except Exception as e:
            logger.error(f"Failed to populate video face list: {e}")

    def _on_face_thumb_clicked(self, face_data: dict):
        """When a video face thumbnail is clicked, show the full frame in the main view."""
        if not self.current_img_path:
            return
            
        try:
            from src.utils.video_util import get_video_frame
            t_ms = face_data.get("timestamp_ms") or 0
            pil_img = get_video_frame(self.current_img_path, t_ms)
            
            if pil_img:
                # Convert PIL to QImage
                from PIL import ImageQt
                qimg = ImageQt.ImageQt(pil_img)
                pix = QtGui.QPixmap.fromImage(qimg)
                
                # Show in main label and update zoom state
                self._source_pixmap = pix
                self._zoom_factor = 1.0  # Reset zoom to fit
                self.image_label.setPixmap(pix)
                # Update overlay with the new source pixmap
                self.face_overlay.set_source_pixmap(pix)
                self.face_overlay.clear_faces()
                
                # Position and show overlay correctly
                img_rect = self._get_image_display_rect()
                self.face_overlay.add_face(
                    face_data["bbox"], 
                    face_data.get("person_name") or "Bilinmiyor",
                    face_data.get("face_id"),
                    img_rect=img_rect
                )
                self.face_overlay.setGeometry(self._image_container.rect())
                self.face_overlay.update()
                self.face_overlay.show()
                self.face_overlay.raise_()
        except Exception as e:
            logger.error(f"_on_face_thumb_clicked failed: {e}")

    def _on_face_named(self, face_index: int, name: str):
        """
        Called when user presses Enter in a name input.

        Decision tree:
        1. Face has NO person yet → find_or_create(name), assign
        2. Face HAS person, new name matches ANOTHER existing person → REASSIGN
        3. Face HAS person, new name does NOT exist yet → RENAME in place (global)
        """
        if not name or not self._person_service:
            return

        name = name.strip()

        # Ensure media record exists
        if not self._current_media_id and self._media_service and self._current_event_id and self.current_img_path:
            try:
                self._current_media_id = self._media_service.ensure_media_exists(
                    self._current_event_id, self.current_img_path, "photo"
                )
            except Exception as e:
                logger.warning(f"ensure_media_exists failed: {e}")

        if face_index >= len(self.face_overlay._faces):
            return

        face_info = self.face_overlay._faces[face_index]
        face_id = face_info.get("face_id")

        # Ensure face row is in DB
        if not face_id and self._current_media_id and self._face_service and face_index < len(self._pending_results):
            try:
                # Save ALL pending results, not just this one, to avoid wiping other faces
                saved_ids = self._face_service.save_faces(
                    self._current_media_id, self._pending_results
                )
                if saved_ids:
                    # Update ALL face_ids in the overlay
                    for i, sid in enumerate(saved_ids):
                        if i < len(self.face_overlay._faces):
                            self.face_overlay._faces[i]["face_id"] = str(sid)
                    face_id = str(saved_ids[face_index])
            except Exception as e:
                logger.warning(f"save_faces fallback failed: {e}")

        # --- Look up OLD person currently assigned to this face ---
        old_person_id = None
        old_person_name = None
        if face_id and self._face_service and self._current_media_id:
            try:
                all_faces = self._face_service.get_faces_for_media(self._current_media_id)
                for f in all_faces:
                    if str(f.get("id")) == str(face_id) and f.get("person_id"):
                        old_person_id = UUID(str(f["person_id"]))
                        old_person_name = f.get("person_name")
                        break
            except Exception as e:
                logger.warning(f"Could not look up old person: {e}")

        # --- Check if new name already exists (WITHOUT creating) ---
        existing_person_id = self._person_service.find_by_name(name) if self._person_service else None

        # Same person, same name → noop
        if old_person_id and existing_person_id and str(old_person_id) == str(existing_person_id):
            self._status_label.setText(f"ℹ️ '{name}' zaten atanmış.")
            return

        # --- Decide: rename vs reassign vs new ---
        if old_person_id and not existing_person_id:
            # Name doesn't exist yet → RENAME the existing person in-place
            # This propagates to ALL photos that reference this person_id
            self._person_service.rename(old_person_id, name)
            final_person_id = old_person_id
            action = "yeniden adlandırıldı (tüm fotoğraflara yansıdı)"

        elif old_person_id and existing_person_id:
            # Name belongs to a DIFFERENT existing person → REASSIGN
            final_person_id = existing_person_id
            action = "yeniden atandı"

            # Unlink old person from this media if no other face still uses them
            try:
                all_faces = self._face_service.get_faces_for_media(self._current_media_id) if self._face_service else []
                still_linked = any(
                    str(f.get("id")) != str(face_id)
                    and str(f.get("person_id") or "") == str(old_person_id)
                    for f in all_faces
                )
                if not still_linked:
                    self._person_service.unlink_from_media(old_person_id, self._current_media_id)
            except Exception as e:
                logger.warning(f"Old person unlink failed: {e}")

        else:
            # No old person → create/find and assign fresh
            final_person_id = self._person_service.find_or_create(name)
            action = "kaydedildi"

        if not final_person_id:
            return

        # Assign person to face detection row
        if face_id and self._face_service:
            self._face_service.assign_person(UUID(str(face_id)), final_person_id)

        # Link person to media
        if self._current_media_id and self._person_service:
            self._person_service.link_to_media(final_person_id, self._current_media_id)

        self.face_overlay.update_person_name(face_index, name)
        # Update person_id in the face dict so the note textarea is enabled on re-open
        for f in self.face_overlay._faces:
            if f["face_index"] == face_index:
                f["person_id"] = str(final_person_id)
                break
        self._status_label.setText(f"✅ '{name}' {action}.")
        self.facesChanged.emit()

    def _on_face_cleared(self, face_index: int):
        """Clear the person assignment for a single face without re-detecting anything."""
        if face_index >= len(self.face_overlay._faces):
            return

        face_info = self.face_overlay._faces[face_index]
        face_id = face_info.get("face_id")

        if not face_id:
            return  # face not saved to DB yet — nothing to clear

        # Find the old person_id so we can unlink from media_persons if needed
        old_person_id = None
        if self._current_media_id and self._face_service:
            try:
                all_faces = self._face_service.get_faces_for_media(self._current_media_id)
                for f in all_faces:
                    if str(f.get("id")) == str(face_id):
                        old_person_id = f.get("person_id")
                        break
            except Exception as e:
                logger.warning(f"_on_face_cleared: could not fetch faces: {e}")

        # Clear person_id on just this face row
        if self._face_service:
            try:
                self._face_service.clear_person_for_face(UUID(str(face_id)))
            except Exception as e:
                logger.warning(f"clear_person_for_face failed: {e}")
                return

        # Unlink the person from media_persons if no other face in this media still uses them
        if old_person_id and self._current_media_id and self._person_service:
            try:
                all_faces = self._face_service.get_faces_for_media(self._current_media_id)
                still_linked = any(
                    str(f.get("id")) != str(face_id)
                    and str(f.get("person_id") or "") == str(old_person_id)
                    for f in all_faces
                )
                if not still_linked:
                    self._person_service.unlink_from_media(UUID(str(old_person_id)), self._current_media_id)
            except Exception as e:
                logger.warning(f"_on_face_cleared: unlink_from_media failed: {e}")

        # Update only this face's badge in the overlay
        self.face_overlay.update_person_name(face_index, "")
        self._status_label.setText("✕ Yüz etiketi temizlendi.")
        self.facesChanged.emit()

    def _on_face_reset(self, face_index: int):
        """Delete all face detections for this media from DB and re-run inference."""
        if not self.current_img_path:
            return

        # Delete DB records
        if self._current_media_id and self._face_service:
            try:
                self._face_service.delete_faces_for_media(self._current_media_id)
            except Exception as e:
                logger.warning(f"delete_faces_for_media failed: {e}")

        # Clear overlay and re-detect WITHOUT similarity matching
        self.face_overlay.clear_faces()
        self._pending_results = []
        self._skip_similarity = True  # skip auto-matching on next detection
        self._status_label.setText("🔄 Yüzler yeniden algılanıyor…")

        if self._face_service:
            self._start_detection(self.current_img_path)
            
        self.facesChanged.emit()

    # ------------------------------------------------------------------
    # Image / layout helpers
    # ------------------------------------------------------------------

    def _scale_and_show(self, pixmap: QtGui.QPixmap, smooth: bool = True):
        """Scale pixmap based on zoom factor and fit to container."""
        if pixmap.isNull():
            return

        # Base scale that fits the image into the visible container
        container_size = self.scroll_area.size() - QtCore.QSize(20, 20) # padding
        pw, ph = pixmap.width(), pixmap.height()
        cw, ch = container_size.width(), container_size.height()

        if pw == 0 or ph == 0:
            return

        fit_scale = min(cw / pw, ch / ph)
        total_scale = fit_scale * self._zoom_factor

        new_width = int(pw * total_scale)
        new_height = int(ph * total_scale)

        # Scale and show
        mode = QtCore.Qt.SmoothTransformation if smooth else QtCore.Qt.FastTransformation
        scaled = pixmap.scaled(
            new_width, new_height,
            QtCore.Qt.KeepAspectRatio,
            mode,
        )
        self.image_label.setPixmap(scaled)
        # Ensure label matches the pixmap size so scrollbars work correctly
        self.image_label.setFixedSize(scaled.size())

    def _refresh_pixmap(self):
        """Re-scale the cached source pixmap on resize — never reloads from disk."""
        if self._source_pixmap and not self._source_pixmap.isNull():
            self._scale_and_show(self._source_pixmap, smooth=False)

    def _get_image_display_rect(self) -> QtCore.QRect:
        """
        Calculate the pixel rect of the scaled image within the image container.
        Needed to translate normalised bbox coords to display coords.
        """
        pm = self.image_label.pixmap()
        if pm is None or pm.isNull():
            return self._image_container.rect()

        # The image_label's geometry inside _image_container perfectly describes
        # where the scaled image pixels reside, because we did setFixedSize()
        # on the label to precisely match the scaled pixmap.
        return self.image_label.geometry()

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        self.setFocus()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Right, QtCore.Qt.Key_Down):
            self.nextRequested.emit()
        elif event.key() in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Up):
            self.prevRequested.emit()
        elif event.key() == QtCore.Qt.Key_Space:
            self.doubleClicked.emit() # space bar toggles back to gallery
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming towards cursor."""
        if not self._source_pixmap or self._source_pixmap.isNull():
            return

        angle = event.angleDelta().y()
        zoom_step = 1.1 if angle > 0 else 1/1.1
        
        # Clamp zoom factor
        new_factor = self._zoom_factor * zoom_step
        if not (0.1 <= new_factor <= 20.0):
            return

        # 1. Capture old mouse positions
        container_pos = self._image_container.mapFrom(self, event.position().toPoint())
        old_x, old_y = container_pos.x(), container_pos.y()
        old_w = max(1, self._image_container.width())
        old_h = max(1, self._image_container.height())

        viewport = self.scroll_area.viewport()
        viewport_pos = viewport.mapFrom(self, event.position().toPoint())

        # 2. Apply zoom
        self._zoom_factor = new_factor
        self._refresh_pixmap()
        self._image_container.adjustSize()
        
        # Need to force event loop to process layout changes so scrollbars update max values
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        
        # 3. Calculate new scrollbar values to keep mouse pointing at the same spot
        new_w = self._image_container.width()
        new_h = self._image_container.height()
        
        scale_x = new_w / old_w
        scale_y = new_h / old_h
        
        new_x = old_x * scale_x
        new_y = old_y * scale_y

        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        
        h_bar.setValue(int(new_x - viewport_pos.x()))
        v_bar.setValue(int(new_y - viewport_pos.y()))

        # Update overlay geometry and alignment
        self.face_overlay.setGeometry(self._image_container.rect())
        self.face_overlay._img_rect = self._get_image_display_rect()
        self.face_overlay.raise_()
        self.face_overlay.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_img_path:
            self._refresh_pixmap()
            # Reposition overlay to match container
            self.face_overlay.setGeometry(self._image_container.rect())
            img_rect = self._get_image_display_rect()
            self.face_overlay._img_rect = img_rect
            self.face_overlay.raise_()
            self.face_overlay.update()
