"""
folder_scanner_util.py — Cross-platform directory scanning, date parsing, and naming utilities.
Supports Windows, macOS, and Linux.
"""

import os
import re
import unicodedata
import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
from PIL import Image

from src.utils.document_util import DOCUMENT_EXTS
from src.utils.pdf_util import PDF_EXTS
from src.utils.video_util import VIDEO_EXTS

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
ALL_SUPPORTED_EXTS = IMAGE_EXTS | DOCUMENT_EXTS | PDF_EXTS | VIDEO_EXTS

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


class NamingTemplate(str, Enum):
    YEAR_PREFIX = "year_prefix"          # "2024 Divan Toplantısı"
    YEAR_SUFFIX = "year_suffix"          # "Divan Toplantısı (2024)"
    FULL_DATE_PREFIX = "full_date"       # "01.01.2024 Divan Toplantısı"
    CLEAN_ONLY = "clean_only"            # "Divan Toplantısı"
    ORIGINAL = "original"                # "01.01.2024 divan toplantısı"


def normalize_unicode(text: str) -> str:
    """Normalize text to NFC (resolves macOS decomposed NFD unicode characters)."""
    if not text:
        return ""
    return unicodedata.normalize("NFC", text).strip()


def sanitize_folder_name(name: str) -> str:
    """
    Sanitizes folder name for cross-platform filesystem safety (Windows & macOS/Linux).
    - Removes invalid characters: < > : " / \\ | ? * and control chars.
    - Strips leading/trailing spaces and dots (illegal on Windows).
    - Avoids Windows reserved names (CON, PRN, AUX, NUL, etc.).
    """
    clean = normalize_unicode(name)
    # Replace illegal characters with underscore
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', clean)
    # Replace consecutive spaces or underscores
    clean = re.sub(r'[\s_]+', '_', clean).strip('. _')
    if not clean or clean.upper() in WINDOWS_RESERVED_NAMES:
        clean = f"folder_{clean}" if clean else "event_folder"
    return clean


def parse_date_and_name_from_folder(folder_name: str) -> Tuple[Optional[datetime.datetime], str]:
    """
    Extracts date (if present) and clean title from folder name.
    Supports formats:
    - DD.MM.YYYY (e.g. '01.01.2024 Divan Toplantısı', '15-05-2024 Toplantı')
    - YYYY.MM.DD or YYYY-MM-DD (e.g. '2024.01.01 Divan Toplantısı')
    - YYYY (e.g. '2024 Divan Toplantısı', 'Divan Toplantısı 2024')
    
    Returns:
        (datetime_obj or None, clean_event_name)
    """
    name = normalize_unicode(folder_name)
    clean_title = name
    parsed_date = None

    # 1. Format: DD.MM.YYYY or DD-MM-YYYY or DD_MM_YYYY
    match_dmy = re.search(r'(?:\b|^)(\d{1,2})[.\-_/](\d{1,2})[.\-_/](\d{4})(?:\b|$)', name)
    if match_dmy:
        d, m, y = map(int, match_dmy.groups())
        try:
            parsed_date = datetime.datetime(y, m, d, 12, 0)
            clean_title = name.replace(match_dmy.group(0), "").strip(" .-_/[]()")
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            return parsed_date, clean_title or name
        except ValueError:
            pass

    # 2. Format: YYYY.MM.DD or YYYY-MM-DD
    match_ymd = re.search(r'(?:\b|^)(\d{4})[.\-_/](\d{1,2})[.\-_/](\d{1,2})(?:\b|$)', name)
    if match_ymd:
        y, m, d = map(int, match_ymd.groups())
        try:
            parsed_date = datetime.datetime(y, m, d, 12, 0)
            clean_title = name.replace(match_ymd.group(0), "").strip(" .-_/[]()")
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            return parsed_date, clean_title or name
        except ValueError:
            pass

    # 3. Format: Year prefix or suffix (1900-2099)
    match_year = re.search(r'(?:\b|^)(19\d{2}|20\d{2})(?:\b|$)', name)
    if match_year:
        y = int(match_year.group(1))
        parsed_date = datetime.datetime(y, 1, 1, 12, 0)
        # Keep clean title without raw year if needed
        clean_title = name.replace(match_year.group(0), "").strip(" .-_/[]()")
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
        return parsed_date, clean_title or name

    return None, clean_title


def detect_earliest_file_date(folder_path: str) -> Optional[datetime.datetime]:
    """Scans media files in a folder for the earliest EXIF/filesystem date."""
    if not os.path.exists(folder_path):
        return None

    earliest_time = None
    try:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if not os.path.isfile(file_path):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALL_SUPPORTED_EXTS:
                continue

            # Check EXIF for images
            if ext in IMAGE_EXTS:
                try:
                    with Image.open(file_path) as img:
                        exif = img._getexif()
                        if exif:
                            dt_str = exif.get(36867) or exif.get(306) # DateTimeOriginal or DateTime
                            if dt_str:
                                dt = datetime.datetime.strptime(dt_str[:19], "%Y:%m:%d %H:%M:%S")
                                ts = dt.timestamp()
                                if earliest_time is None or ts < earliest_time:
                                    earliest_time = ts
                except Exception:
                    pass

            # Fallback to filesystem mtime
            try:
                ts = os.path.getmtime(file_path)
                if earliest_time is None or ts < earliest_time:
                    earliest_time = ts
            except Exception:
                pass
    except Exception:
        pass

    if earliest_time:
        return datetime.datetime.fromtimestamp(earliest_time)
    return None


def format_event_name(
    original_folder_name: str,
    clean_title: str,
    event_date: Optional[datetime.datetime],
    template: NamingTemplate = NamingTemplate.YEAR_PREFIX,
) -> str:
    """Formats the target event name according to the selected template."""
    clean = normalize_unicode(clean_title)
    if not clean:
        clean = normalize_unicode(original_folder_name)

    if template == NamingTemplate.ORIGINAL:
        return normalize_unicode(original_folder_name)

    if not event_date:
        return clean

    year_str = str(event_date.year)
    date_str = event_date.strftime("%d.%m.%Y")

    if template == NamingTemplate.YEAR_PREFIX:
        # Check if year is already leading
        if clean.startswith(year_str):
            return clean
        return f"{year_str} {clean}".strip()

    elif template == NamingTemplate.YEAR_SUFFIX:
        # Check if year is already trailing in parentheses
        if clean.endswith(f"({year_str})"):
            return clean
        return f"{clean} ({year_str})".strip()

    elif template == NamingTemplate.FULL_DATE_PREFIX:
        if clean.startswith(date_str):
            return clean
        return f"{date_str} {clean}".strip()

    elif template == NamingTemplate.CLEAN_ONLY:
        return clean

    return clean


@dataclass
class ScannedEventFolder:
    """Represents a discovered event subfolder."""
    folder_path: str
    original_name: str
    clean_name: str
    event_date: datetime.datetime
    target_name: str
    photo_count: int = 0
    pdf_count: int = 0
    doc_count: int = 0
    video_count: int = 0
    media_files: List[str] = field(default_factory=list)
    is_selected: bool = True
    status: str = "Hazır"
    collision_event_id: Optional[str] = None

    @property
    def total_media_count(self) -> int:
        return self.photo_count + self.pdf_count + self.doc_count + self.video_count

    @property
    def has_media(self) -> bool:
        return self.total_media_count > 0


def scan_subfolders(
    root_folder: str,
    template: NamingTemplate = NamingTemplate.YEAR_PREFIX,
) -> List[ScannedEventFolder]:
    """
    Scans direct subdirectories under root_folder and compiles ScannedEventFolder list.
    """
    if not os.path.exists(root_folder) or not os.path.isdir(root_folder):
        return []

    results: List[ScannedEventFolder] = []
    root_path = os.path.normpath(root_folder)

    try:
        entries = sorted(os.listdir(root_path))
    except Exception:
        return []

    for entry in entries:
        sub_path = os.path.join(root_path, entry)
        if not os.path.isdir(sub_path):
            continue
        if entry.startswith(".") or entry == "__pycache__":
            continue

        orig_name = normalize_unicode(entry)
        parsed_date, clean_title = parse_date_and_name_from_folder(orig_name)

        # Count media files inside
        photo_count = 0
        pdf_count = 0
        doc_count = 0
        video_count = 0
        media_files = []

        try:
            for fname in sorted(os.listdir(sub_path)):
                fpath = os.path.join(sub_path, fname)
                if not os.path.isfile(fpath) or fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext in IMAGE_EXTS:
                    photo_count += 1
                    media_files.append(fpath)
                elif ext in PDF_EXTS:
                    pdf_count += 1
                    media_files.append(fpath)
                elif ext in DOCUMENT_EXTS:
                    doc_count += 1
                    media_files.append(fpath)
                elif ext in VIDEO_EXTS:
                    video_count += 1
                    media_files.append(fpath)
        except Exception:
            pass

        # If date not in folder name, fallback to earliest media file date
        if parsed_date is None:
            parsed_date = detect_earliest_file_date(sub_path)
        if parsed_date is None:
            parsed_date = datetime.datetime.now()

        target_name = format_event_name(orig_name, clean_title, parsed_date, template)

        item = ScannedEventFolder(
            folder_path=sub_path,
            original_name=orig_name,
            clean_name=clean_title,
            event_date=parsed_date,
            target_name=target_name,
            photo_count=photo_count,
            pdf_count=pdf_count,
            doc_count=doc_count,
            video_count=video_count,
            media_files=media_files,
            is_selected=len(media_files) > 0,
            status="Hazır" if len(media_files) > 0 else "Boş Klasör",
        )
        results.append(item)

    return results
