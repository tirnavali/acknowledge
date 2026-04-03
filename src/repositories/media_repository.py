# src/repositories/media_repository.py
import os
from uuid import UUID
from src.database import get_db
from sqlalchemy import text


def sanitize_str(value):
    """Remove NUL (0x00) characters that PostgreSQL doesn't allow in text fields."""
    if isinstance(value, str):
        return value.replace('\x00', '').strip()
    return value or ""


def _build_prefix_tsquery(query: str) -> str:
    """Convert a plain query into a prefix tsquery: 'anka pol' → 'anka:* & pol:*'."""
    words = [w for w in query.strip().split() if w]
    return ' & '.join(f'{w}:*' for w in words)


def _abs(path: str) -> str:
    """Normalize a file path to absolute form."""
    return os.path.normpath(os.path.abspath(path)) if path else path


class MediaRepository:
    def get_by_file_path(self, file_path: str) -> dict | None:
        """Find a media record by its file_path."""
        with get_db() as db:
            result = db.execute(
                text("SELECT * FROM medias WHERE file_path = :file_path"),
                {"file_path": _abs(sanitize_str(file_path))}
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

    def save_captions(self, media_id: UUID, result: "CaptionResult") -> None:
        """Update caption and tag fields for a media record."""
        with get_db() as db:
            db.execute(text("""
                UPDATE medias
                SET caption_en = :caption_en, caption_tr = :caption_tr,
                    tags_en    = :tags_en,    tags_tr    = :tags_tr
                WHERE id = :media_id
            """), {
                "media_id": str(media_id),
                "caption_en": sanitize_str(result.caption_en),
                "caption_tr": sanitize_str(result.caption_tr),
                "tags_en":    sanitize_str(result.tags_en),
                "tags_tr":    sanitize_str(result.tags_tr),
            })
            db.commit()

    def ensure_media_exists(self, event_id: UUID, file_path: str, media_type: str = "photo") -> UUID:
        """Ensure a media record exists for the given file_path. Returns the media_id."""
        clean_path = _abs(sanitize_str(file_path))
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

    def get_all_for_person(self, person_id: UUID) -> list[dict]:
        """Return all media records linked to a person via media_persons."""
        with get_db() as db:
            result = db.execute(text("""
                SELECT m.*
                FROM medias m
                JOIN media_persons mp ON m.id = mp.media_id
                WHERE mp.person_id = :person_id
                ORDER BY m.file_path
            """), {"person_id": str(person_id)})
            return [dict(row._mapping) for row in result.fetchall()]

    def mark_face_detected(self, media_id: UUID) -> None:
        """Set face_detected_at = now for a media record."""
        with get_db() as db:
            db.execute(
                text("UPDATE medias SET face_detected_at = now() WHERE id = :mid"),
                {"mid": str(media_id)}
            )
            db.commit()

    def search_across_events(self, query: str) -> list[dict]:
        """PostgreSQL FTS across all IPTC fields + persons. Returns rows with 'rank'.
        Supports prefix wildcard: 'anka' matches 'ankara', 'pol' matches 'polis', etc.
        """
        clean = sanitize_str(query)
        tsq = _build_prefix_tsquery(clean)
        with get_db() as db:
            result = db.execute(text("""
                WITH person_names AS (
                    SELECT mp.media_id, STRING_AGG(p.name, ' ') AS names
                    FROM media_persons mp
                    JOIN persons p ON mp.person_id = p.id
                    GROUP BY mp.media_id
                ),
                docs AS (
                    SELECT
                        m.*,
                        e.name  AS event_name,
                        COALESCE(pn.names, '') AS person_names,
                        to_tsvector('simple',
                            COALESCE(m.iptc_headline, '')               || ' ' ||
                            COALESCE(m.iptc_caption, '')                || ' ' ||
                            COALESCE(m.iptc_keywords, '')               || ' ' ||
                            COALESCE(m.iptc_object_name, '')            || ' ' ||
                            COALESCE(m.iptc_city, '')                   || ' ' ||
                            COALESCE(m.iptc_state, '')                  || ' ' ||
                            COALESCE(m.iptc_country, '')                || ' ' ||
                            COALESCE(m.iptc_credit, '')                 || ' ' ||
                            COALESCE(m.iptc_source, '')                 || ' ' ||
                            COALESCE(m.iptc_byline, '')                 || ' ' ||
                            COALESCE(m.iptc_byline_title, '')           || ' ' ||
                            COALESCE(m.iptc_category, '')               || ' ' ||
                            COALESCE(m.iptc_writer, '')                 || ' ' ||
                            COALESCE(m.iptc_copyright, '')              || ' ' ||
                            COALESCE(m.iptc_supplemental_categories,'') || ' ' ||
                            COALESCE(pn.names, '')                      || ' ' ||
                            COALESCE(e.name, '')                        || ' ' ||
                            COALESCE(m.file_path, '')
                        ) AS doc
                    FROM medias m
                    JOIN events e ON m.event_id = e.id
                    LEFT JOIN person_names pn ON m.id = pn.media_id
                )
                SELECT *,
                    ts_rank(doc, to_tsquery('simple', :tsq)) AS rank
                FROM docs
                WHERE doc @@ to_tsquery('simple', :tsq)
                ORDER BY rank DESC
            """), {"tsq": tsq})
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

