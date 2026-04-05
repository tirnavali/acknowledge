"""Media service for handling media-related business logic."""

from src.services.base_service import BaseService
from src.repositories.media_repository import MediaRepository
from src.repositories.event_repository import EventRepository
import logging
import os
from src.utils import path_util

class MediaService(BaseService):
    """Service for managing media files."""
    
    def __init__(self, media_repository: MediaRepository, event_repository: EventRepository):
        super().__init__()
        self.media_repository = media_repository
        self.event_repository = event_repository
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_all(self):
        """Get all media records."""
        try:
            return self.media_repository.get_all()
        except Exception as e:
            self.logger.error(f"Error getting all media: {e}")
            raise
    
    def get_by_id(self, media_id):
        """Get media by ID."""
        try:
            return self.media_repository.get_by_id(media_id)
        except Exception as e:
            self.logger.error(f"Error getting media by ID {media_id}: {e}")
            raise

    def get_by_file_path(self, file_path):
        """Get media by filesystem path."""
        try:
            return self.media_repository.get_by_file_path(file_path)
        except Exception as e:
            self.logger.error(f"Error getting media by file path {file_path}: {e}")
            raise

    def create(self, media_data):
        """Create new media record."""
        try:
            return self.media_repository.create(media_data)
        except Exception as e:
            self.logger.error(f"Error creating media: {e}")
            raise
    
    def update(self, media_id, media_data):
        """Update media record."""
        try:
            return self.media_repository.update(media_id, media_data)
        except Exception as e:
            self.logger.error(f"Error updating media {media_id}: {e}")
            raise
    
    def delete(self, media_id):
        """Delete media record."""
        try:
            return self.media_repository.delete(media_id)
        except Exception as e:
            self.logger.error(f"Error deleting media {media_id}: {e}")
            raise
    
    def get_gallery_items(self, event_id):
        """Get gallery items for an event."""
        try:
            event = self.event_repository.get_by_id(event_id)
            if not event or not event.vault_folder_path:
                return []
            
            abs_folder_path = os.path.abspath(event.vault_folder_path)
            if not os.path.exists(abs_folder_path):
                return []
            
            # Fetch ALL metadata from DB in one query for this event
            db_records = self.media_repository.get_all_for_event(event_id)
            # Create a lookup map: resolved absolute path -> record dict
            db_map = {path_util.from_db_path(r['file_path']): r for r in db_records}
            
            items = []
            for filename in os.listdir(abs_folder_path):
                if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                    img_path = os.path.join(abs_folder_path, filename)
                    abs_path = path_util.normalize_path(img_path)
                    db_record = db_map.get(abs_path)
                    
                    # Create lazy item (metadata from DB if available)
                    from gallery_item_model import GalleryItem
                    item = GalleryItem(
                        filename, 
                        img_path, 
                        in_db=(db_record is not None),
                        db_metadata=db_record
                    )
                    items.append(item)
            return items
        except Exception as e:
            self.logger.error(f"Error getting gallery items for event {event_id}: {e}")
            raise
    
    def save_iptc_data(self, media_id, iptc_data):
        """Save IPTC data to both the image file and the database."""
        try:
            # Save to database
            self.media_repository.save_iptc(media_id, iptc_data)
            return True
        except Exception as e:
            self.logger.error(f"Error saving IPTC data for media {media_id}: {e}")
            raise

    def ensure_media_exists(self, event_id, file_path, media_type="photo"):
        """Ensure a media record exists for the given file_path. Returns the media_id."""
        try:
            return self.media_repository.ensure_media_exists(event_id, file_path, media_type)
        except Exception as e:
            self.logger.error(f"Error ensuring media exists for {file_path}: {e}")
            raise
    
    def get_iptc_data(self, media_id):
        """Get IPTC data for a media item."""
        try:
            return self.media_repository.get_iptc_data(media_id)
        except Exception as e:
            self.logger.error(f"Error getting IPTC data for media {media_id}: {e}")
            raise

    def get_all_for_event(self, event_id):
        """Return all media records for a given event."""
        try:
            return self.media_repository.get_all_for_event(event_id)
        except Exception as e:
            self.logger.error(f"Error getting all media for event {event_id}: {e}")
            raise

    def mark_face_detected(self, media_id):
        """Mark face detection as completed for a media record."""
        try:
            return self.media_repository.mark_face_detected(media_id)
        except Exception as e:
            self.logger.error(f"Error marking face detected for media {media_id}: {e}")
            raise

    def get_file_paths_for_event(self, event_id):
        """Get all file paths for a given event."""
        try:
            return self.media_repository.get_file_paths_for_event(event_id)
        except Exception as e:
            self.logger.error(f"Error getting file paths for event {event_id}: {e}")
            raise

    def get_gallery_items_for_search(self, query: str) -> list:
        """Search IPTC metadata across all events and return GalleryItems."""
        try:
            from gallery_item_model import GalleryItem
            records = self.media_repository.search_across_events(query)
            items = []
            for rec in records:
                path = rec.get("file_path", "")
                if path and os.path.exists(path):
                    items.append(GalleryItem(
                        os.path.basename(path),
                        path,
                        in_db=True,
                        db_metadata=rec,
                    ))
            return items
        except Exception as e:
            self.logger.error(f"Error searching across events for '{query}': {e}")
            raise

    def search_across_events_raw(self, query: str) -> list[dict]:
        """Return raw DB records for FTS search (no Qt objects created here)."""
        try:
            return self.media_repository.search_across_events(query)
        except Exception as e:
            self.logger.error(f"Error in raw search for '{query}': {e}")
            raise

    def save_captions(self, media_id, result) -> None:
        """Save caption and tag fields to the database."""
        try:
            self.media_repository.save_captions(media_id, result)
        except Exception as e:
            self.logger.error(f"Error saving captions for media {media_id}: {e}")
            raise

    def get_gallery_items_for_person(self, person_id):
        """Get GalleryItems for all media linked to a person."""
        try:
            from gallery_item_model import GalleryItem
            import os
            records = self.media_repository.get_all_for_person(person_id)
            items = []
            for rec in records:
                path = rec.get("file_path", "")
                if path and os.path.exists(path):
                    items.append(GalleryItem(
                        os.path.basename(path),
                        path,
                        in_db=True,
                        db_metadata=rec,
                    ))
            return items
        except Exception as e:
            self.logger.error(f"Error getting gallery items for person {person_id}: {e}")
            raise