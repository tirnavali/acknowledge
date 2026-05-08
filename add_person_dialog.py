"""
AddPersonDialog — Yeni kişi ekleme diyaloğu.
Kullanıcı bir isim ve referans fotoğraf seçer; fotoğrafta tam olarak 1 yüz
tespit edilmesi gerekir. Kaydet butonu yalnızca bu koşul sağlandığında aktif olur.
"""
import os
import numpy as np
from PySide6 import QtCore, QtWidgets, QtGui


class FaceDetectWorker(QtCore.QThread):
    """Tek bir görüntü dosyasında yüz tespiti yapar (UI'yi bloklamaz)."""
    detected = QtCore.Signal(object)   # list[FaceResult]
    error    = QtCore.Signal(str)

    def __init__(self, face_service, image_path: str, parent=None):
        super().__init__(parent)
        self._face_service = face_service
        self._image_path = image_path

    def run(self):
        try:
            results = self._face_service.detect_faces(self._image_path)
            self.detected.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class AddPersonDialog(QtWidgets.QDialog):
    def __init__(self, face_service, person_service, parent=None):
        super().__init__(parent)
        self._face_service = face_service
        self._person_service = person_service
        self._image_path: str | None = None
        self._embedding: np.ndarray | None = None
        self._detect_worker: FaceDetectWorker | None = None

        self.setWindowTitle("Yeni Kişi Ekle")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._init_ui()

    # ── Public properties ──────────────────────────────────────────────────

    @property
    def person_name(self) -> str:
        return self._name_input.text().strip()

    @property
    def reference_embedding(self) -> np.ndarray | None:
        return self._embedding

    # ── UI ────────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Name input
        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(QtWidgets.QLabel("İsim:"))
        self._name_input = QtWidgets.QLineEdit()
        self._name_input.setPlaceholderText("Kişinin adı ve soyadı")
        self._name_input.textChanged.connect(self._update_save_button)
        name_row.addWidget(self._name_input)
        layout.addLayout(name_row)

        # Photo select button
        photo_row = QtWidgets.QHBoxLayout()
        self._photo_label = QtWidgets.QLabel("Fotoğraf seçilmedi")
        self._photo_label.setStyleSheet("color: #888; font-size: 11px;")
        self._photo_label.setWordWrap(True)
        photo_btn = QtWidgets.QPushButton("Fotoğraf Seç…")
        photo_btn.setFixedWidth(120)
        photo_btn.clicked.connect(self._pick_photo)
        photo_row.addWidget(photo_btn)
        photo_row.addWidget(self._photo_label, 1)
        layout.addLayout(photo_row)

        # Face preview
        self._preview = QtWidgets.QLabel()
        self._preview.setFixedSize(160, 160)
        self._preview.setAlignment(QtCore.Qt.AlignCenter)
        self._preview.setStyleSheet(
            "border: 1px solid #3f3f46; background: #1e1e1e; color: #888; font-size: 11px;"
        )
        self._preview.setText("Yüz önizlemesi\nburada görünecek")
        self._preview.setWordWrap(True)
        layout.addWidget(self._preview, alignment=QtCore.Qt.AlignHCenter)

        # Status label
        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 12px;")
        self._status.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._status)

        # Instruction hint
        hint = QtWidgets.QLabel(
            "Not: Yüzün net göründüğü, ön cepheden çekilmiş, tek kişilik bir fotoğraf seçin."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(hint)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QtWidgets.QPushButton("İptal")
        cancel_btn.clicked.connect(self.reject)
        self._save_btn = QtWidgets.QPushButton("Kaydet")
        self._save_btn.setEnabled(False)
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setStyleSheet(
            "QPushButton:enabled { background-color: #0078D7; color: white; font-weight: bold; }"
        )
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

    # ── Slots ──────────────────────────────────────────────────────────────

    def _pick_photo(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Referans Fotoğraf Seç",
            "",
            "Görüntü Dosyaları (*.jpg *.jpeg *.png *.bmp *.webp)",
        )
        if not path:
            return

        self._image_path = path
        self._embedding = None
        self._photo_label.setText(os.path.basename(path))
        self._status.setText("⏳ Yüz tespit ediliyor…")
        self._status.setStyleSheet("color: #aaa; font-size: 12px;")
        self._preview.setText("…")
        self._save_btn.setEnabled(False)

        self._detect_worker = FaceDetectWorker(self._face_service, path, parent=self)
        self._detect_worker.detected.connect(self._on_faces_detected)
        self._detect_worker.error.connect(self._on_detect_error)
        self._detect_worker.start()

    def _on_faces_detected(self, results: list):
        count = len(results)
        if count == 0:
            self._status.setText("Yüz bulunamadı. Lütfen daha net veya farklı açıdan çekilmiş bir fotoğraf seçin.")
            self._status.setStyleSheet("color: #e74c3c; font-size: 12px;")
            self._preview.setText("Yüz bulunamadı")
            self._embedding = None
        elif count > 1:
            self._status.setText(
                f"{count} yüz tespit edildi. Bu kişinin yalnızca kendisinin göründüğü bir fotoğraf seçin."
            )
            self._status.setStyleSheet("color: #e67e22; font-size: 12px;")
            self._preview.setText(f"{count} yüz\ntespit edildi")
            self._embedding = None
        else:
            face = results[0]
            self._embedding = face.embedding
            self._show_face_crop(face)
            self._check_existing_person(face.embedding)

        self._update_save_button()

    def _check_existing_person(self, embedding):
        """Warn if this face already matches a registered person in the DB."""
        try:
            person_id, person_name = self._face_service.find_similar_person(embedding)
        except Exception:
            person_id, person_name = None, None

        if person_name:
            self._status.setText(
                f"⚠️ Bu yüz veritabanında '{person_name}' olarak tanındı. "
                "Farklı bir kişiyse devam edebilirsiniz."
            )
            self._status.setStyleSheet("color: #e67e22; font-size: 12px;")
        else:
            self._status.setText("✓ 1 yüz tespit edildi. Kaydedebilirsiniz.")
            self._status.setStyleSheet("color: #27ae60; font-size: 12px;")

    def _on_detect_error(self, msg: str):
        self._status.setText(f"Hata: {msg}")
        self._status.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self._embedding = None
        self._update_save_button()

    def _show_face_crop(self, face):
        try:
            img = QtGui.QImage(self._image_path)
            if img.isNull():
                return
            w, h = img.width(), img.height()
            x1 = int(face.x1 * w)
            y1 = int(face.y1 * h)
            x2 = int(face.x2 * w)
            y2 = int(face.y2 * h)
            # Add 20% padding around the crop
            pad_x = int((x2 - x1) * 0.2)
            pad_y = int((y2 - y1) * 0.2)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)
            crop = img.copy(x1, y1, x2 - x1, y2 - y1)
            pixmap = QtGui.QPixmap.fromImage(crop).scaled(
                160, 160,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            self._preview.setPixmap(pixmap)
        except Exception:
            self._preview.setText("Önizleme yüklenemedi")

    def _update_save_button(self):
        self._save_btn.setEnabled(
            bool(self.person_name) and self._embedding is not None
        )

    def _on_save(self):
        if not self.person_name:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen bir isim girin.")
            return
        if self._embedding is None:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Geçerli bir yüz tespit edilmedi.")
            return

        # Check if a person with this name already exists in the DB
        try:
            existing_id = self._person_service.find_by_name(self.person_name)
        except Exception:
            existing_id = None

        if existing_id:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Kişi Zaten Mevcut",
                f'"{self.person_name}" adlı bir kişi zaten kayıtlı.\n'
                "Referans fotoğrafını güncellemek ve taramayı yeniden çalıştırmak istiyor musunuz?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

        self.accept()
