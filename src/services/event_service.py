import shutil
import os
from src.domain.entities.event import Event
from src.repositories.event_repository import EventRepository

class EventService:
    def __init__(self, vault_base_path: str):
        self.vault_base_path = vault_base_path
        self.event_repo = EventRepository()
    
    def create_and_import_event(self, name: str, event_date, source_folder: str) -> Event:
        # 1. Entity oluştur
        event = Event(
            name=name,
            event_date=event_date,
            imported_folder_path=source_folder
        )
        
        # 2. Vault'a kopyala
        dest_path = os.path.join(self.vault_base_path, str(event.id))
        shutil.copytree(source_folder, dest_path)
        
        # 3. State güncelle (iş mantığı entity içinde)
        event.mark_as_imported(dest_path)
        
        # 4. Kaydet
        self.event_repo.save(event)
        
        return event