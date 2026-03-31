"""
FaceOverlayWidget — transparent overlay drawn on top of the image display.

Responsibilities:
- Draw semi-transparent bounding boxes around detected faces with soft padding
- Show a name badge above each box when a name is assigned
- Show a zoom popup (with name input) when the user clicks a bounding box
- Emit face_named(face_index, name_str) when user confirms a name via zoom popup
- Emit face_reset(face_index) when user clicks reset in zoom popup
- Scale bbox coordinates from normalised (0..1) to pixel space on resize
"""
from __future__ import annotations
from PySide6 import QtCore, QtWidgets, QtGui


PADDING       = 0.015                                     # extra pad around bbox (fraction of image)
BOX_COLOR     = QtGui.QColor(80, 200, 255, 200)           # cyan border
BOX_FILL      = QtGui.QColor(80, 200, 255, 30)
BADGE_BG      = QtGui.QColor(0, 0, 0, 200)
BADGE_FG      = QtGui.QColor(255, 255, 255, 240)
BADGE_H       = 24
BADGE_FONT_PT = 10


# ---------------------------------------------------------------------------
# Helper: floating name input
# ---------------------------------------------------------------------------

class NameLineEdit(QtWidgets.QLineEdit):
    """Small floating name input."""

    committed = QtCore.Signal(str)  # emitted on Enter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("İsim gir, Enter'a bas…")
        self.setFixedHeight(28)
        self.setStyleSheet("""
            QLineEdit {
                background: rgba(0,0,0,180);
                color: #fff;
                border: 1px solid rgba(80,200,255,200);
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10pt;
            }
            QLineEdit:focus { border: 1px solid #50C8FF; }
        """)
        self.returnPressed.connect(lambda: self.committed.emit(self.text().strip()))


# ---------------------------------------------------------------------------
# Zoom popup dialog — contains the name input + reset
# ---------------------------------------------------------------------------

class FaceZoomPopup(QtWidgets.QDialog):
    """
    Popup that shows a cropped zoomed view of a single face AND
    provides the name-input field + reset button for labelling.
    """

    # Forwarded signals
    face_named = QtCore.Signal(int, str)   # (face_index, name)
    face_reset = QtCore.Signal(int)        # (face_index)

    def __init__(
        self,
        pixmap: QtGui.QPixmap,
        face_name: str | None,
        face_index: int,
        parent=None,
    ):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowTitle("Yüz Zoom")
        self._face_index = face_index

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Rounded container
        container = QtWidgets.QFrame(self)
        container.setObjectName("container")
        container.setStyleSheet("""
            QFrame#container {
                background: rgba(20,20,30,230);
                border: 2px solid rgba(80,200,255,180);
                border-radius: 10px;
            }
        """)
        cLayout = QtWidgets.QVBoxLayout(container)
        cLayout.setContentsMargins(10, 10, 10, 10)
        cLayout.setSpacing(8)

        # Zoomed face image
        img_label = QtWidgets.QLabel()
        popup_size = QtCore.QSize(220, 220)
        scaled = pixmap.scaled(popup_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        img_label.setPixmap(scaled)
        img_label.setAlignment(QtCore.Qt.AlignCenter)
        cLayout.addWidget(img_label)

        # --- Name input row ---
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)

        self._name_edit = NameLineEdit()
        if face_name:
            self._name_edit.setText(face_name)
        self._name_edit.committed.connect(self._on_committed)
        row.addWidget(self._name_edit)

        # Reset button
        reset_btn = QtWidgets.QPushButton("🔄")
        reset_btn.setFixedSize(28, 28)
        reset_btn.setToolTip("Etiketi sil ve yeniden algıla")
        reset_btn.setCursor(QtCore.Qt.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: rgba(200, 60, 60, 180);
                color: white;
                border: 1px solid rgba(255,100,100,200);
                border-radius: 4px;
                font-size: 13px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(255, 80, 80, 220);
            }
        """)
        reset_btn.clicked.connect(self._on_reset)
        row.addWidget(reset_btn)

        cLayout.addLayout(row)

        # Confirm button
        confirm_btn = QtWidgets.QPushButton("✔ Kaydet")
        confirm_btn.setCursor(QtCore.Qt.PointingHandCursor)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: rgba(80,200,255,180);
                color: #000;
                border: none;
                border-radius: 4px;
                font-size: 10pt;
                font-weight: bold;
                padding: 4px 0;
            }
            QPushButton:hover {
                background: rgba(80,200,255,230);
            }
        """)
        confirm_btn.clicked.connect(lambda: self._on_committed(self._name_edit.text().strip()))
        cLayout.addWidget(confirm_btn)

        # Close button
        close_btn = QtWidgets.QPushButton("✕ Kapat")
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(60,60,70,200);
                color: #aaa;
                border: 1px solid rgba(120,120,130,150);
                border-radius: 4px;
                font-size: 9pt;
                padding: 3px 0;
            }
            QPushButton:hover {
                background: rgba(90,90,100,230);
                color: #fff;
            }
        """)
        close_btn.clicked.connect(self.close)
        cLayout.addWidget(close_btn)

        # Close hint
        hint = QtWidgets.QLabel("Esc veya dışına tıkla")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("color: #555; font-size: 7pt;")
        cLayout.addWidget(hint)

        layout.addWidget(container)
        self.setLayout(layout)
        self.adjustSize()

        # Focus the input immediately
        self._name_edit.setFocus()

    def _on_committed(self, name: str) -> None:
        if name:
            self.face_named.emit(self._face_index, name)
        self.close()

    def _on_reset(self) -> None:
        self.face_reset.emit(self._face_index)
        self.close()

    def mousePressEvent(self, event):
        # Close only if click is outside the container
        child = self.childAt(event.pos())
        if child is None:
            self.close()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Main overlay widget
# ---------------------------------------------------------------------------

class FaceOverlayWidget(QtWidgets.QWidget):
    """
    Transparent overlay widget positioned over the displayed image.
    Name labelling is done exclusively via the zoom popup.
    """

    # Emitted when user types a name and presses Enter in the zoom popup
    face_named = QtCore.Signal(int, str)
    # Emitted when user clicks the reset button in the zoom popup
    face_reset = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._faces: list[dict] = []
        self._img_rect: QtCore.QRect = QtCore.QRect()
        # The original (un-scaled) QPixmap — used for zoom crops
        self._source_pixmap: QtGui.QPixmap | None = None
        self._zoom_popup: FaceZoomPopup | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_source_pixmap(self, pixmap: QtGui.QPixmap | None):
        """Provide the full-res pixmap for zoom crops."""
        self._source_pixmap = pixmap

    def set_faces(self, faces: list[dict], img_rect: QtCore.QRect) -> None:
        """
        Update displayed faces.

        faces items: { 'bbox', 'face_id', 'person_name', 'face_index' }
        bbox: {x1,y1,x2,y2} normalised floats
        img_rect: pixel rect of the scaled image within this widget
        """
        self._faces = []
        self._img_rect = img_rect

        for i, face in enumerate(faces):
            existing = face.get("person_name") or ""
            idx = face.get("face_index", i)
            self._faces.append({
                "bbox"        : face["bbox"],
                "face_id"     : face.get("face_id"),
                "person_name" : existing,
                "face_index"  : idx,
            })

        self.update()

    def clear_faces(self) -> None:
        if self._zoom_popup:
            self._zoom_popup.close()
            self._zoom_popup = None
        self._faces = []
        self._img_rect = QtCore.QRect()
        self._source_pixmap = None
        self.update()

    def update_person_name(self, face_index: int, name: str) -> None:
        """Called externally after a name is saved, to refresh the badge."""
        for f in self._faces:
            if f["face_index"] == face_index:
                f["person_name"] = name
                break
        self.update()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bbox_to_pixels(self, bbox: dict) -> QtCore.QRect:
        r = self._img_rect
        if r.isEmpty():
            return QtCore.QRect()
        pad_x = PADDING * r.width()
        pad_y = PADDING * r.height()
        x1 = int(r.left() + bbox["x1"] * r.width()  - pad_x)
        y1 = int(r.top()  + bbox["y1"] * r.height() - pad_y)
        x2 = int(r.left() + bbox["x2"] * r.width()  + pad_x)
        y2 = int(r.top()  + bbox["y2"] * r.height() + pad_y)
        return QtCore.QRect(
            QtCore.QPoint(max(r.left(), x1), max(r.top(), y1)),
            QtCore.QPoint(min(r.right(), x2), min(r.bottom(), y2)),
        )

    def _crop_face_pixmap(self, bbox: dict) -> QtGui.QPixmap | None:
        """Crop the face from the source pixmap using normalised bbox coords."""
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return None
        pm = self._source_pixmap
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

    def _show_zoom(self, face: dict, global_pos: QtCore.QPoint) -> None:
        if self._zoom_popup:
            self._zoom_popup.close()
        crop = self._crop_face_pixmap(face["bbox"])
        if crop is None or crop.isNull():
            return
        popup = FaceZoomPopup(
            crop,
            face.get("person_name"),
            face["face_index"],
            self.window(),
        )
        popup.face_named.connect(self.face_named)
        popup.face_reset.connect(self.face_reset)

        # Position near the click, but keep on screen
        screen = QtWidgets.QApplication.screenAt(global_pos)
        if screen:
            sg = screen.availableGeometry()
            px = min(global_pos.x() + 15, sg.right()  - popup.width()  - 10)
            py = min(global_pos.y() + 15, sg.bottom() - popup.height() - 10)
            popup.move(px, py)
        else:
            popup.move(global_pos + QtCore.QPoint(15, 15))
        popup.show()
        self._zoom_popup = popup

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        for face in self._faces:
            rect = self._bbox_to_pixels(face["bbox"])
            if rect.isEmpty():
                continue

            # Bounding box fill + border
            painter.fillRect(rect, BOX_FILL)
            pen = QtGui.QPen(BOX_COLOR, 2)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Name badge above the box
            name = face.get("person_name") or ""
            if name:
                font = painter.font()
                font.setPointSize(BADGE_FONT_PT)
                font.setBold(True)
                painter.setFont(font)
                fm = QtGui.QFontMetrics(font)
                text_w = fm.horizontalAdvance(name) + 20
                badge_w = max(rect.width(), text_w)
                badge_x = rect.left() + (rect.width() - badge_w) // 2
                badge_y = rect.top() - BADGE_H - 2
                badge_rect = QtCore.QRect(badge_x, badge_y, badge_w, BADGE_H)

                if badge_rect.top() < 0:
                    badge_rect.moveTop(rect.bottom() + 4)

                painter.fillRect(badge_rect, BADGE_BG)
                painter.setPen(QtGui.QPen(BOX_COLOR, 1))
                painter.drawRect(badge_rect)
                painter.setPen(BADGE_FG)
                painter.drawText(badge_rect, QtCore.Qt.AlignCenter, name)

            # Click-to-label hint (when no name yet)
            else:
                font = painter.font()
                font.setPointSize(8)
                font.setBold(False)
                painter.setFont(font)
                painter.setPen(QtGui.QColor(200, 200, 200, 180))
                painter.drawText(rect, QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter, "🖱 tıkla → isim ver")

    def mousePressEvent(self, event):
        """Open zoom popup (with name input) when user clicks inside a bounding box."""
        if event.button() == QtCore.Qt.LeftButton:
            for face in self._faces:
                rect = self._bbox_to_pixels(face["bbox"])
                if rect.contains(event.pos()):
                    self._show_zoom(face, event.globalPosition().toPoint())
                    break
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()
