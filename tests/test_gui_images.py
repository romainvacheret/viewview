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
    from PySide6 import QtWidgets

    from viewview.gui import MainWidget, MetadataHandler


    class GuiImageTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

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
                        self.assertEqual(widget.metadata._ratingw.text(), '4')
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
                    self.assertEqual(widget.metadata._ratingw.text(), '0')
                    self.assertEqual(widget.metadata._dimensionw.text(), '32x24')

                (root / 'directory.jpg').mkdir()
                (root / 'ignored.txt').write_text('Not an image')
                widget.file_management._selected_folder = root
                widget.file_management._update_list()
                listing = widget.file_management._list
                self.assertEqual(
                    {listing.item(i).text() for i in range(listing.count())},
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
