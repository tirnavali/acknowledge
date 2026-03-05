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
    
    def on_gallery_item_clicked(self, index):
        """Handle gallery item click - populate form and update single view"""
        item = self.gallery_item_model.itemFromIndex(index)
        if item:
            # Update single view image
            self.single_view_widget.set_image(item.img_path)
            print("\n" + "="*60)
            print(f"📷 Image: {item.img_path}")
            print("="*60)
            
            # Clear all fields first to ensure refresh
            self.media_title_input.clear()
            self.media_location_input.clear()
            self.media_description_input.clear()
            self.media_tags_input.clear()
            
            # Print EXIF Data independently
            print("\n" + "─"*60)
            print("📋 EXIF DATA:")
            print("─"*60)
            if item.exif_data:
                for key, value in item.exif_data.items():
                    print(f"  {key}: {value}")
            else:
                print("  No EXIF data available")
            
            # Print IPTC Data independently
            print("\n" + "─"*60)
            print("📰 IPTC DATA:")
            print("─"*60)
            if item.iptc_data:
                for key, value in item.iptc_data.items():
                    print(f"  {key}: {value}")
            else:
                print("  No IPTC data available")
            
            print("\n" + "─"*60)
            print("🔧 POPULATING FORM FIELDS:")
            print("─"*60)
            
            # Populate form fields from EXIF data (priority) or IPTC data (fallback)
            # Title (from Windows XP Title tag or IPTC Headline)
            if 'Title' in item.exif_data:
                title_text = str(item.exif_data['Title'])
                print(f"  Title (from EXIF): {title_text}")
                self.media_title_input.setPlainText(title_text)
            elif 'Subject' in item.exif_data:
                subject_text = str(item.exif_data['Subject'])
                print(f"  Title (from EXIF Subject): {subject_text}")
                self.media_title_input.setPlainText(subject_text)
            elif 'Headline' in item.iptc_data:
                headline_text = str(item.iptc_data['Headline'])
                print(f"  Title (from IPTC Headline): {headline_text}")
                self.media_title_input.setPlainText(headline_text)
            elif 'Object Name' in item.iptc_data:
                object_name_text = str(item.iptc_data['Object Name'])
                print(f"  Title (from IPTC Object Name): {object_name_text}")
                self.media_title_input.setPlainText(object_name_text)
            
            # Date - Note: PIL EXIF doesn't include date fields in the current implementation
            # You may need to extend __read_exif in gallery_item_model.py to include DateTimeOriginal
            self.media_date_input.setDateTime(QtCore.QDateTime.currentDateTime())
            
            # Location (from IPTC)
            if 'City' in item.iptc_data or 'State' in item.iptc_data or 'Country' in item.iptc_data:
                location_parts = []
                if 'City' in item.iptc_data:
                    location_parts.append(item.iptc_data['City'])
                if 'State' in item.iptc_data:
                    location_parts.append(item.iptc_data['State'])
                if 'Country' in item.iptc_data:
                    location_parts.append(item.iptc_data['Country'])
                location_text = ', '.join(location_parts)
                print(f"  Location (from IPTC): {location_text}")
                self.media_location_input.setText(location_text)
            
            # Description (from EXIF Subject or IPTC Caption)
            if 'Subject' in item.exif_data:
                description_text = str(item.exif_data['Subject'])
                print(f"  Description (from EXIF Subject): {description_text}")
                self.media_description_input.setPlainText(description_text)
            elif 'Caption' in item.iptc_data:
                caption_text = str(item.iptc_data['Caption'])
                print(f"  Description (from IPTC Caption): {caption_text}")
                self.media_description_input.setPlainText(caption_text)
            
            # Tags (from EXIF Keywords or IPTC Keywords)
            if 'Tags' in item.exif_data:
                tags_text = str(item.exif_data['Tags'])
                print(f"  Tags (from EXIF): {tags_text}")
                self.media_tags_input.setPlainText(tags_text)
            elif 'Keywords' in item.iptc_data:
                keywords_text = str(item.iptc_data['Keywords'])
                print(f"  Tags (from IPTC Keywords): {keywords_text}")
                self.media_tags_input.setPlainText(keywords_text)
            
            # Force widget updates
            self.media_title_input.update()
            self.media_description_input.update()
            self.media_tags_input.update()
            
            print("="*60 + "\n")


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
        
        self.media_tags_input = QtWidgets.QTextEdit()
        self.media_tags_input.setFixedWidth(fixed_width)
        self.media_tags_input.setPlaceholderText("Tags")
        self.media_tags_input.setMaximumHeight(100)
  
        
        # Create labels with icons only (tooltips on hover)
        style = self.style()
        
        # Title label with icon
        title_label = QtWidgets.QLabel("📝")
        title_label.setToolTip("Title - The name or title of the media")
        
        # Date label with icon
        date_label = QtWidgets.QLabel("📅")
        date_label.setToolTip("Date - When the media was created or captured")
        
        # Location label with icon
        location_label = QtWidgets.QLabel("📍")
        location_label.setToolTip("Location - Where the media was captured")
        
        # Description label with icon
        description_label = QtWidgets.QLabel("📄")
        description_label.setToolTip("Description - Detailed description of the media content")
        
        # Tags label with icon
        tags_label = QtWidgets.QLabel("🏷️")
        tags_label.setToolTip("Tags - Categories or labels for organizing media")
        
        # Add rows to form layout (label, input)
        self.media_details_form.addRow(title_label, self.media_title_input)
        self.media_details_form.addRow(date_label, self.media_date_input)
        self.media_details_form.addRow(location_label, self.media_location_input)
        self.media_details_form.addRow(description_label, self.media_description_input)
        self.media_details_form.addRow(tags_label, self.media_tags_input)
        
        # Optional: Add some styling
        self.media_details_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.media_details_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.media_details_form.setHorizontalSpacing(5)  # Reduce horizontal space between label and input
        self.media_details_form.setVerticalSpacing(2)    # Compact vertical spacing

        
    def layouts(self):
        self.events_layout = QtWidgets.QHBoxLayout()
        self.events_column = QtWidgets.QVBoxLayout()
        self.events_gallery = QtWidgets.QVBoxLayout()
        
        # Create a container widget for the form with max height
        self.media_details_container = QtWidgets.QWidget()
        self.media_details_container.setMaximumHeight(300)  # Set max height
        self.media_details_container.setMaximumWidth(500)
        self.media_details_form = QtWidgets.QFormLayout()
        self.media_details_container.setLayout(self.media_details_form)
        
        self.events_layout.addLayout(self.events_column)
        self.events_layout.addLayout(self.events_gallery)
        self.events_layout.addWidget(self.media_details_container, alignment=QtCore.Qt.AlignTop)  # Align to top
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
