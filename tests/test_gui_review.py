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
    from PIL.ExifTags import Base
    from PySide6 import QtCore, QtTest, QtWidgets
    from viewview.gui import MainWidget
    from viewview.core.review import read_deletion_marks, review_path, read_rating
    from viewview.core.library_db import DATABASE_NAME

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

        def press_key(self, key):
            self.widget.activateWindow()
            target = (self.widget.grid.view if self.widget.view_tabs.currentIndex() == 1
                      else self.widget.file_management._list)
            target.setFocus()
            app.processEvents()
            QtTest.QTest.keyClick(target, key)
            app.processEvents()

        def test_arrow_navigation_in_both_views_stops_at_boundaries(self):
            first, second = self.paths
            for tab in (0, 1):
                self.widget.view_tabs.setCurrentIndex(tab)
                self.widget.set_current_image(first)
                self.press_key(QtCore.Qt.Key.Key_Left)
                self.assertEqual(self.widget.image_path, first)
                self.press_key(QtCore.Qt.Key.Key_Right)
                self.assertEqual(self.widget.image_path, second)
                self.press_key(QtCore.Qt.Key.Key_Right)
                self.assertEqual(self.widget.image_path, second)
                self.press_key(QtCore.Qt.Key.Key_Left)
                self.assertEqual(self.widget.image_path, first)

        def test_rating_keys_persist_advance_and_do_not_toggle_same_rating(self):
            first, second = self.paths
            for tab in (0, 1):
                self.widget.view_tabs.setCurrentIndex(tab)
                for number in (1, 2, 3, 4, 5, 0):
                    self.widget.set_current_image(first)
                    self.press_key(getattr(QtCore.Qt.Key, f'Key_{number}'))
                    self.assertEqual(read_rating(self.root, first), number)
                    self.assertEqual(self.widget.image_path, second)
                self.press_key(QtCore.Qt.Key.Key_4)
                self.press_key(QtCore.Qt.Key.Key_4)
                self.assertEqual(self.widget.image_path, second)
                self.assertEqual(read_rating(self.root, second), 4)
                self.assertEqual(self.widget.metadata._ratingw.value(), 4)

        def test_rating_failure_does_not_advance(self):
            self.widget.set_current_image(self.paths[0])
            with patch('viewview.gui.set_rating', side_effect=PermissionError('Read-only library')):
                self.press_key(QtCore.Qt.Key.Key_5)
            self.assertEqual(self.widget.image_path, self.paths[0])
            self.assertEqual(self.widget.metadata._ratingw.value(), 0)
            self.assertIn('Could not save rating', self.widget.metadata.review_error.text())

        def test_navigation_and_rating_disabled_while_typing_and_on_import(self):
            self.widget.set_current_image(self.paths[0])
            entry = self.widget.metadata.tags_editor.input
            entry.setFocus()
            app.processEvents()
            QtTest.QTest.keyClicks(entry, '12345')
            QtTest.QTest.keyClick(entry, QtCore.Qt.Key.Key_Left)
            self.assertEqual(entry.text(), '12345')
            self.assertEqual(entry.cursorPosition(), 4)
            self.assertEqual(self.widget.image_path, self.paths[0])
            self.assertIsNone(read_rating(self.root, self.paths[0]))
            self.widget.tabs.setCurrentIndex(1)
            self.press_key(QtCore.Qt.Key.Key_5)
            self.press_key(QtCore.Qt.Key.Key_Right)
            self.assertEqual(self.widget.image_path, self.paths[0])
            self.assertIsNone(read_rating(self.root, self.paths[0]))

        def test_grid_navigation_stays_within_selected_folder(self):
            folder = self.root / 'nested'
            folder.mkdir()
            nested = folder / 'only.jpg'
            Image.new('RGB', (24, 16), 'blue').save(nested)
            self.widget._refresh_library()
            self.widget.select_grid_folder(folder)
            self.widget.view_tabs.setCurrentIndex(1)
            self.widget.set_current_image(nested)
            self.press_key(QtCore.Qt.Key.Key_Left)
            self.press_key(QtCore.Qt.Key.Key_Right)
            self.press_key(QtCore.Qt.Key.Key_3)
            self.assertEqual(self.widget.image_path, nested)
            self.assertEqual(read_rating(self.root, nested), 3)

        def test_rating_is_editable_persistent_and_can_override_exif_with_zero(self):
            first, second = self.paths
            exif = Image.Exif()
            exif[Base.Rating] = 4
            Image.new('RGB', (24, 16), 'red').save(first, exif=exif)
            original = first.read_bytes()
            self.assertFalse(self.widget.metadata._ratingw.isEnabled())
            self.widget.set_current_image(first)
            rating = self.widget.metadata._ratingw
            self.assertTrue(rating.isEnabled())
            self.assertEqual(rating.value(), 4)
            self.assertFalse((self.root / DATABASE_NAME).exists())
            rating.setValue(5)
            self.assertEqual(read_rating(self.root, first), 5)
            self.widget.set_current_image(second)
            self.assertEqual(rating.value(), 0)
            self.widget.set_current_image(first)
            self.assertEqual(rating.value(), 5)
            self.widget.close()
            reopened = self.open_window(self.root)
            reopened.set_current_image(first)
            self.assertEqual(reopened.metadata._ratingw.value(), 5)
            reopened.metadata._ratingw.setValue(0)
            reopened.set_current_image(second)
            reopened.set_current_image(first)
            self.assertEqual(reopened.metadata._ratingw.value(), 0)
            self.assertEqual(read_rating(self.root, first), 0)
            self.assertEqual(first.read_bytes(), original)

        def test_rating_save_failure_restores_previous_value(self):
            first = self.paths[0]
            self.widget.set_current_image(first)
            self.widget.metadata._ratingw.setValue(3)
            with patch('viewview.gui.set_rating', side_effect=PermissionError('Read-only library')):
                self.widget.metadata._ratingw.setValue(5)
            self.assertEqual(self.widget.metadata._ratingw.value(), 3)
            self.assertEqual(read_rating(self.root, first), 3)
            self.assertEqual(self.widget.image_path, first)
            self.assertIn('Could not save rating', self.widget.metadata.review_error.text())

        def test_clicking_stars_sets_changes_and_clears_persistent_rating(self):
            first, second = self.paths
            rating = self.widget.metadata._ratingw
            self.widget.set_current_image(first)
            def click(number):
                QtTest.QTest.mouseClick(rating.stars[number - 1], QtCore.Qt.MouseButton.LeftButton)
                app.processEvents()
            click(4)
            self.assertEqual(rating.value(), 4)
            self.assertEqual([star.isChecked() for star in rating.stars], [True] * 4 + [False])
            self.assertEqual(read_rating(self.root, first), 4)
            click(2)
            self.assertEqual(rating.value(), 2)
            self.assertEqual([star.isChecked() for star in rating.stars], [True, True, False, False, False])
            click(5)
            self.assertEqual(read_rating(self.root, first), 5)
            click(5)
            self.assertEqual(rating.value(), 0)
            self.assertTrue(all(not star.isChecked() for star in rating.stars))
            self.assertEqual(read_rating(self.root, first), 0)
            self.widget.set_current_image(second)
            self.widget.set_current_image(first)
            self.assertEqual(rating.value(), 0)
            with patch('viewview.gui.set_rating', side_effect=PermissionError('Read-only library')):
                click(3)
            self.assertEqual(rating.value(), 0)
            self.assertTrue(all(not star.isChecked() for star in rating.stars))

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
            self.assertFalse((self.root / DATABASE_NAME).exists())
            self.widget.set_current_image(self.paths[0])
            self.widget.tabs.setCurrentIndex(1)
            self.assertFalse(self.widget._mark_shortcut.isEnabled())
            entry = self.widget.import_widget.tags_input
            entry.setFocus()
            QtTest.QTest.keyClicks(entry, 'x')
            self.assertEqual(entry.text(), 'x')
            self.assertFalse((self.root / DATABASE_NAME).exists())
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
            self.assertFalse((self.root / DATABASE_NAME).exists())

        def test_invalid_index_disables_marks_without_overwriting_it(self):
            (self.root / 'review.json').write_text('broken')
            self.widget.set_current_image(self.paths[0])
            self.assertFalse(self.widget.metadata.deletion_checkbox.isEnabled())
            self.assertFalse(self.widget._mark_shortcut.isEnabled())
            self.assertIn('Could not load', self.widget.metadata.review_error.text())
            self.assertEqual((self.root / 'review.json').read_text(), 'broken')

        def test_corrupt_database_disables_marks_without_overwriting_it(self):
            path = self.root / DATABASE_NAME
            path.write_bytes(b'broken database')
            self.widget.set_current_image(self.paths[0])
            self.assertFalse(self.widget.metadata.deletion_checkbox.isEnabled())
            self.assertFalse(self.widget._mark_shortcut.isEnabled())
            self.assertIn('Library database error', self.widget.metadata.review_error.text())
            self.assertEqual(path.read_bytes(), b'broken database')

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
