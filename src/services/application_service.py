"""Application service to orchestrate all services."""

import logging
from src.services.event_service import EventService
from src.services.media_service import MediaService
from src.services.face_service import FaceService
from src.services.person_service import PersonService
from src.repositories.event_repository import EventRepository
from src.repositories.media_repository import MediaRepository
from src.repositories.face_repository import FaceRepository
from src.repositories.person_repository import PersonRepository
from src.repositories.person_note_repository import PersonNoteRepository

class ApplicationService:
    """Main application service that orchestrates all other services."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize all services with their dependencies."""
        # Create repositories
        self.event_repo = EventRepository()
        self.media_repo = MediaRepository()
        self.face_repo = FaceRepository()
        self.person_repo = PersonRepository()
        self.person_note_repo = PersonNoteRepository()

        # Create services
        self.event_service = EventService(self.event_repo)
        self.media_service = MediaService(self.media_repo, self.event_repo)
        self.face_service = FaceService(self.face_repo, self.person_repo)
        self.person_service = PersonService(self.person_repo, self.person_note_repo)
        
        self.logger.info("Application services initialized successfully")
    
    def get_event_service(self):
        """Get event service."""
        return self.event_service
    
    def get_media_service(self):
        """Get media service."""
        return self.media_service
    
    def get_face_service(self):
        """Get face service."""
        return self.face_service
    
    def get_person_service(self):
        """Get person service."""
        return self.person_service
    
    def initialize_application(self):
        """Initialize the application."""
        self.logger.info("Initializing application...")
        # Add any initialization logic here
        pass