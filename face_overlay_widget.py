"""
FaceOverlayWidget — transparent overlay drawn on top of the image display.

Responsibilities:
- Draw semi-transparent bounding boxes around detected faces with soft padding
- Show a name label (QLineEdit) below each box for user input
- Show a zoom popup when the user clicks a bounding box
- Emit face_named(face_index, name_str) when user confirms a name
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
    """Small floating name input placed below a face bounding box."""

    committed = QtCore.Signal(str)  # emitted on Enter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("İsim gir, Enter'a bas…")
        self.setFixedHeight(24)
        self.setStyleSheet("""
            QLineEdit {
                background: rgba(0,0,0,180);
                color: #fff;
                border: 1px solid rgba(80,200,255,200);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10pt;
            }
            QLineEdit:focus { border: 1px solid #50C8FF; }
        """)
        self.returnPressed.connect(lambda: self.committed.emit(self.text().strip()))


# ---------------------------------------------------------------------------
# Zoom popup dialog
# ---------------------------------------------------------------------------

class FaceZoomPopup(QtWidgets.QDialog):
    """
    Small popup that shows a cropped, zoomed view of a single face.
    Displayed when the user clicks on a bounding box.
    """

    def __init__(self, pixmap: QtGui.QPixmap, face_name: str | None, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowTitle("Yüz Zoom")

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
        cLayout.setContentsMargins(8, 8, 8, 8)
        cLayout.setSpacing(4)

        # Zoomed face image
        img_label = QtWidgets.QLabel()
        # Scale to a fixed popup size keeping aspect ratio
        popup_size = QtCore.QSize(220, 220)
        scaled = pixmap.scaled(popup_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        img_label.setPixmap(scaled)
        img_label.setAlignment(QtCore.Qt.AlignCenter)
        cLayout.addWidget(img_label)

        # Name label
        if face_name:
            name_lbl = QtWidgets.QLabel(face_name)
            name_lbl.setAlignment(QtCore.Qt.AlignCenter)
            name_lbl.setStyleSheet("color: #50C8FF; font-weight: bold; font-size: 11pt;")
            cLayout.addWidget(name_lbl)

        # Close hint
        hint = QtWidgets.QLabel("Kapat: Esc veya tıkla")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("color: #666; font-size: 8pt;")
        cLayout.addWidget(hint)

        layout.addWidget(container)
        self.setLayout(layout)
        self.adjustSize()

    def mousePressEvent(self, event):
        self.close()

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
    """

    # Emitted when user types a name and presses Enter: (face_index, name)
    face_named = QtCore.Signal(int, str)
    # Emitted when user clicks the reset button: (face_index)
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
        for f in self._faces:
            f["name_input"].deleteLater()
            f["reset_btn"].deleteLater()
        self._faces = []
        self._img_rect = img_rect

        for i, face in enumerate(faces):
            inp = NameLineEdit(self)
            existing = face.get("person_name") or ""
            if existing:
                inp.setText(existing)
            idx = face.get("face_index", i)
            inp.committed.connect(lambda name, fi=idx: self.face_named.emit(fi, name))
            inp.show()

            # Reset button (🔄) — deletes DB label, re-runs inference
            btn = QtWidgets.QPushButton("🔄", self)
            btn.setFixedSize(24, 24)
            btn.setToolTip("Etiketi sil ve yeniden algıla")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(200, 60, 60, 180);
                    color: white;
                    border: 1px solid rgba(255,100,100,200);
                    border-radius: 4px;
                    font-size: 12px;
                    padding: 0;
                }
                QPushButton:hover {
                    background: rgba(255, 80, 80, 220);
                }
            """)
            btn.clicked.connect(lambda checked=False, fi=idx: self.face_reset.emit(fi))
            btn.show()

            self._faces.append({
                "bbox"        : face["bbox"],
                "face_id"     : face.get("face_id"),
                "person_name" : existing,
                "face_index"  : idx,
                "name_input"  : inp,
                "reset_btn"   : btn,
            })

        self._layout_inputs()
        self.update()

    def clear_faces(self) -> None:
        if self._zoom_popup:
            self._zoom_popup.close()
            self._zoom_popup = None
        for f in self._faces:
            f["name_input"].deleteLater()
            f["reset_btn"].deleteLater()
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

    def _layout_inputs(self) -> None:
        for face in self._faces:
            rect = self._bbox_to_pixels(face["bbox"])
            inp: NameLineEdit = face["name_input"]
            btn: QtWidgets.QPushButton = face["reset_btn"]
            if rect.isEmpty():
                inp.hide()
                btn.hide()
                continue
            # Width: at least bbox width, minimum 130px, leave room for reset btn
            btn_w = btn.width() + 4
            inp_w = max(rect.width(), 130)
            total_w = inp_w + btn_w
            inp_x = rect.left() + (rect.width() - total_w) // 2
            inp_y = rect.bottom() + 4
            inp_x = max(0, min(inp_x, self.width() - total_w))
            inp_y = min(inp_y, self.height() - inp.height() - 2)
            inp.setFixedWidth(inp_w)
            inp.move(inp_x, inp_y)
            inp.show()
            btn.move(inp_x + inp_w + 4, inp_y)
            btn.show()

    def _crop_face_pixmap(self, bbox: dict) -> QtGui.QPixmap | None:
        """Crop the face from the source pixmap using normalised bbox coords."""
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return None
        pm = self._source_pixmap
        w, h = pm.width(), pm.height()
        # Add generous padding for context
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
        popup = FaceZoomPopup(crop, face.get("person_name"), self.window())
        # Position near the click, but keep on screen
        screen = QtWidgets.QApplication.screenAt(global_pos)
        if screen:
            sg = screen.availableGeometry()
            px = min(global_pos.x() + 15, sg.right() - popup.width() - 10)
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
                # Measure text width
                font = painter.font()
                font.setPointSize(BADGE_FONT_PT)
                font.setBold(True)
                painter.setFont(font)
                fm = QtGui.QFontMetrics(font)
                text_w = fm.horizontalAdvance(name) + 20   # padding
                badge_w = max(rect.width(), text_w)
                badge_x = rect.left() + (rect.width() - badge_w) // 2
                badge_y = rect.top() - BADGE_H - 2
                badge_rect = QtCore.QRect(badge_x, badge_y, badge_w, BADGE_H)

                # Keep within widget
                if badge_rect.top() < 0:
                    # Draw below box instead
                    badge_rect.moveTop(rect.bottom() + face["name_input"].height() + 6)

                painter.fillRect(badge_rect, BADGE_BG)
                # Cyan border on badge
                painter.setPen(QtGui.QPen(BOX_COLOR, 1))
                painter.drawRect(badge_rect)
                # Text
                painter.setPen(BADGE_FG)
                painter.drawText(badge_rect, QtCore.Qt.AlignCenter, name)

    def mousePressEvent(self, event):
        """Open zoom popup when user clicks inside a bounding box."""
        if event.button() == QtCore.Qt.LeftButton:
            for face in self._faces:
                rect = self._bbox_to_pixels(face["bbox"])
                if rect.contains(event.pos()):
                    self._show_zoom(face, event.globalPosition().toPoint())
                    # Focus the name input for this face
                    face["name_input"].setFocus()
                    break
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_inputs()
        self.update()
