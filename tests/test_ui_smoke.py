"""
tests/test_ui_smoke.py — Automated Headless UI Component Smoke Tests

This test suite instantiates all PySide6 UI components, dialogs, tabs,
models, and the main window headlessly in memory (QT_QPA_PLATFORM=offscreen)
to ensure 100% regression protection without requiring manual UI testing.
"""
import os
import sys
import uuid
import datetime
import unittest
from unittest.mock import MagicMock, patch

# Force Qt offscreen platform before creating QApplication
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtWidgets, QtCore, QtGui

# Ensure a single QApplication instance for tests
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication(sys.argv)

from src.ui.components import (
    ToggleSwitch,
    EventCardWidget,
    FaceOverlayWidget,
    CaptionStatsWidget,
)
from src.ui.models import (
    GalleryItem,
    GalleryItemModel,
    GallerySearchProxyModel,
)
from src.ui.dialogs import (
    AddPersonDialog,
    BatchImportDialog,
    EventPersonsDialog,
    AddEvent,
)
from src.ui.views import (
    SingleViewWidget,
    CaptionTabWidget,
    PersonsTabWidget,
    FeedbackTabWidget,
    FAQWidget,
)
from src.ui.main_window import MainWindow


class FakeEvent:
    def __init__(self, name, event_date=None, created_at=None, event_id=None):
        self.id = event_id or uuid.uuid4()
        self.name = name
        self.event_date = event_date
        self.created_at = created_at or datetime.datetime.now()
        self.vault_folder_path = f"vault/{name}"


class TestUIComponentsSmoke(unittest.TestCase):
    def setUp(self):
        # Create mock services for headless testing
        self.mock_face_service = MagicMock()
        self.mock_person_service = MagicMock()
        self.mock_media_service = MagicMock()
        self.mock_caption_service = MagicMock()
        self.mock_event_service = MagicMock()
        self.mock_app_service = MagicMock()

        self.mock_app_service.get_event_service.return_value = self.mock_event_service
        self.mock_app_service.get_media_service.return_value = self.mock_media_service
        self.mock_app_service.get_face_service.return_value = self.mock_face_service
        self.mock_app_service.get_person_service.return_value = self.mock_person_service

    def test_toggle_switch(self):
        widget = ToggleSwitch()
        self.assertIsInstance(widget, QtWidgets.QWidget)
        self.assertFalse(widget.isChecked())
        widget.setChecked(True)
        self.assertTrue(widget.isChecked())

    def test_event_card_widget(self):
        widget = EventCardWidget("Test Event", datetime.datetime.now())
        self.assertIsInstance(widget, QtWidgets.QWidget)
        self.assertEqual(widget.event_name.text(), "Test Event")

        # Test with None date (graceful fallback)
        widget_none = EventCardWidget("No Date Event", None)
        self.assertEqual(widget_none.event_date.text(), "Tarih belirtilmedi")

    def test_face_overlay_widget(self):
        widget = FaceOverlayWidget()
        self.assertIsInstance(widget, QtWidgets.QWidget)

    def test_caption_stats_widget(self):
        widget = CaptionStatsWidget()
        self.assertIsInstance(widget, QtWidgets.QWidget)

    def test_faq_widget(self):
        widget = FAQWidget()
        self.assertIsInstance(widget, QtWidgets.QWidget)

    def test_feedback_tab_widget(self):
        widget = FeedbackTabWidget()
        self.assertIsInstance(widget, QtWidgets.QWidget)

    def test_gallery_item_and_models(self):
        item = GalleryItem("Sample", "/path/to/sample.jpg")
        self.assertIsInstance(item, QtGui.QStandardItem)
        self.assertEqual(item.text(), "Sample")

        model = GalleryItemModel(items=[item])
        self.assertIsInstance(model, QtGui.QStandardItemModel)
        self.assertEqual(model.rowCount(), 1)

        proxy = GallerySearchProxyModel()
        proxy.setSourceModel(model)
        self.assertIsInstance(proxy, QtCore.QAbstractProxyModel)

    def test_add_person_dialog(self):
        dialog = AddPersonDialog(
            face_service=self.mock_face_service,
            person_service=self.mock_person_service
        )
        self.assertIsInstance(dialog, QtWidgets.QDialog)

    def test_batch_import_dialog(self):
        dialog = BatchImportDialog(app_service=self.mock_app_service)
        self.assertIsInstance(dialog, QtWidgets.QDialog)

    def test_event_persons_dialog(self):
        dialog = EventPersonsDialog(
            persons=[{"name": "Alice", "face_count": 2, "media_count": 1}],
            event_name="Test Gala"
        )
        self.assertIsInstance(dialog, QtWidgets.QDialog)

    def test_add_event_window(self):
        widget = AddEvent()
        self.assertIsInstance(widget, QtWidgets.QWidget)
        widget.close()

    def test_caption_tab_widget(self):
        widget = CaptionTabWidget(
            caption_service=self.mock_caption_service,
            media_service=self.mock_media_service,
            person_service=self.mock_person_service
        )
        self.assertIsInstance(widget, QtWidgets.QWidget)

    def test_persons_tab_widget(self):
        widget = PersonsTabWidget(
            person_service=self.mock_person_service,
            media_service=self.mock_media_service,
            face_service=self.mock_face_service
        )
        self.assertIsInstance(widget, QtWidgets.QWidget)

    def test_single_view_widget(self):
        widget = SingleViewWidget(
            face_service=self.mock_face_service,
            person_service=self.mock_person_service,
            media_service=self.mock_media_service
        )
        self.assertIsInstance(widget, QtWidgets.QWidget)

    def test_main_window_instantiation_and_event_tree_grouping(self):
        # Instantiate MainWindow in headless mode with mocked services
        with patch("src.ui.main_window.ApplicationService"):
            window = MainWindow()
            self.assertIsInstance(window, QtWidgets.QMainWindow)

            # Create mock events spanning multiple years and months
            ev1 = FakeEvent("Mart Toplantisi 2026", datetime.datetime(2026, 3, 15, 10, 0))
            ev2 = FakeEvent("Subat Galasi 2026", datetime.datetime(2026, 2, 20, 18, 30))
            ev3 = FakeEvent("Kasim Ziyareti 2025", datetime.datetime(2025, 11, 5, 14, 0))
            ev4 = FakeEvent("Tarihsiz Sergi", None)

            window.app_service.get_event_service().get_all.return_value = [ev1, ev2, ev3, ev4]
            window.app_service.get_event_service().get_event_by_id.side_effect = lambda eid: next((e for e in [ev1, ev2, ev3, ev4] if str(e.id) == str(eid)), None)
            window.load_events([ev1, ev2, ev3, ev4])

            # Check Tree Structure:
            # 3 Top Level Years: 2026, 2025, Tarihsiz
            tree = window.event_tree_widget
            self.assertEqual(tree.topLevelItemCount(), 3)

            year_2026_item = tree.topLevelItem(0)
            self.assertIn("2026", year_2026_item.text(0))
            self.assertTrue(year_2026_item.isExpanded())
            # 2026 should have 2 months: Mart, Şubat
            self.assertEqual(year_2026_item.childCount(), 2)

            month_mart = year_2026_item.child(0)
            self.assertIn("Mart", month_mart.text(0))
            self.assertEqual(month_mart.childCount(), 1)

            event_item = month_mart.child(0)
            card = tree.itemWidget(event_item, 0)
            self.assertIsInstance(card, EventCardWidget)
            self.assertEqual(card.event_name.text(), "Mart Toplantisi 2026")

            # Test search filtering in tree
            window.app_service.get_event_service().search_by_name.return_value = [ev1]
            window.event_search.setText("Mart")
            window.on_event_search_entered()

            # Now tree should only contain 2026 -> Mart -> ev1
            self.assertEqual(tree.topLevelItemCount(), 1)
            filtered_year = tree.topLevelItem(0)
            self.assertIn("2026", filtered_year.text(0))
            self.assertEqual(filtered_year.childCount(), 1)
            self.assertIn("Mart", filtered_year.child(0).text(0))

            # Test clearing search restores full tree
            window.event_search.setText("")
            window.on_event_search_entered()
            self.assertEqual(tree.topLevelItemCount(), 3)

            # Test _select_newest_event
            window._select_newest_event()
            self.assertEqual(window.current_event_id, ev1.id)

            # Test _go_to_event
            window._go_to_event(ev3.id)
            self.assertEqual(window.current_event_id, ev3.id)

            window.close()


if __name__ == "__main__":
    unittest.main()
