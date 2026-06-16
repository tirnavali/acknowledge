"""Application service to orchestrate all services."""

import logging
import os
from src.services.event_service import EventService
from src.services.media_service import MediaService
from src.services.face_service import FaceService
from src.services.caption_service import CaptionService
from src.services.person_service import PersonService
from src.repositories.event_repository import EventRepository
from src.repositories.media_repository import MediaRepository
from src.repositories.face_repository import FaceRepository
from src.repositories.person_repository import PersonRepository
from src.repositories.person_note_repository import PersonNoteRepository
from src.utils import config_util

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
        self.event_service = EventService(self.event_repo, self.media_repo)
        self.media_service = MediaService(self.media_repo, self.event_repo)
        self.face_service = FaceService(self.face_repo, self.person_repo)
        self.person_service = PersonService(self.person_repo, self.person_note_repo)
        self.caption_service = self._make_caption_service()

        self.logger.info("Application services initialized successfully")

    def _make_caption_service(self):
        """Pick the caption backend at startup based on settings.json.

        Two options are exclusive (only one model loads into VRAM):
        - "qwen" → CaptionService (Qwen2.5-VL-3B, transformers, local)
        - "gemma" → OllamaCaptionService (Gemma4 via Ollama HTTP, thinking on)

        Switch requires app restart so the previous model releases VRAM.
        """
        backend = config_util.get_setting("caption_backend", "qwen")
        if backend == "gemma":
            from src.services.ollama_caption_service import OllamaCaptionService
            svc = OllamaCaptionService(
                model=os.environ.get("OLLAMA_CAPTION_MODEL", "gemma4:latest"),
                url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                # thinking=False: Gemma4 think-mode swallows structured-output
                # responses (see OllamaCaptionService.__init__ note). Natural
                # chain-of-thought without the flag works better here.
                thinking=False,
            )
            self.logger.info("Caption backend: Gemma4 (Ollama)")
            return svc
        self.logger.info("Caption backend: Qwen2.5-VL-3B (local transformers)")
        return CaptionService()

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

    def get_caption_service(self):
        return self.caption_service

    def initialize_application(self):
        """Initialize the application."""
        self.logger.info("Initializing application...")
        # Add any initialization logic here
        pass