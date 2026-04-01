"""Event service for handling event-related business logic."""

from src.services.base_service import BaseService
from src.repositories.event_repository import EventRepository
from src.domain.entities.event import Event
import logging
import os
import shutil

class EventService(BaseService):
    """Service for managing events."""
    
    def __init__(self, event_repository: EventRepository):
        super().__init__()
        self.event_repository = event_repository
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_all(self):
        """Get all events."""
        try:
            return self.event_repository.get_all()
        except Exception as e:
            self.logger.error(f"Error getting all events: {e}")
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
    ) -> Event:
        """
        Create an event and copy media files from source_folder into the vault.

        Steps:
        1. Create a vault subfolder named after the event.
        2. Copy all image files from source_folder into it.
        3. Persist the event record and return it.
        """
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
        vault_folder = os.path.join(vault_base_path, safe_name)
        os.makedirs(vault_folder, exist_ok=True)

        image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
        copied = 0
        for filename in os.listdir(source_folder):
            if os.path.splitext(filename)[1].lower() in image_exts:
                src = os.path.join(source_folder, filename)
                dst = os.path.join(vault_folder, filename)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                copied += 1

        event = Event.create(
            name=name,
            event_date=event_date,
            imported_folder_path=source_folder,
        )
        event.mark_as_imported(vault_folder)
        self.event_repository.save(event)
        self.logger.info(f"Created event '{name}', imported {copied} files to {vault_folder}")
        return event