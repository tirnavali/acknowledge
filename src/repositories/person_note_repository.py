from uuid import UUID
from sqlalchemy import text
from src.database import get_db


class PersonNoteRepository:

    def upsert(self, person_id: UUID, media_id: UUID, note: str) -> None:
        with get_db() as db:
            db.execute(text("""
                INSERT INTO person_notes (id, person_id, media_id, note)
                VALUES (gen_random_uuid(), :pid, :mid, :note)
                ON CONFLICT (person_id, media_id)
                DO UPDATE SET note = EXCLUDED.note, updated_at = now()
            """), {"pid": str(person_id), "mid": str(media_id), "note": note})
            db.commit()

    def get(self, person_id: UUID, media_id: UUID) -> str:
        with get_db() as db:
            row = db.execute(text("""
                SELECT note FROM person_notes
                WHERE person_id = :pid AND media_id = :mid
            """), {"pid": str(person_id), "mid": str(media_id)}).fetchone()
            return row.note if row else ""

    def search_notes(self, query: str) -> list[dict]:
        """
        Full-text search across note content.
        Returns rows with: person_id, person_name, media_id, file_path, note
        """
        with get_db() as db:
            rows = db.execute(text("""
                SELECT pn.person_id, p.name AS person_name,
                       pn.media_id, m.file_path, pn.note
                FROM person_notes pn
                JOIN persons p ON pn.person_id = p.id
                JOIN medias  m ON pn.media_id  = m.id
                WHERE pn.note ILIKE :q
                ORDER BY p.name, m.file_path
            """), {"q": f"%{query}%"}).fetchall()
            return [dict(r._mapping) for r in rows]
