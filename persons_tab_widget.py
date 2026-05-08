"""
PersonsTabWidget — Kişiler sekmesi için bağımsız widget.
Kişi listesi, not araması, yeniden adlandırma, silme ve yeni kişi ekleme işlevlerini içerir.
"""
import os
from PySide6 import QtCore, QtWidgets


class PersonRenameWorker(QtCore.QThread):
    """Renames a person in the DB then updates IPTC keywords in all linked files."""
    progress = QtCore.Signal(int, int)   # current, total
    finished = QtCore.Signal(int)        # number of files whose keywords were updated
    error    = QtCore.Signal(str)

    def __init__(self, person_service, person_id, old_name, new_name, media_records, parent=None):
        super().__init__(parent)
        self._person_service = person_service
        self._person_id = person_id
        self._old_name = old_name
        self._new_name = new_name
        self._media_records = media_records

    def run(self):
        from iptcinfo3 import IPTCInfo
        from src.utils import path_util

        try:
            self._person_service.rename(self._person_id, self._new_name)
        except Exception as e:
            self.error.emit(f"Veritabanı güncellenemedi: {e}")
            return

        old_lower = self._old_name.lower()
        files_updated = 0
        total = len(self._media_records)
        for i, rec in enumerate(self._media_records):
            self.progress.emit(i + 1, total)
            abs_path = path_util.from_db_path(rec.get("file_path", ""))
            if not abs_path or not os.path.exists(abs_path):
                continue
            try:
                info = IPTCInfo(abs_path, force=True)
                raw_kws = info["keywords"] or []
                str_kws = [k.decode("utf-8") if isinstance(k, bytes) else k for k in raw_kws]
                new_kws, changed = [], False
                for kw in str_kws:
                    if kw.lower() == old_lower:
                        new_kws.append(self._new_name)
                        changed = True
                    else:
                        new_kws.append(kw)
                if changed:
                    info["keywords"] = [k.encode("utf-8") for k in new_kws]
                    info.save()
                    files_updated += 1
            except Exception:
                pass
        self.finished.emit(files_updated)


class PersonScanWorker(QtCore.QThread):
    """Scans all existing face_detections and assigns matching ones to a newly created person."""
    progress = QtCore.Signal(int, int)  # (current, total)
    finished = QtCore.Signal(int)       # total matches assigned

    def __init__(self, person_id, reference_embedding, face_service, person_service, parent=None):
        super().__init__(parent)
        self._person_id = person_id
        self._embedding = reference_embedding
        self._face_svc = face_service
        self._person_svc = person_service

    def run(self):
        try:
            matches = self._face_svc.find_unassigned_faces_matching(self._embedding)
        except Exception:
            matches = []

        total = len(matches)
        assigned = 0
        for i, face in enumerate(matches):
            self.progress.emit(i + 1, total)
            try:
                self._face_svc.assign_person(face["face_id"], self._person_id)
                self._person_svc.link_to_media(self._person_id, face["media_id"])
                assigned += 1
            except Exception:
                pass
        self.finished.emit(assigned)


class PersonsTabWidget(QtWidgets.QWidget):
    # Emitted when user double-clicks a person row; carries (person_name, gallery_items)
    person_gallery_requested = QtCore.Signal(str, list)
    # Emitted when user double-clicks a note row; carries the full note record dict
    note_navigation_requested = QtCore.Signal(dict)
    # Status bar messages (progress, completion)
    status_message = QtCore.Signal(str)

    def __init__(self, person_service, media_service, face_service=None, parent=None):
        super().__init__(parent)
        self._person_service = person_service
        self._media_service = media_service
        self._face_service = face_service
        self._rename_worker = None
        self._scan_worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Row 1: person name search + action buttons ──
        top_bar = QtWidgets.QHBoxLayout()

        add_btn = QtWidgets.QPushButton("+ Yeni Kişi Ekle")
        add_btn.setFixedHeight(30)
        add_btn.setStyleSheet(
            "QPushButton { background-color: #0078D7; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #005fa3; }"
        )
        add_btn.clicked.connect(self._add_new_person)
        top_bar.addWidget(add_btn)

        self._persons_search = QtWidgets.QLineEdit()
        self._persons_search.setPlaceholderText("İsimde ara…")
        self._persons_search.setFixedHeight(30)
        self._persons_search.textChanged.connect(self._filter_persons_table)
        top_bar.addWidget(self._persons_search)

        refresh_btn = QtWidgets.QPushButton("Yenile")
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self.load_persons)
        top_bar.addWidget(refresh_btn)

        rename_btn = QtWidgets.QPushButton("İsim Değiştir")
        rename_btn.setFixedHeight(30)
        rename_btn.clicked.connect(self._rename_selected_person)
        top_bar.addWidget(rename_btn)

        delete_btn = QtWidgets.QPushButton("Kişi Sil")
        delete_btn.setFixedHeight(30)
        delete_btn.setStyleSheet("QPushButton { color: #c0392b; } QPushButton:hover { background-color: #c0392b; color: white; }")
        delete_btn.clicked.connect(self._delete_selected_person)
        top_bar.addWidget(delete_btn)
        layout.addLayout(top_bar)

        # ── Row 2: note search ──
        note_bar = QtWidgets.QHBoxLayout()
        note_icon = QtWidgets.QLabel("🔍")
        note_bar.addWidget(note_icon)
        self._notes_search = QtWidgets.QLineEdit()
        self._notes_search.setPlaceholderText("Notlarda ara…")
        self._notes_search.setFixedHeight(30)
        self._notes_search.textChanged.connect(self._on_notes_search_changed)
        note_bar.addWidget(self._notes_search)
        layout.addLayout(note_bar)

        # ── Stacked area: persons table / notes results table ──
        self._persons_table = QtWidgets.QTableWidget()
        self._persons_table.setColumnCount(2)
        self._persons_table.setHorizontalHeaderLabels(["İsim", "Fotoğraf Sayısı"])
        self._persons_table.horizontalHeader().setStretchLastSection(False)
        self._persons_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self._persons_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents
        )
        self._persons_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._persons_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._persons_table.setAlternatingRowColors(True)
        self._persons_table.verticalHeader().setVisible(False)
        self._persons_table.setSortingEnabled(True)
        self._persons_table.setCursor(QtCore.Qt.PointingHandCursor)
        self._persons_table.cellDoubleClicked.connect(self._on_person_row_clicked)
        layout.addWidget(self._persons_table)

        self._notes_table = QtWidgets.QTableWidget()
        self._notes_table.setColumnCount(3)
        self._notes_table.setHorizontalHeaderLabels(["Kişi", "Not", "Dosya"])
        hh = self._notes_table.horizontalHeader()
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self._notes_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._notes_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._notes_table.setAlternatingRowColors(True)
        self._notes_table.verticalHeader().setVisible(False)
        self._notes_table.setSortingEnabled(False)
        self._notes_table.setCursor(QtCore.Qt.PointingHandCursor)
        self._notes_table.cellDoubleClicked.connect(self._on_note_row_clicked)
        self._notes_table.hide()
        layout.addWidget(self._notes_table)

        hint = QtWidgets.QLabel("Bir satıra çift tıklayarak o kişiye ait fotoğrafları Etkinlikler sekmesinde görüntüleyin.")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(hint)

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_persons(self):
        try:
            rows = self._person_service.get_all_with_counts()
        except Exception:
            rows = []

        self._persons_table.setSortingEnabled(False)
        self._persons_table.setRowCount(len(rows))
        for i, person in enumerate(rows):
            name_item = QtWidgets.QTableWidgetItem(person["name"])
            name_item.setData(QtCore.Qt.UserRole, person["id"])
            count_item = QtWidgets.QTableWidgetItem()
            count_item.setData(QtCore.Qt.DisplayRole, int(person["photo_count"]))
            count_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self._persons_table.setItem(i, 0, name_item)
            self._persons_table.setItem(i, 1, count_item)
        self._persons_table.setSortingEnabled(True)
        self._persons_search.clear()

    # ── Private slots ──────────────────────────────────────────────────────────

    def _filter_persons_table(self, text: str):
        text = text.lower()
        for row in range(self._persons_table.rowCount()):
            item = self._persons_table.item(row, 0)
            visible = text in (item.text().lower() if item else "")
            self._persons_table.setRowHidden(row, not visible)

    def _on_notes_search_changed(self, text: str):
        query = text.strip()
        if not query:
            self._notes_table.hide()
            self._persons_table.show()
            return

        self._persons_table.hide()
        self._notes_table.show()

        try:
            results = self._person_service.search_notes(query)
        except Exception:
            results = []

        from src.utils import path_util
        self._notes_table.setSortingEnabled(False)
        self._notes_table.setRowCount(len(results))
        for i, rec in enumerate(results):
            person_item = QtWidgets.QTableWidgetItem(rec.get("person_name", ""))
            person_item.setData(QtCore.Qt.UserRole, rec)

            note_item = QtWidgets.QTableWidgetItem(rec.get("note", ""))
            note_item.setToolTip(rec.get("note", ""))

            abs_path = path_util.from_db_path(rec.get("file_path", ""))
            file_item = QtWidgets.QTableWidgetItem(os.path.basename(abs_path))
            file_item.setToolTip(abs_path)

            self._notes_table.setItem(i, 0, person_item)
            self._notes_table.setItem(i, 1, note_item)
            self._notes_table.setItem(i, 2, file_item)

    def _on_note_row_clicked(self, row: int, _col: int):
        person_item = self._notes_table.item(row, 0)
        if person_item is None:
            return
        rec = person_item.data(QtCore.Qt.UserRole)
        if not rec:
            return
        self.note_navigation_requested.emit(rec)

    def _on_person_row_clicked(self, row: int, _col: int):
        name_item = self._persons_table.item(row, 0)
        if name_item is None:
            return
        person_id = name_item.data(QtCore.Qt.UserRole)
        person_name = name_item.text()
        if not person_id:
            return

        try:
            items = self._media_service.get_gallery_items_for_person(person_id)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Hata", f"Fotoğraflar yüklenemedi: {e}")
            return

        self.person_gallery_requested.emit(person_name, items)

    def _rename_selected_person(self):
        selected = self._persons_table.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen yeniden adlandırmak istediğiniz kişiyi seçin.")
            return

        row = self._persons_table.currentRow()
        name_item = self._persons_table.item(row, 0)
        if not name_item:
            return

        old_name = name_item.text()
        person_id = name_item.data(QtCore.Qt.UserRole)

        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "İsim Değiştir", f'"{old_name}" için yeni isim:', text=old_name
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        try:
            media_records = self._person_service.get_media_paths_for_person(person_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Hata", f"Kişi medyaları alınamadı: {e}")
            return

        self._rename_worker = PersonRenameWorker(
            self._person_service, person_id, old_name, new_name, media_records
        )
        self._rename_worker.progress.connect(
            lambda cur, tot: self.status_message.emit(f"⏳ Dosyalar güncelleniyor… {cur}/{tot}")
        )
        self._rename_worker.finished.connect(lambda n: self._on_rename_finished(n, new_name))
        self._rename_worker.error.connect(lambda msg: QtWidgets.QMessageBox.critical(self, "Hata", msg))
        self.status_message.emit(f"⏳ '{new_name}' için dosyalar güncelleniyor…")
        self._rename_worker.start()

    def _on_rename_finished(self, files_updated: int, new_name: str):
        self.load_persons()
        if files_updated > 0:
            self.status_message.emit(
                f"✅ '{new_name}' olarak yeniden adlandırıldı — {files_updated} dosyada anahtar kelime güncellendi."
            )
        else:
            self.status_message.emit(f"✅ '{new_name}' olarak yeniden adlandırıldı.")

    def _delete_selected_person(self):
        selected = self._persons_table.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen silmek istediğiniz kişiyi seçin.")
            return

        row = self._persons_table.currentRow()
        name_item = self._persons_table.item(row, 0)
        if not name_item:
            return

        name = name_item.text()
        person_id = name_item.data(QtCore.Qt.UserRole)

        reply = QtWidgets.QMessageBox.question(
            self,
            "Kişi Sil",
            f'"{name}" adlı kişiyi silmek istediğinizden emin misiniz?\nFotoğraflardaki bağlantılar da kaldırılacaktır.',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            self._person_service.delete(person_id)
            self.load_persons()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Hata", f"Kişi silinemedi: {e}")

    def _add_new_person(self):
        if self._face_service is None:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Yüz tanıma servisi mevcut değil.")
            return

        from add_person_dialog import AddPersonDialog
        dlg = AddPersonDialog(self._face_service, self._person_service, parent=self)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        name = dlg.person_name
        embedding = dlg.reference_embedding

        try:
            person_id = self._person_service.find_or_create(name)
            self._person_service.set_reference_embedding(person_id, embedding)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Hata", f"Kişi kaydedilemedi: {e}")
            return

        self.load_persons()
        self.status_message.emit(f"✅ '{name}' eklendi. Mevcut medyalar taranıyor…")

        self._scan_worker = PersonScanWorker(
            person_id, embedding, self._face_service, self._person_service
        )
        self._scan_worker.progress.connect(
            lambda cur, tot: self.status_message.emit(f"🔍 '{name}' taranıyor… {cur}/{tot} yüz")
        )
        self._scan_worker.finished.connect(lambda n: self._on_scan_finished(n, name))
        self._scan_worker.start()

    def _on_scan_finished(self, matched: int, name: str):
        self.load_persons()
        if matched > 0:
            self.status_message.emit(
                f"✅ '{name}' taraması tamamlandı — {matched} fotoğrafta eşleşme bulundu."
            )
        else:
            self.status_message.emit(
                f"✅ '{name}' eklendi — mevcut medyalarda eşleşme bulunamadı. Yeni içe aktarımlarda otomatik tanınacak."
            )
