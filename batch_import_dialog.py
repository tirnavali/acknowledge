"""
batch_import_dialog.py — UI for scanning and batch importing year/parent folders containing hundreds of subfolders.
Cross-platform (Windows & macOS).
"""

import os
from PySide6 import QtWidgets, QtCore, QtGui
from src.utils.folder_scanner_util import (
    scan_subfolders,
    format_event_name,
    NamingTemplate,
    ScannedEventFolder,
)
from src.utils.path_util import normalize_path


class BatchImportWorker(QtCore.QThread):
    """Executes batch event import in a background thread."""

    event_progress = QtCore.Signal(int, int, str)  # (current_event, total_events, event_name)
    file_progress  = QtCore.Signal(int, int)       # (current_file, total_files)
    finished       = QtCore.Signal(dict)           # summary dict
    error          = QtCore.Signal(str)

    def __init__(self, event_service, items: list[ScannedEventFolder], vault_base_path: str, parent=None):
        super().__init__(parent)
        self._service = event_service
        self._items = items
        self._vault_base_path = vault_base_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            def on_progress(ev_idx, tot_evs, f_idx, tot_files, ev_name):
                self.event_progress.emit(ev_idx, tot_evs, ev_name)
                self.file_progress.emit(f_idx, tot_files)

            summary = self._service.import_batch_events(
                event_items=self._items,
                vault_base_path=self._vault_base_path,
                progress_callback=on_progress,
                is_cancelled=lambda: self._is_cancelled,
            )
            self.finished.emit(summary)
        except Exception as e:
            self.error.emit(str(e))


class BatchImportDialog(QtWidgets.QDialog):
    """
    Batch Import Dialog for importing structured parent/year folders with subfolders.
    """

    importCompleted = QtCore.Signal()

    def __init__(self, app_service, parent=None):
        super().__init__(parent)
        self.app_service = app_service
        self.event_service = app_service.get_event_service()
        self.vault_base_path = os.getenv("MEDIA_VAULT_PATH", "media_vault")
        self.scanned_items: list[ScannedEventFolder] = []
        self._worker: BatchImportWorker | None = None

        self.setWindowTitle("Toplu Etkinlik İçe Aktarma (Batch Import)")
        self.setMinimumSize(960, 650)
        self.resize(1050, 720)

        self._init_ui()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header & Folder Selector
        header_box = QtWidgets.QGroupBox("1. Ana Klasör Seçimi (Yıllık / Gruplanmış Klasör)")
        header_layout = QtWidgets.QVBoxLayout(header_box)

        folder_row = QtWidgets.QHBoxLayout()
        self.root_folder_input = QtWidgets.QLineEdit()
        self.root_folder_input.setPlaceholderText("Yüzlerce etkinlik alt klasörü içeren ana klasörü seçin...")
        self.root_folder_input.setReadOnly(True)
        self.browse_btn = QtWidgets.QPushButton("📁 Klasör Seç")
        self.browse_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #2b5b84;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3872a5; }
        """)
        self.browse_btn.clicked.connect(self._select_root_folder)

        folder_row.addWidget(self.root_folder_input, stretch=1)
        folder_row.addWidget(self.browse_btn)
        header_layout.addLayout(folder_row)
        main_layout.addWidget(header_box)

        # 2. Options Bar (Naming Template + Filter + Select All)
        options_box = QtWidgets.QGroupBox("2. İsimlendirme ve Seçim Seçenekleri")
        options_layout = QtWidgets.QHBoxLayout(options_box)

        # Template dropdown
        template_label = QtWidgets.QLabel("İsimlendirme Şablonu:")
        self.template_combo = QtWidgets.QComboBox()
        self.template_combo.addItem("2024 Divan Toplantısı [Yıl + İsim]", NamingTemplate.YEAR_PREFIX)
        self.template_combo.addItem("Divan Toplantısı (2024) [İsim + (Yıl)]", NamingTemplate.YEAR_SUFFIX)
        self.template_combo.addItem("01.01.2024 Divan Toplantısı [Tam Tarih + İsim]", NamingTemplate.FULL_DATE_PREFIX)
        self.template_combo.addItem("Orijinal Klasör Adı", NamingTemplate.ORIGINAL)
        self.template_combo.addItem("Sadece Temiz İsim (Yılsız)", NamingTemplate.CLEAN_ONLY)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)

        options_layout.addWidget(template_label)
        options_layout.addWidget(self.template_combo, stretch=1)

        # Quick select buttons
        self.select_all_btn = QtWidgets.QPushButton("Tümünü Seç")
        self.select_all_btn.clicked.connect(lambda: self._set_all_selected(True))
        self.deselect_all_btn = QtWidgets.QPushButton("Tümünü Kaldır")
        self.deselect_all_btn.clicked.connect(lambda: self._set_all_selected(False))

        options_layout.addWidget(self.select_all_btn)
        options_layout.addWidget(self.deselect_all_btn)

        # Search filter
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("🔍 Tabloda ara...")
        self.search_input.textChanged.connect(self._filter_table)
        options_layout.addWidget(self.search_input, stretch=1)

        main_layout.addWidget(options_box)

        # 3. Preview Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Seç", "Klasör Adı", "Algılanan Tarih", "Hedef Etkinlik Adı (Düzenlenebilir)",
            "Medya Sayısı", "İçerik Detayı", "Durum"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)

        main_layout.addWidget(self.table, stretch=1)

        # 4. Progress Area (Hidden by default, shown during import)
        self.progress_group = QtWidgets.QGroupBox("İçe Aktarma İlerlemesi")
        self.progress_group.setVisible(False)
        prog_layout = QtWidgets.QVBoxLayout(self.progress_group)

        self.overall_label = QtWidgets.QLabel("Toplam İlerleme: 0 / 0")
        self.overall_label.setStyleSheet("font-weight: bold;")
        self.overall_bar = QtWidgets.QProgressBar()
        self.overall_bar.setRange(0, 100)
        self.overall_bar.setValue(0)

        self.current_folder_label = QtWidgets.QLabel("Geçerli Klasör: Bekleniyor...")
        self.current_folder_bar = QtWidgets.QProgressBar()
        self.current_folder_bar.setRange(0, 100)
        self.current_folder_bar.setValue(0)

        prog_layout.addWidget(self.overall_label)
        prog_layout.addWidget(self.overall_bar)
        prog_layout.addWidget(self.current_folder_label)
        prog_layout.addWidget(self.current_folder_bar)
        main_layout.addWidget(self.progress_group)

        # 5. Bottom Status and Action Buttons
        bottom_layout = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("Lütfen içe aktarılacak ana klasörü seçin.")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")

        self.cancel_btn = QtWidgets.QPushButton("Vazgeç")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)

        self.import_btn = QtWidgets.QPushButton("🚀 Seçilenleri İçe Aktar (0 Etkinlik)")
        self.import_btn.setEnabled(False)
        self.import_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #388e3c; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.import_btn.clicked.connect(self._start_batch_import)

        bottom_layout.addWidget(self.status_label, stretch=1)
        bottom_layout.addWidget(self.cancel_btn)
        bottom_layout.addWidget(self.import_btn)
        main_layout.addLayout(bottom_layout)

    def _select_root_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Yıllık / Gruplanmış Klasör Seç")
        if not folder:
            return

        folder = normalize_path(folder)
        self.root_folder_input.setText(folder)
        self._scan_folder(folder)

    def _scan_folder(self, folder: str):
        self.status_label.setText("⏳ Alt klasörler ve medya içerikleri taranıyor...")
        QtWidgets.QApplication.processEvents()

        template = self.template_combo.currentData() or NamingTemplate.YEAR_PREFIX
        self.scanned_items = scan_subfolders(folder, template=template)

        # Cross-check database for existing events to show status
        try:
            existing_events = self.event_service.get_all()
            existing_names_years = {
                (e.name.lower(), e.event_date.year if e.event_date else None): e.id
                for e in existing_events
            }
            for item in self.scanned_items:
                year = item.event_date.year if item.event_date else None
                key = (item.target_name.lower(), year)
                if key in existing_names_years:
                    item.status = "Mevcut (Birleştirilecek)"
                    item.collision_event_id = str(existing_names_years[key])
        except Exception:
            pass

        self._populate_table()

    def _populate_table(self):
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.scanned_items))

        total_medias = 0
        ready_count = 0

        for row, item in enumerate(self.scanned_items):
            # 0. Checkbox
            chk = QtWidgets.QTableWidgetItem()
            chk.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            chk.setCheckState(QtCore.Qt.Checked if item.is_selected else QtCore.Qt.Unchecked)
            self.table.setItem(row, 0, chk)

            # 1. Original Name
            orig_item = QtWidgets.QTableWidgetItem(item.original_name)
            orig_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row, 1, orig_item)

            # 2. Detected Date
            date_str = item.event_date.strftime("%d.%m.%Y") if item.event_date else "—"
            date_item = QtWidgets.QTableWidgetItem(date_str)
            date_item.setTextAlignment(QtCore.Qt.AlignCenter)
            date_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row, 2, date_item)

            # 3. Target Event Name (Editable)
            target_item = QtWidgets.QTableWidgetItem(item.target_name)
            target_item.setToolTip("İsmi değiştirmek için çift tıklayın")
            self.table.setItem(row, 3, target_item)

            # 4. Total Media Count
            count_item = QtWidgets.QTableWidgetItem(str(item.total_media_count))
            count_item.setTextAlignment(QtCore.Qt.AlignCenter)
            count_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row, 4, count_item)

            # 5. Media Breakdown Badge
            breakdown = []
            if item.photo_count: breakdown.append(f"📷 {item.photo_count}")
            if item.pdf_count: breakdown.append(f"📄 {item.pdf_count}")
            if item.doc_count: breakdown.append(f"📝 {item.doc_count}")
            if item.video_count: breakdown.append(f"🎥 {item.video_count}")
            breakdown_str = "  ".join(breakdown) if breakdown else "Boş"
            detail_item = QtWidgets.QTableWidgetItem(breakdown_str)
            detail_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row, 5, detail_item)

            # 6. Status
            status_item = QtWidgets.QTableWidgetItem(item.status)
            status_item.setTextAlignment(QtCore.Qt.AlignCenter)
            if item.status == "Hazır":
                status_item.setForeground(QtGui.QColor("#4caf50"))
            elif "Mevcut" in item.status:
                status_item.setForeground(QtGui.QColor("#ff9800"))
            else:
                status_item.setForeground(QtGui.QColor("#888888"))
            status_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row, 6, status_item)

            if item.has_media:
                total_medias += item.total_media_count
                if item.is_selected:
                    ready_count += 1

        self.table.itemChanged.connect(self._on_table_item_changed)
        self._update_status_and_buttons()

    def _on_table_item_changed(self, table_item: QtWidgets.QTableWidgetItem):
        row = table_item.row()
        col = table_item.column()
        if row < 0 or row >= len(self.scanned_items):
            return

        item = self.scanned_items[row]
        if col == 0:
            item.is_selected = (table_item.checkState() == QtCore.Qt.Checked)
            self._update_status_and_buttons()
        elif col == 3:
            item.target_name = table_item.text().strip()

    def _on_template_changed(self):
        template = self.template_combo.currentData()
        for item in self.scanned_items:
            item.target_name = format_event_name(
                item.original_name, item.clean_name, item.event_date, template
            )
        self.table.blockSignals(True)
        for row, item in enumerate(self.scanned_items):
            target_item = self.table.item(row, 3)
            if target_item:
                target_item.setText(item.target_name)
        self.table.blockSignals(False)

    def _set_all_selected(self, selected: bool):
        self.table.blockSignals(True)
        for row, item in enumerate(self.scanned_items):
            if item.has_media:
                item.is_selected = selected
                chk = self.table.item(row, 0)
                if chk:
                    chk.setCheckState(QtCore.Qt.Checked if selected else QtCore.Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_status_and_buttons()

    def _filter_table(self, query: str):
        q = query.strip().lower()
        for row in range(self.table.rowCount()):
            if not q:
                self.table.setRowHidden(row, False)
                continue
            orig_text = self.table.item(row, 1).text().lower() if self.table.item(row, 1) else ""
            target_text = self.table.item(row, 3).text().lower() if self.table.item(row, 3) else ""
            match = (q in orig_text or q in target_text)
            self.table.setRowHidden(row, not match)

    def _update_status_and_buttons(self):
        selected_items = [it for it in self.scanned_items if it.is_selected and it.has_media]
        selected_count = len(selected_items)
        selected_medias = sum(it.total_media_count for it in selected_items)
        total_folders = len(self.scanned_items)

        self.status_label.setText(
            f"📁 Toplam {total_folders} Alt Klasör ({selected_count} Seçili) — {selected_medias} Medya Dosyası"
        )
        self.import_btn.setEnabled(selected_count > 0)
        self.import_btn.setText(f"🚀 Seçilenleri İçe Aktar ({selected_count} Etkinlik)")

    def _start_batch_import(self):
        selected_items = [it for it in self.scanned_items if it.is_selected and it.has_media]
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen içe aktarılacak en az bir alt klasör seçin.")
            return

        confirm = QtWidgets.QMessageBox.question(
            self,
            "Toplu İçe Aktarma Onayı",
            f"{len(selected_items)} etkinlik ve toplam {sum(it.total_media_count for it in selected_items)} medya "
            f"dosyası sisteme aktarılacaktır.\n\nİşlemi başlatmak istiyor musunuz?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return

        # Disable UI controls during import
        self.browse_btn.setEnabled(False)
        self.template_combo.setEnabled(False)
        self.select_all_btn.setEnabled(False)
        self.deselect_all_btn.setEnabled(False)
        self.import_btn.setEnabled(False)
        self.table.setEnabled(False)

        # Show progress panel
        self.progress_group.setVisible(True)
        self.overall_bar.setValue(0)
        self.current_folder_bar.setValue(0)

        self._worker = BatchImportWorker(
            self.event_service,
            selected_items,
            self.vault_base_path,
            parent=self,
        )
        self._worker.event_progress.connect(self._on_event_progress)
        self._worker.file_progress.connect(self._on_file_progress)
        self._worker.finished.connect(self._on_import_finished)
        self._worker.error.connect(self._on_import_error)
        self._worker.start()

    def _on_event_progress(self, cur_event: int, tot_events: int, event_name: str):
        pct = int(cur_event * 100 / tot_events) if tot_events > 0 else 0
        self.overall_bar.setValue(pct)
        self.overall_label.setText(f"Toplam İlerleme: Etkinlik {cur_event} / {tot_events} (%{pct})")
        self.current_folder_label.setText(f"İşleniyor: {event_name}")

    def _on_file_progress(self, cur_file: int, tot_files: int):
        pct = int(cur_file * 100 / tot_files) if tot_files > 0 else 0
        self.current_folder_bar.setValue(pct)

    def _on_import_finished(self, summary: dict):
        self.overall_bar.setValue(100)
        self.current_folder_bar.setValue(100)

        # Re-enable UI
        self.browse_btn.setEnabled(True)
        self.template_combo.setEnabled(True)
        self.select_all_btn.setEnabled(True)
        self.deselect_all_btn.setEnabled(True)
        self.import_btn.setEnabled(True)
        self.table.setEnabled(True)

        succ = summary.get("successful", 0)
        errors = summary.get("errors", [])
        skipped = summary.get("skipped", 0)

        msg = f"Toplu içe aktarma tamamlandı!\n\n"
        msg += f"✅ Başarılı: {succ} Etkinlik\n"
        if skipped:
            msg += f"⏭️ Atlanan: {skipped} Klasör\n"
        if errors:
            msg += f"❌ Hatalı: {len(errors)} Klasör\n"

        if errors:
            QtWidgets.QMessageBox.warning(self, "İçe Aktarma Özeti", msg)
        else:
            QtWidgets.QMessageBox.information(self, "İçe Aktarma Tamamlandı", msg)

        # Trigger batch face detection for imported events in parent window
        if hasattr(self.parent(), "_start_batch_face_detection"):
            for ev in summary.get("created_events", []):
                try:
                    self.parent()._start_batch_face_detection(ev)
                except Exception:
                    pass

        self.importCompleted.emit()
        self.close()

    def _on_import_error(self, err_msg: str):
        QtWidgets.QMessageBox.critical(self, "Toplu İçe Aktarma Hatası", f"Beklenmeyen bir hata oluştu:\n{err_msg}")
        self.browse_btn.setEnabled(True)
        self.template_combo.setEnabled(True)
        self.import_btn.setEnabled(True)
        self.table.setEnabled(True)

    def _on_cancel_clicked(self):
        if self._worker and self._worker.isRunning():
            reply = QtWidgets.QMessageBox.question(
                self, "İptal Onayı", "Devam eden içe aktarma işlemini iptal etmek istiyor musunuz?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self._worker.cancel()
                self._worker.wait(2000)
                self.close()
        else:
            self.close()
