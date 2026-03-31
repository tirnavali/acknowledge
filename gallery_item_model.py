from PySide6 import QtGui, QtCore
from typing import List
from PIL import Image, ExifTags
from iptcinfo3 import IPTCInfo
import os

class GalleryItem(QtGui.QStandardItem):
    def __init__(self, title, img_path, in_db: bool = False):
        super().__init__(title)
        self.img_path = img_path
        self.in_db = in_db
        self.exif_data = {}
        self.iptc_data = {}
        self.setTextAlignment(QtCore.Qt.AlignCenter)
        self.setSizeHint(QtCore.QSize(300, 300))
        self.setToolTip(self.img_path)
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.__read_exif()
        self.__read_iptc()
    
    def __str__(self):
        return self.text()

    def __read_exif(self):
        try:
            with Image.open(self.img_path) as img:
                exif = img._getexif()
                if exif is not None:
                    # Comprehensive EXIF tags mapping
                    tag_mapping = {
                        # Windows XP tags
                        'XPTitle': 'Title',
                        'XPSubject': 'Subject',
                        'XPRating': 'Rating',
                        'XPKeywords': 'Tags',
                        'XPComment': 'Comments',
                        'Rating': 'Rating',
                        
                        # Camera information
                        'Make': 'Camera Make',
                        'Model': 'Camera Model',
                        'LensModel': 'Lens Model',
                        'LensMake': 'Lens Make',
                        'Software': 'Software',
                        
                        # Date/Time
                        'DateTime': 'Date/Time',
                        'DateTimeOriginal': 'Date/Time Original',
                        'DateTimeDigitized': 'Date/Time Digitized',
                        
                        # Exposure settings
                        'ExposureTime': 'Shutter Speed',
                        'FNumber': 'Aperture',
                        'ISOSpeedRatings': 'ISO',
                        'ISO': 'ISO',
                        'ExposureProgram': 'Exposure Program',
                        'ExposureMode': 'Exposure Mode',
                        'ExposureBiasValue': 'Exposure Compensation',
                        'MeteringMode': 'Metering Mode',
                        
                        # Flash
                        'Flash': 'Flash',
                        
                        # Focal length
                        'FocalLength': 'Focal Length',
                        'FocalLengthIn35mmFilm': 'Focal Length (35mm)',
                        
                        # Image properties
                        'Orientation': 'Orientation',
                        'XResolution': 'X Resolution',
                        'YResolution': 'Y Resolution',
                        'ResolutionUnit': 'Resolution Unit',
                        'ColorSpace': 'Color Space',
                        'WhiteBalance': 'White Balance',
                        
                        # GPS
                        'GPSInfo': 'GPS Info',
                        'GPSLatitude': 'GPS Latitude',
                        'GPSLongitude': 'GPS Longitude',
                        'GPSAltitude': 'GPS Altitude',
                        
                        # Other
                        'Artist': 'Artist',
                        'Copyright': 'Copyright',
                        'ImageDescription': 'Image Description',
                        'UserComment': 'User Comment'
                    }
                    
                    for tag, value in exif.items():
                        tag_name = ExifTags.TAGS.get(tag, tag)
                        if tag_name in tag_mapping:
                            # Handle XP tags which are usually stored as UTF-16LE bytes
                            if isinstance(value, bytes):
                                try:
                                    value = value.decode('utf-16le').strip('\x00')
                                except:
                                    try:
                                        value = value.decode('utf-8').strip('\x00')
                                    except:
                                        pass
                            
                            # Handle tuple values (like FNumber, ExposureTime)
                            elif isinstance(value, tuple) and len(value) == 2:
                                # Convert rational numbers (numerator, denominator)
                                if value[1] != 0:
                                    if tag_name == 'ExposureTime':
                                        # Format as fraction for shutter speed
                                        if value[0] < value[1]:
                                            value = f"1/{int(value[1]/value[0])}"
                                        else:
                                            value = f"{value[0]/value[1]:.1f}s"
                                    elif tag_name == 'FNumber':
                                        # Format as f-stop
                                        value = f"f/{value[0]/value[1]:.1f}"
                                    elif tag_name == 'FocalLength':
                                        # Format as mm
                                        value = f"{value[0]/value[1]:.1f}mm"
                                    else:
                                        value = value[0] / value[1]
                            
                            # Skip GPS Info (it's a complex dict, handle separately if needed)
                            if tag_name == 'GPSInfo':
                                continue
                            
                            display_name = tag_mapping[tag_name]
                            self.exif_data[display_name] = str(value)
                    
                    self.setText(os.path.basename(self.img_path))
        except Exception as e:
            print(f"Error reading EXIF for {self.img_path}: {e}")
            self.setText(os.path.basename(self.img_path))
    
    def __read_iptc(self):
        """Read IPTC metadata from image"""
        try:
            info = IPTCInfo(self.img_path, force=True)
            
            # Common IPTC fields
            iptc_fields = {
                'headline': 'Headline',
                'caption/abstract': 'Caption',
                'keywords': 'Keywords',
                'object name': 'Object Name',
                'city': 'City',
                'province/state': 'State',
                'country/primary location name': 'Country',
                'credit': 'Credit',
                'source': 'Source',
                'copyright notice': 'Copyright',
                'writer/editor': 'Writer',
                'by-line': 'By-line',
                'by-line title': 'By-line Title',
                'date created': 'Date Created',
                'category': 'Category',
                'supplemental category': 'Supplemental Categories',
                'contact': 'People'
            }
            
            for iptc_key, display_name in iptc_fields.items():
                try:
                    # IPTCInfo uses dictionary-style access, not .get()
                    value = info[iptc_key]
                    if value:
                        def decode_bytes(v):
                            if isinstance(v, bytes):
                                try:
                                    return v.decode('utf-8')
                                except:
                                    try:
                                        return v.decode('latin-1')
                                    except:
                                        return str(v)
                            return str(v)

                        # Handle list values (like keywords)
                        if isinstance(value, list):
                            value = ', '.join([decode_bytes(v) for v in value])
                        # Handle single bytes
                        elif isinstance(value, bytes):
                            value = decode_bytes(value)
                        
                        if value and str(value).strip():
                            self.iptc_data[display_name] = str(value).replace('\x00', '')
                except (KeyError, AttributeError):
                    # Field doesn't exist in this image
                    continue
        
        except Exception as e:
            print(f"Error reading IPTC for {self.img_path}: {e}")

class GalleryItemModel(QtGui.QStandardItemModel):
    def __init__(self, items: List[GalleryItem]):
        super().__init__()
        self.items = items
        self.setup_model()

    def setup_model(self):
        for item in self.items:
            icon = QtGui.QIcon(self._make_icon(item))
            item.setIcon(icon)
            self.appendRow(item)

    def _make_icon(self, item: GalleryItem) -> QtGui.QPixmap:
        """Return thumbnail pixmap, with a green badge if the item is in DB."""
        pixmap = QtGui.QPixmap(item.img_path)
        if pixmap.isNull():
            pixmap = QtGui.QPixmap(150, 150)
            pixmap.fill(QtGui.QColor("#e0e0e0"))
        else:
            pixmap = pixmap.scaled(150, 150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        if item.in_db:
            # Draw a small green circle badge in the top-right corner
            badge_size = 22
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            cx = pixmap.width() - badge_size // 2 - 4
            cy = badge_size // 2 + 4
            painter.setBrush(QtGui.QColor("#2d7d46"))
            painter.setPen(QtGui.QColor("white"))
            painter.drawEllipse(QtCore.QPoint(cx, cy), badge_size // 2, badge_size // 2)
            painter.setPen(QtGui.QColor("white"))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(13)
            painter.setFont(font)
            painter.drawText(
                QtCore.QRect(cx - badge_size // 2, cy - badge_size // 2, badge_size, badge_size),
                QtCore.Qt.AlignCenter,
                "\u2713"
            )
            painter.end()

        return pixmap


class GallerySearchProxyModel(QtCore.QSortFilterProxyModel):
    """
    Filters gallery items based on search text, matching against IPTC and EXIF data.
    Supports multi-keyword 'AND' searches and ranks by relevance (score).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text = ""
    
    def setFilterText(self, text):
        self._filter_text = text.strip().lower()
        self.invalidateFilter()
        if self._filter_text:
            self.sort(0, QtCore.Qt.DescendingOrder)
        else:
            self.sort(-1) # Revert to original order
            
    def filterAcceptsRow(self, source_row, source_parent):
        if not self._filter_text:
            return True
            
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        item = model.itemFromIndex(index)
        
        if not item:
            return False
            
        score = self._calculate_score(item, self._filter_text)
        item.setData(score, QtCore.Qt.UserRole + 1)
        return score > 0
        
    def lessThan(self, left, right):
        if not self._filter_text:
            return left.row() < right.row()
            
        left_item = self.sourceModel().itemFromIndex(left)
        right_item = self.sourceModel().itemFromIndex(right)
        
        if not left_item or not right_item:
            return False
            
        left_score = left_item.data(QtCore.Qt.UserRole + 1) or 0
        right_score = right_item.data(QtCore.Qt.UserRole + 1) or 0
        
        return left_score < right_score

    def _calculate_score(self, item, search_text):
        score = 0
        keywords = search_text.split()
        
        iptc = item.iptc_data
        exif = item.exif_data
        
        # Weights: 
        # People (contact/persons) -> highest 
        # Headline/Caption -> high
        # File name/tags -> medium
        # EXIF metadata -> lowest
        text_blocks = [
            (iptc.get('People', ''), 10),
            (iptc.get('Headline', ''), 5),
            (iptc.get('Caption', ''), 4),
            (iptc.get('Keywords', ''), 3),
            (item.text(), 2),
            (" ".join(str(v) for v in iptc.values()), 1),
            (" ".join(str(v) for v in exif.values()), 0.5)
        ]
        
        for kw in keywords:
            kw_matched = False
            for text, weight in text_blocks:
                if text and kw in text.lower():
                    score += weight
                    kw_matched = True
            
            # AND logic: All keywords must be found somewhere in the item
            if not kw_matched:
                return 0
                
        return score


