import sys, os  
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtGui import QAction

from event_card_widget import EventCardWidget
from gallery_item_model import GalleryItemModel, GalleryItem
from sqlalchemy import text
from src.database import SessionLocal, Base, engine
import src.models
from dotenv import load_dotenv
import add_event_window
from src.repositories.event_repository import EventRepository

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tirnavali Acknowledge")
        self.setGeometry(100, 100, 800, 600)
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
        
        with SessionLocal() as db:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            db.commit()

        Base.metadata.create_all(bind=engine)
        print("✅ Veritabanı tabloları hazır.")
    
    def UI(self):
        self.init_toolbar()
        self.tabWidget()
        self.event_widgets()
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
        self.add_event_win = add_event_window.AddEvent()


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

    def fetch_gallery_items(self, folder_path):
        items = []
        # Use absolute path to avoid issues with current working directory
        abs_folder_path = os.path.abspath(folder_path)
        if not os.path.exists(abs_folder_path):
            return items
            
        for filename in os.listdir(abs_folder_path):
            if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                img_path = os.path.join(abs_folder_path, filename)
                item = GalleryItem(filename, img_path)
                items.append(item)
        return items

    def event_widgets(self):
        self.event_search = QtWidgets.QLineEdit()
        self.event_search.setPlaceholderText("Ara...")
        self.event_search.setFixedHeight(30)
        self.event_search.setFixedWidth(200)

        self.event_card_list_widget = QtWidgets.QListWidget()
        self.event_card_list_widget.setMaximumWidth(200)
        
        # Add a custom item to the list widget
        events = self.fetch_events()
        for i in events:
            item = QtWidgets.QListWidgetItem(self.event_card_list_widget)
            card = EventCardWidget(i.name, i.event_date)
            item.setSizeHint(card.sizeHint())
            self.event_card_list_widget.addItem(item)
            self.event_card_list_widget.setItemWidget(item, card)
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
        self.gallery_item_model = GalleryItemModel(self.fetch_gallery_items(f"{self.media_vault_path}/event_00001/"))
        self.event_gallery_list_widget.setModel(self.gallery_item_model)
        self.event_gallery_list_widget.setIconSize(QtCore.QSize(150, 150))

        
    def layouts(self):
        self.events_layout = QtWidgets.QHBoxLayout()
        self.events_column = QtWidgets.QVBoxLayout()
        self.events_gallery = QtWidgets.QVBoxLayout()
        
        self.events_layout.addLayout(self.events_column)
        self.events_layout.addLayout(self.events_gallery)
        # event column
        self.events_column.addWidget(self.event_search)
        self.events_column.addWidget(self.event_card_list_widget)
        # event gallery
        self.events_gallery.addWidget(self.event_gallery_search)
        self.events_gallery.addWidget(self.event_gallery_list_widget)       
       
       
        
        self.events_tab.setLayout(self.events_layout)

        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_tab.setLayout(self.settings_layout)



def app():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    app()
