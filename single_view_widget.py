import sys
from PySide6 import QtCore, QtWidgets, QtGui

class SingleViewWidget(QtWidgets.QWidget):
    """
    A widget to display a single image in a large view with scaling and navigation.
    """
    doubleClicked = QtCore.Signal()
    nextRequested = QtCore.Signal()
    prevRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.initUI()
        self.current_img_path = None

    def initUI(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Filename label
        self.filename_label = QtWidgets.QLabel("Dosya adı")
        self.filename_label.setAlignment(QtCore.Qt.AlignCenter)
        self.filename_label.setStyleSheet("""
            font-weight: bold; 
            color: #aaa; 
            font-size: 14px;
            background-color: rgba(0, 0, 0, 100);
            padding: 5px;
            border-radius: 4px;
        """)
        self.layout.addWidget(self.filename_label)

        # Image display area
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #1e1e1e; border: none;")

        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll_area.setWidget(self.image_label)

        self.layout.addWidget(self.scroll_area)

    def set_image(self, img_path):
        self.current_img_path = img_path
        if not img_path or not os.path.exists(img_path):
            self.image_label.setText("Resim yüklenemedi.")
            self.filename_label.setText("")
            return

        self.filename_label.setText(os.path.basename(img_path))

        pixmap = QtGui.QPixmap(img_path)
        if pixmap.isNull():
            self.image_label.setText("Geçersiz resim dosyası.")
            return

        # Scale pixmap to fit the scroll area while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            self.scroll_area.size(), 
            QtCore.Qt.KeepAspectRatio, 
            QtCore.Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

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
            self.set_image(self.current_img_path)

import os
