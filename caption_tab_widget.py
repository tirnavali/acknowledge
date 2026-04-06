"""
CaptionTabWidget — "Altyazı" tab for AI-powered image captioning and tagging.

Uses Qwen2.5-VL-3B-Instruct via CaptionService.
All heavy work runs in QThread workers; UI is never blocked.
"""
from __future__ import annotations
import json
import logging
import os

from PySide6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class ModelLoadWorker(QtCore.QThread):
    finished = QtCore.Signal()
    error    = QtCore.Signal(str)

    def __init__(self, caption_service, parent=None):
        super().__init__(parent)
        self._svc = caption_service

    def run(self):
        try:
            self._svc._load_model()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class CaptionWorker(QtCore.QThread):
    finished = QtCore.Signal(object)   # CaptionResult
    error    = QtCore.Signal(str)

    def __init__(self, caption_service, img_path, parent=None):
        super().__init__(parent)
        self._svc      = caption_service
        self._img_path = img_path

    def run(self):
        try:
            result = self._svc.analyse(self._img_path)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class BatchCaptionWorker(QtCore.QThread):
    progress = QtCore.Signal(int, int)   # (current, total)
    one_done = QtCore.Signal(object)     # CaptionResult per image
    finished = QtCore.Signal(list)       # list[CaptionResult]
    error    = QtCore.Signal(str)

    def __init__(self, caption_service, img_paths, parent=None):
        super().__init__(parent)
        self._svc       = caption_service
        self._img_paths = img_paths
        self._stop      = False

    def stop(self):
        self._stop = True

    def run(self):
        results = []
        total   = len(self._img_paths)
        for i, path in enumerate(self._img_paths, 1):
            if self._stop:
                break
            try:
                result = self._svc.analyse(path)
            except Exception as e:
                from src.domain.entities.caption_result import CaptionResult
                result = CaptionResult(img_path=path, error=str(e))
                logger.warning(f"BatchCaptionWorker: error on {path}: {e}")
            results.append(result)
            self.one_done.emit(result)
            self.progress.emit(i, total)
        self.finished.emit(results)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class CaptionTabWidget(QtWidgets.QWidget):
    stats_updated = QtCore.Signal(object)  # Emitted with CaptionResult

    def __init__(self, caption_service, media_service, parent=None):
        super().__init__(parent)
        self._svc         = caption_service
        self._media_svc   = media_service
        self._model_worker  = None
        self._caption_worker = None
        self._batch_worker  = None
        self._single_result = None   # last CaptionResult for export

        self._build_ui()
        self._start_model_load()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- Status bar ---
        status_row = QtWidgets.QHBoxLayout()
        self._spinner = QtWidgets.QProgressBar()
        self._spinner.setRange(0, 0)   # indeterminate
        self._spinner.setFixedWidth(120)
        self._spinner.setFixedHeight(16)
        self._status_label = QtWidgets.QLabel("Model yükleniyor…")
        status_row.addWidget(self._spinner)
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        root.addLayout(status_row)

        # --- Splitter ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(splitter)

        # == LEFT PANEL ==
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)

        # Mode radio buttons
        mode_row = QtWidgets.QHBoxLayout()
        self._radio_single = QtWidgets.QRadioButton("Tekli Resim")
        self._radio_batch  = QtWidgets.QRadioButton("Toplu İşleme")
        self._radio_single.setChecked(True)
        mode_row.addWidget(self._radio_single)
        mode_row.addWidget(self._radio_batch)
        mode_row.addStretch()
        left_layout.addLayout(mode_row)

        # Stacked widget
        self._stack = QtWidgets.QStackedWidget()
        left_layout.addWidget(self._stack)

        # Page 0 — Single
        single_page = QtWidgets.QWidget()
        sp_layout   = QtWidgets.QVBoxLayout(single_page)
        sp_layout.setContentsMargins(0, 0, 0, 0)

        file_row = QtWidgets.QHBoxLayout()
        self._btn_pick   = QtWidgets.QPushButton("Dosya Seç")
        self._lbl_file   = QtWidgets.QLabel("Seçili dosya yok")
        self._lbl_file.setWordWrap(True)
        file_row.addWidget(self._btn_pick)
        file_row.addWidget(self._lbl_file, 1)
        sp_layout.addLayout(file_row)

        self._preview = QtWidgets.QLabel()
        self._preview.setFixedSize(320, 240)
        self._preview.setAlignment(QtCore.Qt.AlignCenter)
        self._preview.setStyleSheet("background:#1a1a1a; border:1px solid #333;")
        sp_layout.addWidget(self._preview)

        self._btn_analyse = QtWidgets.QPushButton("Analiz Et")
        self._btn_analyse.setEnabled(False)
        sp_layout.addWidget(self._btn_analyse)
        sp_layout.addStretch()
        self._stack.addWidget(single_page)

        # Page 1 — Batch
        batch_page  = QtWidgets.QWidget()
        bp_layout   = QtWidgets.QVBoxLayout(batch_page)
        bp_layout.setContentsMargins(0, 0, 0, 0)

        self._btn_add_files = QtWidgets.QPushButton("Dosya Ekle")
        bp_layout.addWidget(self._btn_add_files)

        self._file_list = QtWidgets.QListWidget()
        self._file_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        bp_layout.addWidget(self._file_list)

        batch_ctrl = QtWidgets.QHBoxLayout()
        self._btn_batch_start  = QtWidgets.QPushButton("Başlat")
        self._btn_batch_cancel = QtWidgets.QPushButton("İptal")
        self._btn_batch_cancel.setEnabled(False)
        batch_ctrl.addWidget(self._btn_batch_start)
        batch_ctrl.addWidget(self._btn_batch_cancel)
        bp_layout.addLayout(batch_ctrl)

        self._batch_progress = QtWidgets.QProgressBar()
        self._batch_progress.setValue(0)
        bp_layout.addWidget(self._batch_progress)

        self._batch_status = QtWidgets.QLabel("")
        bp_layout.addWidget(self._batch_status)
        bp_layout.addStretch()
        self._stack.addWidget(batch_page)

        splitter.addWidget(left)
        splitter.setStretchFactor(0, 1)

        # == RIGHT PANEL ==
        right        = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(8)

        self._txt_caption_en = QtWidgets.QTextEdit()
        self._txt_caption_en.setReadOnly(True)
        self._txt_caption_en.setMinimumHeight(80)

        self._txt_caption_tr = QtWidgets.QTextEdit()
        self._txt_caption_tr.setReadOnly(True)
        self._txt_caption_tr.setMinimumHeight(80)

        self._le_tags_en = QtWidgets.QLineEdit()
        self._le_tags_en.setReadOnly(True)

        self._le_tags_tr = QtWidgets.QLineEdit()
        self._le_tags_tr.setReadOnly(True)

        form.addRow("İngilizce Açıklama:", self._txt_caption_en)
        form.addRow("Türkçe Açıklama:",    self._txt_caption_tr)
        form.addRow("İngilizce Etiketler:", self._le_tags_en)
        form.addRow("Türkçe Etiketler:",   self._le_tags_tr)
        right_layout.addLayout(form)

        self._btn_export = QtWidgets.QPushButton("JSON Dışa Aktar")
        self._btn_export.setVisible(False)
        right_layout.addWidget(self._btn_export)

        self._lbl_stats = QtWidgets.QLabel("")
        self._lbl_stats.setStyleSheet("color: #888; font-size: 11px; margin-top: 10px;")
        right_layout.addWidget(self._lbl_stats)

        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 2)

        # --- Connections ---
        self._radio_single.toggled.connect(self._on_mode_changed)
        self._btn_pick.clicked.connect(self._on_pick_file)
        self._btn_analyse.clicked.connect(self._on_analyse)
        self._btn_add_files.clicked.connect(self._on_add_files)
        self._btn_batch_start.clicked.connect(self._on_batch_start)
        self._btn_batch_cancel.clicked.connect(self._on_batch_cancel)
        self._btn_export.clicked.connect(self._on_export_json)

        self._selected_path: str = ""

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _on_mode_changed(self, single_checked: bool):
        self._stack.setCurrentIndex(0 if single_checked else 1)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _start_model_load(self):
        self._spinner.setVisible(True)
        self._status_label.setText("Model yükleniyor…")
        self._btn_analyse.setEnabled(False)
        self._btn_batch_start.setEnabled(False)

        self._model_worker = ModelLoadWorker(self._svc, parent=self)
        self._model_worker.finished.connect(self._on_model_ready)
        self._model_worker.error.connect(self._on_model_error)
        self._model_worker.start()

    def _on_model_ready(self):
        self._spinner.setVisible(False)
        self._status_label.setText("Model hazır.")
        self._btn_batch_start.setEnabled(True)
        # Analyse button enabled only if a file is already selected
        if self._selected_path:
            self._btn_analyse.setEnabled(True)

    def _on_model_error(self, msg: str):
        self._spinner.setVisible(False)
        self._status_label.setText(f"Model yüklenemedi: {msg}")

    # ------------------------------------------------------------------
    # Single mode
    # ------------------------------------------------------------------

    def _on_pick_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Resim Seç", "",
            "Resimler (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff)"
        )
        if not path:
            return
        self._selected_path = path
        self._lbl_file.setText(os.path.basename(path))
        self._load_preview(path)
        if self._svc.is_ready():
            self._btn_analyse.setEnabled(True)

    def _load_preview(self, path: str):
        pix = QtGui.QPixmap(path)
        if not pix.isNull():
            pix = pix.scaled(
                self._preview.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        self._preview.setPixmap(pix)

    def _on_analyse(self):
        if not self._selected_path:
            return
        self._btn_analyse.setEnabled(False)
        self._status_label.setText("Analiz ediliyor…")
        self._spinner.setVisible(True)

        self._caption_worker = CaptionWorker(self._svc, self._selected_path, parent=self)
        self._caption_worker.finished.connect(self._on_single_finished)
        self._caption_worker.error.connect(self._on_worker_error)
        self._caption_worker.start()

    def _on_single_finished(self, result):
        self._spinner.setVisible(False)
        self._btn_analyse.setEnabled(True)
        self._single_result = result

        if result.error:
            self._status_label.setText(f"Hata: {result.error}")
            return

        self._txt_caption_en.setPlainText(result.caption_en)
        self._txt_caption_tr.setPlainText(result.caption_tr)
        self._le_tags_en.setText(result.tags_en)
        self._le_tags_tr.setText(result.tags_tr)
        self._status_label.setText("Analiz tamamlandı.")
        self._lbl_stats.setText(f"⏱ İşlem süresi: {result.duration:.2f} sn")
        self._btn_export.setVisible(True)
        self.stats_updated.emit(result)
        self._try_save_to_db(result)

    # ------------------------------------------------------------------
    # Batch mode
    # ------------------------------------------------------------------

    def _on_add_files(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Resim Seç", "",
            "Resimler (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff)"
        )
        for path in paths:
            item = QtWidgets.QListWidgetItem(os.path.basename(path))
            item.setData(QtCore.Qt.UserRole, path)
            self._file_list.addItem(item)

    def _on_batch_start(self):
        paths = []
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            paths.append(item.data(QtCore.Qt.UserRole))
        if not paths:
            QtWidgets.QMessageBox.information(self, "Bilgi", "Lütfen en az bir dosya ekleyin.")
            return

        self._batch_progress.setMaximum(len(paths))
        self._batch_progress.setValue(0)
        self._btn_batch_start.setEnabled(False)
        self._btn_batch_cancel.setEnabled(True)
        self._status_label.setText("Toplu analiz başladı…")

        self._batch_worker = BatchCaptionWorker(self._svc, paths, parent=self)
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.one_done.connect(self._on_batch_one_done)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.error.connect(self._on_worker_error)
        self._batch_worker.start()

    def _on_batch_cancel(self):
        if self._batch_worker:
            self._batch_worker.stop()
        self._btn_batch_cancel.setEnabled(False)
        self._status_label.setText("İptal ediliyor…")

    def _on_batch_progress(self, current: int, total: int):
        self._batch_progress.setValue(current)
        self._batch_status.setText(f"İşleniyor: {current} / {total}…")

    def _on_batch_one_done(self, result):
        self._try_save_to_db(result)
        self.stats_updated.emit(result)

    def _on_batch_finished(self, results: list):
        self._btn_batch_start.setEnabled(True)
        self._btn_batch_cancel.setEnabled(False)
        self._status_label.setText(f"Toplu analiz tamamlandı. {len(results)} resim işlendi.")
        self._auto_save_batch_json(results)

    def _auto_save_batch_json(self, results: list):
        out_path = os.path.join(os.getcwd(), "batch_results.json")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in results], f, ensure_ascii=False, indent=2)
            logger.info(f"Batch results saved to {out_path}")
        except Exception as e:
            logger.warning(f"Could not save batch_results.json: {e}")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export_json(self):
        if not self._single_result:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "JSON Kaydet", "", "JSON Dosyaları (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._single_result.to_dict(), f, ensure_ascii=False, indent=2)
            self._status_label.setText(f"Kaydedildi: {os.path.basename(path)}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Hata", f"Dosya kaydedilemedi: {e}")

    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    def _try_save_to_db(self, result):
        if result.error or not result.has_data:
            return
        try:
            record = self._media_svc.get_by_file_path(result.img_path)
            if record is None:
                logger.info(f"_try_save_to_db: {result.img_path} not in DB, skipping.")
                return
            from uuid import UUID
            media_id = record["id"]
            if not isinstance(media_id, UUID):
                media_id = UUID(str(media_id))
            self._media_svc.save_captions(media_id, result)
            logger.info(f"Captions saved to DB for {result.img_path}")
        except Exception as e:
            logger.warning(f"_try_save_to_db failed for {result.img_path}: {e}")

    # ------------------------------------------------------------------
    # Generic worker error
    # ------------------------------------------------------------------

    def _on_worker_error(self, msg: str):
        self._spinner.setVisible(False)
        self._btn_analyse.setEnabled(bool(self._selected_path) and self._svc.is_ready())
        self._status_label.setText(f"Hata: {msg}")
