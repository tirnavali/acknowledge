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
import os

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tirnavali Acknowledge")
        self.resize(1400, 900)
        self.current_event_id = None
        self.current_media_id = None
        self.media_repo = MediaRepository()
        self.person_repo = PersonRepository()
        self.face_repo = FaceRepository()
        self.face_service = FaceAnalysisService()  # singleton, lazy model load
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
            ]
            with get_db() as db:
                for col_name, col_type in iptc_columns:
                    try:
                        db.execute(text(f"ALTER TABLE medias ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                    except Exception:
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

        self.toolbar_widget.addAction("Yeni Medya")
        self.toolbar_widget.addAction("Open")
        self.toolbar_widget.addAction("Save")
        self.toolbar_widget.addAction("Save As")
        self.toolbar_widget.addAction("Exit")
        self.toolbar_widget.show()

    def add_event_window(self):
        self.add_event_win = add_event_window.AddEvent(parent=self)


    def tabWidget(self):
        self.tab_widget = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tab_widget)
        self.events_tab = QtWidgets.QWidget()
        self.tab_widget.addTab(self.events_tab, "Etkinlikler")

        self.settings_tab = QtWidgets.QWidget()
        self.tab_widget.addTab(self.settings_tab, "Ayarlar")

        self.tab_widget.show()

    def fetch_events(self):
        return EventRepository().get_all()
    
    def load_events(self):
        """Load events from database and populate the list widget"""
        events = self.fetch_events()
        for event in events:
            item = QtWidgets.QListWidgetItem(self.event_card_list_widget)
            card = EventCardWidget(event.name, event.event_date)
            # Force width so sizeHint() calculates the correct height for wrapped text
            card.setFixedWidth(184)
            card.clicked.connect(lambda e=event: self.on_event_card_clicked(e))
            # Get size hint and add a tiny bit of vertical padding to be safe against cropping
            size = card.sizeHint()
            item.setSizeHint(QtCore.QSize(size.width(), size.height() + 4))
            self.event_card_list_widget.addItem(item)
            self.event_card_list_widget.setItemWidget(item, card)
    
    def load_gallery_items(self, event_id):
        items = []
        event = EventRepository().get_by_id(event_id)
        if not event.vault_folder_path:
            return items
        abs_folder_path = os.path.abspath(event.vault_folder_path)
        if not os.path.exists(abs_folder_path):
            return items

        # Fetch all file_paths already in DB for this event in one query
        db_paths = self.media_repo.get_file_paths_for_event(event_id)

        for filename in os.listdir(abs_folder_path):
            if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                img_path = os.path.join(abs_folder_path, filename)
                in_db = os.path.normpath(img_path) in db_paths
                item = GalleryItem(filename, img_path, in_db=in_db)
                items.append(item)
        return items


    def refresh_events(self):
        """Clear and reload the event list"""
        self.event_card_list_widget.clear()
        self.load_events()
    
    def on_event_card_clicked(self, event):
        """Handle event card click"""
        self.switch_to_grid_view()
        self.current_event_id = event.id

        # Show loading state
        self.gallery_stack.setCurrentIndex(2)  # loading widget
        self.media_details_scroll.setEnabled(False)
        self.media_details_scroll.setStyleSheet(
            "background-color: #ebebeb; border: 1px solid #ccc; border-radius: 4px; opacity: 0.5;"
        )
        QtWidgets.QApplication.processEvents()

        items = self.load_gallery_items(event.id)
        self.gallery_item_model = GalleryItemModel(items)
        if hasattr(self, 'gallery_search_proxy'):
            self.gallery_search_proxy.setSourceModel(self.gallery_item_model)
            self.event_gallery_list_widget.setModel(self.gallery_search_proxy)
            # Apply any existing search text
            self.gallery_search_proxy.setFilterText(self.event_gallery_search.text())
        else:
            self.event_gallery_list_widget.setModel(self.gallery_item_model)

        # Restore state
        self.gallery_stack.setCurrentIndex(0)  # grid view
        self.media_details_scroll.setEnabled(True)
        self.media_details_scroll.setStyleSheet(
            "background-color: #f5f5f5; border: 1px solid #ccc; border-radius: 4px;"
        )
    
    def keyPressEvent(self, event):
        """Global key handler for navigation"""
        # If in Single View, handle arrow keys for navigation
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
        super().keyPressEvent(event)

    def on_gallery_item_clicked(self, index):
        """Handle gallery item click - populate form with DB-first, fallback to file IPTC"""
        item = self._get_item_from_index(index)
        if item:
            # Resolve media_id from DB if available
            media_row = self.media_repo.get_by_file_path(item.img_path)
            media_id = media_row['id'] if media_row else None
            self.current_media_id = media_id

            # Provide context to single view BEFORE set_image (so DB-first works)
            self.single_view_widget.set_context(self.current_event_id, media_id)
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
            self.current_media_id = None
            if self.current_event_id:
                db_iptc = self.media_repo.get_iptc_data(item.img_path)
                if db_iptc:
                    media_row = self.media_repo.get_by_file_path(item.img_path)
                    if media_row:
                        self.current_media_id = media_row['id']

            if db_iptc:
                # Populate from database
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
                    persons = self.person_repo.get_persons_for_media(self.current_media_id)
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
            media_id = self.media_repo.ensure_media_exists(
                self.current_event_id, item.img_path, "photo"
            )
            self.current_media_id = media_id
            self.media_repo.save_iptc(media_id, iptc_data)
            
            # 3. Handle persons
            self.person_repo.unlink_all_from_media(media_id)
            people_text = self.media_people_input.text()
            if people_text:
                for name in people_text.split(','):
                    name = name.strip()
                    if name:
                        person_id = self.person_repo.find_or_create(name)
                        if person_id:
                            self.person_repo.link_to_media(person_id, media_id)
            
            if not silent:
                QtWidgets.QMessageBox.information(self, "Başarılı", "✅ IPTC verileri dosyaya ve veritabanına kaydedildi.")
            self.refresh_gallery_badges()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Hata", f"❌ Kaydetme hatası: {str(e)}")

    def refresh_gallery_badges(self):
        """Refresh the in_db badge on all gallery items for the current event."""
        if not self.current_event_id:
            return
        db_paths = self.media_repo.get_file_paths_for_event(self.current_event_id)
        for row in range(self.gallery_item_model.rowCount()):
            item = self.gallery_item_model.item(row)
            if item:
                in_db = os.path.normpath(item.img_path) in db_paths
                if item.in_db != in_db:
                    item.in_db = in_db
                new_icon = QtGui.QIcon(self.gallery_item_model._make_icon(item))
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
        
        # Load events into the list
        self.load_events()
        
        # Gallery search section
        self.event_gallery_search = QtWidgets.QLineEdit()
        self.event_gallery_search.setPlaceholderText("EXIF İçinde Ara...")
        self.event_gallery_search.setFixedHeight(30)
        self.event_gallery_search.setFixedWidth(600)
        # Gallery Stack section (Grid + Single)
        self.gallery_stack = QtWidgets.QStackedWidget()
        
        # Grid View
        self.event_gallery_list_widget = QtWidgets.QListView()
        self.event_gallery_list_widget.setViewMode(QtWidgets.QListView.IconMode)
        self.event_gallery_list_widget.setGridSize(QtCore.QSize(180, 200))
        self.event_gallery_list_widget.setSpacing(10)
        self.event_gallery_list_widget.setUniformItemSizes(True)
        self.event_gallery_list_widget.setIconSize(QtCore.QSize(150, 150))
        
        # Single View — inject face recognition dependencies
        self.single_view_widget = SingleViewWidget(
            face_service=self.face_service,
            face_repository=self.face_repo,
            person_repository=self.person_repo,
            media_repository=self.media_repo,
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
        self.event_gallery_search.textChanged.connect(self.on_gallery_search)
        
        # Connect click event to print EXIF data
        self.event_gallery_list_widget.clicked.connect(self.on_gallery_item_clicked)
        self.event_gallery_list_widget.doubleClicked.connect(self.switch_to_single_view)

    def _on_faces_changed(self):
        """Update the UI people input and auto-save IPTC when face labels change."""
        index = self.event_gallery_list_widget.currentIndex()
        if not index.isValid():
            return
        item = self._get_item_from_index(index)
        if not item or not self.current_event_id:
            return

        try:
            self.current_media_id = self.media_repo.ensure_media_exists(
                self.current_event_id, item.img_path, "photo"
            )
            persons = self.person_repo.get_persons_for_media(self.current_media_id)
            self.media_people_input.setText(', '.join(persons))
            # Auto-save changes without showing a confirmation popup
            self.save_media_iptc(silent=True)
        except Exception as e:
            import logging
            logging.warning(f"Error updating faces: {e}")

    def on_gallery_search(self, text):
        """Update proxy model with search text to filter and sort the gallery view."""
        if hasattr(self, 'gallery_search_proxy'):
            self.gallery_search_proxy.setFilterText(text)

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

        
    def layouts(self):
        self.events_layout = QtWidgets.QHBoxLayout()
        self.events_column = QtWidgets.QVBoxLayout()
        self.events_gallery = QtWidgets.QVBoxLayout()
        
        # Right side: Details Scroll Area
        self.media_details_scroll = QtWidgets.QScrollArea()
        self.media_details_scroll.setWidgetResizable(True)
        self.media_details_scroll.setFixedWidth(450)
        self.media_details_scroll.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ccc; border-radius: 4px;")
        
        self.media_details_container = QtWidgets.QWidget()
        self.media_details_form = QtWidgets.QFormLayout()
        self.media_details_container.setLayout(self.media_details_form)
        self.media_details_scroll.setWidget(self.media_details_container)
        
        # Single Save button at the top of the details panel
        self.save_media_btn = QtWidgets.QPushButton("💾 Kaydet")
        self.save_media_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d7d46; color: white; padding: 10px;
                border: none; border-radius: 4px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #3a9d5a; }
        """)
        self.save_media_btn.clicked.connect(self.save_media_iptc)
        self.media_details_form.addRow(self.save_media_btn)
        
        self.events_layout.addLayout(self.events_column, 1)
        self.events_layout.addLayout(self.events_gallery, 3)
        self.events_layout.addWidget(self.media_details_scroll, 1)
        
        # event column
        self.events_column.addWidget(self.event_search)
        self.events_column.addWidget(self.event_card_list_widget)
        # event gallery
        self.events_gallery.addWidget(self.event_gallery_search)
        self.events_gallery.addWidget(self.gallery_stack)  
        # media details
        self.media_details_form_widget()     
        
        self.events_tab.setLayout(self.events_layout)

        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_tab.setLayout(self.settings_layout)

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QTabWidget::pane {
                border: 1px solid #ccc;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background: #e0e0e0;
                color: #333;
                padding: 10px 20px;
                border: 1px solid #ccc;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #000;
            }
            QListView, QListWidget {
                background-color: #ffffff;
                border: 1px solid #ccc;
                color: #222;
                border-radius: 4px;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #bbb;
                color: #222;
                padding: 5px;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #bbb;
                color: #222;
                border-radius: 4px;
            }
            QLabel {
                color: #222;
            }
            QMenuBar {
                background-color: #f0f0f0;
                color: #222;
            }
            QMenuBar::item:selected {
                background-color: #ddd;
            }
            QMenu {
                background-color: #ffffff;
                color: #222;
                border: 1px solid #ccc;
            }
            QMenu::item:selected {
                background-color: #e0e0e0;
            }
            QScrollArea {
                background-color: #f5f5f5;
            }
            QWidget {
                background-color: #f5f5f5;
                color: #222;
            }
        """)



def app():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    app()
