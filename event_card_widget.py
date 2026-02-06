from PySide6 import QtWidgets

class EventCardWidget(QtWidgets.QWidget):
    def __init__(self, event_name, event_date):
        super().__init__()
        self.layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.layout)
        self.event_name = QtWidgets.QLabel("Event Name: " + event_name)
        self.layout.addWidget(self.event_name)
        self.event_date = QtWidgets.QLabel("Event Date: " + event_date.strftime("%Y-%m-%d %H:%M:%S"))
        self.layout.addWidget(self.event_date)
