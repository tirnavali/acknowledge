from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
@dataclass
class Event:
    name: str
    event_date: datetime
    imported_folder_path: str
    id: UUID = field(default_factory=uuid4)
    vault_folder_path: str = ""
    import_success: bool = False
    
    def mark_as_imported(self, vault_path: str):
        """İş kuralı: İçe aktarma tamamlandığında çağrılır"""
        self.vault_folder_path = vault_path
        self.import_success = True
    
    def is_ready_for_processing(self) -> bool:
        return self.import_success and bool(self.vault_folder_path)