import shutil
import os
from src.domain.entities.event import Event
from src.repositories.event_repository import EventRepository
from src.repositories.media_repository import MediaRepository

class EventService:
    def __init__(self, vault_base_path: str):
        self.vault_base_path = vault_base_path
        self.event_repo = EventRepository()
        self.media_repo = MediaRepository()
    
    def create_and_import_event(self, name: str, event_date, source_folder: str) -> Event:
        # 1. Entity oluştur (Class Method Factory)
        event = Event.create(name, event_date, source_folder)
        
        # 2. Vault'a kopyala
        dest_path = os.path.join(self.vault_base_path, str(event.id))
        shutil.copytree(source_folder, dest_path)
        
        # 3. State güncelle (iş mantığı entity içinde)
        event.mark_as_imported(dest_path)
        
        # 4. Kaydet
        self.event_repo.save(event)

        # 5. Klasördeki tüm görselleri medias tablosuna ekle
        for filename in os.listdir(dest_path):
            if filename.lower().endswith((".jpg", ".jpeg", ".png")):
                img_path = os.path.join(dest_path, filename)
                try:
                    self.media_repo.ensure_media_exists(event.id, img_path, "photo")
                except Exception:
                    pass  # Zaten varsa atla
        
        return event