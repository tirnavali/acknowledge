# src/repositories/media_repository.py
import os
from uuid import UUID
from src.database import get_db
from sqlalchemy import text
from src.utils import path_util


def sanitize_str(value):
    """Remove NUL (0x00) characters that PostgreSQL doesn't allow in text fields."""
    if isinstance(value, str):
        return value.replace('\x00', '').strip()
    return value or ""


def _build_prefix_tsquery(query: str) -> str:
    """Convert a plain query into a prefix tsquery: 'anka pol' → 'anka:* & pol:*'.
    Strips non-alphanumeric characters so 'KURT0942.jpg' becomes 'KURT0942:*' without error.
    Returns empty string if no valid words remain (caller must handle this).
    """
    import re
    words = [re.sub(r'[^a-zA-Z0-9\u00C0-\u024F]', '', w) for w in query.strip().split()]
    words = [w for w in words if w]
    return ' & '.join(f'{w}:*' for w in words)




def _abs(path: str) -> str:
    """Normalize a file path to DB format (relative or normalized absolute)."""
    if not path:
        return ""
    return path_util.to_db_path(path)


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
                SELECT id, title, iptc_headline, iptc_caption, iptc_keywords,
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
                has_data = any([
                    d.get('title'),
                    *[d.get(col) for col in d if col.startswith('iptc_')]
                ])
                return d if has_data else None
            return None

    def save_iptc(self, media_id: UUID, iptc_data: dict) -> None:
        """Update IPTC fields for a media record."""
        # Sanitize all values
        clean = {k: sanitize_str(v) for k, v in iptc_data.items()}
        with get_db() as db:
            db.execute(text("""
                UPDATE medias SET
                    title = :title,
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
                "title": clean.get("Title", ""),
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
                    tags_en    = :tags_en,    tags_tr    = :tags_tr,
                    captioned_at = now()
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
            # We use PostgreSQL's ON CONFLICT to avoid race conditions.
            # 1. Try to INSERT. If file_path exists, DO NOTHING.
            import uuid
            new_id = uuid.uuid4()
            
            result = db.execute(text("""
                INSERT INTO medias (id, event_id, file_path, media_type)
                VALUES (:id, :event_id, :file_path, :media_type)
                ON CONFLICT (file_path) DO NOTHING
                RETURNING id
            """), {
                "id": str(new_id),
                "event_id": str(event_id),
                "file_path": clean_path,
                "media_type": media_type,
            })
            
            row = result.fetchone()
            if row:
                db.commit()
                # Return the ID from the INSERT
                val = row[0] if hasattr(row, "__getitem__") else row.id
                return val if isinstance(val, UUID) else UUID(str(val))
            
            # 2. If INSERT returned nothing (conflict), fetch the existing ID.
            result = db.execute(
                text("SELECT id FROM medias WHERE file_path = :file_path"),
                {"file_path": clean_path}
            )
            row = result.fetchone()
            db.commit()
            if row:
                val = row[0] if hasattr(row, "__getitem__") else row.id
                return val if isinstance(val, UUID) else UUID(str(val))
            
            raise RuntimeError(f"Failed to ensure media exists: {clean_path}")

    def get_all_for_event(self, event_id: UUID) -> list[dict]:
        """Return all media records and their metadata for a given event."""
        with get_db() as db:
            result = db.execute(text("""
                WITH pnames AS (
                    SELECT mp.media_id, STRING_AGG(p.name, E'\n') AS names
                    FROM media_persons mp
                    JOIN persons p ON mp.person_id = p.id
                    GROUP BY mp.media_id
                )
                SELECT m.*, COALESCE(pn.names, '') AS person_names
                FROM medias m
                LEFT JOIN pnames pn ON m.id = pn.media_id
                WHERE m.event_id = :event_id
            """), {"event_id": str(event_id)})
            return [dict(row._mapping) for row in result.fetchall()]

    def get_all_ordered_by_date(self) -> list[dict]:
        """Return all media records across all events ordered by IPTC date then insert time."""
        with get_db() as db:
            result = db.execute(text(
                "SELECT * FROM medias ORDER BY iptc_date_created DESC NULLS LAST, created_at DESC NULLS LAST, file_path ASC"
            ))
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

    def mark_captioned(self, media_id: UUID) -> None:
        """Set captioned_at = now for a media record."""
        with get_db() as db:
            db.execute(
                text("UPDATE medias SET captioned_at = now() WHERE id = :mid"),
                {"mid": str(media_id)}
            )
            db.commit()

    def search_across_events(self, query: str) -> list[dict]:
        """PostgreSQL FTS across all metadata fields + ILIKE exact-phrase boost.

        All queries use AND-of-words prefix matching so every word must appear
        somewhere in the document (position-agnostic).  When the raw query string
        also appears as a literal substring (case-insensitive), that result is
        ranked 2.0 and floats to the top — giving "exact phrase" prioritisation
        without restricting recall.
        """
        raw_clean = sanitize_str(query)
        # For ILIKE exact boost, we strip quotes so that "mavi kravat" matches 
        # the phrase 'mavi kravat' in the text.
        boost_query = raw_clean.replace('"', '').replace("'", "").strip()
        tsq = _build_prefix_tsquery(raw_clean)

        with get_db() as db:
            if not tsq:
                # Only punctuation/special chars remain — ILIKE on filename only.
                result = db.execute(text("""
                    SELECT m.*, e.name AS event_name,
                           COALESCE(pn.names, '') AS person_names,
                           0.05::float AS rank
                    FROM medias m
                    JOIN events e ON m.event_id = e.id
                    LEFT JOIN (
                        SELECT mp.media_id, STRING_AGG(p.name, E'\n') AS names
                        FROM media_persons mp
                        JOIN persons p ON mp.person_id = p.id
                        GROUP BY mp.media_id
                    ) pn ON m.id = pn.media_id
                    WHERE m.file_path ILIKE '%' || :raw || '%'
                    ORDER BY m.file_path
                """), {"raw": boost_query})
            else:
                result = db.execute(text("""
                    WITH person_names AS (
                        SELECT mp.media_id, STRING_AGG(p.name, E'\n') AS names
                        FROM media_persons mp
                        JOIN persons p ON mp.person_id = p.id
                        GROUP BY mp.media_id
                    ),
                    docs AS (
                        SELECT
                            m.*,
                            e.name AS event_name,
                            COALESCE(pn.names, '') AS person_names,
                            (
                                COALESCE(m.title, '')                       || ' ' ||
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
                                COALESCE(m.caption_tr, '')                  || ' ' ||
                                COALESCE(m.caption_en, '')                  || ' ' ||
                                COALESCE(m.tags_tr, '')                     || ' ' ||
                                COALESCE(m.tags_en, '')                     || ' ' ||
                                COALESCE(pn.names, '')                      || ' ' ||
                                COALESCE(e.name, '')                        || ' ' ||
                                COALESCE(m.file_path, '')                   || ' ' ||
                                COALESCE(m.text_content, '')
                            ) AS concat_text,
                            to_tsvector('simple',
                                COALESCE(m.title, '')                       || ' ' ||
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
                                COALESCE(m.caption_tr, '')                  || ' ' ||
                                COALESCE(m.caption_en, '')                  || ' ' ||
                                COALESCE(m.tags_tr, '')                     || ' ' ||
                                COALESCE(m.tags_en, '')                     || ' ' ||
                                COALESCE(pn.names, '')                      || ' ' ||
                                COALESCE(e.name, '')                        || ' ' ||
                                COALESCE(m.file_path, '')                   || ' ' ||
                                COALESCE(m.text_content, '')
                            ) AS doc
                        FROM medias m
                        JOIN events e ON m.event_id = e.id
                        LEFT JOIN person_names pn ON m.id = pn.media_id
                    )
                    SELECT *,
                        CASE
                            WHEN concat_text ILIKE '%' || :raw || '%' THEN 2.0
                            ELSE ts_rank(doc, to_tsquery('simple', :tsq))
                        END AS rank
                    FROM docs
                    WHERE doc @@ to_tsquery('simple', :tsq)
                       OR (LENGTH(:raw) > 0 AND concat_text ILIKE '%' || :raw || '%')
                    ORDER BY rank DESC
                """), {"tsq": tsq, "raw": boost_query})
            return [dict(row._mapping) for row in result.fetchall()]

    def save_star_rating(self, media_id: UUID, rating: int) -> None:
        """Persist a star rating (0–5) for a media record."""
        rating = max(0, min(5, int(rating)))
        with get_db() as db:
            db.execute(
                text("UPDATE medias SET star_rating = :r WHERE id = :id"),
                {"r": rating, "id": str(media_id)},
            )
            db.commit()

    def save_document_media(
        self,
        event_id: UUID,
        file_path: str,
        title: str | None = None,
        text_content: str | None = None,
        technical_metadata: dict | None = None,
    ) -> UUID:
        """Insert or update a document media record including text content."""
        import uuid as _uuid
        import json
        clean_path = _abs(sanitize_str(file_path))
        new_id = _uuid.uuid4()
        tech_meta_json = json.dumps(technical_metadata) if technical_metadata else None
        with get_db() as db:
            result = db.execute(text("""
                INSERT INTO medias (id, event_id, file_path, media_type, title, text_content, technical_metadata)
                VALUES (:id, :event_id, :file_path, 'document', :title, :text_content, CAST(:technical_metadata AS jsonb))
                ON CONFLICT (file_path) DO UPDATE SET
                    title = EXCLUDED.title,
                    text_content = EXCLUDED.text_content,
                    technical_metadata = EXCLUDED.technical_metadata
                RETURNING id
            """), {
                "id": str(new_id),
                "event_id": str(event_id),
                "file_path": clean_path,
                "title": sanitize_str(title) if title else None,
                "text_content": sanitize_str(text_content) if text_content else None,
                "technical_metadata": tech_meta_json,
            })
            row = result.fetchone()
            db.commit()
            if row:
                val = row[0] if hasattr(row, "__getitem__") else row.id
                return val if isinstance(val, UUID) else UUID(str(val))
            raise RuntimeError(f"Failed to save document media: {clean_path}")

    def save_video_media(
        self,
        event_id: UUID,
        file_path: str,
        title: str | None = None,
        technical_metadata: dict | None = None,
        iptc_date_created: str | None = None,
    ) -> UUID:
        """Insert or update a video media record."""
        import uuid as _uuid
        import json
        clean_path = _abs(sanitize_str(file_path))
        new_id = _uuid.uuid4()
        tech_meta_json = json.dumps(technical_metadata) if technical_metadata else None
        with get_db() as db:
            result = db.execute(text("""
                INSERT INTO medias (id, event_id, file_path, media_type, title, technical_metadata, iptc_date_created)
                VALUES (:id, :event_id, :file_path, 'video', :title, CAST(:technical_metadata AS jsonb), :iptc_date_created)
                ON CONFLICT (file_path) DO UPDATE SET
                    title = EXCLUDED.title,
                    technical_metadata = EXCLUDED.technical_metadata,
                    iptc_date_created = EXCLUDED.iptc_date_created
                RETURNING id
            """), {
                "id": str(new_id),
                "event_id": str(event_id),
                "file_path": clean_path,
                "title": sanitize_str(title) if title else None,
                "technical_metadata": tech_meta_json,
                "iptc_date_created": iptc_date_created,
            })
            row = result.fetchone()
            db.commit()
            if row:
                val = row[0] if hasattr(row, "__getitem__") else row.id
                return val if isinstance(val, UUID) else UUID(str(val))
            raise RuntimeError(f"Failed to save video media: {clean_path}")

    def get_file_paths_for_event(self, event_id: UUID) -> set:
        """Return a set of normalised file_paths stored in DB for the given event."""
        import os
        with get_db() as db:
            result = db.execute(
                text("SELECT file_path FROM medias WHERE event_id = :event_id"),
                {"event_id": str(event_id)}
            )
            return {os.path.normpath(row.file_path) for row in result.fetchall()}

    def delete(self, media_id: UUID, file_path: str | None = None) -> None:
        """Delete a media record and remove vault file + thumbnail from disk.
        Database-level ON DELETE CASCADE handles related face_detections, media_persons, etc.
        """
        with get_db() as db:
            db.execute(
                text("DELETE FROM medias WHERE id = :id"),
                {"id": str(media_id)},
            )
            db.commit()

        if file_path:
            abs_path = path_util.from_db_path(file_path)
            if os.path.exists(abs_path):
                os.remove(abs_path)
            thumb = os.path.join(
                os.path.dirname(abs_path), ".thumbnails",
                os.path.basename(abs_path) + ".thumb.jpg",
            )
            if os.path.exists(thumb):
                os.remove(thumb)

    def apply_schema_migrations(self) -> None:
        """Apply necessary schema updates (adding columns, enforcing constraints)."""
        iptc_columns = [
            ("iptc_headline", "VARCHAR(500)"),
            ("iptc_caption", "TEXT"),
            ("iptc_keywords", "TEXT"),
            ("iptc_object_name", "VARCHAR(500)"),
            ("iptc_city", "VARCHAR(250)"),
            ("iptc_state", "VARCHAR(250)"),
            ("iptc_country", "VARCHAR(250)"),
            ("iptc_credit", "VARCHAR(500)"),
            ("iptc_source", "VARCHAR(500)"),
            ("iptc_copyright", "VARCHAR(500)"),
            ("iptc_writer", "VARCHAR(250)"),
            ("iptc_byline", "VARCHAR(250)"),
            ("iptc_byline_title", "VARCHAR(250)"),
            ("iptc_date_created", "VARCHAR(50)"),
            ("iptc_category", "VARCHAR(100)"),
            ("iptc_supplemental_categories", "VARCHAR(500)"),
            ("title", "VARCHAR(500)"),
            ("tags_en", "TEXT"),
            ("tags_tr", "TEXT"),
        ]
        
        with get_db() as db:
            # 1. Add missing IPTC columns
            for col_name, col_type in iptc_columns:
                try:
                    db.execute(text(f"ALTER TABLE medias ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                except Exception:
                    pass
            
            # 2. Add timestamp_ms to face_detections
            try:
                db.execute(text("ALTER TABLE face_detections ADD COLUMN IF NOT EXISTS timestamp_ms FLOAT"))
            except Exception:
                pass
                
            # 3. Enforce ON DELETE CASCADE for all tables that reference medias.id
            constraints = [
                ("face_detections", "face_detections_media_id_fkey"),
                ("media_persons", "media_persons_media_id_fkey"),
                ("person_notes", "person_notes_media_id_fkey"),
            ]
            
            for table, conname in constraints:
                db.execute(text(f"""
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{conname}') THEN
                            EXECUTE 'ALTER TABLE {table} DROP CONSTRAINT {conname}';
                        END IF;
                        EXECUTE 'ALTER TABLE {table} ADD CONSTRAINT {conname} 
                            FOREIGN KEY (media_id) REFERENCES medias(id) ON DELETE CASCADE';
                    END $$;
                """))
            
            db.commit()

