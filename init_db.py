import os
import sys
from sqlalchemy import text
from src.database import engine, Base, SessionLocal, get_db
# Modelleri import etmezseniz tablolar oluşmaz!
from src.models import Event, Media, Photo, Video, Pdf 
from src.utils import path_util

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
            db.execute(text("ALTER TABLE medias ADD COLUMN IF NOT EXISTS star_rating SMALLINT NOT NULL DEFAULT 0"))
            db.execute(text("ALTER TABLE medias ADD COLUMN IF NOT EXISTS captioned_at TIMESTAMPTZ"))
            db.commit()
            print("✅ 'face_detected_at', 'person_cleared', 'tags_en', 'tags_tr', 'star_rating', 'captioned_at' kolonları eklendi (veya zaten vardı).")

        # Migrate absolute file_path values to relative (for cross-platform support)
        with get_db() as db:
            rows = db.execute(text("SELECT id, file_path FROM medias")).fetchall()
            seen_in_loop = set()
            migrated = deleted = 0
            for row in rows:
                fp = row.file_path or ""
                if not fp:
                    continue
                
                # Always try to convert to DB (relative) format
                rel_fp = path_util.to_db_path(fp)
                
                # 1. Check if we've already processed this path in this loop
                # 2. Check if another record already has this relative path in the DB
                is_duplicate = rel_fp in seen_in_loop
                if not is_duplicate:
                    # Check DB for pre-existing relative path (from another record)
                    overlap = db.execute(
                        text("SELECT id FROM medias WHERE file_path = :p AND id != :id"),
                        {"p": rel_fp, "id": str(row.id)}
                    ).fetchone()
                    if overlap:
                        is_duplicate = True

                if is_duplicate:
                    # Duplicate record (e.g. from interrupted migration, OS switch, or normalization overlap)
                    db.execute(
                        text("DELETE FROM medias WHERE id = :id"),
                        {"id": str(row.id)}
                    )
                    deleted += 1
                else:
                    if rel_fp != fp:
                        db.execute(
                            text("UPDATE medias SET file_path = :p WHERE id = :id"),
                            {"p": rel_fp, "id": str(row.id)}
                        )
                        migrated += 1
                    seen_in_loop.add(rel_fp)
            db.commit()
            print(f"✅ {migrated} kayıt bağıl yola dönüştürüldü (cross-platform), {deleted} yinelenen kayıt silindi.")

    except Exception as e:
        print(f"❌ HATA: Veritabanına bağlanılamadı.\nDetay: {e}")
        print("İpucu: Docker çalışıyor mu? .env dosyasındaki şifreler doğru mu?")

if __name__ == "__main__":
    init_db()