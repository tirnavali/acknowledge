"""iOS-style toggle switch widget for PySide6.

Drop-in replacement for QCheckBox:
  - Same `toggled(bool)` signal
  - `isChecked()`, `setChecked()`, `setEnabled()`, `setText()`, `setToolTip()`
"""
from PySide6 import QtCore, QtGui, QtWidgets


class ToggleSwitch(QtWidgets.QWidget):
    """Animated sliding toggle switch with an optional label."""

    toggled = QtCore.Signal(bool)

    # Visual constants
    _TRACK_W = 38
    _TRACK_H = 20
    _THUMB_D = 14
    _PADDING = 3        # space between thumb and track edge
    _LABEL_GAP = 8      # gap between track and label text
    _ANIM_MS = 150

    _COLOR_ON  = QtGui.QColor("#4CAF50")
    _COLOR_OFF = QtGui.QColor("#555555")
    _COLOR_THUMB = QtGui.QColor("#ffffff")
    _COLOR_DISABLED = QtGui.QColor("#3a3a3a")
    _COLOR_LABEL = QtGui.QColor("#cccccc")
    _COLOR_LABEL_DISABLED = QtGui.QColor("#666666")

    def __init__(self, text: str = "", checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._text = text
        self._enabled = True

        # Animated thumb position: 0.0 = off, 1.0 = on
        self._anim_pos = 1.0 if checked else 0.0
        self._animation = QtCore.QPropertyAnimation(self, b"_pos", self)
        self._animation.setDuration(self._ANIM_MS)
        self._animation.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed,
            QtWidgets.QSizePolicy.Fixed,
        )
        self._update_size_hint()

    # ── Qt property used by QPropertyAnimation ────────────────────────────
    def _get_pos(self) -> float:
        return self._anim_pos

    def _set_pos(self, value: float):
        self._anim_pos = value
        self.update()

    _pos = QtCore.Property(float, _get_pos, _set_pos)

    # ── Public API (matches QCheckBox) ─────────────────────────────────────
    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked == checked:
            return
        self._checked = checked
        self._animate_to(1.0 if checked else 0.0)
        self.toggled.emit(checked)

    def setText(self, text: str):
        self._text = text
        self._update_size_hint()
        self.update()

    def text(self) -> str:
        return self._text

    def setEnabled(self, enabled: bool):
        self._enabled = enabled
        super().setEnabled(enabled)
        self.update()

    # ── Size hint ──────────────────────────────────────────────────────────
    def _update_size_hint(self):
        fm = self.fontMetrics()
        label_w = (fm.horizontalAdvance(self._text) + self._LABEL_GAP) if self._text else 0
        w = self._TRACK_W + label_w
        h = max(self._TRACK_H, fm.height())
        self.setFixedSize(w, h)

    def sizeHint(self) -> QtCore.QSize:
        return self.size()

    # ── Interaction ────────────────────────────────────────────────────────
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton and self._enabled:
            self.setChecked(not self._checked)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Return):
            self.setChecked(not self._checked)
        else:
            super().keyPressEvent(event)

    # ── Animation helper ───────────────────────────────────────────────────
    def _animate_to(self, target: float):
        self._animation.stop()
        self._animation.setStartValue(self._anim_pos)
        self._animation.setEndValue(target)
        self._animation.start()

    # ── Painting ───────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # Track
        track_color = (
            self._COLOR_DISABLED if not self._enabled
            else self._COLOR_ON if self._checked else self._COLOR_OFF
        )
        # Blend: animate color between off and on
        if self._enabled and 0.0 < self._anim_pos < 1.0:
            t = self._anim_pos
            r = int(self._COLOR_OFF.red()   + t * (self._COLOR_ON.red()   - self._COLOR_OFF.red()))
            g = int(self._COLOR_OFF.green() + t * (self._COLOR_ON.green() - self._COLOR_OFF.green()))
            b = int(self._COLOR_OFF.blue()  + t * (self._COLOR_ON.blue()  - self._COLOR_OFF.blue()))
            track_color = QtGui.QColor(r, g, b)

        track_rect = QtCore.QRectF(
            0,
            (self.height() - self._TRACK_H) / 2,
            self._TRACK_W,
            self._TRACK_H,
        )
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(track_rect, self._TRACK_H / 2, self._TRACK_H / 2)

        # Thumb
        travel = self._TRACK_W - self._THUMB_D - 2 * self._PADDING
        thumb_x = self._PADDING + self._anim_pos * travel
        thumb_y = (self.height() - self._THUMB_D) / 2
        thumb_rect = QtCore.QRectF(thumb_x, thumb_y, self._THUMB_D, self._THUMB_D)
        p.setBrush(self._COLOR_THUMB)
        p.drawEllipse(thumb_rect)

        # Label
        if self._text:
            lx = self._TRACK_W + self._LABEL_GAP
            label_color = (
                self._COLOR_LABEL_DISABLED if not self._enabled
                else self._COLOR_LABEL
            )
            p.setPen(label_color)
            p.setFont(self.font())
            p.drawText(
                QtCore.QRectF(lx, 0, self.width() - lx, self.height()),
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                self._text,
            )

        p.end()
