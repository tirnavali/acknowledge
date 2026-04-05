import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum, Boolean, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from .database import Base
import enum

# Import FaceDetection so create_all picks it up
from .face_detection_model import FaceDetection  # noqa: F401

class MediaType(str, enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"
    PDF = "pdf"
    TRANSCRIPT = "transcript"

# Junction table for N-to-N: Media <-> Person
media_persons = Table(
    "media_persons",
    Base.metadata,
    Column("media_id", UUID(as_uuid=True), ForeignKey("medias.id", ondelete="CASCADE"), primary_key=True),
    Column("person_id", UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True),
)

class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # İstenilen Alanlar
    name = Column(String(250), nullable=False, index=True) # Arama yapılır diye index ekledim
    event_date = Column(DateTime(timezone=True), nullable=True) # Etkinliğin gerçekleştiği tarih
    imported_folder_path = Column(String, nullable=False) # İçeri alınacak medya klasörünün dosya yolu
    vault_folder_path = Column(String, nullable=False) # İçeri alınan medya klasörünün uygulamadaki dosya yolu
    import_success = Column(Boolean, nullable=False, default=False) # İçeri alma işleminin başarılı olup olmadığı
    description = Column(Text, nullable=True) # Etkinlik notları
    
    # İlişkiler: Bir etkinliğin çok medyası olur
    # cascade="all, delete" -> Etkinlik silinirse dosyaları da veritabanından silinsin
    medias = relationship("Media", back_populates="event", cascade="all, delete-orphan")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Event(name='{self.name}')>"


class Media(Base):
    __tablename__ = "medias"

    # DEĞİŞİKLİK BURADA: Integer yerine UUID
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Key tipi de UUID olmalı
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    
    media_type = Column(String, nullable=False) # Polimorfik ayrıştırıcı
    file_path = Column(String, unique=True, nullable=False)
    title = Column(String(500), nullable=True)
    
    caption_tr = Column(Text, nullable=True)
    caption_en = Column(Text, nullable=True)
    technical_metadata = Column(JSONB, nullable=True)
    text_content = Column(Text, nullable=True)
    face_encoding = Column(Vector(128), nullable=True)
    face_detected_at = Column(DateTime(timezone=True), nullable=True)

    # IPTC Metadata Columns
    iptc_headline = Column(String(500), nullable=True)
    iptc_caption = Column(Text, nullable=True)
    iptc_keywords = Column(Text, nullable=True)
    iptc_object_name = Column(String(500), nullable=True)
    iptc_city = Column(String(250), nullable=True)
    iptc_state = Column(String(250), nullable=True)
    iptc_country = Column(String(250), nullable=True)
    iptc_credit = Column(String(500), nullable=True)
    iptc_source = Column(String(500), nullable=True)
    iptc_copyright = Column(String(500), nullable=True)
    iptc_writer = Column(String(250), nullable=True)
    iptc_byline = Column(String(250), nullable=True)
    iptc_byline_title = Column(String(250), nullable=True)
    iptc_date_created = Column(String(50), nullable=True)
    iptc_category = Column(String(100), nullable=True)
    iptc_supplemental_categories = Column(String(500), nullable=True)

    event = relationship("Event", back_populates="medias")
    persons = relationship("Person", secondary=media_persons, back_populates="medias")
    face_detections = relationship("FaceDetection", back_populates="media", cascade="all, delete-orphan")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Polimorfizm Ayarları (Değişmedi)
    __mapper_args__ = {
        'polymorphic_identity': 'media',
        'polymorphic_on': media_type
    }

# Alt Sınıflar (Polimorfik)
class Video(Media):
    __mapper_args__ = {'polymorphic_identity': 'video'}

class Photo(Media):
    __mapper_args__ = {'polymorphic_identity': 'photo'}

class Pdf(Media):
    __mapper_args__ = {'polymorphic_identity': 'pdf'}

class Transcript(Media):
    __mapper_args__ = {'polymorphic_identity': 'transcript'}


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(250), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medias = relationship("Media", secondary=media_persons, back_populates="persons")

    def __repr__(self):
        return f"<Person(name='{self.name}')>"


class PersonNote(Base):
    __tablename__ = "person_notes"

    id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    media_id  = Column(UUID(as_uuid=True), ForeignKey("medias.id",  ondelete="CASCADE"), nullable=False)
    note      = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("person_id", "media_id", name="uq_person_note"),)