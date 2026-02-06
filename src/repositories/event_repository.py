# src/repositories/event_repository.py
from uuid import UUID
from src.database import get_db
from src.domain.entities.event import Event
from sqlalchemy import text
class EventRepository:
    def save(self, event: Event) -> None:
        with get_db() as db:
            db.execute(text("""
                INSERT INTO events (id, name, event_date, imported_folder_path, vault_folder_path, import_success)
                VALUES (:id, :name, :event_date, :imported_folder_path, :vault_folder_path, :import_success)
                ON CONFLICT (id) DO UPDATE SET
                    name = :name, vault_folder_path = :vault_folder_path, import_success = :import_success
            """), {
                "id": str(event.id),
                "name": event.name,
                "event_date": event.event_date,
                "imported_folder_path": event.imported_folder_path,
                "vault_folder_path": event.vault_folder_path,
                "import_success": event.import_success
            })
            db.commit()
    
    def get_by_id(self, event_id: UUID) -> Event | None:
        with get_db() as db:
            result = db.execute(text("SELECT * FROM events WHERE id = :id"), {"id": str(event_id)})
            row = result.fetchone()
            if row:
                return Event(
                    id=row.id if isinstance(row.id, UUID) else UUID(row.id),
                    name=row.name,
                    event_date=row.event_date,
                    imported_folder_path=row.imported_folder_path,
                    vault_folder_path=row.vault_folder_path,
                    import_success=row.import_success
                )
            return None

    def get_all(self) -> list[Event]:
        with get_db() as db:
            result = db.execute(text("SELECT * FROM events ORDER BY event_date DESC LIMIT 100"))
            rows = result.fetchall()
            return [Event(
                id=row.id if isinstance(row.id, UUID) else UUID(row.id),
                name=row.name,
                event_date=row.event_date,
                imported_folder_path=row.imported_folder_path,
                vault_folder_path=row.vault_folder_path,
                import_success=row.import_success
            ) for row in rows]