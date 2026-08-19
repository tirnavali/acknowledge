"""
tests/test_batch_import_recursive.py — Tests for recursive folder scanning and batch import.
"""

import os
import shutil
import tempfile
import datetime
import unittest
from unittest.mock import MagicMock
from PIL import Image

from src.utils.folder_scanner_util import (
    scan_subfolders,
    find_candidate_event_folders,
    NamingTemplate,
)
from src.services.event_service import EventService
from src.domain.entities.event import Event


class TestBatchImportRecursive(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_batch_archive_")
        self.vault_dir = tempfile.mkdtemp(prefix="test_vault_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.vault_dir, ignore_errors=True)

    def _create_dummy_image(self, file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        img = Image.new("RGB", (50, 50), color="blue")
        img.save(file_path, "JPEG")

    def _create_dummy_text_file(self, file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Sample document content")

    def test_multi_level_year_month_event_scanning(self):
        """
        Tests hierarchy:
        Root (2023) /
          ├── 10-EKIM 2023 /
          │     ├── 27.10.2023 ANKARA TBMM /
          │     │     ├── IMG_001.jpg
          │     │     └── IMG_002.jpg
          │     └── 29.10.2023 CUMHURIYET /
          │           ├── Fotolar /
          │           │     └── IMG_003.jpg
          │           └── doc1.docx
          └── 09-EYLUL 2023 /
                └── 23.09.2023 ISTANBUL /
                      └── IMG_004.jpg
        """
        ev1_dir = os.path.join(self.test_dir, "10-EKIM 2023", "27.10.2023 ANKARA TBMM")
        self._create_dummy_image(os.path.join(ev1_dir, "IMG_001.jpg"))
        self._create_dummy_image(os.path.join(ev1_dir, "IMG_002.jpg"))

        ev2_dir = os.path.join(self.test_dir, "10-EKIM 2023", "29.10.2023 CUMHURIYET")
        self._create_dummy_image(os.path.join(ev2_dir, "Fotolar", "IMG_003.jpg"))
        self._create_dummy_text_file(os.path.join(ev2_dir, "doc1.docx"))

        ev3_dir = os.path.join(self.test_dir, "09-EYLUL 2023", "23.09.2023 ISTANBUL")
        self._create_dummy_image(os.path.join(ev3_dir, "IMG_004.jpg"))

        # Scan the root (which only contains month folders)
        scanned = scan_subfolders(self.test_dir, template=NamingTemplate.ORIGINAL)

        # Must discover 3 distinct event folders (NOT the month folders)
        self.assertEqual(len(scanned), 3)

        scanned_map = {item.original_name: item for item in scanned}
        self.assertIn("27.10.2023 ANKARA TBMM", scanned_map)
        self.assertIn("29.10.2023 CUMHURIYET", scanned_map)
        self.assertIn("23.09.2023 ISTANBUL", scanned_map)

        # Check media counts for ev1
        item1 = scanned_map["27.10.2023 ANKARA TBMM"]
        self.assertEqual(item1.photo_count, 2)
        self.assertEqual(item1.total_media_count, 2)
        self.assertEqual(item1.event_date.day, 27)
        self.assertEqual(item1.event_date.month, 10)
        self.assertEqual(item1.event_date.year, 2023)

        # Check media counts for ev2 (including nested Fotolar subfolder + docx)
        item2 = scanned_map["29.10.2023 CUMHURIYET"]
        self.assertEqual(item2.photo_count, 1)
        self.assertEqual(item2.doc_count, 1)
        self.assertEqual(item2.total_media_count, 2)

    def test_recursive_media_import_and_db_bulk_persistence(self):
        """
        Tests create_and_import_event when event source folder has nested subdirectories.
        Ensures all files are copied to vault and media records are created in database.
        """
        src_event_folder = os.path.join(self.test_dir, "27.10.2023 Butce Gorusmesi")
        self._create_dummy_image(os.path.join(src_event_folder, "root_photo.jpg"))
        self._create_dummy_image(os.path.join(src_event_folder, "Fotolar", "sub_photo.jpg"))
        self._create_dummy_text_file(os.path.join(src_event_folder, "Belgeler", "notlar.docx"))

        mock_event_repo = MagicMock()
        mock_media_repo = MagicMock()

        # Mock get_by_name_and_date returning None
        mock_event_repo.get_by_name_and_date.return_value = None

        service = EventService(
            event_repository=mock_event_repo,
            media_repository=mock_media_repo,
        )

        event = service.create_and_import_event(
            name="2023 Butce Gorusmesi",
            event_date=datetime.datetime(2023, 10, 27),
            source_folder=src_event_folder,
            vault_base_path=self.vault_dir,
        )

        self.assertIsInstance(event, Event)
        self.assertTrue(event.import_success)

        # Verify event saved in repo
        mock_event_repo.save.assert_called_once()

        # Verify media records saved in bulk
        mock_media_repo.bulk_save_media.assert_called_once()
        saved_records = mock_media_repo.bulk_save_media.call_args[1]["media_records"]

        # All 3 files (from root, Fotolar, Belgeler) must be imported
        self.assertEqual(len(saved_records), 3)

        media_types = {r["media_type"] for r in saved_records}
        self.assertIn("photo", media_types)
        self.assertIn("document", media_types)

        # Check thumbnails created on disk
        vault_path = mock_event_repo.save.call_args[0][0].vault_folder_path
        # Convert to local path
        from src.utils import path_util
        abs_vault_path = path_util.from_db_path(vault_path)
        thumb_dir = os.path.join(abs_vault_path, ".thumbnails")
        self.assertTrue(os.path.exists(thumb_dir))
        self.assertTrue(os.path.exists(os.path.join(thumb_dir, "root_photo.jpg.thumb.jpg")))
        self.assertTrue(os.path.exists(os.path.join(thumb_dir, "sub_photo.jpg.thumb.jpg")))


if __name__ == "__main__":
    unittest.main()
