from PySide6 import QtGui, QtCore
from typing import List
from PIL import Image, ExifTags
import os

class GalleryItem(QtGui.QStandardItem):
    def __init__(self, title, img_path):
        super().__init__(title)
        self.img_path = img_path
        self.exif_data = {}
        self.setTextAlignment(QtCore.Qt.AlignCenter)
        self.setSizeHint(QtCore.QSize(300, 300))
        self.setToolTip(self.img_path)
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.__read_exif()
    
    def __str__(self):
        return self.text()

    def __read_exif(self):
        try:
            with Image.open(self.img_path) as img:
                exif = img._getexif()
                if exif is not None:
                    # Specific tags mapping (including Windows XP tags)
                    tag_mapping = {
                        'XPTitle': 'Title',
                        'XPSubject': 'Subject',
                        'XPRating': 'Rating',
                        'XPKeywords': 'Tags',
                        'XPComment': 'Comments',
                        'Rating': 'Rating'
                    }
                    
                    for tag, value in exif.items():
                        tag_name = ExifTags.TAGS.get(tag, tag)
                        if tag_name in tag_mapping:
                            # Handle XP tags which are usually stored as UTF-16LE bytes
                            if isinstance(value, bytes):
                                try:
                                    value = value.decode('utf-16le').strip('\x00')
                                except:
                                    pass
                            
                            display_name = tag_mapping[tag_name]
                            self.exif_data[display_name] = str(value)
                    
                    # Create display string for requested fields
                    display_fields = ['Title', 'Subject', 'Rating', 'Tags', 'Comments']
                    desc_parts = []
                    for field in display_fields:
                        if field in self.exif_data:
                            desc_parts.append(f"{field}: {self.exif_data[field]}")
                    
                    if desc_parts:
                        self.setText("\n".join(desc_parts))
                    else:
                        self.setText(os.path.basename(self.img_path))
        except Exception as e:
            print(f"Error reading EXIF for {self.img_path}: {e}")
            self.setText(os.path.basename(self.img_path))

class GalleryItemModel(QtGui.QStandardItemModel):
    def __init__(self, items: List[GalleryItem]):
        super().__init__()
        self.items = items
        self.setup_model()

    def setup_model(self):
        for item in self.items:
            icon = QtGui.QIcon(item.img_path)
            item.setIcon(icon)
            self.appendRow(item)


