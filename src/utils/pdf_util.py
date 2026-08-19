"""PDF utilities for rendering thumbnails, extracting text, and extracting metadata using PySide6.QtPdf."""

import os
import logging
from PySide6 import QtGui, QtCore
from PySide6.QtPdf import QPdfDocument

logger = logging.getLogger(__name__)

PDF_EXTS = {".pdf"}


def is_pdf(file_path: str) -> bool:
    """Check if file has a PDF extension."""
    return os.path.splitext(file_path)[1].lower() in PDF_EXTS


def generate_pdf_thumbnail(pdf_path: str, thumb_path: str, target_size: int = 300) -> bool:
    """
    Render the first page of a PDF as a JPEG thumbnail.
    Uses PySide6.QtPdf.QPdfDocument which is built-in and cross-platform (Windows & macOS).
    """
    try:
        doc = QPdfDocument()
        err = doc.load(pdf_path)
        if err != QPdfDocument.Error.None_ or doc.pageCount() == 0:
            logger.warning(f"Failed to load PDF for thumbnail: {pdf_path} (error: {err})")
            return _generate_fallback_pdf_thumbnail(pdf_path, thumb_path, target_size)

        # Get first page dimensions
        page_size = doc.pagePointSize(0)
        if page_size.width() <= 0 or page_size.height() <= 0:
            doc.close()
            return _generate_fallback_pdf_thumbnail(pdf_path, thumb_path, target_size)

        # Calculate render scale to fit target_size while keeping aspect ratio
        pw = page_size.width()
        ph = page_size.height()
        scale = min(target_size / pw, target_size / ph) * 2.0  # 2x for sharp thumbnail
        render_w = max(1, int(pw * scale))
        render_h = max(1, int(ph * scale))

        image = doc.render(0, QtCore.QSize(render_w, render_h))
        doc.close()

        if image.isNull():
            return _generate_fallback_pdf_thumbnail(pdf_path, thumb_path, target_size)

        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        image = image.scaled(target_size, target_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        
        # Save thumbnail
        image.save(thumb_path, "JPEG", 85)
        return True

    except Exception as e:
        logger.warning(f"Error generating PDF thumbnail for {pdf_path}: {e}")
        return _generate_fallback_pdf_thumbnail(pdf_path, thumb_path, target_size)


def _generate_fallback_pdf_thumbnail(pdf_path: str, thumb_path: str, target_size: int = 300) -> bool:
    """Generate a vector/graphic PDF-icon thumbnail when direct rendering fails."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (target_size, target_size), color=(245, 245, 250))
        draw = ImageDraw.Draw(img)

        # Page shape
        pw, ph = int(target_size * 0.55), int(target_size * 0.70)
        px = (target_size - pw) // 2
        py = (target_size - ph) // 2
        corner = 16
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=corner, fill="white", outline="#e04040", width=2)

        # Folded corner (Red tint for PDF)
        fold = int(target_size * 0.10)
        draw.polygon([(px + pw - fold, py), (px + pw, py + fold), (px + pw - fold, py + fold)], fill="#fde8e8")
        draw.line([(px + pw - fold, py), (px + pw, py + fold), (px + pw - fold, py + fold)], fill="#e04040", width=2)

        # Red PDF extension badge
        badge_w, badge_h = int(pw * 0.65), 32
        badge_x0 = px + (pw - badge_w) // 2
        badge_y0 = py + ph // 2 - badge_h // 2
        badge_x1 = badge_x0 + badge_w
        badge_y1 = badge_y0 + badge_h
        draw.rounded_rectangle([badge_x0, badge_y0, badge_x1, badge_y1], radius=6, fill="#e02020")

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        draw.text(((badge_x0 + badge_x1) / 2, (badge_y0 + badge_y1) / 2),
                  "PDF", fill="white", font=font, anchor="mm")

        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        img.save(thumb_path, "JPEG", quality=85)
        return True
    except Exception as e:
        logger.error(f"Fallback thumbnail generation failed: {e}")
        return False


def extract_pdf_text(pdf_path: str) -> str | None:
    """Extract all text from a PDF file using QPdfDocument."""
    try:
        doc = QPdfDocument()
        err = doc.load(pdf_path)
        if err != QPdfDocument.Error.None_:
            return None

        page_count = doc.pageCount()
        all_text = []
        for page_idx in range(page_count):
            try:
                # QPdfDocument.getAllText extracts structured text from page
                sel = doc.getAllText(page_idx)
                if sel and sel.text():
                    all_text.append(sel.text().strip())
            except Exception:
                pass

        doc.close()
        return "\n\n".join(t for t in all_text if t) if all_text else None
    except Exception as e:
        logger.warning(f"Could not extract text from PDF {pdf_path}: {e}")
        return None


def extract_pdf_metadata(pdf_path: str) -> dict:
    """Extract metadata (Title, Author, Creation Date, Page count) from PDF."""
    meta = {}
    try:
        doc = QPdfDocument()
        err = doc.load(pdf_path)
        if err == QPdfDocument.Error.None_:
            meta["page_count"] = doc.pageCount()
            title = doc.metaData(QPdfDocument.MetaDataField.Title)
            author = doc.metaData(QPdfDocument.MetaDataField.Author)
            subject = doc.metaData(QPdfDocument.MetaDataField.Subject)
            creator = doc.metaData(QPdfDocument.MetaDataField.Creator)
            producer = doc.metaData(QPdfDocument.MetaDataField.Producer)
            creation_date = doc.metaData(QPdfDocument.MetaDataField.CreationDate)
            
            if title: meta["title"] = str(title)
            if author: meta["author"] = str(author)
            if subject: meta["subject"] = str(subject)
            if creator: meta["creator"] = str(creator)
            if producer: meta["producer"] = str(producer)
            if creation_date: meta["created"] = str(creation_date)
            doc.close()
    except Exception as e:
        logger.warning(f"Could not extract PDF metadata for {pdf_path}: {e}")
    return meta
