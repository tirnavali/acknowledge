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
            result = db.execute(
                text("SELECT id FROM persons WHERE name = :name"),
                {"name": name}
            )
            row = result.fetchone()
            if row:
                return row.id if isinstance(row.id, UUID) else UUID(str(row.id))
            new_id = uuid_module.uuid4()
            db.execute(text("""
                INSERT INTO persons (id, name) VALUES (:id, :name)
            """), {"id": str(new_id), "name": name})
            db.commit()
            return new_id

    def find_by_name(self, name: str) -> UUID | None:
        """Look up a person by name. Returns UUID if found, None otherwise. Does NOT create."""
        name = name.strip()
        if not name:
            return None
        with get_db() as db:
            result = db.execute(
                text("SELECT id FROM persons WHERE name = :name"),
                {"name": name}
            )
            row = result.fetchone()
            return (row.id if isinstance(row.id, UUID) else UUID(str(row.id))) if row else None


    def get_by_id(self, person_id: UUID) -> dict | None:
        """Return person row or None."""
        with get_db() as db:
            result = db.execute(
                text("SELECT id, name FROM persons WHERE id = :pid"),
                {"pid": str(person_id)}
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def rename(self, person_id: UUID, new_name: str) -> None:
        """
        Rename a person in-place.
        Because face_detections and media_persons reference person.id (not name),
        all linked photos automatically reflect the new name on next DB read.
        """
        with get_db() as db:
            db.execute(
                text("UPDATE persons SET name = :name WHERE id = :pid"),
                {"name": new_name.strip(), "pid": str(person_id)}
            )
            db.commit()


    def get_all(self) -> list[dict]:
        """Get all persons."""
        with get_db() as db:
            result = db.execute(text("SELECT * FROM persons ORDER BY name"))
            return [dict(row._mapping) for row in result.fetchall()]

    def get_all_with_counts(self) -> list[dict]:
        """Get all persons with their linked photo counts."""
        with get_db() as db:
            result = db.execute(text("""
                SELECT p.id, p.name, COUNT(mp.media_id) AS photo_count
                FROM persons p
                LEFT JOIN media_persons mp ON p.id = mp.person_id
                GROUP BY p.id, p.name
                ORDER BY p.name
            """))
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

    def unlink_from_media(self, person_id: UUID, media_id: UUID) -> None:
        """Remove a specific person-media link (used on face reassignment)."""
        with get_db() as db:
            db.execute(text("""
                DELETE FROM media_persons
                WHERE media_id = :media_id AND person_id = :person_id
            """), {"media_id": str(media_id), "person_id": str(person_id)})
            db.commit()

    def delete(self, person_id: UUID) -> None:
        """Delete a person. CASCADE removes media_persons links automatically."""
        with get_db() as db:
            db.execute(
                text("DELETE FROM persons WHERE id = :pid"),
                {"pid": str(person_id)}
            )
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
