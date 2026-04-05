import sys, os
import random
import logging
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtGui import QAction

from event_card_widget import EventCardWidget
from gallery_item_model import GalleryItemModel, GalleryItem
from sqlalchemy import text
from src.database import get_db, Base, engine
import src.models
from dotenv import load_dotenv
import add_event_window
from src.repositories.event_repository import EventRepository
from src.repositories.media_repository import MediaRepository
from src.repositories.person_repository import PersonRepository
from src.repositories.face_repository import FaceRepository
from src.services.face_service import FaceAnalysisService
from single_view_widget import SingleViewWidget
from src.services.application_service import ApplicationService
from caption_tab_widget import CaptionTabWidget
import os

logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class BatchFaceWorker(QtCore.QThread):
    """Runs face detection + auto-matching on a list of image files in the background."""

    progress        = QtCore.Signal(int, int)   # (current, total)
    finished        = QtCore.Signal()
    error           = QtCore.Signal(str)
    image_processed = QtCore.Signal(str)        # emits file_path when one image is done

    def __init__(self, file_paths, event_id, face_service, media_service, person_service, parent=None, force=False):
        super().__init__(parent)
        self._file_paths  = file_paths
        self._event_id    = event_id
        self._face_svc    = face_service
        self._media_svc   = media_service
        self._person_svc  = person_service
        self._force       = force

    def run(self):
        total = len(self._file_paths)
        for i, file_path in enumerate(self._file_paths, 1):
            try:
                media_id = self._media_svc.ensure_media_exists(
                    self._event_id, file_path, "photo"
                )
                media_row = self._media_svc.get_by_file_path(file_path)
                if not self._force and media_row and media_row.get("face_detected_at"):
                    self.progress.emit(i, total)
                    continue

                if self._force:
                    self._face_svc.delete_faces_for_media(media_id)

                results = self._face_svc.detect_faces(file_path)
                saved_ids = self._face_svc.save_faces(media_id, results) if results else []

                for face_result, face_id in zip(results or [], saved_ids):
                    if face_result.embedding is not None:
                        pid, _ = self._face_svc.find_similar_person(face_result.embedding)
                        if pid:
                            self._face_svc.assign_person(face_id, pid)
                            self._person_svc.link_to_media(pid, media_id)

                # --- Automatic Metadata Extraction ---
                from src.utils import metadata_util
                meta = metadata_util.extract_metadata(file_path)
                # Only save if we found at least some metadata (to avoid unnecessary writes)
                if any(v.strip() for v in meta.values()):
                    self._media_svc.save_iptc_data(media_id, meta)
                
                self._media_svc.mark_face_detected(media_id)
            except Exception as e:
                logger.warning(f"BatchFaceWorker: error on {file_path}: {e}")
            self.image_processed.emit(file_path)
            self.progress.emit(i, total)
        self.finished.emit()


class SearchWorker(QtCore.QThread):
    """Runs the FTS DB query in the background to avoid freezing the UI."""
    finished = QtCore.Signal(object, str)   # (list[dict], query_text)
    error    = QtCore.Signal(str)

    def __init__(self, media_service, query, parent=None):
        super().__init__(parent)
        self._media_service = media_service
        self._query = query

    def run(self):
        try:
            records = self._media_service.search_across_events_raw(self._query)
            self.finished.emit(records, self._query)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tirnavali Acknowledge")
        self.resize(1400, 900)
        self.current_event_id = None
        self.current_media_id = None
        self.app_service = ApplicationService()
        self._face_detection_queue: list = []   # list of (file_paths, event)
        self._batch_face_worker = None
        self._search_worker = None              # background FTS worker
        self._search_mode = False               # True while cross-event search is active
        self._selected_event_card = None        # currently highlighted EventCardWidget
        self.init_db()
        self.init_vault()
        self.UI()
        self.show()

    def init_vault(self):
        print("⏳ Vault klasörleri kontrol ediliyor...")
        load_dotenv()
        self.media_vault_path = os.getenv("MEDIA_VAULT_PATH", "image_vault")
        if not os.path.exists(self.media_vault_path):
            os.makedirs(self.media_vault_path)
        print("✅ Vault klasörleri hazır.")

    def init_db(self):
        print("⏳ Veritabanı tabloları güncelleniyor...")
        
        # Validate database configuration
        if engine is None:
            QtWidgets.QMessageBox.critical(
                None,
                "Veritabanı Yapılandırması Gerekli",
                "Veritabanı yapılandırması bulunamadı!\n\n"
                "Lütfen .env dosyasını oluşturun ve Docker Desktop'ı başlatın.\n\n"
                "Detaylı talimatlar için terminal çıktısına bakın."
            )
            sys.exit(1)
        
        try:
            with get_db() as db:
                db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                db.commit()

            Base.metadata.create_all(bind=engine)
        
            # Add IPTC columns to existing medias table (create_all doesn't add columns to existing tables)
            caption_columns = [
                ("tags_en", "TEXT"),
                ("tags_tr", "TEXT"),
            ]
            with get_db() as db:
                for col_name, col_type in caption_columns:
                    try:
                        db.execute(text(f"ALTER TABLE medias ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                    except Exception:
                        pass
                db.commit()

            iptc_columns = [
                ("iptc_headline", "VARCHAR(500)"),
                ("iptc_caption", "TEXT"),
                ("iptc_keywords", "TEXT"),
                ("iptc_object_name", "VARCHAR(500)"),
                ("iptc_city", "VARCHAR(250)"),
                ("iptc_state", "VARCHAR(250)"),
                ("iptc_country", "VARCHAR(250)"),
                ("iptc_credit", "VARCHAR(500)"),
                ("iptc_source", "VARCHAR(500)"),
                ("iptc_copyright", "VARCHAR(500)"),
                ("iptc_writer", "VARCHAR(250)"),
                ("iptc_byline", "VARCHAR(250)"),
                ("iptc_byline_title", "VARCHAR(250)"),
                ("iptc_date_created", "VARCHAR(50)"),
                ("iptc_category", "VARCHAR(100)"),
                ("iptc_supplemental_categories", "VARCHAR(500)"),
                ("title", "VARCHAR(500)"),
            ]
            with get_db() as db:
                for col_name, col_type in iptc_columns:
                    try:
                        db.execute(text(f"ALTER TABLE medias ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                    except Exception as e:
                        print(f"Warning: Could not add column {col_name}: {e}")
                        pass  # Column already exists
                db.commit()
            
            print("✅ Veritabanı tabloları hazır.")
        except Exception as e:
            logging.error(f"❌ Veritabanı bağlantı hatası: {str(e)}")
            QtWidgets.QMessageBox.critical(
                None,
                "Veritabanı Bağlantı Hatası",
                f"Veritabanına bağlanılamadı!\n\n"
                f"Hata: {str(e)}\n\n"
                f"Docker Desktop çalışıyor mu?\n"
                f"Terminal'de 'docker-compose up -d' komutunu deneyin."
            )
            sys.exit(1)
    
    def UI(self):
        self.init_menubar()
        self.init_toolbar()
        self.tabWidget()
        self.event_widgets()
        # self.media_details_form_widget()
        self.layouts()
        self._init_persons_tab()
        self.apply_style()

    def init_menubar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("Dosya")
        
        open_action = QAction("Aç", self)
        file_menu.addAction(open_action)
        
        save_action = QAction("Kaydet", self)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Çıkış", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        view_menu = menubar.addMenu("Görünüm")
        
        grid_view_action = QAction("Izgara Görünümü", self)
        grid_view_action.triggered.connect(self.switch_to_grid_view)
        view_menu.addAction(grid_view_action)
        
        single_view_action = QAction("Tekli Görünüm", self)
        single_view_action.triggered.connect(self.switch_to_single_view)
        view_menu.addAction(single_view_action)

    def switch_to_grid_view(self):
        self.gallery_stack.setCurrentIndex(0)

    def switch_to_single_view(self):
        self.gallery_stack.setCurrentIndex(1)
        self.single_view_widget.setFocus()
        # If an item is selected, update single view
        index = self.event_gallery_list_widget.currentIndex()
        if index.isValid():
            self.on_gallery_item_clicked(index)

    def _get_item_from_index(self, index):
        if not index.isValid():
            return None
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            source_index = index.model().mapToSource(index)
            return self.gallery_item_model.itemFromIndex(source_index)
        return self.gallery_item_model.itemFromIndex(index)

    def navigate_next(self):
        index = self.event_gallery_list_widget.currentIndex()
        if not index.isValid():
            return
        model = index.model()
        row = index.row()
        if row < model.rowCount() - 1:
            next_index = model.index(row + 1, 0)
            self.event_gallery_list_widget.setCurrentIndex(next_index)
            self.on_gallery_item_clicked(next_index)

    def navigate_previous(self):
        index = self.event_gallery_list_widget.currentIndex()
        if not index.isValid():
            return
        model = index.model()
        row = index.row()
        if row > 0:
            prev_index = model.index(row - 1, 0)
            self.event_gallery_list_widget.setCurrentIndex(prev_index)
            self.on_gallery_item_clicked(prev_index)

    def init_toolbar(self):
        self.toolbar_widget = self.addToolBar("Toolbar")
        
        self.add_event = QAction("Yeni Etkinlik", self)
        self.add_event.triggered.connect(self.add_event_window)
        self.toolbar_widget.addAction(self.add_event)

        self.toolbar_widget.addAction("Çıkış")
        self.toolbar_widget.show()

    def add_event_window(self):
        self.add_event_win = add_event_window.AddEvent(parent=self)


    def tabWidget(self):
        self.tab_widget = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tab_widget)
        self.events_tab = QtWidgets.QWidget()
        self.tab_widget.addTab(self.events_tab, "Etkinlikler")

        self.persons_tab = QtWidgets.QWidget()
        self.tab_widget.addTab(self.persons_tab, "Kişiler")

        self.settings_tab = QtWidgets.QWidget()
        self.tab_widget.addTab(self.settings_tab, "Ayarlar")

        self.caption_tab = CaptionTabWidget(
            caption_service=self.app_service.get_caption_service(),
            media_service=self.app_service.get_media_service(),
            parent=self,
        )
        self.tab_widget.addTab(self.caption_tab, "Altyazı")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.show()

    def fetch_events(self):
        return self.app_service.get_event_service().get_all()
    
    def load_events(self, events=None):
        """Load events from database or provided list and populate the list widget"""
        if events is None:
            events = self.fetch_events()
            
        for event in events:
            item = QtWidgets.QListWidgetItem(self.event_card_list_widget)
            card = EventCardWidget(event.name, event.event_date)
            # Store event in card so we can retrieve it in menu
            card.event = event
            # Force width so sizeHint() calculates the correct height for wrapped text
            card.setFixedWidth(184)
            card.clicked.connect(lambda e=event, c=card: self.on_event_card_clicked(e, c))
            # Get size hint and add a tiny bit of vertical padding to be safe against cropping
            size = card.sizeHint()
            item.setSizeHint(QtCore.QSize(size.width(), size.height() + 4))
            self.event_card_list_widget.addItem(item)
            self.event_card_list_widget.setItemWidget(item, card)
    
    def load_gallery_items(self, event_id):
        """Load gallery items for an event using the service layer."""
        return self.app_service.get_media_service().get_gallery_items(event_id)


    def refresh_events(self):
        """Clear and reload the event list"""
        self.event_card_list_widget.clear()
        self.load_events()

    def on_event_search_entered(self):
        """Handle search by name for events."""
        query = self.event_search.text().strip()
        self.event_card_list_widget.clear()
        
        if not query:
            self.load_events()
            return
            
        try:
            results = self.app_service.get_event_service().search_by_name(query)
            if results:
                self.load_events(results)
                self.statusBar().showMessage(f"🔍 '{query}' için {len(results)} sonuç bulundu.", 3000)
            else:
                self.statusBar().showMessage(f"❌ '{query}' için sonuç bulunamadı.", 3000)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Arama Hatası", f"Etkinlik araması sırasında hata oluştu: {e}")


    # ------------------------------------------------------------------
    # Background batch face detection
    # ------------------------------------------------------------------

    def _start_batch_face_detection(self, event):
        vault_path = event.vault_folder_path
        image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
        file_paths = [
            os.path.join(vault_path, f)
            for f in os.listdir(vault_path)
            if os.path.splitext(f)[1].lower() in image_exts
        ]
        if not file_paths:
            return
        self._start_batch_face_detection_for_files(file_paths, event)

    def _on_batch_face_progress(self, current, total):
        self.statusBar().showMessage(f"🔍 Yüz tanıma: {current}/{total}")

    def _on_batch_face_finished(self):
        if self._face_detection_queue:
            self._process_next_face_detection()
        else:
            self.statusBar().showMessage("✅ Yüz tanıma tamamlandı.", 5000)

    def _on_batch_image_processed(self, file_path: str):
        """If single view is showing this file, refresh its face overlay from DB."""
        if self.single_view_widget.current_img_path == file_path:
            self.single_view_widget.refresh_faces_from_db()

    def _is_batch_pending_for_event(self, event_id) -> bool:
        """Return True if event_id is currently being processed or is queued."""
        if self._batch_face_worker and self._batch_face_worker.isRunning():
            if self._batch_face_worker._event_id == event_id:
                return True
        return any(item[1].id == event_id for item in self._face_detection_queue)

    def _resume_batch_face_detection(self, event, force=False):
        """Start batch detection for any images not yet processed in this event.

        Called each time an event is opened so interrupted runs are automatically
        resumed after an app restart or worker crash.
        """
        vault_path = event.vault_folder_path
        logger.debug(f"_resume_batch_face_detection: event={event.id} vault_path={vault_path!r}")
        if not vault_path or not os.path.exists(vault_path):
            logger.debug(f"_resume_batch_face_detection: returning — vault_path missing or not on disk")
            return

        # Skip if this event is already queued or being processed
        active_event_ids = {item[1].id for item in self._face_detection_queue}
        if self._batch_face_worker and self._batch_face_worker.isRunning():
            active_event_ids.add(getattr(self._batch_face_worker, '_event_id', None))
        if event.id in active_event_ids:
            logger.debug(f"_resume_batch_face_detection: returning — event already active")
            if force:
                self.statusBar().showMessage(f"⚠️ '{event.name}' zaten işleniyor veya kuyrukta.", 4000)
            return

        image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
        disk_files = {
            os.path.join(vault_path, f)
            for f in os.listdir(vault_path)
            if os.path.splitext(f)[1].lower() in image_exts
        }
        logger.debug(f"_resume_batch_face_detection: disk_files={len(disk_files)}")
        if not disk_files:
            logger.debug(f"_resume_batch_face_detection: returning — no image files on disk")
            return

        # Find files that haven't been through face detection yet
        db_records = self.app_service.get_media_service().get_all_for_event(event.id)
        processed = {
            os.path.normpath(r['file_path'])
            for r in db_records
            if r.get('face_detected_at')
        }
        unprocessed = list(disk_files) if force else [f for f in disk_files if os.path.normpath(f) not in processed]
        logger.debug(f"_resume_batch_face_detection: processed={len(processed)} unprocessed={len(unprocessed)}")
        if not unprocessed:
            logger.debug(f"_resume_batch_face_detection: returning — all images already processed")
            if force:
                self.statusBar().showMessage(f"✅ '{event.name}' için işlenecek yeni medya bulunamadı.", 4000)
            return  # everything already done

        self._start_batch_face_detection_for_files(unprocessed, event, force=force)

    def _start_batch_face_detection_for_files(self, file_paths, event, force=False):
        """Enqueue a batch job; start immediately only if no worker is running."""
        self._face_detection_queue.append((list(file_paths), event, force))
        total_queued = sum(len(item[0]) for item in self._face_detection_queue)
        if self._batch_face_worker is None or not self._batch_face_worker.isRunning():
            self._process_next_face_detection()
        else:
            self.statusBar().showMessage(
                f"🔍 Yüz tanıma kuyruğu: {len(self._face_detection_queue)} etkinlik bekliyor"
            )

    def _process_next_face_detection(self):
        """Pop the next job from the queue and start it."""
        if not self._face_detection_queue:
            return
            
        item = self._face_detection_queue.pop(0)
        if len(item) == 3:
            file_paths, event, force = item
        else:
            file_paths, event = item
            force = False
            
        svc = self.app_service
        self._batch_face_worker = BatchFaceWorker(
            file_paths,
            event.id,
            svc.get_face_service(),
            svc.get_media_service(),
            svc.get_person_service(),
            parent=self,
            force=force
        )
        self._batch_face_worker.progress.connect(self._on_batch_face_progress)
        self._batch_face_worker.finished.connect(self._on_batch_face_finished)
        self._batch_face_worker.image_processed.connect(self._on_batch_image_processed)
        self._batch_face_worker.start()
        queue_info = f" (+{len(self._face_detection_queue)} kuyrukta)" if self._face_detection_queue else ""
        self.statusBar().showMessage(f"🔍 Yüz tanıma: 0/{len(file_paths)}{queue_info}")
    
    def on_event_card_clicked(self, event, card=None):
        """Handle event card click"""
        # Deselect previous card, highlight new one
        if self._selected_event_card:
            self._selected_event_card.setSelected(False)
        if card:
            card.setSelected(True)
            self._selected_event_card = card

        self.switch_to_grid_view()
        self.current_event_id = event.id

        if self._search_mode:
            # In search mode: just narrow the already-loaded cross-event results by this event
            self.gallery_search_proxy.setEventFilter(event.id)
            self._resume_batch_face_detection(event)
            return

        # Normal mode: load this event's items from disk + DB
        self.gallery_stack.setCurrentIndex(2)  # loading widget
        self.media_details_scroll.setEnabled(False)
        self.media_details_scroll.setStyleSheet(
            "background-color: #252526; border: 1px solid #3f3f46; border-radius: 4px; opacity: 0.5;"
        )
        QtWidgets.QApplication.processEvents()

        items = self.app_service.get_media_service().get_gallery_items(event.id)
        self.gallery_item_model = GalleryItemModel(items)
        if hasattr(self, 'gallery_search_proxy'):
            self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
            self.gallery_search_proxy.setEventFilter(None)
            self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
            self.gallery_search_proxy.setFilterText(self.event_gallery_search.text())
        else:
            self.event_gallery_list_widget.setModel(self.gallery_item_model)

        self.gallery_item_model.start_loading()
        self._resume_batch_face_detection(event)

        self.gallery_stack.setCurrentIndex(0)  # grid view
        self.media_details_scroll.setEnabled(True)
        self.media_details_scroll.setStyleSheet(
            "background-color: #252526; border: 1px solid #3f3f46; border-radius: 4px;"
        )

    def _clear_event_card_selection(self):
        """Deselect all event cards and clear the current event."""
        self.event_card_list_widget.clearSelection()
        for i in range(self.event_card_list_widget.count()):
            w = self.event_card_list_widget.itemWidget(self.event_card_list_widget.item(i))
            if w:
                w.setSelected(False)
        self._selected_event_card = None
        self.current_event_id = None

    def eventFilter(self, obj, event):
        if obj is self.event_gallery_search and event.type() == QtCore.QEvent.FocusIn:
            self._clear_event_card_selection()
        
        # Override default Space bar selection in the list widget to open the image instead
        if obj is self.event_gallery_list_widget and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Space:
                index = self.event_gallery_list_widget.currentIndex()
                if index.isValid():
                    self.switch_to_single_view()
                return True # Consume event so list widget doesn't select/deselect
                
        return super().eventFilter(obj, event)

    def show_event_context_menu(self, pos):
        """Show context menu for event card"""
        item = self.event_card_list_widget.itemAt(pos)
        if not item:
            return
        
        card = self.event_card_list_widget.itemWidget(item)
        if not card or not hasattr(card, 'event'):
            return
            
        event = card.event
        
        menu = QtWidgets.QMenu(self)
        details_action = menu.addAction("🔍 Detaylar")
        process_action = menu.addAction("⚙️ Yüz Tanıma ve İndeksleme Başlat")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Sil")
        
        action = menu.exec(self.event_card_list_widget.mapToGlobal(pos))
        
        if action == details_action:
            self.on_event_details(event)
        elif action == process_action:
            self._resume_batch_face_detection(event, force=True)
            self.statusBar().showMessage(f"🚀 '{event.name}' için işlem manuel olarak başlatıldı...", 4000)
        elif action == delete_action:
            self.on_event_delete(event)

    def on_event_details(self, event):
        """Show event details in a popup"""
        msg = f"Etkinlik Adı: {event.name}\n"
        msg += f"Tarih: {event.event_date.strftime('%Y-%m-%d %H:%M:%S') if event.event_date else 'Yok'}\n"
        msg += f"Vault Yolu: {event.vault_folder_path}\n"
        msg += f"İçe Aktarma Yolu: {event.imported_folder_path}\n"
        QtWidgets.QMessageBox.information(self, "Etkinlik Detayları", msg)

    def on_event_delete(self, event):
        """Confirm and delete event"""
        reply = QtWidgets.QMessageBox.question(
            self, "Silme Onayı",
            f"'{event.name}' etkinliğini ve tüm medya kayıtlarını silmek istediğinize emin misiniz?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                # Delete from service
                self.app_service.get_event_service().delete(event.id)
                # If this was currently open, reset view
                if self.current_event_id == event.id:
                    self.current_event_id = None
                    self.gallery_item_model = GalleryItemModel([])
                    self.event_gallery_list_widget.setModel(self.gallery_item_model)
                
                # Reload list
                self.refresh_events()
                QtWidgets.QMessageBox.information(self, "Başarılı", "Etkinlik silindi.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Hata", f"Silme işlemi başarısız: {e}")
    
    def keyPressEvent(self, event):
        """Global key handler for navigation"""
        # If in Single View, handle navigation and view toggle
        if self.gallery_stack.currentIndex() == 1:
            if event.key() in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right, QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
                # Check if focused widget is a text input
                focused = QtWidgets.QApplication.focusWidget()
                if not isinstance(focused, (QtWidgets.QLineEdit, QtWidgets.QTextEdit)):
                    if event.key() in (QtCore.Qt.Key_Right, QtCore.Qt.Key_Down):
                        self.navigate_next()
                    else:
                        self.navigate_previous()
                    event.accept()
                    return
            elif event.key() == QtCore.Qt.Key_Space:
                # Space in single view goes back to gallery
                self.switch_to_grid_view()
                event.accept()
                return

        super().keyPressEvent(event)

    def on_gallery_item_clicked(self, index):
        """Handle gallery item click - populate form with DB-first, fallback to file IPTC"""
        item = self._get_item_from_index(index)
        if item:
            # Resolve media_id from DB if available
            media_row = self.app_service.get_media_service().get_by_file_path(item.img_path)
            media_id = media_row['id'] if media_row else None
            self.current_media_id = media_id

            # Provide context to single view BEFORE set_image (so DB-first works)
            face_detected_at = media_row.get('face_detected_at') if media_row else None
            is_batch_pending = (
                not face_detected_at
                and self._is_batch_pending_for_event(self.current_event_id)
            )
            self.single_view_widget.set_context(
                self.current_event_id, media_id,
                face_detected_at=face_detected_at,
                is_batch_pending=is_batch_pending,
            )
            # Update single view image
            self.single_view_widget.set_image(item.img_path)
            
            # Clear all fields first
            for w in [self.media_headline_input, self.media_object_name_input,
                      self.media_location_input, self.media_credit_input,
                      self.media_source_input, self.media_copyright_input,
                      self.media_writer_input, self.media_byline_input,
                      self.media_byline_title_input, self.media_category_input,
                      self.media_supplemental_categories_input, self.media_people_input]:
                w.clear()
            for w in [self.media_title_input, self.media_description_input, self.media_tags_input]:
                w.clear()
            
            # Title from EXIF
            if 'Title' in item.exif_data:
                self.media_title_input.setPlainText(str(item.exif_data['Title']))
            elif 'Subject' in item.exif_data:
                self.media_title_input.setPlainText(str(item.exif_data['Subject']))

            # --- DB-first loading: prefer DB over file IPTC ---
            db_iptc = None
            if self.current_event_id:
                db_iptc = self.app_service.get_media_service().get_iptc_data(item.img_path)
                if db_iptc:
                    self.current_media_id = db_iptc['id']

            if db_iptc:
                # Populate from database
                self.media_title_input.setPlainText(db_iptc.get('title') or '')
                self.media_headline_input.setText(db_iptc.get('iptc_headline') or '')
                self.media_object_name_input.setText(db_iptc.get('iptc_object_name') or '')
                self.media_description_input.setPlainText(db_iptc.get('iptc_caption') or '')
                self.media_tags_input.setPlainText(db_iptc.get('iptc_keywords') or '')
                self.media_credit_input.setText(db_iptc.get('iptc_credit') or '')
                self.media_source_input.setText(db_iptc.get('iptc_source') or '')
                self.media_copyright_input.setText(db_iptc.get('iptc_copyright') or '')
                self.media_writer_input.setText(db_iptc.get('iptc_writer') or '')
                self.media_byline_input.setText(db_iptc.get('iptc_byline') or '')
                self.media_byline_title_input.setText(db_iptc.get('iptc_byline_title') or '')
                self.media_category_input.setText(db_iptc.get('iptc_category') or '')
                self.media_supplemental_categories_input.setText(db_iptc.get('iptc_supplemental_categories') or '')
                
                # Location
                loc = ', '.join(filter(None, [
                    db_iptc.get('iptc_city'), db_iptc.get('iptc_state'), db_iptc.get('iptc_country')
                ]))
                self.media_location_input.setText(loc)
                
                # Date
                date_str = db_iptc.get('iptc_date_created') or ''
                if len(date_str) == 8:
                    qdate = QtCore.QDate.fromString(date_str, "yyyyMMdd")
                    self.media_date_input.setDate(qdate)
                else:
                    self.media_date_input.setDateTime(QtCore.QDateTime.currentDateTime())
                
                # Persons from DB
                if self.current_media_id:
                    persons = self.app_service.get_person_service().get_persons_for_media(self.current_media_id)
                    self.media_people_input.setText(', '.join(persons))
            else:
                # Fallback: populate from file IPTC
                self.media_date_input.setDateTime(QtCore.QDateTime.currentDateTime())
                if 'Headline' in item.iptc_data: self.media_headline_input.setText(item.iptc_data['Headline'])
                if 'Object Name' in item.iptc_data: self.media_object_name_input.setText(item.iptc_data['Object Name'])
                if 'Caption' in item.iptc_data: self.media_description_input.setPlainText(item.iptc_data['Caption'])
                if 'Keywords' in item.iptc_data: self.media_tags_input.setPlainText(item.iptc_data['Keywords'])
                if 'Credit' in item.iptc_data: self.media_credit_input.setText(item.iptc_data['Credit'])
                if 'Source' in item.iptc_data: self.media_source_input.setText(item.iptc_data['Source'])
                if 'Copyright' in item.iptc_data: self.media_copyright_input.setText(item.iptc_data['Copyright'])
                if 'Writer' in item.iptc_data: self.media_writer_input.setText(item.iptc_data['Writer'])
                if 'By-line' in item.iptc_data: self.media_byline_input.setText(item.iptc_data['By-line'])
                if 'By-line Title' in item.iptc_data: self.media_byline_title_input.setText(item.iptc_data['By-line Title'])
                if 'Category' in item.iptc_data: self.media_category_input.setText(item.iptc_data['Category'])
                if 'Supplemental Categories' in item.iptc_data: self.media_supplemental_categories_input.setText(item.iptc_data['Supplemental Categories'])
                if 'People' in item.iptc_data: self.media_people_input.setText(item.iptc_data['People'])
                loc_parts = [item.iptc_data.get(k, '') for k in ('City', 'State', 'Country') if k in item.iptc_data]
                if loc_parts: self.media_location_input.setText(', '.join(loc_parts))
                if 'Date Created' in item.iptc_data:
                    date_str = item.iptc_data['Date Created']
                    if len(date_str) == 8:
                        qdate = QtCore.QDate.fromString(date_str, "yyyyMMdd")
                        self.media_date_input.setDate(qdate)


    def save_media_iptc(self, silent=False):
        """Save IPTC data to both the image file and the database."""
        index = self.event_gallery_list_widget.currentIndex()
        if not index.isValid():
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen önce bir fotoğraf seçin.")
            return
        
        item = self._get_item_from_index(index)
        if not item or not self.current_event_id:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen bir etkinlik ve fotoğraf seçin.")
            return
        
        try:
            # Collect IPTC data from form
            location = self.media_location_input.text()
            loc_parts = [p.strip() for p in location.split(',')]
            city  = loc_parts[0] if len(loc_parts) >= 1 else ''
            state = loc_parts[1] if len(loc_parts) >= 2 else ''
            country = loc_parts[2] if len(loc_parts) >= 3 else ''

            iptc_data = {
                "Title": self.media_title_input.toPlainText(),
                "Headline": self.media_headline_input.text(),
                "Caption": self.media_description_input.toPlainText(),
                "Keywords": self.media_tags_input.toPlainText(),
                "Object Name": self.media_object_name_input.text(),
                "City": city, "State": state, "Country": country,
                "Credit": self.media_credit_input.text(),
                "Source": self.media_source_input.text(),
                "Copyright": self.media_copyright_input.text(),
                "Writer": self.media_writer_input.text(),
                "By-line": self.media_byline_input.text(),
                "By-line Title": self.media_byline_title_input.text(),
                "Date Created": "",
                "Category": self.media_category_input.text(),
                "Supplemental Categories": self.media_supplemental_categories_input.text(),
            }
            
            # 1. Write IPTC metadata to the image file
            self._write_iptc_to_file(item.img_path, iptc_data)
            
            # 2. Save to database (ensure media record exists)
            media_id = self.app_service.get_media_service().ensure_media_exists(
                self.current_event_id, item.img_path, 'photo'
            )
            self.current_media_id = media_id
            self.app_service.get_media_service().save_iptc_data(media_id, iptc_data)
            
            # 3. Handle persons
            self.app_service.get_person_service().unlink_all_from_media(media_id)
            people_text = self.media_people_input.text()
            if people_text:
                for name in people_text.split(','):
                    name = name.strip()
                    if name:
                        person_id = self.app_service.get_person_service().find_or_create(name)
                        if person_id:
                            self.app_service.get_person_service().link_to_media(person_id, media_id)
            
            if not silent:
                QtWidgets.QMessageBox.information(self, "Başarılı", "✅ IPTC verileri dosyaya ve veritabanına kaydedildi.")
            self.refresh_gallery_badges()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Hata", f"❌ Kaydetme hatası: {str(e)}")

    def refresh_gallery_badges(self):
        """Refresh the in_db badge on all gallery items for the current event."""
        if not self.current_event_id:
            return
        db_paths = self.app_service.get_media_service().get_file_paths_for_event(self.current_event_id)
        for row in range(self.gallery_item_model.rowCount()):
            item = self.gallery_item_model.item(row)
            if item:
                in_db = os.path.normpath(item.img_path) in db_paths
                if item.in_db != in_db:
                    item.in_db = in_db
                new_icon = QtGui.QIcon(GalleryItemModel.generate_pixmap(item))
                item.setIcon(new_icon)


    def _write_iptc_to_file(self, img_path: str, iptc_data: dict):
        """Write IPTC metadata directly into the image file using iptcinfo3."""
        from iptcinfo3 import IPTCInfo
        
        def clean(val):
            return val.replace('\x00', '').strip() if val else ''
        
        def to_list(val):
            """Convert a non-empty string to a single-item list, empty string to []."""
            v = clean(val)
            return [v.encode('utf-8')] if v else []
        
        try:
            info = IPTCInfo(img_path, force=True)
        except Exception:
            info = IPTCInfo(img_path, force=True)
        
        # String fields (single value)
        string_fields = {
            'headline':                          clean(iptc_data.get('Headline', '')),
            'caption/abstract':                  clean(iptc_data.get('Caption', '')),
            'object name':                       clean(iptc_data.get('Object Name', '')),
            'city':                              clean(iptc_data.get('City', '')),
            'province/state':                    clean(iptc_data.get('State', '')),
            'country/primary location name':     clean(iptc_data.get('Country', '')),
            'credit':                            clean(iptc_data.get('Credit', '')),
            'source':                            clean(iptc_data.get('Source', '')),
            'copyright notice':                  clean(iptc_data.get('Copyright', '')),
            'writer/editor':                     clean(iptc_data.get('Writer', '')),
            'by-line title':                     clean(iptc_data.get('By-line Title', '')),
        }
        for field, value in string_fields.items():
            info[field] = value
        
        # List fields (iptcinfo3 requires iterable for these)
        info['by-line'] = to_list(iptc_data.get('By-line', ''))
        info['category'] = to_list(iptc_data.get('Category', ''))
        info['supplemental category'] = to_list(iptc_data.get('Supplemental Categories', ''))
        
        # Keywords as list
        keywords_raw = clean(iptc_data.get('Keywords', ''))
        if keywords_raw:
            info['keywords'] = [k.strip().encode('utf-8') for k in keywords_raw.split(',') if k.strip()]
        else:
            info['keywords'] = []
        
        info.save_as(img_path)


    def event_widgets(self):
        self.event_search = QtWidgets.QLineEdit()
        self.event_search.setPlaceholderText("Ara...")
        self.event_search.setFixedHeight(30)
        self.event_search.setFixedWidth(200)

        self.event_card_list_widget = QtWidgets.QListWidget()
        self.event_card_list_widget.setFixedWidth(200)
        self.event_card_list_widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.event_card_list_widget.setResizeMode(QtWidgets.QListView.Adjust)
        self.event_card_list_widget.setWordWrap(True)
        
        # Context menu setup
        self.event_card_list_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.event_card_list_widget.customContextMenuRequested.connect(self.show_event_context_menu)
        
        # Search functionality
        self.event_search.returnPressed.connect(self.on_event_search_entered)
        
        # Load events into the list
        self.load_events()
        
        # Gallery search section
        self.gallery_search_layout = QtWidgets.QHBoxLayout()
        self.event_gallery_search = QtWidgets.QLineEdit()
        self.event_gallery_search.setPlaceholderText("EXIF İçinde Ara...")
        self.event_gallery_search.setFixedHeight(30)
        self.event_gallery_search.setMinimumWidth(300)
        
        self.event_gallery_date_cb = QtWidgets.QCheckBox("Tarih Filtresi:")
        self.event_gallery_date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.event_gallery_date.setCalendarPopup(True)
        self.event_gallery_date.setFixedHeight(30)
        self.event_gallery_date.setEnabled(False)
        self.event_gallery_date_cb.toggled.connect(self.event_gallery_date.setEnabled)

        self.event_gallery_search_btn = QtWidgets.QPushButton("Ara")
        self.event_gallery_search_btn.setFixedHeight(30)
        
        self.gallery_search_layout.addWidget(self.event_gallery_search)
        self.gallery_search_layout.addWidget(self.event_gallery_date_cb)
        self.gallery_search_layout.addWidget(self.event_gallery_date)
        self.gallery_search_layout.addWidget(self.event_gallery_search_btn)
        self.gallery_search_layout.addStretch()
        # Gallery Stack section (Grid + Single)
        self.gallery_stack = QtWidgets.QStackedWidget()
        
        # Grid View
        self.event_gallery_list_widget = QtWidgets.QListView()
        self.event_gallery_list_widget.setViewMode(QtWidgets.QListView.IconMode)
        self.event_gallery_list_widget.setGridSize(QtCore.QSize(180, 200))
        self.event_gallery_list_widget.setSpacing(10)
        self.event_gallery_list_widget.setUniformItemSizes(True)
        self.event_gallery_list_widget.setIconSize(QtCore.QSize(150, 150))
        
        # Context menu
        self.event_gallery_list_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.event_gallery_list_widget.customContextMenuRequested.connect(self.show_gallery_context_menu)
        
        # Single View — inject face recognition dependencies
        self.single_view_widget = SingleViewWidget(
            face_service=self.app_service.get_face_service(),
            person_service=self.app_service.get_person_service(),
            media_service=self.app_service.get_media_service(),
        )
        self.single_view_widget.doubleClicked.connect(self.switch_to_grid_view)
        self.single_view_widget.nextRequested.connect(self.navigate_next)
        self.single_view_widget.prevRequested.connect(self.navigate_previous)
        self.single_view_widget.facesChanged.connect(self._on_faces_changed)
        
        self.gallery_stack.addWidget(self.event_gallery_list_widget)
        self.gallery_stack.addWidget(self.single_view_widget)

        # Loading widget (index=2)
        self._loading_widget = QtWidgets.QWidget()
        _loading_layout = QtWidgets.QVBoxLayout(self._loading_widget)
        _loading_layout.setAlignment(QtCore.Qt.AlignCenter)
        _loading_label = QtWidgets.QLabel("⏳ Yükleniyor...")
        _loading_label.setAlignment(QtCore.Qt.AlignCenter)
        _loading_label.setStyleSheet("font-size: 22px; color: #555; font-weight: bold;")
        _loading_layout.addWidget(_loading_label)
        self.gallery_stack.addWidget(self._loading_widget)

        self.gallery_item_model = GalleryItemModel([])
        from gallery_item_model import GallerySearchProxyModel
        self.gallery_search_proxy = GallerySearchProxyModel()
        self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
        self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
        
        # Connect search
        self.event_gallery_search.returnPressed.connect(self.on_gallery_search)
        self.event_gallery_search_btn.clicked.connect(self.on_gallery_search)
        self.event_gallery_search.installEventFilter(self)
        
        # Install event filter to capture Space bar properly before QListView consumes it
        self.event_gallery_list_widget.installEventFilter(self)
        
        # Connect click event to print EXIF data
        self.event_gallery_list_widget.clicked.connect(self.on_gallery_item_clicked)
        self.event_gallery_list_widget.doubleClicked.connect(self.switch_to_single_view)

    def show_gallery_context_menu(self, pos):
        """Show context menu for gallery item"""
        index = self.event_gallery_list_widget.indexAt(pos)
        if not index.isValid():
            return
            
        item = self._get_item_from_index(index)
        if not item:
            return
            
        menu = QtWidgets.QMenu(self)
        reveal_action = menu.addAction("📁 Dosya Konumunu Aç")
        
        action = menu.exec(self.event_gallery_list_widget.mapToGlobal(pos))
        
        if action == reveal_action:
            from src.utils import path_util
            path_util.reveal_in_explorer(item.img_path)

    def _on_faces_changed(self):
        """Update the UI people input and auto-save IPTC when face labels change."""
        index = self.event_gallery_list_widget.currentIndex()
        if not index.isValid():
            return
        item = self._get_item_from_index(index)
        if not item or not self.current_event_id:
            return

        try:
            self.current_media_id = self.app_service.get_media_service().ensure_media_exists(
                self.current_event_id, item.img_path, 'photo'
            )
            persons = self.app_service.get_person_service().get_persons_for_media(self.current_media_id)
            self.media_people_input.setText(', '.join(persons))
            # Auto-save changes without showing a confirmation popup
            self.save_media_iptc(silent=True)
        except Exception as e:
            import logging
            logging.warning(f"Error updating faces: {e}")

    def on_gallery_search(self):
        """Search IPTC across all events; narrow by event when user clicks an event card."""
        if not hasattr(self, 'gallery_search_proxy'):
            return
        self._clear_event_card_selection()  # ensure deselected even if called via button
        text = self.event_gallery_search.text().strip()
        date_filter = None
        if self.event_gallery_date_cb.isChecked():
            date_filter = self.event_gallery_date.date().toString("yyyyMMdd")

        if text:
            # Show loading screen and kick off background FTS query
            self._search_mode = True
            self._pending_search_date_filter = date_filter
            self._pending_search_text = text
            self.gallery_stack.setCurrentIndex(2)  # loading widget

            # Cancel any previous search still running
            if self._search_worker and self._search_worker.isRunning():
                self._search_worker.finished.disconnect()
                self._search_worker.error.disconnect()
                self._search_worker.quit()

            self._search_worker = SearchWorker(
                self.app_service.get_media_service(), text, parent=self
            )
            self._search_worker.finished.connect(self._on_search_finished)
            self._search_worker.error.connect(self._on_search_error)
            self._search_worker.start()
        else:
            # Search cleared: exit search mode and reload current event
            self._search_mode = False
            self.gallery_search_proxy.setEventFilter(None)
            if self.current_event_id:
                items = self.app_service.get_media_service().get_gallery_items(self.current_event_id)
                self.gallery_item_model = GalleryItemModel(items)
                self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
                self.gallery_search_proxy.setFilterText("", date_filter)
                self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
                self.gallery_item_model.start_loading()
            else:
                self.gallery_search_proxy.setFilterText("", date_filter)

    def _on_search_finished(self, records, query_text):
        """Called on the main thread when the background FTS query completes."""
        # Ignore stale results if the user already typed something else
        if query_text != self._pending_search_text:
            return
        from gallery_item_model import GalleryItem
        items = [
            GalleryItem(
                r.get('title') or os.path.basename(r.get('file_path', '')),
                r['file_path'], in_db=True, db_metadata=r
            )
            for r in records
            if r.get('file_path') and os.path.exists(r['file_path'])
        ]
        date_filter = self._pending_search_date_filter
        self.gallery_item_model = GalleryItemModel(items)
        self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
        self.gallery_search_proxy.setEventFilter(None)
        self.gallery_search_proxy.setFilterText(query_text, date_filter)
        self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
        self.gallery_item_model.start_loading()
        self.gallery_stack.setCurrentIndex(0)
        self.statusBar().showMessage(f"🔍 {len(items)} sonuç bulundu.", 4000)

    def _on_search_error(self, message):
        self.gallery_stack.setCurrentIndex(0)
        self.statusBar().showMessage(f"❌ Arama hatası: {message}", 6000)

    def media_details_form_widget(self):
        """Create form fields for media details"""
        fixed_width = 300
        # Create input fields and store references
        self.media_title_input = QtWidgets.QTextEdit()
        self.media_title_input.setMaximumHeight(50)
        self.media_title_input.setFixedWidth(fixed_width)
        self.media_title_input.setPlaceholderText("Title")
        
        self.media_headline_input = QtWidgets.QLineEdit()
        self.media_headline_input.setFixedWidth(fixed_width)
        self.media_headline_input.setPlaceholderText("Headline")

        self.media_object_name_input = QtWidgets.QLineEdit()
        self.media_object_name_input.setFixedWidth(fixed_width)
        self.media_object_name_input.setPlaceholderText("Object Name")

        self.media_date_input = QtWidgets.QDateTimeEdit()
        self.media_date_input.setFixedWidth(fixed_width)
        self.media_date_input.setCalendarPopup(True)
        self.media_date_input.setDisplayFormat("dd.MM.yyyy HH:mm")
        
        self.media_location_input = QtWidgets.QLineEdit()
        self.media_location_input.setFixedWidth(fixed_width)
        self.media_location_input.setPlaceholderText("Location")
        
        self.media_description_input = QtWidgets.QTextEdit()
        self.media_description_input.setMaximumHeight(100)
        self.media_description_input.setFixedWidth(fixed_width)
        self.media_description_input.setPlaceholderText("Description")
        
        self.media_tags_input = QtWidgets.QTextEdit()
        self.media_tags_input.setFixedWidth(fixed_width)
        self.media_tags_input.setPlaceholderText("Tags")
        self.media_tags_input.setMaximumHeight(100)

        # New IPTC Fields
        self.media_credit_input = QtWidgets.QLineEdit()
        self.media_credit_input.setFixedWidth(fixed_width)
        self.media_credit_input.setPlaceholderText("Credit")

        self.media_source_input = QtWidgets.QLineEdit()
        self.media_source_input.setFixedWidth(fixed_width)
        self.media_source_input.setPlaceholderText("Source")

        self.media_copyright_input = QtWidgets.QLineEdit()
        self.media_copyright_input.setFixedWidth(fixed_width)
        self.media_copyright_input.setPlaceholderText("Copyright")

        self.media_writer_input = QtWidgets.QLineEdit()
        self.media_writer_input.setFixedWidth(fixed_width)
        self.media_writer_input.setPlaceholderText("Writer/Editor")

        self.media_byline_input = QtWidgets.QLineEdit()
        self.media_byline_input.setFixedWidth(fixed_width)
        self.media_byline_input.setPlaceholderText("By-line")

        self.media_byline_title_input = QtWidgets.QLineEdit()
        self.media_byline_title_input.setFixedWidth(fixed_width)
        self.media_byline_title_input.setPlaceholderText("By-line Title")

        self.media_category_input = QtWidgets.QLineEdit()
        self.media_category_input.setFixedWidth(fixed_width)
        self.media_category_input.setPlaceholderText("Category")

        self.media_supplemental_categories_input = QtWidgets.QLineEdit()
        self.media_supplemental_categories_input.setFixedWidth(fixed_width)
        self.media_supplemental_categories_input.setPlaceholderText("Supplemental Categories")

        self.media_people_input = QtWidgets.QLineEdit()
        self.media_people_input.setFixedWidth(fixed_width)
        self.media_people_input.setPlaceholderText("Kişiler (Virgülle ayırın)")

        # Create labels and add rows
        self.media_details_form.addRow(QtWidgets.QLabel("📝 Title:"), self.media_title_input)
        self.media_details_form.addRow(QtWidgets.QLabel("� Headline:"), self.media_headline_input)
        self.media_details_form.addRow(QtWidgets.QLabel("🆔 Object Name:"), self.media_object_name_input)
        self.media_details_form.addRow(QtWidgets.QLabel("📅 Date:"), self.media_date_input)
        self.media_details_form.addRow(QtWidgets.QLabel("📍 Location:"), self.media_location_input)
        self.media_details_form.addRow(QtWidgets.QLabel("📄 Description:"), self.media_description_input)
        self.media_details_form.addRow(QtWidgets.QLabel("🏷️ Tags:"), self.media_tags_input)
        self.media_details_form.addRow(QtWidgets.QLabel("👥 Kişiler:"), self.media_people_input)
        
        self.media_details_form.addRow(QtWidgets.QLabel("💳 Credit:"), self.media_credit_input)
        self.media_details_form.addRow(QtWidgets.QLabel("🏗️ Source:"), self.media_source_input)
        self.media_details_form.addRow(QtWidgets.QLabel("©️ Copyright:"), self.media_copyright_input)
        
        self.media_details_form.addRow(QtWidgets.QLabel("✍️ Writer:"), self.media_writer_input)
        self.media_details_form.addRow(QtWidgets.QLabel("👤 By-line:"), self.media_byline_input)
        self.media_details_form.addRow(QtWidgets.QLabel("🎓 By-line Title:"), self.media_byline_title_input)
        
        self.media_details_form.addRow(QtWidgets.QLabel("🗂️ Category:"), self.media_category_input)
        self.media_details_form.addRow(QtWidgets.QLabel("➕ Sup. Categories:"), self.media_supplemental_categories_input)

        # Styling
        self.media_details_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.media_details_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.media_details_form.setHorizontalSpacing(10)
        self.media_details_form.setVerticalSpacing(8)

        
    def _on_tab_changed(self, index: int):
        if self.tab_widget.widget(index) is self.persons_tab:
            self._load_persons_table()

    def _on_person_row_clicked(self, row: int, _col: int):
        name_item = self._persons_table.item(row, 0)
        if name_item is None:
            return
        person_id = name_item.data(QtCore.Qt.UserRole)
        person_name = name_item.text()
        if not person_id:
            return

        try:
            items = self.app_service.get_media_service().get_gallery_items_for_person(person_id)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Hata", f"Fotoğraflar yüklenemedi: {e}")
            return

        self.current_event_id = None
        self.current_media_id = None
        self.gallery_item_model = GalleryItemModel(items)
        if hasattr(self, "gallery_search_proxy"):
            self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
            self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
            self.gallery_search_proxy.setFilterText("")
        else:
            self.event_gallery_list_widget.setModel(self.gallery_item_model)
        self.gallery_item_model.start_loading()

        self._person_filter_label.setText(f"Kişi filtresi: {person_name}  —  {len(items)} fotoğraf")
        self._person_filter_bar.show()

        self.tab_widget.setCurrentWidget(self.events_tab)
        self.gallery_stack.setCurrentIndex(0)

    def _clear_person_filter(self):
        self._person_filter_bar.hide()
        self.current_event_id = None
        self.gallery_item_model = GalleryItemModel([])
        if hasattr(self, "gallery_search_proxy"):
            self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
            self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
        else:
            self.event_gallery_list_widget.setModel(self.gallery_item_model)

    def _init_persons_tab(self):
        layout = QtWidgets.QVBoxLayout(self.persons_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Row 1: person name search + refresh + delete ──
        top_bar = QtWidgets.QHBoxLayout()
        self._persons_search = QtWidgets.QLineEdit()
        self._persons_search.setPlaceholderText("İsimde ara…")
        self._persons_search.setFixedHeight(30)
        self._persons_search.textChanged.connect(self._filter_persons_table)
        top_bar.addWidget(self._persons_search)

        refresh_btn = QtWidgets.QPushButton("Yenile")
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self._load_persons_table)
        top_bar.addWidget(refresh_btn)

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
        # Persons table (default view)
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

        # Notes results table (shown only during note search)
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

    def _load_persons_table(self):
        try:
            rows = self.app_service.get_person_service().get_all_with_counts()
        except Exception:
            rows = []

        self._persons_table.setSortingEnabled(False)
        self._persons_table.setRowCount(len(rows))
        for i, person in enumerate(rows):
            name_item = QtWidgets.QTableWidgetItem(person["name"])
            name_item.setData(QtCore.Qt.UserRole, person["id"])  # store UUID for lookup
            count_item = QtWidgets.QTableWidgetItem()
            count_item.setData(QtCore.Qt.DisplayRole, int(person["photo_count"]))
            count_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self._persons_table.setItem(i, 0, name_item)
            self._persons_table.setItem(i, 1, count_item)
        self._persons_table.setSortingEnabled(True)
        self._persons_search.clear()

    def _filter_persons_table(self, text: str):
        text = text.lower()
        for row in range(self._persons_table.rowCount()):
            item = self._persons_table.item(row, 0)
            visible = text in (item.text().lower() if item else "")
            self._persons_table.setRowHidden(row, not visible)

    def _on_notes_search_changed(self, text: str):
        query = text.strip()
        if not query:
            # Restore persons table
            self._notes_table.hide()
            self._persons_table.show()
            return

        # Show notes results table
        self._persons_table.hide()
        self._notes_table.show()

        try:
            results = self.app_service.get_person_service().search_notes(query)
        except Exception:
            results = []

        from src.utils import path_util
        self._notes_table.setSortingEnabled(False)
        self._notes_table.setRowCount(len(results))
        for i, rec in enumerate(results):
            person_item = QtWidgets.QTableWidgetItem(rec.get("person_name", ""))
            person_item.setData(QtCore.Qt.UserRole, rec)   # full record for navigation

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

        from src.utils import path_util
        abs_path = path_util.from_db_path(rec.get("file_path", ""))
        if not abs_path or not os.path.exists(abs_path):
            QtWidgets.QMessageBox.warning(self, "Hata", "Dosya bulunamadı.")
            return

        # Load the single photo in gallery and switch to single view
        from gallery_item_model import GalleryItem
        item = GalleryItem(
            os.path.basename(abs_path),
            abs_path,
            in_db=True,
            db_metadata=rec,
        )
        self.gallery_item_model = GalleryItemModel([item])
        if hasattr(self, "gallery_search_proxy"):
            self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
            self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
            self.gallery_search_proxy.setFilterText("")
        else:
            self.event_gallery_list_widget.setModel(self.gallery_item_model)
        self.gallery_item_model.start_loading()

        self._person_filter_label.setText(f"Not araması: {rec.get('person_name', '')}  —  {os.path.basename(abs_path)}")
        self._person_filter_bar.show()

        # Switch to events tab and open single view for this image
        self.tab_widget.setCurrentWidget(self.events_tab)
        self.gallery_stack.setCurrentIndex(1)
        self.single_view_widget.set_context(
            event_id=None,
            media_id=rec.get("media_id"),
        )
        self.single_view_widget.set_image(abs_path)

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
            self.app_service.get_person_service().delete(person_id)
            self._load_persons_table()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Hata", f"Kişi silinemedi: {e}")

    def layouts(self):
        self.events_layout = QtWidgets.QHBoxLayout()
        self.events_column = QtWidgets.QVBoxLayout()
        self.events_gallery = QtWidgets.QVBoxLayout()
        
        # Right side: Details Scroll Area
        self.media_details_scroll = QtWidgets.QScrollArea()
        self.media_details_scroll.setWidgetResizable(True)
        self.media_details_scroll.setFixedWidth(450)
        self.media_details_scroll.setStyleSheet("background-color: #252526; border: 1px solid #3f3f46; border-radius: 4px;")
        
        self.media_details_container = QtWidgets.QWidget()
        self.media_details_form = QtWidgets.QFormLayout()
        self.media_details_container.setLayout(self.media_details_form)
        self.media_details_scroll.setWidget(self.media_details_container)
        
        # Single Save button at the top of the details panel
        self.save_media_btn = QtWidgets.QPushButton("💾 Kaydet")
        self.save_media_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D7; color: white; padding: 10px;
                border: none; border-radius: 4px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #005A9E; }
        """)
        self.save_media_btn.clicked.connect(self.save_media_iptc)
        self.media_details_form.addRow(self.save_media_btn)
        
        self.events_layout.addLayout(self.events_column, 1)
        self.events_layout.addLayout(self.events_gallery, 3)
        self.events_layout.addWidget(self.media_details_scroll, 1)
        
        # event column
        self.events_column.addWidget(self.event_search)
        self.event_card_list_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.event_card_list_widget.customContextMenuRequested.connect(self.show_event_context_menu)
        self.events_column.addWidget(self.event_card_list_widget)
        # Person filter banner (hidden by default)
        self._person_filter_bar = QtWidgets.QWidget()
        self._person_filter_bar.setStyleSheet(
            "background: #1a3a5c; border: 1px solid #2d6ca2; border-radius: 4px;"
        )
        _pfbar_layout = QtWidgets.QHBoxLayout(self._person_filter_bar)
        _pfbar_layout.setContentsMargins(10, 4, 6, 4)
        self._person_filter_label = QtWidgets.QLabel()
        self._person_filter_label.setStyleSheet("color: #8ecfff; font-weight: bold; font-size: 12px;")
        _pfbar_layout.addWidget(self._person_filter_label)
        _pfbar_layout.addStretch()
        _clear_filter_btn = QtWidgets.QPushButton("✕ Filtreyi Temizle")
        _clear_filter_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #8ecfff;
                          border: 1px solid #2d6ca2; border-radius: 3px;
                          padding: 2px 8px; font-size: 11px; }
            QPushButton:hover { background: #2d6ca2; color: white; }
        """)
        _clear_filter_btn.clicked.connect(self._clear_person_filter)
        _pfbar_layout.addWidget(_clear_filter_btn)
        self._person_filter_bar.hide()

        # event gallery
        self.events_gallery.addLayout(self.gallery_search_layout)
        self.events_gallery.addWidget(self._person_filter_bar)
        self.events_gallery.addWidget(self.gallery_stack)  
        # media details
        self.media_details_form_widget()     
        
        self.events_tab.setLayout(self.events_layout)

        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_tab.setLayout(self.settings_layout)

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #ffffff; }
            QTabWidget::pane { border: 1px solid #3f3f46; background-color: #1e1e1e; }
            QTabBar::tab { background: #252526; color: #ffffff; padding: 10px 20px; border: 1px solid #3f3f46; border-bottom: none; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px;}
            QTabBar::tab:selected { background: #1e1e1e; color: #ffffff; font-weight: bold; border-bottom: 2px solid #0078D7; }
            QListView, QListWidget { background-color: #252526; border: 1px solid #3f3f46; color: #ffffff; border-radius: 4px; }
            QLineEdit, QTextEdit, QDateEdit, QDateTimeEdit { background-color: #333333; border: 1px solid #555555; color: #ffffff; padding: 4px; border-radius: 4px; }
            QLineEdit:focus, QTextEdit:focus, QDateEdit:focus { border: 1px solid #0078D7; }
            QLabel { color: #ffffff; }
            QMenuBar { background-color: #1e1e1e; color: #ffffff; }
            QMenuBar::item:selected { background-color: #333333; }
            QMenu { background-color: #252526; color: #ffffff; border: 1px solid #3f3f46; }
            QMenu::item:selected { background-color: #0078D7; color: white;}
            QScrollArea { background-color: #252526; border: none; }
            QWidget { background-color: #1e1e1e; color: #ffffff; }
            QPushButton { background-color: #333333; color: white; padding: 6px 15px; border: 1px solid #555555; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #3f3f46; border: 1px solid #0078D7; }
            QPushButton:pressed { background-color: #0078D7; border: 1px solid #0078D7; }
            QCheckBox { color: #ffffff; }
        """)



def app():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.app_service.initialize_application()
    sys.exit(app.exec())

if __name__ == "__main__":
    app()
