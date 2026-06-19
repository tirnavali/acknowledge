"""Dialog showing all persons detected in an event with face thumbnails."""
from __future__ import annotations
import json
import logging

from PySide6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


def _crop_face(file_path: str, bbox, timestamp_ms: float | None = None) -> QtGui.QPixmap | None:
    """Load image/video and crop the face region. For videos, seeks to timestamp_ms if provided."""
    try:
        from src.utils.path_util import from_db_path
        from PIL import Image, ImageOps
        abs_path = from_db_path(file_path)
        
        # If it's a video, use PyAV helper
        from src.utils.video_util import VIDEO_EXTS, get_video_frame
        ext = "." + abs_path.lower().split('.')[-1]
        is_video = ext in VIDEO_EXTS
        
        if is_video:
            pil_img = get_video_frame(abs_path, timestamp_ms or 0)
            if not pil_img:
                return None
        else:
            with Image.open(abs_path) as img:
                img = ImageOps.exif_transpose(img)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                pil_img = img.copy() # copy to avoid closing issue
    except Exception as e:
        logger.warning(f"Could not load image/frame for cropping {file_path}: {e}")
        return None

    try:
        w, h = pil_img.size
        if isinstance(bbox, str):
            bbox = json.loads(bbox)
        if not isinstance(bbox, dict):
            return None
        
        # Increased padding (0.15) to show more context around the face
        pad = 0.15
        x1 = max(0.0, bbox["x1"] - pad)
        y1 = max(0.0, bbox["y1"] - pad)
        x2 = min(1.0, bbox["x2"] + pad)
        y2 = min(1.0, bbox["y2"] + pad)
        
        left, top, right, bottom = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)
        # Ensure we have a valid crop area
        if right <= left or bottom <= top:
            return None
            
        face_img = pil_img.crop((left, top, right, bottom))
        
        # Convert to QPixmap
        face_img.thumbnail((120, 120), Image.LANCZOS)
        width, height = face_img.size
        bytes_per_line = 3 * width
        data = face_img.tobytes("raw", "RGB")
        qimg = QtGui.QImage(data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888)
        return QtGui.QPixmap.fromImage(qimg.copy())
    except Exception as e:
        logger.debug(f"Crop failed for {file_path}: {e}")
        return None


class _PersonRow(QtWidgets.QFrame):
    clicked = QtCore.Signal()   # Emitted when row is clicked

    def __init__(self, person: dict, parent=None):
        super().__init__(parent)
        self._name = person["name"]
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 12, 6)
        layout.setSpacing(12)

        # Custom checkbox label
        self.check_label = QtWidgets.QLabel()
        self.check_label.setFixedSize(18, 18)
        self.check_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.check_label)

        # Face thumbnail
        thumb_label = QtWidgets.QLabel()
        thumb_label.setFixedSize(60, 60)
        thumb_label.setAlignment(QtCore.Qt.AlignCenter)
        thumb_label.setStyleSheet("border-radius: 4px; background: #3a3a3e;")

        crop = None
        if person.get("sample_file_path") and person.get("sample_bbox"):
            crop = _crop_face(person["sample_file_path"], person["sample_bbox"])

        if crop and not crop.isNull():
            thumb_label.setPixmap(
                crop.scaled(60, 60, QtCore.Qt.KeepAspectRatioByExpanding,
                            QtCore.Qt.SmoothTransformation)
                .copy(QtCore.QRect(0, 0, 60, 60))
            )
        else:
            thumb_label.setText("👤")
            thumb_label.setStyleSheet(
                "border-radius: 4px; background: #3a3a3e; font-size: 28px;"
            )
        layout.addWidget(thumb_label)

        # Name + count
        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setSpacing(2)

        name_label = QtWidgets.QLabel(person["name"])
        name_label.setStyleSheet("color: #f0f0f0; font-size: 13px; font-weight: bold; background: transparent;")
        text_layout.addWidget(name_label)

        face_count = person.get("face_count") or 0
        media_count = person.get("media_count") or 0
        count_label = QtWidgets.QLabel(f"{media_count} medyada · {face_count} yüz")
        count_label.setStyleSheet("color: #a0a0a0; font-size: 11px; background: transparent;")
        text_layout.addWidget(count_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        self._is_checked = False
        self.update_style(False)

    def toggle_checked(self):
        self.set_checked(not self._is_checked)

    def set_checked(self, checked: bool):
        self._is_checked = checked
        self.update_style(checked)

    def update_style(self, is_checked: bool):
        if is_checked:
            self.check_label.setText("✓")
            self.check_label.setStyleSheet("""
                QLabel {
                    color: #14141e;
                    background-color: #50C8FF;
                    border: 1px solid #50C8FF;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            self.setStyleSheet("""
                QFrame {
                    background: rgba(80, 200, 255, 40);
                    border: 1px solid rgba(80, 200, 255, 150);
                    border-radius: 6px;
                }
                QFrame:hover {
                    background: rgba(80, 200, 255, 70);
                }
            """)
        else:
            self.check_label.setText("")
            self.check_label.setStyleSheet("""
                QLabel {
                    background-color: #1e1e1e;
                    border: 2px solid #5a5a5e;
                    border-radius: 4px;
                }
            """)
            self.setStyleSheet("""
                QFrame {
                    background: rgba(45,45,50,200);
                    border: 1px solid transparent;
                    border-radius: 6px;
                }
                QFrame:hover {
                    background: rgba(0,120,215,180);
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.toggle_checked()
            self.clicked.emit()
        super().mousePressEvent(event)


class EventPersonsDialog(QtWidgets.QDialog):
    person_selected = QtCore.Signal(str)     # kept for compatibility
    persons_selected = QtCore.Signal(list)   # list of selected person names

    def __init__(self, persons: list[dict], event_name: str, active_persons: set[str] = None, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowTitle("Etkinlik Kişileri")
        self.setMinimumWidth(360)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        container = QtWidgets.QFrame(self)
        container.setObjectName("container")
        container.setStyleSheet("""
            QFrame#container {
                background: rgba(20, 20, 30, 235);
                border: 2px solid rgba(80, 200, 255, 160);
                border-radius: 10px;
            }
        """)
        c_layout = QtWidgets.QVBoxLayout(container)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(10)

        # Header
        header_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(f"👥  {event_name}")
        title.setStyleSheet("color: #50C8FF; font-size: 13px; font-weight: bold;")
        header_row.addWidget(title)
        header_row.addStretch()
        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(180,60,60,180);
                color: white;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(220,60,60,220); }
        """)
        close_btn.clicked.connect(self.close)
        header_row.addWidget(close_btn)
        c_layout.addLayout(header_row)

        # Scrollable person list
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setMaximumHeight(380)

        inner = QtWidgets.QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QtWidgets.QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(6)

        self.rows: list[_PersonRow] = []
        if persons:
            for p in persons:
                row = _PersonRow(p)
                if active_persons and p["name"] in active_persons:
                    row.set_checked(True)
                row.clicked.connect(self._on_row_clicked)
                self.rows.append(row)
                inner_layout.addWidget(row)
        else:
            empty = QtWidgets.QLabel("Bu etkinlikte henüz kişi bulunamadı.")
            empty.setAlignment(QtCore.Qt.AlignCenter)
            empty.setStyleSheet("color: #a0a0a0; font-size: 12px; padding: 20px;")
            inner_layout.addWidget(empty)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        c_layout.addWidget(scroll)

        # Action Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(8)

        self.toggle_all_btn = QtWidgets.QPushButton("Tümünü Seç")
        self.toggle_all_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.toggle_all_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 10);
                color: #e0e0e0;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 20);
            }
        """)
        self.toggle_all_btn.clicked.connect(self._toggle_all_selection)
        btn_layout.addWidget(self.toggle_all_btn)

        btn_layout.addStretch()

        cancel_btn = QtWidgets.QPushButton("İptal")
        cancel_btn.setCursor(QtCore.Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a0a0a0;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 5px 14px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 10);
                color: white;
            }
        """)
        cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(cancel_btn)

        self.filter_btn = QtWidgets.QPushButton("Filtrele")
        self.filter_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.filter_btn.clicked.connect(self._on_filter_clicked)
        btn_layout.addWidget(self.filter_btn)
        c_layout.addLayout(btn_layout)

        # Initial button setup
        self._on_row_clicked()

        hint = QtWidgets.QLabel("Seçimleri yapıp Filtrele butonuna tıklayın  ·  ESC kapat")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("color: #555; font-size: 10px; margin-top: 2px;")
        c_layout.addWidget(hint)

        outer.addWidget(container)

    def _on_row_clicked(self):
        any_checked = any(row._is_checked for row in self.rows)
        self.filter_btn.setEnabled(any_checked)
        if any_checked:
            self.filter_btn.setStyleSheet("""
                QPushButton {
                    background: #0078D7;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 5px 16px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #0086f0;
                }
            """)
        else:
            self.filter_btn.setStyleSheet("""
                QPushButton {
                    background: #2b2b2b;
                    color: #777;
                    border: 1px solid #3f3f46;
                    border-radius: 4px;
                    padding: 5px 16px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        
        all_checked = all(row._is_checked for row in self.rows) if self.rows else False
        self.toggle_all_btn.setText("Seçimleri Kaldır" if all_checked else "Tümünü Seç")

    def _toggle_all_selection(self):
        any_checked = any(row._is_checked for row in self.rows)
        target_state = not any_checked
        for row in self.rows:
            row.set_checked(target_state)
        self._on_row_clicked()

    def _on_filter_clicked(self):
        selected_names = [row._name for row in self.rows if row._is_checked]
        if selected_names:
            self.persons_selected.emit(selected_names)
            # Emit compatibility signal with the first person name
            self.person_selected.emit(selected_names[0])
            self.accept()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        container = self.findChild(QtWidgets.QFrame, "container")
        if container and not container.geometry().contains(event.pos()):
            self.close()
        super().mousePressEvent(event)
