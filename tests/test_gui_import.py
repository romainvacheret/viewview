"""Run GUI imports with real media and worker threads, isolated from CLI tests."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


def check_import_gui():
    import json
    import shutil
    import tempfile
    import threading
    import time
    from unittest.mock import patch
    from PIL import Image
    from PIL.ExifTags import Base, IFD
    from PySide6 import QtCore, QtTest, QtWidgets
    from viewview.gui import MainWidget
    from viewview.import_gui import import_images, parse_tags

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(Path('viewview/style.qss').read_text())

    class ImportGuiTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.addCleanup(self.temp.cleanup)
            root = Path(self.temp.name)
            self.source = root / 'source'
            self.source.mkdir()
            self.destination = root / 'library'
            (self.destination / '2026/07/01').mkdir(parents=True)
            (self.destination / '2024').mkdir()
            self.dated('existing.jpg', '2026:07:01 12:00:00')
            self.dated('new.jpg', '2026:07:02 13:00:00')
            Image.new('RGB', (24, 16), 'blue').save(self.source / 'undated.png')
            (self.source / 'invalid.jpg').write_bytes(b'not a photograph')
            shutil.copy2(self.source / 'existing.jpg', self.destination / '2026/07/01/existing.jpg')
            self.widget = MainWidget()
            self.widget.resize(1440, 900)
            self.widget.show()
            self.addCleanup(self.cleanup_widget)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(self.destination)):
                self.widget.select_folder()
            self.importer = self.widget.import_widget
            self.widget.tabs.setCurrentIndex(1)

        def cleanup_widget(self):
            self.wait_idle()
            self.widget.close()
            app.processEvents()

        def dated(self, name, date):
            exif = Image.Exif()
            exif[IFD.Exif] = {Base.DateTimeOriginal: date}
            Image.new('RGB', (24, 16), 'red').save(self.source / name, exif=exif)

        def wait_for(self, predicate):
            deadline = time.monotonic() + 8
            while not predicate() and time.monotonic() < deadline:
                QtTest.QTest.qWait(10)
            self.assertTrue(predicate(), self.importer.summary.text())

        def wait_idle(self):
            self.wait_for(lambda: not self.importer.is_busy and not self.importer._timer.isActive()
                          and not self.importer._pending_preview)

        def preview(self, tags=''):
            self.importer.tags_input.setText(tags)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(self.source)):
                self.importer.source_button.click()
            self.wait_idle()
            self.assertIsNotNone(self.importer._plan, self.importer.details.toPlainText())

        def test_tag_delimiters(self):
            self.assertEqual(parse_tags(' holiday family ,  summer holiday, family, ,family '),
                             ('holiday family', 'summer holiday', 'family'))
            self.assertEqual(parse_tags('"summer holiday" family'), ('"summer holiday" family',))

        def test_preview_is_read_only_and_shows_complete_destination(self):
            before = {p.relative_to(self.destination): p.read_bytes()
                      for p in self.destination.rglob('*') if p.is_file()}
            self.preview(' Summer holiday , family ')
            self.assertEqual(self.widget.tabs.count(), 2)
            self.assertEqual(self.importer._destination, self.destination)
            self.assertEqual(len(self.importer._plan.files), 2)
            self.assertEqual(len(self.importer._plan.skipped_files), 1)
            self.assertEqual(len(self.importer._plan.invalid_files), 1)
            self.assertIn('invalid.jpg', self.importer.details.toPlainText())
            self.assertEqual(before, {p.relative_to(self.destination): p.read_bytes()
                                     for p in self.destination.rglob('*') if p.is_file()})
            self.assertFalse((self.destination / '_undated').exists())
            root = self.importer.tree.topLevelItem(0)
            self.assertEqual([root.text(i) for i in (1, 2, 3)], ['1', '2', '3'])
            folders = {}
            def visit(item):
                folders[Path(item.toolTip(0)).relative_to(self.destination).as_posix()] = item
                for index in range(item.childCount()):
                    visit(item.child(index))
            visit(root)
            self.assertIn('2024', folders)
            self.assertEqual(folders['2026/07/02'].text(4), 'Create')
            self.assertEqual(folders['2026'].text(4), 'Existing')
            self.assertEqual(folders['_undated'].text(2), '1')
            self.assertTrue(self.importer.import_button.isEnabled())

        def test_copy_import_applies_multiple_tags_and_refreshes_viewer(self):
            self.preview(' Summer holiday , family, family ')
            self.importer.import_button.click()
            self.wait_idle()
            self.assertTrue((self.source / 'new.jpg').exists())
            self.assertTrue((self.destination / '2026/07/02/new.jpg').exists())
            self.assertTrue((self.destination / '_undated/undated.png').exists())
            self.assertEqual(len(self.widget.file_management._image_items), 3)
            self.assertIn('Copied 2 files', self.importer.result_label.text())
            paths = ['2026/07/01/existing.jpg', '2026/07/02/new.jpg', '_undated/undated.png']
            self.assertEqual(json.loads((self.destination / 'tags.json').read_text()),
                             {'Summer holiday': paths, 'family': paths})
            self.assertEqual(len(list(self.destination.glob('import-report-*.json'))), 1)
            self.assertEqual(len(self.importer._plan.files), 0)
            self.assertEqual(len(self.importer._plan.identical_files), 3)

        def test_move_leaves_duplicates_and_invalid_files_in_source(self):
            self.importer.move_button.click()
            self.preview()
            self.importer.import_button.click()
            self.wait_idle()
            self.assertFalse((self.source / 'new.jpg').exists())
            self.assertFalse((self.source / 'undated.png').exists())
            self.assertTrue((self.source / 'existing.jpg').exists())
            self.assertTrue((self.source / 'invalid.jpg').exists())
            self.assertIn('Moved 2 files', self.importer.result_label.text())
            self.assertFalse(self.importer.import_button.isEnabled())

        def test_invalid_tag_index_disables_import_before_any_move(self):
            (self.destination / 'tags.json').write_text('broken')
            self.importer.move_button.click()
            self.preview_failure('family')
            self.assertIn('Invalid tag index', self.importer.details.toPlainText())
            self.assertTrue((self.source / 'new.jpg').exists())
            self.assertFalse(self.importer.import_button.isEnabled())

        def preview_failure(self, tags):
            self.importer.tags_input.setText(tags)
            self.importer.set_source(self.source)
            self.wait_idle()
            self.assertIsNone(self.importer._plan)

        def test_source_equal_to_destination_is_rejected(self):
            self.importer.set_source(self.destination)
            self.wait_idle()
            self.assertIn('Destination must be outside', self.importer.details.toPlainText())
            self.assertFalse(self.importer.import_button.isEnabled())

        def test_stale_preview_is_discarded_after_source_changes(self):
            started = threading.Event()
            release = threading.Event()
            other = self.source.parent / 'empty'
            other.mkdir()
            def delayed(source, destination, **kwargs):
                if source == self.source:
                    started.set()
                    release.wait(3)
                return import_images(source, destination, **kwargs)
            with patch('viewview.import_gui.import_images', side_effect=delayed):
                self.importer.set_source(self.source)
                self.wait_for(started.is_set)
                self.importer.set_source(other)
                self.assertFalse(self.importer.import_button.isEnabled())
                release.set()
                self.wait_idle()
            self.assertEqual(self.importer._source, other)
            self.assertEqual(self.importer._plan.files, [])
            self.assertFalse(self.importer.import_button.isEnabled())

        def test_import_runs_off_main_thread_and_close_waits_for_it(self):
            self.preview()
            started = threading.Event()
            release = threading.Event()
            threads = []
            def delayed(source, destination, **kwargs):
                threads.append(QtCore.QThread.currentThread())
                if not kwargs.get('dry_run'):
                    started.set()
                    release.wait(3)
                return import_images(source, destination, **kwargs)
            with patch('viewview.import_gui.import_images', side_effect=delayed):
                self.importer.import_button.click()
                self.wait_for(started.is_set)
                self.assertFalse(self.importer.source_button.isEnabled())
                self.assertFalse(self.widget.close())
                self.widget.tabs.setCurrentIndex(0)
                self.assertEqual(self.widget.tabs.currentIndex(), 0)
                release.set()
                self.wait_idle()
            self.assertTrue(all(thread != app.thread() for thread in threads))
            self.assertTrue(self.widget.close())

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ImportGuiTests))
    return 0 if result.wasSuccessful() else 1


class GuiImportProcessTests(unittest.TestCase):
    def test_gui_import(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'import runpy; runpy.run_path("tests/test_gui_import.py", run_name="__main__")'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    raise SystemExit(check_import_gui())
