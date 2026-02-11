from PySide6 import QtGui, QtCore
from typing import List
from PIL import Image, ExifTags
from iptcinfo3 import IPTCInfo
import os

class GalleryItem(QtGui.QStandardItem):
    def __init__(self, title, img_path):
        super().__init__(title)
        self.img_path = img_path
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
                'supplemental category': 'Supplemental Categories'
            }
            
            for iptc_key, display_name in iptc_fields.items():
                try:
                    # IPTCInfo uses dictionary-style access, not .get()
                    value = info[iptc_key]
                    if value:
                        # Handle list values (like keywords)
                        if isinstance(value, list):
                            value = ', '.join([str(v) for v in value])
                        # Handle bytes
                        elif isinstance(value, bytes):
                            try:
                                value = value.decode('utf-8')
                            except:
                                value = str(value)
                        
                        if value and str(value).strip():
                            self.iptc_data[display_name] = str(value)
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
            icon = QtGui.QIcon(item.img_path)
            item.setIcon(icon)
            self.appendRow(item)


