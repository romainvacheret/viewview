from datetime import datetime
from pathlib import Path
import tempfile
import unittest

import os
import subprocess
import sys


def check_images():
    from PIL import Image
    from PIL.ExifTags import Base, IFD
    from PySide6 import QtCore, QtTest, QtWidgets

    from viewview.gui import MainWidget, MetadataHandler


    class GuiImageTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        def test_folder_tree_hierarchy_clicks_refresh_and_navigation(self):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                nested = root / '2026' / '07'
                nested.mkdir(parents=True)
                (root / 'empty').mkdir()
                first = nested / 'first.jpg'
                second = root / 'last.jpg'
                for path in (first, second):
                    Image.new('RGB', (24, 16), 'red').save(path)
                (root / 'notes.txt').write_text('Not an image')
                widget = MainWidget()
                self.addCleanup(widget.close)
                widget.resize(1200, 800)
                widget.show()
                panel = widget.file_management
                panel._selected_folder = root
                panel._update_list()
                self.app.processEvents()
                tree = panel._list
                root_item = tree.topLevelItem(0)
                year = panel._folder_items[root / '2026']
                month = panel._folder_items[nested]
                self.assertEqual(tree.topLevelItemCount(), 1)
                self.assertIs(year.parent(), root_item)
                self.assertIs(month.parent(), year)
                self.assertIs(panel._image_items[0].parent(), month)
                self.assertEqual(panel._image_items[0].text(0), 'first.jpg')
                self.assertIn(root / 'empty', panel._folder_items)
                self.assertEqual(len(panel._image_items), 2)
                self.assertTrue(root_item.isExpanded())
                self.assertFalse(year.isExpanded())

                def click(item, double=False):
                    QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                           pos=tree.visualItemRect(item).center())
                    if double:
                        QtTest.QTest.mouseDClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                                pos=tree.visualItemRect(item).center())
                    self.app.processEvents()

                click(year)
                self.assertFalse(year.isExpanded())
                click(year, double=True)
                self.assertTrue(year.isExpanded())
                click(month, double=True)
                self.assertTrue(month.isExpanded())
                click(panel._image_items[0])
                self.assertEqual(widget.image_path, first)
                click(year)
                self.assertTrue(year.isExpanded())
                click(year, double=True)
                self.assertFalse(year.isExpanded())
                self.assertEqual(widget.image_path, first)

                # Disclosure arrows retain their standard single-click toggle.
                rect = tree.visualItemRect(year)
                arrow = QtCore.QPoint(rect.left() - tree.indentation() // 2, rect.center().y())
                QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=arrow)
                self.app.processEvents()
                self.assertTrue(year.isExpanded())
                panel._update_list()
                self.assertTrue(panel._folder_items[root / '2026'].isExpanded())
                self.assertTrue(panel._folder_items[nested].isExpanded())
                panel._folder_items[root / '2026'].setExpanded(False)
                panel._update_list()
                self.assertFalse(panel._folder_items[root / '2026'].isExpanded())
                panel.select_next_image(first)
                self.assertEqual(widget.image_path, second)
                self.assertIs(tree.currentItem(), panel._image_items[1])
                self.assertFalse(panel._folder_items[root / '2026'].isExpanded())
                file_icons = [item.icon(0).cacheKey() for item in panel._image_items]
                tree.expandAll()
                self.assertEqual([item.icon(0).cacheKey() for item in panel._image_items], file_icons)
                widget._splitter.set_panel_sizes([panel.maximumWidth(), 700, widget.metadata.width()])
                self.app.processEvents()
                self.assertEqual(tree.horizontalScrollBar().maximum(), 0)

        def test_supported_images_display_with_metadata(self):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                nested = root / 'nested'
                nested.mkdir()
                widget = MainWidget()
                self.addCleanup(widget.close)
                for extension in ('.jpg', '.JPG', '.jpeg', '.JPEG', '.JpEg', '.png', '.PNG',
                                  '.heic', '.HEIC', '.heif', '.HEIF'):
                    path = nested / f'picture{extension}'
                    exif = Image.Exif()
                    exif[IFD.Exif] = {Base.DateTimeOriginal: '2026:11:02 12:30:00'}
                    exif[Base.Rating] = 4
                    exif[Base.ImageDescription] = 'A picture'
                    exif[Base.Model] = 'Camera'
                    exif[Base.Software] = 'Editor'
                    exif[Base.Copyright] = 'Photographer'
                    Image.new('RGB', (24, 16)).save(path, exif=exif)
                    with self.subTest(extension=extension):
                        info = MetadataHandler().read_metadata(path)
                        self.assertEqual(info.metadata.intial_date, datetime(2026, 11, 2, 12, 30))
                        widget.set_current_image(path)
                        self.assertFalse(widget.image_display.pixmap().isNull())
                        self.assertEqual(widget.metadata._datew.text(), '02/11/2026')
                        self.assertEqual(widget.metadata._ratingw.value(), 4)
                        self.assertEqual(widget.metadata._descriptionw.text(), 'A picture')
                        self.assertEqual(widget.metadata._cameraw.text(), 'Camera')
                        self.assertEqual(widget.metadata._softwarew.text(), 'Editor')
                        self.assertEqual(widget.metadata._copyrightw.text(), 'Photographer')
                        self.assertEqual(widget.metadata._dimensionw.text(), '24x16')

                # Missing metadata must replace the previous picture's values.
                for extension in ('.png', '.heic'):
                    widget.set_current_image(nested / 'picture.jpeg')
                    plain = root / f'plain{extension}'
                    Image.new('RGB', (32, 24), 'red').save(plain)
                    widget.set_current_image(plain)
                    self.assertFalse(widget.image_display.pixmap().isNull())
                    color = widget.image_display.pixmap().toImage().pixelColor(0, 0)
                    self.assertGreater(color.red(), 240)
                    self.assertLess(color.green(), 15)
                    for field in ('_datew', '_descriptionw', '_cameraw', '_softwarew', '_copyrightw'):
                        self.assertEqual(getattr(widget.metadata, field).text(), '')
                    self.assertEqual(widget.metadata._ratingw.value(), 0)
                    self.assertEqual(widget.metadata._dimensionw.text(), '32x24')

                (root / 'directory.jpg').mkdir()
                (root / 'ignored.txt').write_text('Not an image')
                widget.file_management._selected_folder = root
                widget.file_management._update_list()
                listing = widget.file_management._list
                self.assertEqual(
                    {str(item.data(0, QtCore.Qt.ItemDataRole.UserRole).relative_to(root))
                     for item in widget.file_management._image_items},
                    {str(path.relative_to(root)) for path in root.rglob('*')
                     if path.is_file() and path.suffix.lower() in
                     {'.jpg', '.jpeg', '.png', '.heic', '.heif'}},
                )
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GuiImageTests)
    result = unittest.TextTestRunner().run(suite)
    return 0 if result.wasSuccessful() else 1


class GuiImageProcessTests(unittest.TestCase):
    def test_gui_images(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'import runpy; runpy.run_path("tests/test_gui_images.py", run_name="__main__")'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    raise SystemExit(check_images())
