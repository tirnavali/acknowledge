import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import contextlib

# .env dosyasını oku
load_dotenv()
# Bağlantı adresini oluştur (PostgreSQL)
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# Motoru Başlat
engine = create_engine(DATABASE_URL)

# Oturum Fabrikası (Veritabanı ile konuşacak nesne)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Temel Model Sınıfı (Tüm tablolar bundan türeyecek)
Base = declarative_base()

# Veritabanı oturumu alıp kapatan yardımcı fonksiyon
@contextlib.contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()