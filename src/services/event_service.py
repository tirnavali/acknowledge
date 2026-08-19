"""Event service for handling event-related business logic."""

from src.services.base_service import BaseService
from src.repositories.event_repository import EventRepository
from src.domain.entities.event import Event
from src.utils.folder_scanner_util import sanitize_folder_name, ScannedEventFolder
from src.utils.document_util import DOCUMENT_EXTS, extract_docx_text, extract_doc_metadata, generate_document_thumbnail
from src.utils.pdf_util import PDF_EXTS, extract_pdf_text, extract_pdf_metadata, generate_pdf_thumbnail
from src.utils.video_util import VIDEO_EXTS, generate_video_thumbnail, extract_video_metadata

import logging
import os
import shutil
import datetime
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


class EventService(BaseService):
    """Service for managing events."""

    def __init__(self, event_repository: EventRepository, media_repository=None):
        super().__init__()
        self.event_repository = event_repository
        self.media_repository = media_repository
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_all(self):
        """Get all events."""
        try:
            return self.event_repository.get_all()
        except Exception as e:
            self.logger.error(f"Error getting all events: {e}")
            raise
    
    def search_by_name(self, query: str) -> list[Event]:
        """Search events by name."""
        try:
            return self.event_repository.search_by_name(query)
        except Exception as e:
            self.logger.error(f"Error searching events by name '{query}': {e}")
            raise
    
    def get_by_id(self, event_id):
        """Get event by ID."""
        try:
            return self.event_repository.get_by_id(event_id)
        except Exception as e:
            self.logger.error(f"Error getting event by ID {event_id}: {e}")
            raise
    
    def create(self, event_data):
        """Create new event."""
        try:
            event = Event(**event_data)
            return self.event_repository.create(event)
        except Exception as e:
            self.logger.error(f"Error creating event: {e}")
            raise
    
    def update(self, event_id, event_data):
        """Update event."""
        try:
            event = Event(id=event_id, **event_data)
            return self.event_repository.update(event)
        except Exception as e:
            self.logger.error(f"Error updating event {event_id}: {e}")
            raise
    
    def delete(self, event_id):
        """Delete event."""
        try:
            return self.event_repository.delete(event_id)
        except Exception as e:
            self.logger.error(f"Error deleting event {event_id}: {e}")
            raise
    
    def get_event_by_id(self, event_id):
        """Get event by ID (alias for get_by_id)."""
        return self.get_by_id(event_id)

    def get_by_name(self, name: str) -> Event | None:
        """Get event by name."""
        try:
            return self.event_repository.get_by_name(name)
        except Exception as e:
            self.logger.error(f"Error getting event by name '{name}': {e}")
            raise

    def get_by_name_and_year(self, name: str, year: int) -> Event | None:
        """Get event by name and year to avoid cross-year duplicate collisions."""
        try:
            return self.event_repository.get_by_name_and_year(name, year)
        except Exception as e:
            self.logger.error(f"Error getting event by name '{name}' and year {year}: {e}")
            raise

    def get_by_name_and_date(self, name: str, event_date) -> Event | None:
        """Get event by name and event date."""
        try:
            return self.event_repository.get_by_name_and_date(name, event_date)
        except Exception as e:
            self.logger.error(f"Error getting event by name '{name}' and date {event_date}: {e}")
            raise

    def compute_vault_folder_path(self, vault_base_path: str, name: str, event_date=None) -> str:
        """
        Computes a safe and unique vault folder path.
        Includes year in folder path to avoid filesystem collisions across different years.
        """
        safe_name = sanitize_folder_name(name)
        year_str = str(event_date.year) if event_date and hasattr(event_date, "year") else None

        if year_str and not safe_name.startswith(year_str):
            folder_dirname = f"{year_str}_{safe_name}"
        else:
            folder_dirname = safe_name

        return os.path.normpath(os.path.join(vault_base_path, folder_dirname))

    def create_and_import_event(
        self,
        name: str,
        event_date,
        source_folder: str,
        vault_base_path: str,
        progress_callback=None,
    ) -> Event:
        """
        Create an event and copy media files from source_folder into the vault.

        Steps:
        1. Check if event with this name AND date/year already exists. If yes, re-use its vault path.
        2. Otherwise, create a unique vault subfolder named after the event and year.
        3. Copy unique files from source_folder into it.
        4. Generate thumbnails (Photo, PDF, Word, Video) and extract text/metadata.
        5. Persist/update the event record and bulk media records.
        """
        existing_event = self.get_by_name_and_date(name, event_date)
        if existing_event:
            event = existing_event
            vault_folder = event.vault_folder_path
        else:
            vault_folder = self.compute_vault_folder_path(vault_base_path, name, event_date)
            os.makedirs(vault_folder, exist_ok=True)
            event = Event.create(
                name=name,
                event_date=event_date,
                imported_folder_path=source_folder,
            )

        image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
        supported_exts = image_exts | DOCUMENT_EXTS | PDF_EXTS | VIDEO_EXTS

        media_files = [
            f for f in sorted(os.listdir(source_folder))
            if os.path.splitext(f)[1].lower() in supported_exts and not f.startswith(".")
        ]
        total = len(media_files)

        doc_metadata: dict[str, dict] = {}
        pdf_metadata: dict[str, dict] = {}
        video_metadata: dict[str, dict] = {}

        for i, filename in enumerate(media_files, 1):
            src = os.path.join(source_folder, filename)
            dst = os.path.join(vault_folder, filename)
            ext = os.path.splitext(filename)[1].lower()

            # Unique files only: If already exists in vault, skip copy and DB import for it
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

            thumb_dir = os.path.join(vault_folder, ".thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_path = os.path.join(thumb_dir, filename + ".thumb.jpg")

            if ext in image_exts:
                if not os.path.exists(thumb_path):
                    try:
                        with Image.open(dst) as img:
                            img = ImageOps.exif_transpose(img)
                            if img.mode != "RGB":
                                img = img.convert("RGB")
                            img.thumbnail((300, 300))
                            img.save(thumb_path, "JPEG", quality=85)
                    except Exception as e:
                        self.logger.warning(f"Could not pre-generate thumbnail for {filename}: {e}")

            elif ext in PDF_EXTS:
                if not os.path.exists(thumb_path):
                    generate_pdf_thumbnail(dst, thumb_path)
                pdf_text = extract_pdf_text(dst)
                pdf_meta = extract_pdf_metadata(dst)
                pdf_metadata[filename] = {
                    "text_content": pdf_text,
                    "technical_metadata": pdf_meta or None,
                    "title": os.path.splitext(filename)[0],
                }

            elif ext in DOCUMENT_EXTS:
                if not os.path.exists(thumb_path):
                    generate_document_thumbnail(dst, thumb_path)
                text = extract_docx_text(dst)
                meta = extract_doc_metadata(dst)
                doc_metadata[filename] = {
                    "text_content": text,
                    "technical_metadata": meta or None,
                    "title": os.path.splitext(filename)[0],
                }

            elif ext in VIDEO_EXTS:
                if not os.path.exists(thumb_path):
                    generate_video_thumbnail(dst, thumb_path)
                meta = extract_video_metadata(dst)
                video_metadata[filename] = {
                    "technical_metadata": meta or None,
                    "title": os.path.splitext(filename)[0],
                    "iptc_date_created": meta.get("creation_time"),
                }

            if progress_callback is not None:
                progress_callback(i, total)

        if not existing_event:
            event.mark_as_imported(vault_folder)
            self.event_repository.save(event)

        if self.media_repository:
            # Batch or individual media records save
            for filename, doc_meta in doc_metadata.items():
                vault_file_path = os.path.join(vault_folder, filename)
                try:
                    self.media_repository.save_document_media(
                        event_id=event.id,
                        file_path=vault_file_path,
                        title=doc_meta["title"],
                        text_content=doc_meta["text_content"],
                        technical_metadata=doc_meta["technical_metadata"],
                    )
                except Exception as e:
                    self.logger.warning(f"Could not persist document record for {filename}: {e}")

            for filename, p_meta in pdf_metadata.items():
                vault_file_path = os.path.join(vault_folder, filename)
                try:
                    self.media_repository.save_pdf_media(
                        event_id=event.id,
                        file_path=vault_file_path,
                        title=p_meta["title"],
                        text_content=p_meta["text_content"],
                        technical_metadata=p_meta["technical_metadata"],
                    )
                except Exception as e:
                    self.logger.warning(f"Could not persist PDF record for {filename}: {e}")

            for filename, v_meta in video_metadata.items():
                vault_file_path = os.path.join(vault_folder, filename)
                try:
                    self.media_repository.save_video_media(
                        event_id=event.id,
                        file_path=vault_file_path,
                        title=v_meta["title"],
                        technical_metadata=v_meta["technical_metadata"],
                        iptc_date_created=v_meta["iptc_date_created"],
                    )
                except Exception as e:
                    self.logger.warning(f"Could not persist video record for {filename}: {e}")

        self.logger.info(f"Created event '{name}', imported {total} files to {vault_folder}")
        return event

    def import_batch_events(
        self,
        event_items: list[ScannedEventFolder],
        vault_base_path: str,
        progress_callback=None,
        is_cancelled=None,
    ) -> dict:
        """
        Imports a batch of scanned event subfolders.

        Args:
            event_items: List of ScannedEventFolder objects selected for import.
            vault_base_path: Destination root path for media vault.
            progress_callback: Callable(event_idx, total_events, file_idx, total_files, event_name)
            is_cancelled: Callable() -> bool returning True if operation was cancelled.

        Returns:
            Dict summary: {"total": int, "successful": int, "skipped": int, "errors": list}
        """
        summary = {
            "total": len(event_items),
            "successful": 0,
            "skipped": 0,
            "errors": [],
            "created_events": [],
        }

        total_events = len(event_items)
        for ev_idx, item in enumerate(event_items, 1):
            if is_cancelled and is_cancelled():
                self.logger.info("Batch import cancelled by user.")
                break

            if not item.is_selected or not item.has_media:
                summary["skipped"] += 1
                continue

            try:
                def file_prog(cur, tot):
                    if progress_callback:
                        progress_callback(ev_idx, total_events, cur, tot, item.target_name)

                created_event = self.create_and_import_event(
                    name=item.target_name,
                    event_date=item.event_date,
                    source_folder=item.folder_path,
                    vault_base_path=vault_base_path,
                    progress_callback=file_prog,
                )
                summary["successful"] += 1
                summary["created_events"].append(created_event)

            except Exception as e:
                self.logger.error(f"Error importing batch event {item.target_name}: {e}")
                summary["errors"].append({
                    "folder": item.folder_path,
                    "name": item.target_name,
                    "error": str(e),
                })

        return summary