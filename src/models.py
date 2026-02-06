import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from .database import Base
import enum

class MediaType(str, enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"
    PDF = "pdf"
    TRANSCRIPT = "transcript"

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
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    
    media_type = Column(String, nullable=False) # Polimorfik ayrıştırıcı
    file_path = Column(String, unique=True, nullable=False)
    
    caption_tr = Column(Text, nullable=True)
    caption_en = Column(Text, nullable=True)
    technical_metadata = Column(JSONB, nullable=True)
    text_content = Column(Text, nullable=True)
    face_encoding = Column(Vector(128), nullable=True)

    event = relationship("Event", back_populates="medias")
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