from PySide6 import QtWidgets, QtCore

class EventCardWidget(QtWidgets.QWidget):
    # Signal emitted when the card is clicked
    clicked = QtCore.Signal()
    
    def __init__(self, event_name, event_date):
        super().__init__()
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(4)
        
        self.event_name = QtWidgets.QLabel(event_name)
        self.event_name.setWordWrap(True)
        # Set tooltip so user can see full name on hover
        self.event_name.setToolTip(event_name)
        self.event_name.setStyleSheet("font-weight: bold; font-size: 13px; color: #f0f0f0;")
        self.event_name.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.layout.addWidget(self.event_name)
        
        self.event_date = QtWidgets.QLabel(event_date.strftime("%Y-%m-%d %H:%M:%S"))
        self.event_date.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self.layout.addWidget(self.event_date)
        
        # Optional: Add visual feedback for hover
        self.setStyleSheet("""
            EventCardWidget {
                border: 1px solid #3f3f46;
                border-radius: 5px;
                padding: 5px;
                background-color: #2d2d30;
            }
            EventCardWidget:hover {
                background-color: #3e3e42;
                border: 1px solid #555558;
            }
            EventCardWidget:focus {
                border: 2px solid #0078d4;
                background-color: #1e3a5f;
            }
        """)
        
        # Make the widget focusable so it can receive keyboard events
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
    
    def mousePressEvent(self, event):
        """Handle mouse click events"""
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
            super().mousePressEvent(event)
        elif event.button() == QtCore.Qt.RightButton:
            # Accept but don't call super() to prevent QListWidget from selecting the item
            event.accept()

    def mouseReleaseEvent(self, event):
        """Consume right-click release to be safe"""
        if event.button() == QtCore.Qt.RightButton:
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def keyPressEvent(self, event):
        """Handle keyboard events - emit clicked signal on Enter/Return"""
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.clicked.emit()
        super().keyPressEvent(event)

        