# src/repositories/person_repository.py
from uuid import UUID
from src.database import get_db
from sqlalchemy import text
import uuid as uuid_module


class PersonRepository:
    def find_or_create(self, name: str) -> UUID:
        """Find a person by name or create a new one. Returns the person_id."""
        name = name.strip()
        if not name:
            return None
        
        with get_db() as db:
            # Try to find existing
            result = db.execute(
                text("SELECT id FROM persons WHERE name = :name"),
                {"name": name}
            )
            row = result.fetchone()
            if row:
                return row.id if isinstance(row.id, UUID) else UUID(str(row.id))
            
            # Create new
            new_id = uuid_module.uuid4()
            db.execute(text("""
                INSERT INTO persons (id, name) VALUES (:id, :name)
            """), {
                "id": str(new_id),
                "name": name,
            })
            db.commit()
            return new_id

    def get_all(self) -> list[dict]:
        """Get all persons."""
        with get_db() as db:
            result = db.execute(text("SELECT * FROM persons ORDER BY name"))
            return [dict(row._mapping) for row in result.fetchall()]

    def link_to_media(self, person_id: UUID, media_id: UUID) -> None:
        """Link a person to a media (create junction record)."""
        with get_db() as db:
            # Check if link already exists
            result = db.execute(text("""
                SELECT 1 FROM media_persons 
                WHERE media_id = :media_id AND person_id = :person_id
            """), {
                "media_id": str(media_id),
                "person_id": str(person_id),
            })
            if result.fetchone():
                return  # Already linked
            
            db.execute(text("""
                INSERT INTO media_persons (media_id, person_id) 
                VALUES (:media_id, :person_id)
            """), {
                "media_id": str(media_id),
                "person_id": str(person_id),
            })
            db.commit()

    def unlink_all_from_media(self, media_id: UUID) -> None:
        """Remove all person links for a media."""
        with get_db() as db:
            db.execute(text("""
                DELETE FROM media_persons WHERE media_id = :media_id
            """), {"media_id": str(media_id)})
            db.commit()

    def get_persons_for_media(self, media_id: UUID) -> list[str]:
        """Get all person names linked to a media."""
        with get_db() as db:
            result = db.execute(text("""
                SELECT p.name FROM persons p
                JOIN media_persons mp ON p.id = mp.person_id
                WHERE mp.media_id = :media_id
                ORDER BY p.name
            """), {"media_id": str(media_id)})
            return [row.name for row in result.fetchall()]
