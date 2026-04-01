"""Face service for handling face detection and recognition."""

from src.services.base_service import BaseService
from src.services.face_analysis_service import FaceAnalysisService
from src.repositories.face_repository import FaceRepository
from src.repositories.person_repository import PersonRepository
from src.database import get_db
from sqlalchemy import text
import logging
import uuid

class FaceService(BaseService):
    """Service for handling face detection and recognition."""
    
    def __init__(self, face_repository: FaceRepository, person_repository: PersonRepository):
        super().__init__()
        self.face_repository = face_repository
        self.person_repository = person_repository
        self.face_analysis_service = FaceAnalysisService()  # singleton
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_all(self):
        """Get all faces."""
        try:
            return self.face_repository.get_all()
        except Exception as e:
            self.logger.error(f"Error getting all faces: {e}")
            raise
    
    def get_by_id(self, face_id):
        """Get face by ID."""
        try:
            return self.face_repository.get_by_id(face_id)
        except Exception as e:
            self.logger.error(f"Error getting face by ID {face_id}: {e}")
            raise
    
    def create(self, face_data):
        """Create new face record."""
        try:
            return self.face_repository.create(face_data)
        except Exception as e:
            self.logger.error(f"Error creating face: {e}")
            raise
    
    def update(self, face_id, face_data):
        """Update face record."""
        try:
            return self.face_repository.update(face_id, face_data)
        except Exception as e:
            self.logger.error(f"Error updating face {face_id}: {e}")
            raise
    
    def delete(self, face_id):
        """Delete face record."""
        try:
            return self.face_repository.delete(face_id)
        except Exception as e:
            self.logger.error(f"Error deleting face {face_id}: {e}")
            raise
    
    def detect_faces(self, image_path):
        """Detect faces in an image."""
        try:
            return self.face_analysis_service.detect(image_path)
        except Exception as e:
            self.logger.error(f"Error detecting faces in {image_path}: {e}")
            raise
    
    def recognize_faces(self, face_embeddings):
        """Recognize faces using embeddings."""
        try:
            return self.face_analysis_service.recognize_faces(face_embeddings)
        except Exception as e:
            self.logger.error(f"Error recognizing faces: {e}")
            raise
    
    def get_face_details(self, face_id):
        """Get detailed information about a face."""
        try:
            return self.face_repository.get_face_details(face_id)
        except Exception as e:
            self.logger.error(f"Error getting face details for {face_id}: {e}")
            raise

    def get_faces_for_media(self, media_id):
        """Get all faces for a media item."""
        try:
            return self.face_repository.get_faces_for_media(media_id)
        except Exception as e:
            self.logger.error(f"Error getting faces for media {media_id}: {e}")
            raise

    def save_faces(self, media_id, results):
        """Save face detection results to database."""
        try:
            # Validate that media_id is actually a UUID
            if not isinstance(media_id, uuid.UUID):
                raise ValueError(f"Expected media_id to be a UUID, got {type(media_id)}")
            return self.face_repository.save_faces(media_id, results)
        except Exception as e:
            self.logger.error(f"Error saving faces for media {media_id}: {e}")
            raise

    def assign_person(self, face_id, person_id):
        """Assign a person to a face detection."""
        try:
            return self.face_repository.assign_person(face_id, person_id)
        except Exception as e:
            self.logger.error(f"Error assigning person {person_id} to face {face_id}: {e}")
            raise

    def delete_faces_for_media(self, media_id):
        """Delete all face detections for a media item."""
        try:
            return self.face_repository.delete_faces_for_media(media_id)
        except Exception as e:
            self.logger.error(f"Error deleting faces for media {media_id}: {e}")
            raise

    def find_similar_person(self, embedding) -> tuple:
        """Find closest matching person for a face embedding via pgvector similarity."""
        try:
            return self.face_repository.find_similar_person(embedding)
        except Exception as e:
            self.logger.error(f"Error finding similar person: {e}")
            raise