import sys
from sqlalchemy import text
from src.database import engine, Base, SessionLocal
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
        
    except Exception as e:
        print(f"❌ HATA: Veritabanına bağlanılamadı.\nDetay: {e}")
        print("İpucu: Docker çalışıyor mu? .env dosyasındaki şifreler doğru mu?")

if __name__ == "__main__":
    init_db()