from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
@dataclass
class Event:
    _name: str = ""
    _event_date: datetime = field(default_factory=datetime.now)
    _imported_folder_path: str = ""
    _id: UUID = field(default_factory=uuid4)
    _vault_folder_path: str = ""
    _import_success: bool = False
    
    @property
    def id(self) -> UUID:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def event_date(self) -> datetime:
        return self._event_date

    @property
    def imported_folder_path(self) -> str:
        return self._imported_folder_path

    @property
    def vault_folder_path(self) -> str:
        return self._vault_folder_path

    @property
    def import_success(self) -> bool:
        return self._import_success

    @classmethod
    def create(cls, name: str, event_date: datetime, imported_folder_path: str) -> "Event":
        """Factory method to create a new Event with initial state"""
        return cls(
            _id=uuid4(),
            _name=name,
            _event_date=event_date,
            _imported_folder_path=imported_folder_path,
            _vault_folder_path="",
            _import_success=False
        )
    
    def mark_as_imported(self, vault_path: str):
        """İş kuralı: İçe aktarma tamamlandığında çağrılır"""
        self._vault_folder_path = vault_path
        self._import_success = True
    
    def is_ready_for_processing(self) -> bool:
        return self._import_success and bool(self._vault_folder_path)