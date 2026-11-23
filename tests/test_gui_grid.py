"""Exercise the grid and real background thumbnails outside CLI-only tests."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


def check_grid():
    import tempfile
    import threading
    import time
    from unittest.mock import patch
    from PIL import Image
    from PIL.ExifTags import Base
    from PySide6 import QtCore, QtTest, QtWidgets
    from viewview.gui import MainWidget
    from viewview.grid import load_thumbnail
    from viewview.core.review import read_rating, is_marked_for_deletion

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(Path('viewview/style.qss').read_text())

    class GridTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name)
            self.alpha = self.root / 'alpha'
            self.beta = self.root / 'beta'
            (self.alpha / 'nested').mkdir(parents=True)
            self.beta.mkdir()
            (self.root / 'empty').mkdir()
            self.portrait = self.alpha / 'nested' / '03-portrait.PNG'
            self.landscape = self.alpha / '01-landscape.jpg'
            self.heic = self.beta / '02.heic'
            self.last = self.root / 'last.jpg'
            Image.new('RGB', (32, 48), 'blue').save(self.portrait)
            Image.new('RGB', (48, 32), 'red').save(self.landscape)
            Image.new('RGB', (48, 32), 'green').save(self.heic)
            Image.new('RGB', (48, 32), 'yellow').save(self.last)
            self.widget = MainWidget()
            self.widget.resize(1300, 850)
            self.widget.show()
            self.addCleanup(self.widget.close)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(self.root)):
                self.widget.select_folder()
            self.grid = self.widget.grid
            self.widget.activateWindow()
            app.processEvents()

        def wait_for(self, predicate):
            deadline = time.monotonic() + 8
            while not predicate() and time.monotonic() < deadline:
                QtTest.QTest.qWait(10)
            self.assertTrue(predicate())

        def show_grid(self, folder=None):
            if folder is not None:
                self.widget.select_grid_folder(folder)
            self.widget.view_tabs.setCurrentIndex(1)
            app.processEvents()

        def click(self, path, double=False):
            index = self.grid.model.index(self.grid.model.rows[path])
            self.grid.view.scrollTo(index)
            app.processEvents()
            point = self.grid.view.visualRect(index).center()
            QtTest.QTest.mouseClick(self.grid.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
            if double:
                QtTest.QTest.mouseDClick(self.grid.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
            app.processEvents()

        def press_x(self):
            self.widget.activateWindow()
            self.grid.view.setFocus()
            app.processEvents()
            QtTest.QTest.keyClick(self.grid.view, QtCore.Qt.Key.Key_X)
            app.processEvents()

        def test_nested_tabs_share_panels_and_tree_order_including_collapsed_folders(self):
            self.assertEqual(self.widget.tabs.count(), 2)
            self.assertEqual(self.widget.view_tabs.count(), 2)
            self.assertIs(self.widget._splitter.widget(0), self.widget.file_management)
            self.assertIs(self.widget._splitter.widget(2), self.widget.metadata)
            self.assertFalse(self.widget.file_management._folder_items[self.alpha].isExpanded())
            paths = tuple(item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                          for item in self.widget.file_management._image_items)
            self.assertEqual(self.grid.model.paths, paths)
            self.assertEqual(paths, (self.portrait, self.landscape, self.heic, self.last))
            self.assertEqual(self.grid.model.cache, {})
            self.assertEqual(self.grid._jobs, {})
            tree = self.widget.file_management._list
            item = self.widget.file_management._folder_items[self.alpha]
            QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                   pos=tree.visualItemRect(item).center())
            self.assertEqual(self.grid.model.paths, (self.portrait, self.landscape))
            self.assertEqual(self.widget.import_widget._destination, self.root)

        def test_real_thumbnails_include_heic_and_portrait_aspect_ratio(self):
            self.show_grid()
            self.wait_for(lambda: len(self.grid.model.cache) == 4)
            portrait = self.grid.model.cache[self.portrait].pixmap(self.grid.view.iconSize())
            self.assertGreater(portrait.height(), portrait.width())
            landscape = self.grid.model.cache[self.landscape].pixmap(self.grid.view.iconSize()).toImage()
            self.assertGreater(landscape.pixelColor(landscape.rect().center()).red(), 240)
            self.assertFalse(self.grid.model.cache[self.heic].isNull())
            self.assertFalse(self.grid.model.errors)

        def test_folder_single_click_selects_and_double_click_toggles_in_both_views(self):
            tree = self.widget.file_management._list
            folder = self.widget.file_management._folder_items[self.alpha]
            for tab in (0, 1):
                with self.subTest(tab=tab):
                    self.widget.view_tabs.setCurrentIndex(tab)
                    app.processEvents()
                    folder.setExpanded(False)
                    point = tree.visualItemRect(folder).center()
                    QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
                    self.assertFalse(folder.isExpanded())
                    self.assertEqual(self.grid.folder, self.alpha)
                    QtTest.QTest.mouseDClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
                    self.assertTrue(folder.isExpanded())
                    QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
                    self.assertTrue(folder.isExpanded())
                    QtTest.QTest.mouseDClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
                    self.assertFalse(folder.isExpanded())

        def test_single_click_updates_metadata_and_edits_without_loading_full_picture(self):
            self.show_grid(self.alpha)
            with patch.object(self.widget.image_display, 'display_image') as display:
                self.click(self.landscape)
                self.assertEqual(self.widget.image_path, self.landscape)
                self.assertEqual(self.widget.metadata._dimensionw.text(), '48x32')
                self.assertEqual(self.widget.view_tabs.currentIndex(), 1)
                display.assert_not_called()
            self.widget.metadata._ratingw.stars[3].click()
            self.assertEqual(read_rating(self.root, self.landscape), 4)
            self.widget.metadata.deletion_checkbox.click()
            self.assertTrue(is_marked_for_deletion(self.root, self.landscape))
            self.assertEqual(self.widget.file_management._list.currentItem().data(0, QtCore.Qt.ItemDataRole.UserRole),
                             self.landscape)

        def test_double_click_opens_single_picture_with_selection_preserved(self):
            self.show_grid()
            self.click(self.landscape, double=True)
            self.assertEqual(self.widget.view_tabs.currentIndex(), 0)
            self.assertEqual(self.widget.image_path, self.landscape)
            self.assertFalse(self.widget.image_display.pixmap().isNull())
            self.widget.view_tabs.setCurrentIndex(1)
            self.assertEqual(self.grid.view.currentIndex().row(), self.grid.model.rows[self.landscape])

        def test_x_advances_only_within_the_grid_scope(self):
            self.show_grid(self.alpha)
            self.click(self.portrait)
            self.press_x()
            self.assertTrue(is_marked_for_deletion(self.root, self.portrait))
            self.assertEqual(self.widget.image_path, self.landscape)
            self.press_x()
            self.assertEqual(self.widget.image_path, self.landscape)
            self.assertTrue(is_marked_for_deletion(self.root, self.landscape))
            self.press_x()
            self.assertFalse(is_marked_for_deletion(self.root, self.landscape))
            self.assertEqual(self.widget.view_tabs.currentIndex(), 1)

        def test_empty_folder_clears_selection_and_disables_review(self):
            self.show_grid()
            self.click(self.landscape)
            self.widget.select_grid_folder(self.root / 'empty')
            self.assertEqual(self.grid.model.rowCount(), 0)
            self.assertTrue(self.grid.empty_label.isVisible())
            self.assertIsNone(self.widget.image_path)
            self.assertFalse(self.widget.metadata.deletion_checkbox.isEnabled())
            self.assertFalse(self.widget.metadata._ratingw.isEnabled())

        def test_refresh_keeps_folder_and_selection_and_includes_new_images(self):
            self.show_grid(self.alpha)
            self.click(self.landscape)
            new = self.alpha / 'new.png'
            Image.new('RGB', (48, 32)).save(new)
            self.widget._refresh_library()
            self.assertEqual(self.grid.folder, self.alpha)
            self.assertIn(new, self.grid.model.paths)
            self.assertEqual(self.widget.image_path, self.landscape)
            self.assertEqual(self.grid.view.currentIndex().row(), self.grid.model.rows[self.landscape])

        def test_bad_image_shows_preview_error_and_can_be_opened_without_crashing(self):
            invalid = self.alpha / 'broken.jpg'
            invalid.write_bytes(b'not an image')
            self.widget._refresh_library()
            self.show_grid(self.alpha)
            self.wait_for(lambda: invalid in self.grid.model.errors)
            self.click(invalid, double=True)
            self.assertEqual(self.widget.image_path, invalid)
            self.assertEqual(self.widget.view_tabs.currentIndex(), 0)
            self.assertIn('Unable to display', self.widget.image_display.text())

        def test_late_results_from_previous_folder_are_discarded(self):
            started, release = threading.Event(), threading.Event()
            self.addCleanup(release.set)
            def delayed(path, size):
                if path.is_relative_to(self.alpha):
                    started.set()
                    release.wait(4)
                return load_thumbnail(path, size)
            with patch('viewview.grid.load_thumbnail', side_effect=delayed):
                self.show_grid(self.alpha)
                self.wait_for(started.is_set)
                self.widget.select_grid_folder(self.beta)
                self.assertEqual(self.grid.model.paths, (self.heic,))
                release.set()
                self.wait_for(lambda: self.heic in self.grid.model.cache and not self.grid._jobs)
            self.assertEqual(set(self.grid.model.cache), {self.heic})

        def test_large_folder_scrolls_and_only_loads_visible_thumbnails(self):
            large = self.root / 'large'
            large.mkdir()
            contents = self.last.read_bytes()
            for number in range(220):
                (large / f'{number:04}.jpg').write_bytes(contents)
            self.widget._refresh_library()
            self.show_grid(large)
            self.wait_for(lambda: bool(self.grid.model.cache))
            self.assertLess(len(self.grid.model.cache), 220)
            self.assertLessEqual(len(self.grid._jobs), 2)
            scrollbar = self.grid.view.verticalScrollBar()
            self.assertGreater(scrollbar.maximum(), 0)
            scrollbar.setValue(scrollbar.maximum())
            self.wait_for(lambda: self.grid.model.paths[-1] in self.grid.model.cache)
            self.assertLessEqual(len(self.grid.model.cache), self.grid.model.cache_limit)

        def test_thumbnail_honors_exif_orientation(self):
            path = self.root / 'rotated.jpg'
            exif = Image.Exif()
            exif[Base.Orientation] = 6
            Image.new('RGB', (60, 40), 'red').save(path, exif=exif)
            preview = load_thumbnail(path, (176, 132))
            self.assertEqual((preview.width(), preview.height()), (40, 60))

        def test_closing_while_previews_load_does_not_wait_or_touch_closed_widgets(self):
            started, release = threading.Event(), threading.Event()
            self.addCleanup(release.set)
            def delayed(path, size):
                started.set()
                release.wait(4)
                return load_thumbnail(path, size)
            with patch('viewview.grid.load_thumbnail', side_effect=delayed):
                self.show_grid()
                self.wait_for(started.is_set)
                self.assertTrue(self.widget.close())
                self.assertTrue(self.grid._closed)
                self.assertFalse(self.grid._timer.isActive())
                release.set()
                self.wait_for(lambda: all(future.done() for future in self.grid._jobs))

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(GridTests))
    return 0 if result.wasSuccessful() else 1


class GuiGridProcessTests(unittest.TestCase):
    def test_gui_grid(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'import runpy; runpy.run_path("tests/test_gui_grid.py", run_name="__main__")'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    raise SystemExit(check_grid())
