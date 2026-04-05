"""Person service for handling person-related business logic."""

from src.services.base_service import BaseService
from src.repositories.person_repository import PersonRepository
from src.repositories.person_note_repository import PersonNoteRepository
import logging

class PersonService(BaseService):
    """Service for managing persons."""

    def __init__(self, person_repository: PersonRepository, person_note_repository: PersonNoteRepository = None):
        super().__init__()
        self.person_repository = person_repository
        self.person_note_repository = person_note_repository
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_all(self):
        """Get all persons."""
        try:
            return self.person_repository.get_all()
        except Exception as e:
            self.logger.error(f"Error getting all persons: {e}")
            raise
    
    def get_by_id(self, person_id):
        """Get person by ID."""
        try:
            return self.person_repository.get_by_id(person_id)
        except Exception as e:
            self.logger.error(f"Error getting person by ID {person_id}: {e}")
            raise
    
    def create(self, person_data):
        """Create new person."""
        try:
            return self.person_repository.create(person_data)
        except Exception as e:
            self.logger.error(f"Error creating person: {e}")
            raise
    
    def update(self, person_id, person_data):
        """Update person."""
        try:
            return self.person_repository.update(person_id, person_data)
        except Exception as e:
            self.logger.error(f"Error updating person {person_id}: {e}")
            raise
    
    def delete(self, person_id):
        """Delete person."""
        try:
            return self.person_repository.delete(person_id)
        except Exception as e:
            self.logger.error(f"Error deleting person {person_id}: {e}")
            raise
    
    def find_or_create(self, name):
        """Find existing person or create new one."""
        try:
            return self.person_repository.find_or_create(name)
        except Exception as e:
            self.logger.error(f"Error finding or creating person '{name}': {e}")
            raise
    
    def link_to_media(self, person_id, media_id):
        """Link person to media."""
        try:
            return self.person_repository.link_to_media(person_id, media_id)
        except Exception as e:
            self.logger.error(f"Error linking person {person_id} to media {media_id}: {e}")
            raise
    
    def get_persons_for_media(self, media_id):
        """Get persons linked to media."""
        try:
            return self.person_repository.get_persons_for_media(media_id)
        except Exception as e:
            self.logger.error(f"Error getting persons for media {media_id}: {e}")
            raise
    
    def unlink_all_from_media(self, media_id):
        """Unlink all persons from media."""
        try:
            return self.person_repository.unlink_all_from_media(media_id)       
        except Exception as e:
            self.logger.error(f"Error unlinking persons from media {media_id}: {e}")
            raise

    def find_by_name(self, name):
        """Find person by name."""
        try:
            return self.person_repository.find_by_name(name)
        except Exception as e:
            self.logger.error(f"Error finding person by name '{name}': {e}")
            raise

    def rename(self, person_id, new_name):
        """Rename a person."""
        try:
            return self.person_repository.rename(person_id, new_name)
        except Exception as e:
            self.logger.error(f"Error renaming person {person_id}: {e}")
            raise

    def unlink_from_media(self, person_id, media_id):
        """Unlink a person from a media."""
        try:
            return self.person_repository.unlink_from_media(person_id, media_id)
        except Exception as e:
            self.logger.error(f"Error unlinking person {person_id} from media {media_id}: {e}")
            raise

    def get_all_with_counts(self):
        """Get all persons with their linked photo counts."""
        try:
            return self.person_repository.get_all_with_counts()
        except Exception as e:
            self.logger.error(f"Error getting persons with counts: {e}")
            raise

    def save_note(self, person_id, media_id, note: str) -> None:
        try:
            self.person_note_repository.upsert(person_id, media_id, note)
        except Exception as e:
            self.logger.error(f"Error saving note for person {person_id} / media {media_id}: {e}")
            raise

    def get_note(self, person_id, media_id) -> str:
        try:
            return self.person_note_repository.get(person_id, media_id)
        except Exception as e:
            self.logger.error(f"Error getting note for person {person_id} / media {media_id}: {e}")
            return ""