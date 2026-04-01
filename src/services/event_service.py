"""Event service for handling event-related business logic."""

from src.services.base_service import BaseService
from src.repositories.event_repository import EventRepository
from src.domain.entities.event import Event
import logging

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