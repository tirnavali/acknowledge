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
        self.init_toolbar()
        self.tabWidget()
        self.event_widgets()
        # self.media_details_form_widget()
        self.layouts()

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
        items = self.load_gallery_items(event.id)
        self.gallery_item_model = GalleryItemModel(items)
        self.event_gallery_list_widget.setModel(self.gallery_item_model)
    
    def on_gallery_item_clicked(self, index):
        """Handle gallery item click - print EXIF data to console"""
        item = self.gallery_item_model.itemFromIndex(index)
        if item:
            print("\n" + "="*60)
            print(f"📷 Image: {item.img_path}")
            print("="*60)
            
            if item.exif_data:
                print("\n📋 EXIF Data:")
                for key, value in item.exif_data.items():
                    print(f"  {key}: {value}")
            else:
                print("  No EXIF data available")
            
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
        # Gallery list section
        self.event_gallery_list_widget = QtWidgets.QListView()
        self.event_gallery_list_widget.setMaximumWidth(600)
        self.event_gallery_list_widget.setViewMode(QtWidgets.QListView.IconMode)
        self.event_gallery_list_widget.setGridSize(QtCore.QSize(180, 200))
        self.event_gallery_list_widget.setSpacing(10)
        self.event_gallery_list_widget.setUniformItemSizes(True)
        self.gallery_item_model = GalleryItemModel([])
        self.event_gallery_list_widget.setModel(self.gallery_item_model)
        self.event_gallery_list_widget.setIconSize(QtCore.QSize(150, 150))
        
        # Connect click event to print EXIF data
        self.event_gallery_list_widget.clicked.connect(self.on_gallery_item_clicked)

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
        self.media_tags_input.setMaximumHeight(50)
  
        
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
        self.events_gallery.addWidget(self.event_gallery_list_widget)  
        # media details
        self.media_details_form_widget()     
        
        self.events_tab.setLayout(self.events_layout)

        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_tab.setLayout(self.settings_layout)



def app():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    app()
