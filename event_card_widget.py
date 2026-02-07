from PySide6 import QtWidgets, QtCore

class EventCardWidget(QtWidgets.QWidget):
    # Signal emitted when the card is clicked
    clicked = QtCore.Signal()
    
    def __init__(self, event_name, event_date):
        super().__init__()
        self.layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.layout)
        self.event_name = QtWidgets.QLabel(event_name)
        self.layout.addWidget(self.event_name)
        self.event_date = QtWidgets.QLabel(event_date.strftime("%Y-%m-%d %H:%M:%S"))
        self.layout.addWidget(self.event_date)
        
        # Optional: Add visual feedback for hover
        self.setStyleSheet("""
            EventCardWidget {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
                background-color: white;
            }
            EventCardWidget:hover {
                background-color: #f0f0f0;
            }
            EventCardWidget:focus {
                border: 2px solid #0078d4;
                background-color: #e6f2ff;
            }
        """)
        
        # Make the widget focusable so it can receive keyboard events
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
    
    def mousePressEvent(self, event):
        """Handle mouse click events"""
        self.clicked.emit()
        super().mousePressEvent(event)
    
    def keyPressEvent(self, event):
        """Handle keyboard events - emit clicked signal on Enter/Return"""
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.clicked.emit()
        super().keyPressEvent(event)

        