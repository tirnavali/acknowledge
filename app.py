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
from single_view_widget import SingleViewWidget
import os

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tirnavali Acknowledge")
        self.setGeometry(100, 100, 1200, 800)
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

    def navigate_next(self):
        index = self.event_gallery_list_widget.currentIndex()
        if not index.isValid():
            next_index = self.gallery_item_model.index(0, 0)
        else:
            row = index.row()
            if row < self.gallery_item_model.rowCount() - 1:
                next_index = self.gallery_item_model.index(row + 1, 0)
            else:
                return # End of list
        
        self.event_gallery_list_widget.setCurrentIndex(next_index)
        self.on_gallery_item_clicked(next_index)

    def navigate_previous(self):
        index = self.event_gallery_list_widget.currentIndex()
        if not index.isValid():
            return
        
        row = index.row()
        if row > 0:
            prev_index = self.gallery_item_model.index(row - 1, 0)
        else:
            return # Start of list
            
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
            # Connect the click signal to a handler
            card.clicked.connect(lambda e=event: self.on_event_card_clicked(e))
            item.setSizeHint(card.sizeHint())
            self.event_card_list_widget.addItem(item)
            self.event_card_list_widget.setItemWidget(item, card)
    
    def load_gallery_items(self, event_id):
        items = []
        event = EventRepository().get_by_id(event_id)
        # Use absolute path to avoid issues with current working directory
        abs_folder_path = os.path.abspath(event.vault_folder_path)
        if not os.path.exists(abs_folder_path):
            return items
            
        for filename in os.listdir(abs_folder_path):
            if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                img_path = os.path.join(abs_folder_path, filename)
                item = GalleryItem(filename, img_path)
                items.append(item)
        return items

    def refresh_events(self):
        """Clear and reload the event list"""
        self.event_card_list_widget.clear()
        self.load_events()
    
    def on_event_card_clicked(self, event):
        """Handle event card click"""
        self.switch_to_grid_view()  # Always switch to grid when a new event is selected
        items = self.load_gallery_items(event.id)
        self.gallery_item_model = GalleryItemModel(items)
        self.event_gallery_list_widget.setModel(self.gallery_item_model)
    
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
        """Handle gallery item click - populate form and update single view"""
        item = self.gallery_item_model.itemFromIndex(index)
        if item:
            # Update single view image
            self.single_view_widget.set_image(item.img_path)
            
            # Clear all fields first to ensure refresh
            self.media_title_input.clear()
            self.media_headline_input.clear()
            self.media_object_name_input.clear()
            self.media_location_input.clear()
            self.media_description_input.clear()
            self.media_tags_input.clear()
            self.media_credit_input.clear()
            self.media_source_input.clear()
            self.media_copyright_input.clear()
            self.media_writer_input.clear()
            self.media_byline_input.clear()
            self.media_byline_title_input.clear()
            self.media_category_input.clear()
            self.media_supplemental_categories_input.clear()
            
            # Populate form fields from EXIF data (priority) or IPTC data (fallback)
            
            # Title
            if 'Title' in item.exif_data:
                self.media_title_input.setPlainText(str(item.exif_data['Title']))
            elif 'Subject' in item.exif_data:
                self.media_title_input.setPlainText(str(item.exif_data['Subject']))
            
            # Date
            self.media_date_input.setDateTime(QtCore.QDateTime.currentDateTime())
            
            # IPTC Fields
            if 'Headline' in item.iptc_data:
                self.media_headline_input.setText(item.iptc_data['Headline'])
            if 'Object Name' in item.iptc_data:
                self.media_object_name_input.setText(item.iptc_data['Object Name'])
            if 'Caption' in item.iptc_data:
                self.media_description_input.setPlainText(item.iptc_data['Caption'])
            if 'Keywords' in item.iptc_data:
                self.media_tags_input.setPlainText(item.iptc_data['Keywords'])
            
            # Location (from IPTC)
            location_parts = []
            if 'City' in item.iptc_data: location_parts.append(item.iptc_data['City'])
            if 'State' in item.iptc_data: location_parts.append(item.iptc_data['State'])
            if 'Country' in item.iptc_data: location_parts.append(item.iptc_data['Country'])
            if location_parts:
                self.media_location_input.setText(', '.join(location_parts))
            
            # Credit & Source
            if 'Credit' in item.iptc_data:
                self.media_credit_input.setText(item.iptc_data['Credit'])
            if 'Source' in item.iptc_data:
                self.media_source_input.setText(item.iptc_data['Source'])
            if 'Copyright' in item.iptc_data:
                self.media_copyright_input.setText(item.iptc_data['Copyright'])
            
            # People
            if 'Writer' in item.iptc_data:
                self.media_writer_input.setText(item.iptc_data['Writer'])
            if 'By-line' in item.iptc_data:
                self.media_byline_input.setText(item.iptc_data['By-line'])
            if 'By-line Title' in item.iptc_data:
                self.media_byline_title_input.setText(item.iptc_data['By-line Title'])
            
            # Categories
            if 'Category' in item.iptc_data:
                self.media_category_input.setText(item.iptc_data['Category'])
            if 'Supplemental Categories' in item.iptc_data:
                self.media_supplemental_categories_input.setText(item.iptc_data['Supplemental Categories'])
            
            # Update date if created date is available
            if 'Date Created' in item.iptc_data:
                # Format is usually YYYYMMDD
                date_str = item.iptc_data['Date Created']
                if len(date_str) == 8:
                    qdate = QtCore.QDate.fromString(date_str, "yyyyMMdd")
                    self.media_date_input.setDate(qdate)


    def event_widgets(self):
        self.event_search = QtWidgets.QLineEdit()
        self.event_search.setPlaceholderText("Ara...")
        self.event_search.setFixedHeight(30)
        self.event_search.setFixedWidth(200)

        self.event_card_list_widget = QtWidgets.QListWidget()
        self.event_card_list_widget.setMaximumWidth(200)
        
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
        
        # Single View
        self.single_view_widget = SingleViewWidget()
        self.single_view_widget.doubleClicked.connect(self.switch_to_grid_view)
        self.single_view_widget.nextRequested.connect(self.navigate_next)
        self.single_view_widget.prevRequested.connect(self.navigate_previous)
        
        self.gallery_stack.addWidget(self.event_gallery_list_widget)
        self.gallery_stack.addWidget(self.single_view_widget)

        self.gallery_item_model = GalleryItemModel([])
        self.event_gallery_list_widget.setModel(self.gallery_item_model)
        
        # Connect click event to print EXIF data
        self.event_gallery_list_widget.clicked.connect(self.on_gallery_item_clicked)
        self.event_gallery_list_widget.doubleClicked.connect(self.switch_to_single_view)

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

        # Create labels and add rows
        self.media_details_form.addRow(QtWidgets.QLabel("📝 Title:"), self.media_title_input)
        self.media_details_form.addRow(QtWidgets.QLabel("� Headline:"), self.media_headline_input)
        self.media_details_form.addRow(QtWidgets.QLabel("🆔 Object Name:"), self.media_object_name_input)
        self.media_details_form.addRow(QtWidgets.QLabel("📅 Date:"), self.media_date_input)
        self.media_details_form.addRow(QtWidgets.QLabel("📍 Location:"), self.media_location_input)
        self.media_details_form.addRow(QtWidgets.QLabel("📄 Description:"), self.media_description_input)
        self.media_details_form.addRow(QtWidgets.QLabel("🏷️ Tags:"), self.media_tags_input)
        
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
        self.media_details_scroll.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333; border-radius: 4px;")
        
        self.media_details_container = QtWidgets.QWidget()
        self.media_details_form = QtWidgets.QFormLayout()
        self.media_details_container.setLayout(self.media_details_form)
        self.media_details_scroll.setWidget(self.media_details_container)
        
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
                background-color: #121212;
            }
            QTabWidget::pane {
                border: 1px solid #333;
                background-color: #121212;
            }
            QTabBar::tab {
                background: #2a2a2a;
                color: #888;
                padding: 10px 20px;
                border: 1px solid #333;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3a3a3a;
                color: white;
            }
            QListView, QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #333;
                color: #e0e0e0;
                border-radius: 4px;
            }
            QLineEdit {
                background-color: #2a2a2a;
                border: 1px solid #444;
                color: white;
                padding: 5px;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: #2a2a2a;
                border: 1px solid #444;
                color: #e0e0e0;
                border-radius: 4px;
            }
            QMenuBar {
                background-color: #1e1e1e;
                color: #ccc;
            }
            QMenuBar::item:selected {
                background-color: #333;
            }
            QMenu {
                background-color: #1e1e1e;
                color: #ccc;
                border: 1px solid #333;
            }
            QMenu::item:selected {
                background-color: #333;
            }
        """)



def app():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    app()
