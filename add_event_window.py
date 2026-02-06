from PySide6 import QtWidgets, QtCore
import os
from src.services.event_service import EventService
from dotenv import load_dotenv

load_dotenv()

class AddEvent(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window)  # Bağımsız pencere olarak aç
        self.setWindowTitle("Yeni Etkinlik")
        self.setGeometry(100, 100, 800, 600)
        self.setFixedSize(self.size())
        self.media_vault_base_path = os.getenv("MEDIA_VAULT_PATH", "media_vault")
        self.UI()
        self.show()

    def UI(self):
        self.widgets()
        self.layouts()

    
    def widgets(self):
        self.add_event_label = QtWidgets.QLabel("Etkinlik Ekleyin")
        self.add_event_seperator = QtWidgets.QFrame()
        self.add_event_seperator.setFrameShape(QtWidgets.QFrame.HLine)
        self.add_event_seperator.setFrameShadow(QtWidgets.QFrame.Sunken)


        self.add_event_name_label = QtWidgets.QLabel("Etkinlik Adı:")
        self.add_event_name_line = QtWidgets.QTextEdit()
        self.add_event_name_line.setPlaceholderText("Etkinlik Adı")

        self.add_event_date_label = QtWidgets.QLabel("Etkinlik Tarihi:")
        self.add_event_date_line = QtWidgets.QDateTimeEdit()
        self.add_event_date_line.setCalendarPopup(True)
        self.add_event_date_line.setDateTime(QtCore.QDateTime.currentDateTime())
        self.add_event_date_line.setDisplayFormat("dd.MM.yyyy HH:mm")


        
        self.submit_button = QtWidgets.QPushButton("Kaydet")
        self.submit_button.clicked.connect(self.add_event)
        
        self.add_event_folder_label = QtWidgets.QLabel("Medya Klasörü:")
        self.add_event_folder_line = QtWidgets.QLineEdit()
        self.add_event_folder_line.setPlaceholderText("Klasör seçin...")
        self.add_event_folder_btn = QtWidgets.QPushButton("Gözat")
        self.add_event_folder_btn.clicked.connect(self.select_folder)

    def layouts(self):
        self.main_layout = QtWidgets.QVBoxLayout()
        self.top_layout = QtWidgets.QHBoxLayout()
        self.bottom_layout = QtWidgets.QFormLayout()
        # register widgets
        self.top_layout.addWidget(self.add_event_label)
        self.top_layout.addWidget(self.add_event_seperator)
        self.bottom_layout.addWidget(self.add_event_name_label)
        self.bottom_layout.addWidget(self.add_event_name_line)
        self.bottom_layout.addWidget(self.add_event_date_label)
        self.bottom_layout.addWidget(self.add_event_date_line)
        
        self.folder_layout = QtWidgets.QHBoxLayout()
        self.folder_layout.addWidget(self.add_event_folder_line)
        self.folder_layout.addWidget(self.add_event_folder_btn)
        
        self.bottom_layout.addRow(self.add_event_folder_label, self.folder_layout)
        self.bottom_layout.addWidget(self.submit_button)

        self.main_layout.addLayout(self.top_layout)
        self.main_layout.addLayout(self.bottom_layout)
        self.setLayout(self.main_layout)

    def select_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Klasör Seç")
        if folder:
            self.add_event_folder_line.setText(folder)
    
    def add_event(self):
        event_name = self.add_event_name_line.toPlainText().strip()
        event_date = self.add_event_date_line.dateTime().toPython()
        event_folder = self.add_event_folder_line.text()
        
        if event_name and event_folder:
            try:
                service = EventService(self.media_vault_base_path)
                event = service.create_and_import_event(
                    name=event_name,
                    event_date=event_date,
                    source_folder=event_folder
                )
                QtWidgets.QMessageBox.information(self, "Başarılı", f"Etkinlik oluşturuldu: {event.name}")
                self.parent().refresh_events()
                self.close()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Hata", f"İçe aktarma hatası: {str(e)}")
        else:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen tüm alanları doldurun.")
