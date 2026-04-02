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
from uuid import UUID
from PySide6 import QtCore, QtWidgets, QtGui

from face_overlay_widget import FaceOverlayWidget

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
        image = QtGui.QImage(self._img_path)
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
        self.face_overlay.hide()

        # Scroll area wraps the container
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self.scroll_area.setWidget(self._image_container)
        layout.addWidget(self.scroll_area)

        # Status bar for detection feedback
        self._status_label = QtWidgets.QLabel("")
        self._status_label.setAlignment(QtCore.Qt.AlignCenter)
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_context(self, event_id, media_id=None, face_detected_at=None, is_batch_pending=False):
        """Call from MainWindow to provide DB context for this image."""
        self._current_event_id = event_id
        self._current_media_id = media_id
        self._face_detected_at = face_detected_at
        self._is_batch_pending = is_batch_pending

    def set_image(self, img_path: str):
        """Load image asynchronously, clear overlay, trigger face detection."""
        self.current_img_path = img_path
        self.face_overlay.clear_faces()
        self._pending_results = []
        self._source_pixmap = None

        if not img_path or not os.path.exists(img_path):
            self.image_label.setText("Resim yüklenemedi.")
            self.filename_label.setText("")
            self._status_label.setText("")
            return

        self.filename_label.setText(os.path.basename(img_path))

        # Stop any in-flight loader for a previous image
        if self._image_loader and self._image_loader.isRunning():
            self._image_loader.quit()
            self._image_loader.wait(200)

        # Show placeholder immediately so the UI feels responsive
        self.image_label.setText("⏳ Yükleniyor…")
        self._status_label.setText("")

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
        self.face_overlay.set_source_pixmap(pixmap)
        self._scale_and_show(pixmap, smooth=True)

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
                else:
                    self._status_label.setText("Yüz algılanamadı.")
                return
            except Exception as e:
                logger.warning(f"Could not get faces from DB: {e}")

        # Batch worker is still running for this image → wait, don't duplicate detection
        if self._is_batch_pending and not self._face_detected_at:
            self._status_label.setText("⏳ Yüz tanıma bekleniyor…")
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
        self._start_detection(img_path)

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

        if not results:
            self._status_label.setText("Yüz algılanamadı.")
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
            face_dicts.append({
                "bbox"        : {"x1": face.x1, "y1": face.y1, "x2": face.x2, "y2": face.y2},
                "face_id"     : None,
                "person_name" : person_name,
                "face_index"  : i,
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
        logger.error(f"Face detection error: {msg}")
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
            face_dicts.append({
                "bbox"        : bbox,
                "face_id"     : str(row["id"]) if row.get("id") else None,
                "person_name" : row.get("person_name"),
                "face_index"  : i,
            })

        self._refresh_person_names()
        img_rect = self._get_image_display_rect()
        self.face_overlay.set_faces(face_dicts, img_rect)
        self.face_overlay.setGeometry(self._image_container.rect())
        self.face_overlay.show()
        self.face_overlay.raise_()

    # ------------------------------------------------------------------
    # Name assignment
    # ------------------------------------------------------------------

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
        """Scale pixmap to fit the container and display it."""
        mode = QtCore.Qt.SmoothTransformation if smooth else QtCore.Qt.FastTransformation
        scaled = pixmap.scaled(
            self._image_container.size(),
            QtCore.Qt.KeepAspectRatio,
            mode,
        )
        self.image_label.setPixmap(scaled)

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

        label_size = self._image_container.size()
        pm_size    = pm.size()

        x_off = (label_size.width()  - pm_size.width())  // 2
        y_off = (label_size.height() - pm_size.height()) // 2

        return QtCore.QRect(
            QtCore.QPoint(x_off, y_off),
            pm_size,
        )

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
        else:
            super().keyPressEvent(event)

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
