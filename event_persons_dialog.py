"""Dialog showing all persons detected in an event with face thumbnails."""
import json
import logging

from PySide6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


def _crop_face(file_path: str, bbox) -> QtGui.QPixmap | None:
    """Load image and crop the face region using normalised bbox dict."""
    try:
        from src.utils.path_util import from_db_path
        abs_path = from_db_path(file_path)
        pm = QtGui.QPixmap(abs_path)
        if pm.isNull():
            return None
        if isinstance(bbox, str):
            bbox = json.loads(bbox)
        if not isinstance(bbox, dict):
            return None
        w, h = pm.width(), pm.height()
        pad = 0.05
        x1 = max(0.0, bbox["x1"] - pad)
        y1 = max(0.0, bbox["y1"] - pad)
        x2 = min(1.0, bbox["x2"] + pad)
        y2 = min(1.0, bbox["y2"] + pad)
        crop_rect = QtCore.QRect(
            int(x1 * w), int(y1 * h),
            int((x2 - x1) * w), int((y2 - y1) * h),
        )
        return pm.copy(crop_rect)
    except Exception as e:
        logger.warning(f"Could not crop face from {file_path}: {e}")
        return None


class _PersonRow(QtWidgets.QFrame):
    clicked = QtCore.Signal(str)   # person name

    def __init__(self, person: dict, parent=None):
        super().__init__(parent)
        self._name = person["name"]
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame {
                background: rgba(45,45,50,200);
                border-radius: 6px;
            }
            QFrame:hover {
                background: rgba(0,120,215,180);
            }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 12, 6)
        layout.setSpacing(12)

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

        arrow = QtWidgets.QLabel("›")
        arrow.setStyleSheet("color: #50C8FF; font-size: 18px; background: transparent;")
        layout.addWidget(arrow)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._name)
        super().mousePressEvent(event)


class EventPersonsDialog(QtWidgets.QDialog):
    person_selected = QtCore.Signal(str)   # person name

    def __init__(self, persons: list[dict], event_name: str, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowTitle("Etkinlik Kişileri")
        self.setMinimumWidth(340)

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
        c_layout.setContentsMargins(10, 10, 10, 10)
        c_layout.setSpacing(8)

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
        scroll.setMaximumHeight(420)

        inner = QtWidgets.QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QtWidgets.QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(4)

        if persons:
            for p in persons:
                row = _PersonRow(p)
                row.clicked.connect(self._on_person_clicked)
                inner_layout.addWidget(row)
        else:
            empty = QtWidgets.QLabel("Bu etkinlikte henüz kişi bulunamadı.")
            empty.setAlignment(QtCore.Qt.AlignCenter)
            empty.setStyleSheet("color: #a0a0a0; font-size: 12px; padding: 20px;")
            inner_layout.addWidget(empty)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        c_layout.addWidget(scroll)

        hint = QtWidgets.QLabel("Kişiye tıkla → galeride filtrele   ·   ESC kapat")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("color: #555; font-size: 10px;")
        c_layout.addWidget(hint)

        outer.addWidget(container)

    def _on_person_clicked(self, name: str):
        self.person_selected.emit(name)
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
