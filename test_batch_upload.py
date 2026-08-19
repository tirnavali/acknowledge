"""
test_batch_upload.py — Automated verification of Batch Import & Duplicate Prevention features.
"""

import os
import sys
import datetime
from PySide6 import QtGui

app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(sys.argv)

from src.utils.folder_scanner_util import (
    parse_date_and_name_from_folder,
    format_event_name,
    NamingTemplate,
    scan_subfolders,
    sanitize_folder_name,
)
from src.utils.pdf_util import (
    generate_pdf_thumbnail,
    extract_pdf_text,
    extract_pdf_metadata,
)
from src.utils.document_util import (
    generate_document_thumbnail,
    extract_docx_text,
    extract_doc_metadata,
)


def test_date_parsing_and_duplicate_prevention():
    print("🧪 Test 1: Tarih Ayrıştırma ve İsim Formatlama Testi...")

    # Case 1: 01.01.2024 divan toplantısı
    d1, name1 = parse_date_and_name_from_folder("01.01.2024 divan toplantısı")
    assert d1 == datetime.datetime(2024, 1, 1, 12, 0), f"Tarih hatalı: {d1}"
    assert name1 == "divan toplantısı", f"İsim hatalı: {name1}"

    # Format 2024
    formatted1_prefix = format_event_name("01.01.2024 divan toplantısı", name1, d1, NamingTemplate.YEAR_PREFIX)
    formatted1_suffix = format_event_name("01.01.2024 divan toplantısı", name1, d1, NamingTemplate.YEAR_SUFFIX)
    assert formatted1_prefix == "2024 divan toplantısı", f"Format hatalı: {formatted1_prefix}"
    assert formatted1_suffix == "divan toplantısı (2024)", f"Format hatalı: {formatted1_suffix}"

    # Case 2: 01.01.2025 divan toplantısı
    d2, name2 = parse_date_and_name_from_folder("01.01.2025 divan toplantısı")
    assert d2 == datetime.datetime(2025, 1, 1, 12, 0), f"Tarih hatalı: {d2}"
    assert name2 == "divan toplantısı", f"İsim hatalı: {name2}"

    # Format 2025
    formatted2_prefix = format_event_name("01.01.2025 divan toplantısı", name2, d2, NamingTemplate.YEAR_PREFIX)
    assert formatted2_prefix == "2025 divan toplantısı", f"Format hatalı: {formatted2_prefix}"

    # Verify duplicate prevention: 2024 vs 2025 are distinct!
    assert formatted1_prefix != formatted2_prefix, "Duplicate engelleme başarısız: İki yıl aynı adı aldı!"

    print("  ✅ Tarih ayrıştırma ve isim formatlama başarılı!")


def test_sanitize_folder_name():
    print("🧪 Test 2: Cross-Platform Klasör Adı Temizleme (Sanitization) Testi...")
    
    # Windows invalid characters: < > : " / \ | ? *
    bad_name = '2024: Divan "Toplantısı" <Özel> / Genel *'
    safe = sanitize_folder_name(bad_name)
    assert ":" not in safe and "<" not in safe and ">" not in safe and '"' not in safe and "/" not in safe and "*" not in safe
    assert safe == "2024_Divan_Toplantısı_Özel_Genel", f"Sanitize hatalı: {safe}"
    
    # Windows reserved name
    con_safe = sanitize_folder_name("CON")
    assert con_safe != "CON", f"Reserved name CON engellenemedi: {con_safe}"

    print("  ✅ Cross-platform klasör adı temizleme başarılı!")


def test_folder_scanning():
    print("🧪 Test 3: Klasör Tarama (Folder Scanner) Testi...")
    test_dir = os.path.abspath("test_archive/2024 Yılı Etkinlikleri")
    if not os.path.exists(test_dir):
        print(f"  ⚠️ Test klasörü bulunamadı: {test_dir}")
        return

    scanned = scan_subfolders(test_dir, NamingTemplate.YEAR_PREFIX)
    assert len(scanned) >= 4, f"Beklenen 4+ alt klasör, bulunan: {len(scanned)}"

    # Check first item
    first = scanned[0]
    print(f"  🔎 İlk taranan klasör: {first.original_name} -> Hedef: {first.target_name}, Medya: {first.total_media_count}")
    assert first.has_media, "Medya dosyaları algılanamadı!"
    assert first.photo_count > 0 or first.pdf_count > 0 or first.doc_count > 0 or first.video_count > 0

    print(f"  ✅ Toplam {len(scanned)} alt klasör başarıyla tarandı!")


def test_pdf_util():
    print("🧪 Test 4: PDF Thumbnail, Metin ve Metaveri Çıkarma Testi...")
    pdf_path = os.path.abspath("test_archive/2024 Yılı Etkinlikleri/01.01.2024 divan toplantısı/divan_tutanagi.pdf")
    if not os.path.exists(pdf_path):
        print(f"  ⚠️ PDF dosyası bulunamadı: {pdf_path}")
        return

    thumb_path = os.path.abspath("test_archive/scratch_pdf_thumb.jpg")
    ok = generate_pdf_thumbnail(pdf_path, thumb_path)
    assert ok and os.path.exists(thumb_path), "PDF thumbnail oluşturulamadı!"

    text = extract_pdf_text(pdf_path)
    print(f"  📄 Çıkarılan PDF Metni (ilk 50 karakter): {text[:50] if text else 'None'}")
    assert text and len(text) > 0, "PDF metni çıkarılamadı!"

    meta = extract_pdf_metadata(pdf_path)
    assert meta.get("page_count", 0) >= 1, "PDF sayfa sayısı okunamadı!"

    if os.path.exists(thumb_path):
        os.remove(thumb_path)
    print("  ✅ PDF işlemleri başarıyla test edildi!")


def test_docx_util():
    print("🧪 Test 5: Word (DOCX) Thumbnail ve Metin Çıkarma Testi...")
    docx_path = os.path.abspath("test_archive/2024 Yılı Etkinlikleri/01.01.2024 divan toplantısı/toplanti_kararlari.docx")
    if not os.path.exists(docx_path):
        print(f"  ⚠️ DOCX dosyası bulunamadı: {docx_path}")
        return

    thumb_path = os.path.abspath("test_archive/scratch_docx_thumb.jpg")
    ok = generate_document_thumbnail(docx_path, thumb_path)
    assert ok and os.path.exists(thumb_path), "DOCX thumbnail oluşturulamadı!"

    text = extract_docx_text(docx_path)
    print(f"  📝 Çıkarılan DOCX Metni (ilk 50 karakter): {text[:50] if text else 'None'}")
    assert text and "Divan Toplantısı" in text, "DOCX metni çıkarılamadı!"

    meta = extract_doc_metadata(docx_path)
    assert meta.get("author") == "Acknowledge Test Generator", "DOCX metaveri okunamadı!"

    if os.path.exists(thumb_path):
        os.remove(thumb_path)
    print("  ✅ Word (DOCX) işlemleri başarıyla test edildi!")


if __name__ == "__main__":
    print("==================================================")
    print("🚀 BATCH IMPORT & DUPLICATE TESTLERİ BAŞLATILIYOR")
    print("==================================================")
    test_date_parsing_and_duplicate_prevention()
    test_sanitize_folder_name()
    test_folder_scanning()
    test_pdf_util()
    test_docx_util()
    print("==================================================")
    print("🎉 TÜM DOĞRULAMA TESTLERİ BAŞARIYLA GEÇTİ!")
    print("==================================================")
