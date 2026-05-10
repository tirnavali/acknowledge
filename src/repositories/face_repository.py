"""
FaceRepository — CRUD for face_detections table.
Also supports pgvector cosine similarity search for automatic person matching.
"""
from __future__ import annotations
import uuid as uuid_module
from uuid import UUID
import numpy as np
from sqlalchemy import text
from src.database import get_db


class FaceRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_faces(self, media_id: UUID, face_results: list) -> list[UUID]:
        """
        Persist detected faces for a media item.
        Clears existing face rows for this media first (full replace).

        Args:
            media_id: UUID of the parent media.
            face_results: List of FaceResult from FaceAnalysisService.

        Returns:
            List of newly created face_detection UUIDs.
        """
        # Validate that media_id is actually a UUID
        if not isinstance(media_id, UUID):
            raise ValueError(f"Expected media_id to be a UUID, got {type(media_id)}")
        
        media_id_str = str(media_id)
        ids = []
        with get_db() as db:
            # Remove old detections
            db.execute(text("DELETE FROM face_detections WHERE media_id = :mid"), {"mid": media_id_str})

            for face in face_results:
                new_id = uuid_module.uuid4()
                embedding_list = face.embedding.tolist() if face.embedding is not None else None
                db.execute(text("""
                    INSERT INTO face_detections (id, media_id, bbox, embedding, timestamp_ms)
                    VALUES (:id, :media_id,
                            CAST(:bbox AS jsonb),
                            CAST(:emb AS vector),
                            :tms)
                """), {
                    "id": str(new_id),
                    "media_id": media_id_str,
                    "bbox": f'{{"x1":{face.x1},"y1":{face.y1},"x2":{face.x2},"y2":{face.y2}}}',
                    "emb": "[" + ",".join(str(v) for v in embedding_list) + "]" if embedding_list else None,
                    "tms": getattr(face, 'timestamp_ms', None),
                })
                ids.append(new_id)
            db.commit()
        return ids

    def assign_person(self, face_id: UUID, person_id: UUID) -> None:
        """Link a face detection to a known person and clear the cleared flag."""
        with get_db() as db:
            db.execute(text("""
                UPDATE face_detections SET person_id = :person_id, person_cleared = FALSE WHERE id = :face_id
            """), {"person_id": str(person_id), "face_id": str(face_id)})
            db.commit()

    def delete_faces_for_media(self, media_id: UUID) -> None:
        """Remove all face detection rows for a media item."""
        with get_db() as db:
            db.execute(
                text("DELETE FROM face_detections WHERE media_id = :mid"),
                {"mid": str(media_id)}
            )
            db.commit()

    def clear_person_for_face(self, face_id: UUID) -> None:
        """Set person_id = NULL and person_cleared = TRUE for a single face detection row."""
        with get_db() as db:
            db.execute(
                text("UPDATE face_detections SET person_id = NULL, person_cleared = TRUE WHERE id = :fid"),
                {"fid": str(face_id)}
            )
            db.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_faces_for_media(self, media_id: UUID) -> list[dict]:
        """
        Return all face detections for a media item with optional person name.

        Returns list of dicts with keys:
            id, bbox (dict), embedding (list|None), person_id, person_name
        """
        with get_db() as db:
            result = db.execute(text("""
                SELECT fd.id, fd.bbox, fd.embedding::text, fd.person_id, fd.person_cleared, fd.timestamp_ms,
                       p.name as person_name
                FROM face_detections fd
                LEFT JOIN persons p ON fd.person_id = p.id
                WHERE fd.media_id = :mid
                ORDER BY fd.timestamp_ms ASC, fd.created_at ASC
            """), {"mid": str(media_id)})
            rows = []
            for row in result.fetchall():
                d = dict(row._mapping)
                # Parse bbox from JSON string if needed
                if isinstance(d.get("bbox"), str):
                    import json
                    d["bbox"] = json.loads(d["bbox"])
                rows.append(d)
            return rows

    def find_similar_person(
        self,
        embedding: np.ndarray,
        threshold: float = 0.5,
    ) -> tuple[UUID | None, str | None]:
        """
        Search ALL labelled face embeddings for the closest match (global).
        Checks both face_detections (assigned faces) and persons.reference_embedding
        (persons registered without any matched media yet).
        Uses pgvector cosine distance (lower = more similar).
        """
        emb_list = embedding.tolist()
        emb_str = "[" + ",".join(str(v) for v in emb_list) + "]"
        with get_db() as db:
            result = db.execute(text("""
                SELECT person_id, name, dist FROM (
                    SELECT fd.person_id::text AS person_id, p.name,
                           (fd.embedding <=> CAST(:emb AS vector)) AS dist
                    FROM face_detections fd
                    JOIN persons p ON fd.person_id = p.id
                    WHERE fd.embedding IS NOT NULL AND fd.person_id IS NOT NULL
                    UNION ALL
                    SELECT p.id::text AS person_id, p.name,
                           (p.reference_embedding <=> CAST(:emb AS vector)) AS dist
                    FROM persons p
                    WHERE p.reference_embedding IS NOT NULL
                ) sub
                ORDER BY dist ASC
                LIMIT 1
            """), {"emb": emb_str})
            row = result.fetchone()
            if row and row.dist is not None and float(row.dist) < threshold:
                return UUID(str(row.person_id)), row.name
        return None, None

    def find_unassigned_faces_matching(
        self,
        embedding: np.ndarray,
        threshold: float = 0.5,
    ) -> list[dict]:
        """
        Return all unassigned face_detections whose embedding is within threshold
        of the given embedding. Used for the one-time person scan background job.

        Returns list of dicts with keys: face_id, media_id, dist.
        """
        emb_list = embedding.tolist()
        emb_str = "[" + ",".join(str(v) for v in emb_list) + "]"
        with get_db() as db:
            result = db.execute(text("""
                SELECT fd.id AS face_id, fd.media_id,
                       (fd.embedding <=> CAST(:emb AS vector)) AS dist
                FROM face_detections fd
                WHERE fd.person_id IS NULL
                  AND (fd.person_cleared IS NULL OR NOT fd.person_cleared)
                  AND fd.embedding IS NOT NULL
                  AND (fd.embedding <=> CAST(:emb AS vector)) < :threshold
                ORDER BY dist ASC
            """), {"emb": emb_str, "threshold": threshold})
            return [
                {"face_id": UUID(str(r.face_id)), "media_id": UUID(str(r.media_id)), "dist": float(r.dist)}
                for r in result.fetchall()
            ]
