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
