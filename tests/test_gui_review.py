"""Exercise persistent review controls without importing Qt into CLI tests."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


def check_review_gui():
    import tempfile
    from unittest.mock import patch
    from PIL import Image
    from PySide6 import QtCore, QtTest, QtWidgets
    from viewview.gui import MainWidget
    from viewview.core.review import read_deletion_marks, review_path

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(Path('viewview/style.qss').read_text())

    class GuiReviewTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name)
            for name in ('first.jpg', 'second.jpg'):
                Image.new('RGB', (24, 16), 'red').save(self.root / name)
            self.widget = self.open_window(self.root)
            listing = self.widget.file_management._list
            self.paths = [item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                          for item in self.widget.file_management._image_items]

        def open_window(self, root):
            widget = MainWidget()
            widget.resize(1000, 700)
            widget.show()
            self.addCleanup(widget.close)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(root)):
                widget.select_folder()
            widget.activateWindow()
            app.processEvents()
            return widget

        def press_x(self):
            self.widget.activateWindow()
            self.widget.file_management._list.setFocus()
            app.processEvents()
            QtTest.QTest.keyClick(self.widget.file_management._list, QtCore.Qt.Key.Key_X)
            app.processEvents()

        def test_checkbox_persists_and_unmarking_survives_reopen(self):
            first, second = self.paths
            self.widget.set_current_image(first)
            checkbox = self.widget.metadata.deletion_checkbox
            self.assertTrue(checkbox.isEnabled())
            self.assertFalse(checkbox.isChecked())
            checkbox.click()
            self.assertEqual(self.widget.image_path, first)
            self.widget.set_current_image(second)
            self.assertFalse(checkbox.isChecked())
            self.widget.set_current_image(first)
            self.assertTrue(checkbox.isChecked())
            self.widget.close()
            reopened = self.open_window(self.root)
            reopened.set_current_image(first)
            self.assertTrue(reopened.metadata.deletion_checkbox.isChecked())
            reopened.metadata.deletion_checkbox.click()
            self.assertEqual(read_deletion_marks(self.root), set())
            self.assertTrue(all(path.exists() for path in self.paths))

        def test_x_toggles_and_selects_next_and_stops_at_last(self):
            first, second = self.paths
            self.widget.set_current_image(first)
            self.press_x()
            self.assertEqual(self.widget.image_path, second)
            self.assertIs(self.widget.file_management._list.currentItem(),
                          self.widget.file_management._image_items[1])
            self.assertFalse(self.widget.metadata.deletion_checkbox.isChecked())
            self.assertEqual(read_deletion_marks(self.root), {review_path(self.root, first)})
            self.press_x()
            self.assertEqual(self.widget.image_path, second)
            self.assertTrue(self.widget.metadata.deletion_checkbox.isChecked())
            self.press_x()
            self.assertEqual(self.widget.image_path, second)
            self.assertFalse(self.widget.metadata.deletion_checkbox.isChecked())
            self.assertEqual(read_deletion_marks(self.root), {review_path(self.root, first)})
            self.widget.set_current_image(first)
            self.press_x()
            self.assertEqual(self.widget.image_path, second)
            self.assertEqual(read_deletion_marks(self.root), set())

        def test_shortcut_disabled_until_photo_selected_and_on_import_tab(self):
            self.assertFalse(self.widget.metadata.deletion_checkbox.isEnabled())
            self.press_x()
            self.assertFalse((self.root / 'review.json').exists())
            self.widget.set_current_image(self.paths[0])
            self.widget.tabs.setCurrentIndex(1)
            self.assertFalse(self.widget._mark_shortcut.isEnabled())
            entry = self.widget.import_widget.tags_input
            entry.setFocus()
            QtTest.QTest.keyClicks(entry, 'x')
            self.assertEqual(entry.text(), 'x')
            self.assertFalse((self.root / 'review.json').exists())
            self.widget.tabs.setCurrentIndex(0)
            self.assertTrue(self.widget._mark_shortcut.isEnabled())

        def test_failed_save_reverts_checkbox_and_does_not_advance(self):
            self.widget.set_current_image(self.paths[0])
            with patch('viewview.gui.set_deletion_mark', side_effect=PermissionError('Read-only library')):
                self.widget.metadata.deletion_checkbox.click()
                self.assertFalse(self.widget.metadata.deletion_checkbox.isChecked())
                self.press_x()
            self.assertEqual(self.widget.image_path, self.paths[0])
            self.assertIn('Could not save', self.widget.metadata.review_error.text())
            self.assertFalse((self.root / 'review.json').exists())

        def test_invalid_index_disables_marks_without_overwriting_it(self):
            (self.root / 'review.json').write_text('broken')
            self.widget.set_current_image(self.paths[0])
            self.assertFalse(self.widget.metadata.deletion_checkbox.isEnabled())
            self.assertFalse(self.widget._mark_shortcut.isEnabled())
            self.assertIn('Could not load', self.widget.metadata.review_error.text())
            self.assertEqual((self.root / 'review.json').read_text(), 'broken')

        def test_switching_library_clears_current_review_state(self):
            self.widget.set_current_image(self.paths[0])
            self.widget.metadata.deletion_checkbox.click()
            other = self.root / 'other-library'
            other.mkdir()
            Image.new('RGB', (24, 16), 'blue').save(other / self.paths[0].name)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(other)):
                self.widget.select_folder()
            self.assertIsNone(self.widget.image_path)
            self.assertFalse(self.widget._mark_shortcut.isEnabled())
            self.widget.set_current_image(other / self.paths[0].name)
            self.assertFalse(self.widget.metadata.deletion_checkbox.isChecked())

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(GuiReviewTests))
    return 0 if result.wasSuccessful() else 1


class GuiReviewProcessTests(unittest.TestCase):
    def test_gui_review(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'import runpy; runpy.run_path("tests/test_gui_review.py", run_name="__main__")'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    raise SystemExit(check_review_gui())
