# src/repositories/media_repository.py
from uuid import UUID
from src.database import get_db
from sqlalchemy import text


def sanitize_str(value):
    """Remove NUL (0x00) characters that PostgreSQL doesn't allow in text fields."""
    if isinstance(value, str):
        return value.replace('\x00', '').strip()
    return value or ""


class MediaRepository:
    def get_by_file_path(self, file_path: str) -> dict | None:
        """Find a media record by its file_path."""
        with get_db() as db:
            result = db.execute(
                text("SELECT * FROM medias WHERE file_path = :file_path"),
                {"file_path": sanitize_str(file_path)}
            )
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None

    def get_by_id(self, media_id: UUID) -> dict | None:
        """Get a media record by ID."""
        with get_db() as db:
            result = db.execute(
                text("SELECT * FROM medias WHERE id = :id"),
                {"id": str(media_id)}
            )
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None

    def get_iptc_data(self, file_path: str) -> dict | None:
        """Get IPTC data stored in DB for a given file path. Returns None if not found."""
        with get_db() as db:
            result = db.execute(text("""
                SELECT id, iptc_headline, iptc_caption, iptc_keywords,
                       iptc_object_name, iptc_city, iptc_state, iptc_country,
                       iptc_credit, iptc_source, iptc_copyright, iptc_writer,
                       iptc_byline, iptc_byline_title, iptc_date_created,
                       iptc_category, iptc_supplemental_categories
                FROM medias WHERE file_path = :file_path
            """), {"file_path": sanitize_str(file_path)})
            row = result.fetchone()
            if row:
                d = dict(row._mapping)
                # Only return if at least one IPTC field is populated
                has_data = any(
                    d.get(col) for col in d
                    if col.startswith('iptc_')
                )
                return d if has_data else None
            return None

    def save_iptc(self, media_id: UUID, iptc_data: dict) -> None:
        """Update IPTC fields for a media record."""
        # Sanitize all values
        clean = {k: sanitize_str(v) for k, v in iptc_data.items()}
        with get_db() as db:
            db.execute(text("""
                UPDATE medias SET
                    iptc_headline = :headline,
                    iptc_caption = :caption,
                    iptc_keywords = :keywords,
                    iptc_object_name = :object_name,
                    iptc_city = :city,
                    iptc_state = :state,
                    iptc_country = :country,
                    iptc_credit = :credit,
                    iptc_source = :source,
                    iptc_copyright = :copyright,
                    iptc_writer = :writer,
                    iptc_byline = :byline,
                    iptc_byline_title = :byline_title,
                    iptc_date_created = :date_created,
                    iptc_category = :category,
                    iptc_supplemental_categories = :supplemental_categories
                WHERE id = :media_id
            """), {
                "media_id": str(media_id),
                "headline": clean.get("Headline", ""),
                "caption": clean.get("Caption", ""),
                "keywords": clean.get("Keywords", ""),
                "object_name": clean.get("Object Name", ""),
                "city": clean.get("City", ""),
                "state": clean.get("State", ""),
                "country": clean.get("Country", ""),
                "credit": clean.get("Credit", ""),
                "source": clean.get("Source", ""),
                "copyright": clean.get("Copyright", ""),
                "writer": clean.get("Writer", ""),
                "byline": clean.get("By-line", ""),
                "byline_title": clean.get("By-line Title", ""),
                "date_created": clean.get("Date Created", ""),
                "category": clean.get("Category", ""),
                "supplemental_categories": clean.get("Supplemental Categories", ""),
            })
            db.commit()

    def ensure_media_exists(self, event_id: UUID, file_path: str, media_type: str = "photo") -> UUID:
        """Ensure a media record exists for the given file_path. Returns the media_id."""
        clean_path = sanitize_str(file_path)
        with get_db() as db:
            # Check if it already exists
            result = db.execute(
                text("SELECT id FROM medias WHERE file_path = :file_path"),
                {"file_path": clean_path}
            )
            row = result.fetchone()
            if row:
                return row.id if isinstance(row.id, UUID) else UUID(str(row.id))
            
            # Create new record
            import uuid
            new_id = uuid.uuid4()
            db.execute(text("""
                INSERT INTO medias (id, event_id, file_path, media_type)
                VALUES (:id, :event_id, :file_path, :media_type)
            """), {
                "id": str(new_id),
                "event_id": str(event_id),
                "file_path": clean_path,
                "media_type": media_type,
            })
            db.commit()
            return new_id

    def get_all_for_event(self, event_id: UUID) -> list[dict]:
        """Return all media records and their metadata for a given event."""
        with get_db() as db:
            result = db.execute(
                text("SELECT * FROM medias WHERE event_id = :event_id"),
                {"event_id": str(event_id)}
            )
            return [dict(row._mapping) for row in result.fetchall()]

    def get_file_paths_for_event(self, event_id: UUID) -> set:
        """Return a set of normalised file_paths stored in DB for the given event."""
        import os
        with get_db() as db:
            result = db.execute(
                text("SELECT file_path FROM medias WHERE event_id = :event_id"),
                {"event_id": str(event_id)}
            )
            return {os.path.normpath(row.file_path) for row in result.fetchall()}

