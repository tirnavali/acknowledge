"""Base service class for all application services."""

from abc import ABC, abstractmethod
import logging

class BaseService(ABC):
    """Base service interface with common functionality."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def get_all(self):
        """Get all records."""
        pass
    
    @abstractmethod
    def get_by_id(self, id):
        """Get record by ID."""
        pass
    
    @abstractmethod
    def create(self, data):
        """Create new record."""
        pass
    
    @abstractmethod
    def update(self, id, data):
        """Update record."""
        pass
    
    @abstractmethod
    def delete(self, id):
        """Delete record."""
        pass