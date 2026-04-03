import os
import sys
from sqlalchemy import text
from src.database import engine, Base, SessionLocal, get_db
# Modelleri import etmezseniz tablolar oluşmaz!
from src.models import Event, Media, Photo, Video, Pdf 

def init_db():
    print("⏳ Veritabanı bağlantısı kontrol ediliyor...")
    
    try:
        # 1. Bağlantı testi ve Eklentilerin Aktif Edilmesi
        with SessionLocal() as db:
            # Vektör araması (Face Rec) için gerekli eklenti
            db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # UUID üretimi için bazen gerekebilir (genellikle modern Postgres'te default vardır ama garanti olsun)
            db.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
            
            # Türkçe Arama Desteği (Unaccent)
            # Bu eklenti sayesinde 'ş' -> 's', 'ı' -> 'i' gibi dönüşümlerle aksansız arama yapılabilir
            db.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            
            db.commit()
            print("✅ Gerekli PostgreSQL eklentileri (vector, uuid, unaccent) aktif edildi.")

        # 2. Tabloların Oluşturulması
        # DİKKAT: drop_all satırı mevcut verileri siler! 
        # Geliştirme aşamasında şema değiştikçe temiz kurulum için kullanıyoruz.
        # Canlıya geçince bu satırı silmelisiniz.
        print("🗑️  Eski tablolar temizleniyor (Development Mode)...")
        #Base.metadata.drop_all(bind=engine)
        
        print("🏗️  Yeni tablolar oluşturuluyor...")
        Base.metadata.create_all(bind=engine)
        print("✅ Başarılı! 'events' ve 'medias' tabloları oluşturuldu.")

        # Add face_detected_at column to existing databases
        with SessionLocal() as db:
            db.execute(text(
                "ALTER TABLE medias ADD COLUMN IF NOT EXISTS face_detected_at TIMESTAMPTZ"
            ))
            db.execute(text(
                "ALTER TABLE face_detections ADD COLUMN IF NOT EXISTS person_cleared BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            db.execute(text("ALTER TABLE medias ADD COLUMN IF NOT EXISTS tags_en TEXT"))
            db.execute(text("ALTER TABLE medias ADD COLUMN IF NOT EXISTS tags_tr TEXT"))
            db.commit()
            print("✅ 'face_detected_at', 'person_cleared', 'tags_en', 'tags_tr' kolonları eklendi (veya zaten vardı).")

        # Migrate relative file_path values to absolute
        with get_db() as db:
            rows = db.execute(text("SELECT id, file_path FROM medias")).fetchall()
            # Build a set of all existing absolute paths for collision detection
            existing_abs = {
                os.path.normpath(os.path.abspath(r.file_path))
                for r in rows if r.file_path and os.path.isabs(r.file_path)
            }
            migrated = deleted = 0
            for row in rows:
                fp = row.file_path or ""
                if fp and not os.path.isabs(fp):
                    abs_fp = os.path.normpath(os.path.abspath(fp))
                    if abs_fp in existing_abs:
                        # An absolute-path record already exists — remove the relative duplicate
                        db.execute(
                            text("DELETE FROM medias WHERE id = :id"),
                            {"id": str(row.id)}
                        )
                        deleted += 1
                    else:
                        db.execute(
                            text("UPDATE medias SET file_path = :p WHERE id = :id"),
                            {"p": abs_fp, "id": str(row.id)}
                        )
                        existing_abs.add(abs_fp)
                        migrated += 1
            db.commit()
            print(f"✅ {migrated} kayıt mutlak yola dönüştürüldü, {deleted} yinelenen kayıt silindi.")

    except Exception as e:
        print(f"❌ HATA: Veritabanına bağlanılamadı.\nDetay: {e}")
        print("İpucu: Docker çalışıyor mu? .env dosyasındaki şifreler doğru mu?")

if __name__ == "__main__":
    init_db()