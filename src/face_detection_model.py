"""
FaceDetection model — stores per-face bounding box and embedding for a media item.
"""
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from .database import Base


class FaceDetection(Base):
    __tablename__ = "face_detections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    media_id = Column(UUID(as_uuid=True), ForeignKey("medias.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)

    # Bounding box stored as normalised floats (0.0–1.0 of original image dimensions)
    # {x1, y1, x2, y2}
    bbox = Column(JSON, nullable=False)

    # 512-dim ArcFace embedding from insightface
    embedding = Column(Vector(512), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    media = relationship("Media", back_populates="face_detections")
    person = relationship("Person")

    def __repr__(self):
        return f"<FaceDetection(media_id={self.media_id}, person_id={self.person_id})>"
