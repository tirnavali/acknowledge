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

AUXILIARY_MEDIA_SUBFOLDER_NAMES = {
    "fotolar", "fotoğraflar", "fotograflar", "photos", "resimler", "images",
    "raw", "jpg", "jpeg", "png", "video", "videolar", "videos", "belgeler",
    "documents", "docs", "pdf", "100canon", "100nikon", "100sony", "dcim",
    "secilenler", "seçilenler", "secilmis", "seçilmiş", "highres", "lowres",
    "baski", "baskı", "web", "social", "sosyal"
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
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', clean)
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
        clean_title = name.replace(match_year.group(0), "").strip(" .-_/[]()")
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
        return parsed_date, clean_title or name

    return None, clean_title


def detect_earliest_file_date(media_files_or_folder) -> Optional[datetime.datetime]:
    """Scans media files for the earliest EXIF/filesystem date."""
    if isinstance(media_files_or_folder, str):
        if not os.path.exists(media_files_or_folder):
            return None
        file_list = []
        for root, _, files in os.walk(media_files_or_folder):
            for f in files:
                if not f.startswith("."):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in ALL_SUPPORTED_EXTS:
                        file_list.append(os.path.join(root, f))
    else:
        file_list = list(media_files_or_folder)

    earliest_time = None
    for file_path in file_list:
        ext = os.path.splitext(file_path)[1].lower()

        # Check EXIF for images
        if ext in IMAGE_EXTS:
            try:
                with Image.open(file_path) as img:
                    exif = img._getexif()
                    if exif:
                        dt_str = exif.get(36867) or exif.get(306) # DateTimeOriginal or DateTime
                        if dt_str:
                            dt = datetime.datetime.strptime(str(dt_str)[:19], "%Y:%m:%d %H:%M:%S")
                            ts = dt.timestamp()
                            if earliest_time is None or ts < earliest_time:
                                earliest_time = ts
                                continue
            except Exception:
                pass

        # Fallback to filesystem mtime
        try:
            ts = os.path.getmtime(file_path)
            if earliest_time is None or ts < earliest_time:
                earliest_time = ts
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
        if clean.startswith(year_str):
            return clean
        return f"{year_str} {clean}".strip()

    elif template == NamingTemplate.YEAR_SUFFIX:
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


def _is_auxiliary_subfolder(name: str) -> bool:
    return name.lower().strip() in AUXILIARY_MEDIA_SUBFOLDER_NAMES


def _collect_all_media_files(folder_path: str) -> Tuple[int, int, int, int, List[str]]:
    """Recursively walks a folder and categorizes all media files."""
    photo_count = 0
    pdf_count = 0
    doc_count = 0
    video_count = 0
    media_files = []

    try:
        for root, dirs, files in os.walk(folder_path):
            # Ignore hidden and thumbnail directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files):
                if f.startswith("."):
                    continue
                fpath = os.path.join(root, f)
                ext = os.path.splitext(f)[1].lower()
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

    return photo_count, pdf_count, doc_count, video_count, media_files


def find_candidate_event_folders(root_folder: str, max_depth: int = 4) -> List[str]:
    """
    Recursively discovers meaningful event folders under root_folder.
    Handles structures like:
    - Root / Event / files
    - Root / Month / Event / files
    - Root / Year / Month / Event / files
    - Root / Event / Fotolar / files
    """
    if not os.path.exists(root_folder) or not os.path.isdir(root_folder):
        return []

    root_path = os.path.normpath(root_folder)
    discovered: List[str] = []

    def scan_level(current_path: str, depth: int):
        if depth > max_depth:
            return

        try:
            entries = sorted(os.listdir(current_path))
        except Exception:
            return

        direct_media = []
        subdirs = []

        for e in entries:
            if e.startswith(".") or e == "__pycache__":
                continue
            full_p = os.path.join(current_path, e)
            if os.path.isdir(full_p):
                subdirs.append(e)
            elif os.path.isfile(full_p):
                ext = os.path.splitext(e)[1].lower()
                if ext in ALL_SUPPORTED_EXTS:
                    direct_media.append(full_p)

        # Case 1: The folder contains direct media files
        if len(direct_media) > 0:
            discovered.append(current_path)
            return

        # Case 2: No direct media files, but has subdirectories
        if len(subdirs) > 0:
            # If all subdirectories are auxiliary names (e.g. 'Fotolar', 'Belgeler', 'RAW')
            if all(_is_auxiliary_subfolder(s) for s in subdirs):
                # Check if there is media in those subdirectories
                _, _, _, _, mfiles = _collect_all_media_files(current_path)
                if len(mfiles) > 0:
                    discovered.append(current_path)
                    return

            # Otherwise, these subdirectories are category/month/event folders: recurse down
            for s in subdirs:
                scan_level(os.path.join(current_path, s), depth + 1)

    # Check if root folder itself directly contains media files
    root_direct_media = []
    root_subdirs = []
    try:
        for e in sorted(os.listdir(root_path)):
            if e.startswith(".") or e == "__pycache__":
                continue
            full_p = os.path.join(root_path, e)
            if os.path.isdir(full_p):
                root_subdirs.append(e)
            elif os.path.isfile(full_p):
                if os.path.splitext(e)[1].lower() in ALL_SUPPORTED_EXTS:
                    root_direct_media.append(full_p)
    except Exception:
        pass

    if len(root_direct_media) > 0 and len(root_subdirs) == 0:
        # User selected a single event folder directly
        return [root_path]

    for s in root_subdirs:
        scan_level(os.path.join(root_path, s), depth=1)

    return discovered


def scan_subfolders(
    root_folder: str,
    template: NamingTemplate = NamingTemplate.YEAR_PREFIX,
) -> List[ScannedEventFolder]:
    """
    Scans subdirectories under root_folder (recursively supporting Year/Month/Event structures)
    and compiles a list of ScannedEventFolder objects with full media counts.
    """
    if not os.path.exists(root_folder) or not os.path.isdir(root_folder):
        return []

    candidate_folders = find_candidate_event_folders(root_folder)
    results: List[ScannedEventFolder] = []

    for folder_path in candidate_folders:
        orig_name = normalize_unicode(os.path.basename(folder_path))
        parsed_date, clean_title = parse_date_and_name_from_folder(orig_name)

        # Recursively count all media files inside this event folder and its subfolders
        p_cnt, pdf_cnt, d_cnt, v_cnt, mfiles = _collect_all_media_files(folder_path)

        # If date could not be parsed from folder name, try parent directory name or file dates
        if parsed_date is None:
            # Check parent folder name (e.g. '10-EKIM 2023' or '2023')
            parent_name = os.path.basename(os.path.dirname(folder_path))
            parent_date, _ = parse_date_and_name_from_folder(parent_name)
            if parent_date:
                parsed_date = parent_date

        if parsed_date is None:
            parsed_date = detect_earliest_file_date(mfiles)

        if parsed_date is None:
            parsed_date = datetime.datetime.now()

        target_name = format_event_name(orig_name, clean_title, parsed_date, template)

        item = ScannedEventFolder(
            folder_path=folder_path,
            original_name=orig_name,
            clean_name=clean_title,
            event_date=parsed_date,
            target_name=target_name,
            photo_count=p_cnt,
            pdf_count=pdf_cnt,
            doc_count=d_cnt,
            video_count=v_cnt,
            media_files=mfiles,
            is_selected=len(mfiles) > 0,
            status="Hazır" if len(mfiles) > 0 else "Boş Klasör",
        )
        results.append(item)

    return results
