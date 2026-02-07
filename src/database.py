import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import contextlib

# .env dosyasını oku
load_dotenv()

# Veritabanı yapılandırmasını kontrol et
def validate_db_config():
    """Validate that all required database environment variables are set."""
    required_vars = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        error_msg = f"""
╔══════════════════════════════════════════════════════════════╗
║           VERİTABANI YAPILANDIRMA HATASI                     ║
╚══════════════════════════════════════════════════════════════╝

❌ Eksik ortam değişkenleri: {', '.join(missing_vars)}

📝 Çözüm adımları:
   1. Proje kök dizininde '.env' dosyası oluşturun
   2. Aşağıdaki değişkenleri ekleyin:
   
      DB_USER=your_username
      DB_PASSWORD=your_password
      DB_HOST=localhost
      DB_PORT=5432
      DB_NAME=your_database_name
      MEDIA_VAULT_PATH=image_vault
   
   3. Docker Desktop'ı yükleyin ve başlatın
   4. Terminal'de şu komutu çalıştırın:
      docker-compose up -d

💡 İpucu: docker-compose.yml dosyasındaki ayarlarla eşleştiğinden emin olun.
"""
        print(error_msg)
        return False, error_msg
    
    return True, None

# Yapılandırmayı doğrula
is_valid, error_message = validate_db_config()
if not is_valid:
    # Hata mesajını sakla ama henüz çıkma - app.py'de göstereceğiz
    DATABASE_URL = None
    engine = None
else:
    # Bağlantı adresini oluştur (PostgreSQL)
    DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    
    try:
        # Motoru Başlat
        engine = create_engine(DATABASE_URL)
    except Exception as e:
        print(f"❌ Veritabanı motoru oluşturulamadı: {e}")
        engine = None

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