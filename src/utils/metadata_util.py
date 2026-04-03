import os
from PIL import Image, ExifTags
from iptcinfo3 import IPTCInfo
import logging

logger = logging.getLogger(__name__)

def extract_metadata(file_path: str) -> dict:
    """
    Extracts EXIF and IPTC metadata from an image file.
    Returns a dictionary with standardized keys:
    - 'Title', 'Headline', 'Caption', 'Keywords', 'Object Name', 'City', 'State', 
      'Country', 'Credit', 'Source', 'Copyright', 'Writer', 'By-line', 
      'By-line Title', 'Date Created', 'Category', 'Supplemental Categories'
    """
    metadata = {
        "Title": "", "Headline": "", "Caption": "", "Keywords": "", 
        "Object Name": "", "City": "", "State": "", "Country": "", 
        "Credit": "", "Source": "", "Copyright": "", "Writer": "", 
        "By-line": "", "By-line Title": "", "Date Created": "", 
        "Category": "", "Supplemental Categories": ""
    }

    if not os.path.exists(file_path):
        return metadata

    # 1. READ EXIF
    try:
        with Image.open(file_path) as img:
            exif = img._getexif()
            if exif is not None:
                tag_mapping = {
                    'XPTitle': 'Title', 'XPSubject': 'Subject', 'XPRating': 'Rating',
                    'XPKeywords': 'Tags', 'XPComment': 'Comments', 'Rating': 'Rating',
                    'ImageDescription': 'Caption', 'Copyright': 'Copyright', 'Artist': 'Writer'
                }
                for tag, value in exif.items():
                    tag_name = ExifTags.TAGS.get(tag, tag)
                    if tag_name in tag_mapping:
                        if isinstance(value, bytes):
                            try: value = value.decode('utf-16le').strip('\x00')
                            except: pass
                        display_name = tag_mapping[tag_name]
                        if display_name == 'Title' and not metadata['Title']:
                            metadata['Title'] = str(value)
                        elif display_name == 'Caption' and not metadata['Caption']:
                            metadata['Caption'] = str(value)
                        elif display_name == 'Copyright' and not metadata['Copyright']:
                            metadata['Copyright'] = str(value)
                        elif display_name == 'Writer' and not metadata['Writer']:
                            metadata['Writer'] = str(value)
    except Exception as e:
        logger.debug(f"EXIF extraction error for {file_path}: {e}")

    # 2. READ IPTC (Takes precedence for fields it covers)
    try:
        # force=True avoids 'IPTC data not found' errors in some cases
        info = IPTCInfo(file_path, force=True)
        iptc_fields = {
            'headline': 'Headline', 'caption/abstract': 'Caption', 'keywords': 'Keywords',
            'object name': 'Object Name', 'city': 'City', 'province/state': 'State',
            'country/primary location name': 'Country', 'credit': 'Credit', 'source': 'Source',
            'copyright notice': 'Copyright', 'writer/editor': 'Writer', 'by-line': 'By-line',
            'by-line title': 'By-line Title', 'date created': 'Date Created', 'category': 'Category',
            'supplemental category': 'Supplemental Categories'
        }
        for iptc_key, display_name in iptc_fields.items():
            try:
                value = info[iptc_key]
                if value:
                    if isinstance(value, list):
                        value = ', '.join([v.decode('utf-8') if isinstance(v, bytes) else str(v) for v in value])
                    elif isinstance(value, bytes):
                        value = value.decode('utf-8')
                    
                    val_str = str(value).replace('\x00', '').strip()
                    if val_str:
                        metadata[display_name] = val_str
            except: continue
    except Exception as e:
        logger.debug(f"IPTC extraction error for {file_path}: {e}")

    return metadata
