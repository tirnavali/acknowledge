from PySide6 import QtWidgets, QtCore
import os
import re
from dotenv import load_dotenv

load_dotenv()


class ImportWorker(QtCore.QThread):
    """Runs create_and_import_event in a background thread."""

    progress = QtCore.Signal(int, int)   # (current, total)
    finished = QtCore.Signal(object)     # emits the created Event
    error    = QtCore.Signal(str)

    def __init__(self, service, name, event_date, source_folder, vault_base_path, parent=None):
        super().__init__(parent)
        self._service         = service
        self._name            = name
        self._event_date      = event_date
        self._source_folder   = source_folder
        self._vault_base_path = vault_base_path

    def run(self):
        try:
            event = self._service.create_and_import_event(
                name=self._name,
                event_date=self._event_date,
                source_folder=self._source_folder,
                vault_base_path=self._vault_base_path,
                progress_callback=lambda cur, tot: self.progress.emit(cur, tot),
            )
            self.finished.emit(event)
        except Exception as e:
            self.error.emit(str(e))


class AddEvent(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle("Yeni Etkinlik")
        self.setGeometry(100, 100, 800, 600)
        self.setFixedSize(self.size())
        self.media_vault_base_path = os.getenv("MEDIA_VAULT_PATH", "media_vault")
        self._worker = None
        self._progress_dialog = None
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
            basename = os.path.basename(folder)
            self.add_event_folder_line.setText(folder)
            
            event_name = basename
            
            # Auto-fill date if DD.MM.YYYY pattern is found in folder name
            match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", basename)
            if match:
                day, month, year = map(int, match.groups())
                qdate = QtCore.QDate(year, month, day)
                if qdate.isValid():
                    qtime = QtCore.QTime(12, 0)
                    self.add_event_date_line.setDateTime(QtCore.QDateTime(qdate, qtime))
                    # Remove the date from the name and cleanup whitespace
                    event_name = basename.replace(match.group(0), "").strip()
                    event_name = re.sub(r"\s+", " ", event_name)

            # Auto-fill event name from folder name if currently empty
            if not self.add_event_name_line.toPlainText().strip():
                self.add_event_name_line.setPlainText(event_name)

    def add_event(self):
        event_name   = self.add_event_name_line.toPlainText().strip()
        event_date   = self.add_event_date_line.dateTime().toPython()
        event_folder = self.add_event_folder_line.text()

        if not (event_name and event_folder):
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen tüm alanları doldurun.")
            return

        service = self.parent().app_service.get_event_service()

        self._progress_dialog = QtWidgets.QProgressDialog(
            "Dosyalar kopyalanıyor...", None, 0, 100, self
        )
        self._progress_dialog.setWindowTitle("Etkinlik İçe Aktarılıyor")
        self._progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setValue(0)

        self.submit_button.setEnabled(False)

        self._worker = ImportWorker(
            service, event_name, event_date, event_folder, self.media_vault_base_path, parent=self
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        if self._progress_dialog is None:
            return
        if total > 0:
            pct = int(current * 100 / total)
            self._progress_dialog.setLabelText(
                f"Dosyalar kopyalanıyor... ({current}/{total})"
            )
            self._progress_dialog.setValue(pct)

    def _on_finished(self, event):
        if self._progress_dialog is not None:
            self._progress_dialog.setValue(100)
            self._progress_dialog.close()
            self._progress_dialog = None

        self.submit_button.setEnabled(True)
        QtWidgets.QMessageBox.information(self, "Başarılı", f"Etkinlik oluşturuldu: {event.name}")
        self.parent()._start_batch_face_detection(event)
        self.parent().refresh_events()
        self.close()

    def _on_error(self, message: str):
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

        self.submit_button.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "Hata", f"İçe aktarma hatası: {message}")
