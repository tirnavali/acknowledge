"""Event service for handling event-related business logic."""

from src.services.base_service import BaseService
from src.repositories.event_repository import EventRepository
from src.domain.entities.event import Event
import logging
import os
import shutil

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
        1. Create a vault subfolder named after the event.
        2. Copy all image files from source_folder into it.
        3. Persist the event record and return it.

        progress_callback(current: int, total: int) is called after each file is copied.
        """
        from src.utils.document_util import DOCUMENT_EXTS, extract_docx_text, extract_doc_metadata, generate_document_thumbnail
        from src.utils.video_util import VIDEO_EXTS, generate_video_thumbnail, extract_video_metadata

        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
        vault_folder = os.path.join(vault_base_path, safe_name)
        os.makedirs(vault_folder, exist_ok=True)

        image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
        supported_exts = image_exts | DOCUMENT_EXTS | VIDEO_EXTS
        media_files = [
            f for f in os.listdir(source_folder)
            if os.path.splitext(f)[1].lower() in supported_exts
        ]
        total = len(media_files)
        doc_metadata: dict[str, dict] = {}   # filename -> {text_content, technical_metadata, title}
        video_metadata: dict[str, dict] = {} # filename -> {technical_metadata, title, iptc_date_created}

        for i, filename in enumerate(media_files, 1):
            src = os.path.join(source_folder, filename)
            dst = os.path.join(vault_folder, filename)
            ext = os.path.splitext(filename)[1].lower()
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

            thumb_dir = os.path.join(vault_folder, ".thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_path = os.path.join(thumb_dir, filename + ".thumb.jpg")

            if ext in image_exts:
                # Pre-generate thumbnail to make gallery load instantaneous
                try:
                    if not os.path.exists(thumb_path):
                        from PIL import Image, ImageOps
                        with Image.open(dst) as img:
                            img = ImageOps.exif_transpose(img)
                            if img.mode != "RGB":
                                img = img.convert("RGB")
                            img.thumbnail((300, 300))
                            img.save(thumb_path, "JPEG", quality=85)
                except Exception as e:
                    self.logger.warning(f"Could not pre-generate thumbnail for {filename}: {e}")
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

        event = Event.create(
            name=name,
            event_date=event_date,
            imported_folder_path=source_folder,
        )
        event.mark_as_imported(vault_folder)
        self.event_repository.save(event)

        if doc_metadata and self.media_repository:
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

        if video_metadata and self.media_repository:
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