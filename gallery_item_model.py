from PySide6 import QtGui, QtCore
from typing import List
from PIL import Image, ExifTags
from iptcinfo3 import IPTCInfo
import os

class GalleryItem(QtGui.QStandardItem):
    def __init__(self, title, img_path, in_db: bool = False, db_metadata: dict = None):
        super().__init__(title)
        self.img_path = img_path
        self.in_db = in_db
        self.exif_data = {}
        self.iptc_data = {}
        self.is_loaded = False # Flag for background worker
        
        self.setTextAlignment(QtCore.Qt.AlignCenter)
        self.setSizeHint(QtCore.QSize(300, 300))
        self.setToolTip(self.img_path)
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        
        # Store event_id so proxy model can filter by event during search
        self.event_id = str(db_metadata.get('event_id', '')) if db_metadata else None

        # Store DB search rank (set by FTS query; 0 for non-search items)
        self.search_rank = float(db_metadata.get('rank') or 0) if db_metadata else 0.0

        # Pre-populate from DB if available to avoid disk I/O
        if db_metadata:
            self._pop_from_db(db_metadata)
            db_title = db_metadata.get('title')
            if db_title:
                self.setText(db_title)
            
    def _pop_from_db(self, db_metadata):
        """Map database columns back to the display-friendly iptc_data dict."""
        iptc_mapping = {
            'iptc_headline': 'Headline',
            'iptc_caption': 'Caption',
            'iptc_keywords': 'Keywords',
            'iptc_object_name': 'Object Name',
            'iptc_city': 'City',
            'iptc_state': 'State',
            'iptc_country': 'Country',
            'iptc_credit': 'Credit',
            'iptc_source': 'Source',
            'iptc_copyright': 'Copyright',
            'iptc_writer': 'Writer',
            'iptc_byline': 'By-line',
            'iptc_byline_title': 'By-line Title',
            'iptc_date_created': 'Date Created',
            'iptc_category': 'Category',
            'iptc_supplemental_categories': 'Supplemental Categories'
        }
        for db_key, display_name in iptc_mapping.items():
            val = db_metadata.get(db_key)
            if val:
                self.iptc_data[display_name] = str(val)

        # Populate People from FTS person_names aggregation
        pnames = db_metadata.get('person_names', '')
        if pnames:
            self.iptc_data['People'] = pnames

    def load_from_file(self):
        """Heavy I/O: Read EXIF/IPTC from file. Called from background thread."""
        if not self.exif_data:
            self.__read_exif()
        if not self.iptc_data:
            self.__read_iptc()
        self.is_loaded = True

    def __read_exif(self):
        # ... (implementation remains same as before)
        try:
            with Image.open(self.img_path) as img:
                exif = img._getexif()
                if exif is not None:
                    tag_mapping = {
                        'XPTitle': 'Title', 'XPSubject': 'Subject', 'XPRating': 'Rating',
                        'XPKeywords': 'Tags', 'XPComment': 'Comments', 'Rating': 'Rating',
                        'Make': 'Camera Make', 'Model': 'Camera Model', 'LensModel': 'Lens Model',
                        'LensMake': 'Lens Make', 'Software': 'Software', 'DateTime': 'Date/Time',
                        'DateTimeOriginal': 'Date/Time Original', 'DateTimeDigitized': 'Date/Time Digitized',
                        'ExposureTime': 'Shutter Speed', 'FNumber': 'Aperture', 'ISOSpeedRatings': 'ISO',
                        'ISO': 'ISO', 'ExposureProgram': 'Exposure Program', 'ExposureMode': 'Exposure Mode',
                        'ExposureBiasValue': 'Exposure Compensation', 'MeteringMode': 'Metering Mode',
                        'Flash': 'Flash', 'FocalLength': 'Focal Length', 'FocalLengthIn35mmFilm': 'Focal Length (35mm)',
                        'Orientation': 'Orientation', 'XResolution': 'X Resolution', 'YResolution': 'Y Resolution',
                        'ResolutionUnit': 'Resolution Unit', 'ColorSpace': 'Color Space', 'WhiteBalance': 'White Balance',
                        'Artist': 'Artist', 'Copyright': 'Copyright', 'ImageDescription': 'Image Description', 'UserComment': 'User Comment'
                    }
                    for tag, value in exif.items():
                        tag_name = ExifTags.TAGS.get(tag, tag)
                        if tag_name in tag_mapping:
                            if isinstance(value, bytes):
                                try: value = value.decode('utf-16le').strip('\x00')
                                except: pass
                            elif isinstance(value, tuple) and len(value) == 2 and value[1] != 0:
                                if tag_name == 'ExposureTime': value = f"1/{int(value[1]/value[0])}" if value[0] < value[1] else f"{value[0]/value[1]:.1f}s"
                                elif tag_name == 'FNumber': value = f"f/{value[0]/value[1]:.1f}"
                                elif tag_name == 'FocalLength': value = f"{value[0]/value[1]:.1f}mm"
                                else: value = value[0] / value[1]
                            
                            display_name = tag_mapping[tag_name]
                            self.exif_data[display_name] = str(value)
        except: pass
    
    def __read_iptc(self):
        # ... (implementation remains same as before)
        try:
            info = IPTCInfo(self.img_path, force=True)
            iptc_fields = {
                'headline': 'Headline', 'caption/abstract': 'Caption', 'keywords': 'Keywords',
                'object name': 'Object Name', 'city': 'City', 'province/state': 'State',
                'country/primary location name': 'Country', 'credit': 'Credit', 'source': 'Source',
                'copyright notice': 'Copyright', 'writer/editor': 'Writer', 'by-line': 'By-line',
                'by-line title': 'By-line Title', 'date created': 'Date Created', 'category': 'Category',
                'supplemental category': 'Supplemental Categories', 'contact': 'People'
            }
            for iptc_key, display_name in iptc_fields.items():
                try:
                    value = info[iptc_key]
                    if value:
                        if isinstance(value, list):
                            value = ', '.join([v.decode('utf-8') if isinstance(v, bytes) else str(v) for v in value])
                        elif isinstance(value, bytes):
                            value = value.decode('utf-8')
                        self.iptc_data[display_name] = str(value).replace('\x00', '')
                except: continue
        except: pass

class GalleryItemWorker(QtCore.QObject):
    """Signal emitter for the background runnable"""
    finished = QtCore.Signal(GalleryItem, QtGui.QPixmap)

class GalleryItemRunnable(QtCore.QRunnable):
    """Worker that handles one image's heavy lifting"""
    def __init__(self, item):
        super().__init__()
        self.item = item
        self.signals = GalleryItemWorker()

    def run(self):
        # 1. Load metadata if missing
        self.item.load_from_file()
        
        # 2. Generate thumbnail
        pixmap = GalleryItemModel.generate_pixmap(self.item)
        
        # 3. Notify UI
        self.signals.finished.emit(self.item, pixmap)

class GalleryItemModel(QtGui.QStandardItemModel):
    def __init__(self, items: List[GalleryItem]):
        super().__init__()
        # Global placeholder to avoid repeated generation
        self._placeholder = self._make_placeholder()
        self.items = items
        self.setup_model()

    def _make_placeholder(self):
        p = QtGui.QPixmap(150, 150)
        p.fill(QtGui.QColor("#f0f0f0"))
        painter = QtGui.QPainter(p)
        painter.setPen(QtGui.QColor("#999"))
        painter.drawText(p.rect(), QtCore.Qt.AlignCenter, "⏳")
        painter.end()
        return p

    def setup_model(self):
        for item in self.items:
            # Ensure text is white for high contrast
            item.setForeground(QtGui.QColor('#ffffff'))
            item.setIcon(QtGui.QIcon(self._placeholder))
            self.appendRow(item)

    @staticmethod
    def generate_pixmap(item: GalleryItem) -> QtGui.QPixmap:
        """Heavylifting for thumbnail generation"""
        pixmap = QtGui.QPixmap(item.img_path)
        if pixmap.isNull():
            pixmap = QtGui.QPixmap(150, 150)
            pixmap.fill(QtGui.QColor("#ffcccc"))
        else:
            pixmap = pixmap.scaled(150, 150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        if item.in_db:
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            badge_size = 22
            cx, cy = pixmap.width() - badge_size // 2 - 4, badge_size // 2 + 4
            painter.setBrush(QtGui.QColor("#2d7d46"))
            painter.setPen(QtGui.QColor("white"))
            painter.drawEllipse(QtCore.QPoint(cx, cy), badge_size // 2, badge_size // 2)
            font = painter.font(); font.setBold(True); font.setPixelSize(13); painter.setFont(font)
            painter.drawText(QtCore.QRect(cx-11, cy-11, 22, 22), QtCore.Qt.AlignCenter, "\u2713")
            painter.end()
        return pixmap

    def start_loading(self):
        """Actually start the background threads"""
        pool = QtCore.QThreadPool.globalInstance()
        # Limit threads so we don't choke the system
        pool.setMaxThreadCount(max(1, os.cpu_count() // 2)) 
        
        for item in self.items:
            runnable = GalleryItemRunnable(item)
            runnable.signals.finished.connect(self._on_item_loaded)
            pool.start(runnable)

    def _on_item_loaded(self, item, pixmap):
        """Update item with loaded thumbnail"""
        item.setIcon(QtGui.QIcon(pixmap))


class GallerySearchProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text = ""
        self._filter_date = None
        self._filter_event_id = None   # set during search mode to narrow by event

    def setEventFilter(self, event_id):
        """Narrow results to a single event (pass None to show all events)."""
        self._filter_event_id = str(event_id) if event_id is not None else None
        self.invalidateFilter()

    def setFilterText(self, text, filter_date=None):
        self._filter_text = text.strip().lower()
        self._filter_date = filter_date
        self.invalidateFilter()
        if self._filter_text or self._filter_date:
            self.sort(0, QtCore.Qt.DescendingOrder)
        else:
            self.sort(-1)

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._filter_text and not self._filter_date and not self._filter_event_id:
            return True
        
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        item = model.itemFromIndex(index)
        if not item: return False

        if self._filter_event_id:
            if not item.event_id or item.event_id != self._filter_event_id:
                return False

        if self._filter_date:
            item_date = item.iptc_data.get('Date Created')
            if not item_date:
                exif_date_str = item.exif_data.get('Date/Time Original') or item.exif_data.get('Date/Time')
                if exif_date_str:
                    item_date = exif_date_str.replace(":", "").replace("-", "")[:8]
            
            if not item_date or not item_date.startswith(self._filter_date):
                return False

        if not self._filter_text:
            return True

        item_rank = getattr(item, 'search_rank', 0)
        if item_rank > 0:
            return True   # already approved by PostgreSQL FTS
        score = self._calculate_score(item, self._filter_text)
        item.setData(score, QtCore.Qt.UserRole + 1)
        return score > 0
        
    def lessThan(self, left, right):
        if not self._filter_text and not self._filter_date: return left.row() < right.row()
        l_item = self.sourceModel().itemFromIndex(left)
        r_item = self.sourceModel().itemFromIndex(right)
        if not l_item or not r_item: return False
        l_rank = getattr(l_item, 'search_rank', 0) or 0
        r_rank = getattr(r_item, 'search_rank', 0) or 0
        if l_rank or r_rank:
            return l_rank < r_rank   # higher DB rank → shown first (DescendingOrder)
        l_score = l_item.data(QtCore.Qt.UserRole + 1) or 0
        r_score = r_item.data(QtCore.Qt.UserRole + 1) or 0
        return l_score < r_score

    def _calculate_score(self, item, search_text):
        score = 0
        keywords = search_text.split()
        iptc, exif = item.iptc_data, item.exif_data
        
        text_blocks = [
            (iptc.get('People', ''), 10), (item.text(), 8),
            (iptc.get('Headline', ''), 5), (iptc.get('Caption', ''), 4),
            (iptc.get('Keywords', ''), 3),
            (" ".join(str(v) for v in iptc.values()), 1),
            (" ".join(str(v) for v in exif.values()), 0.5)
        ]
        for kw in keywords:
            kw_matched = False
            for text, weight in text_blocks:
                if text and kw in text.lower():
                    score += weight
                    kw_matched = True
            if not kw_matched: return 0
        return score



