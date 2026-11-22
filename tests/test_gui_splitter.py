"""Exercise real divider mouse events in a process separate from CLI tests."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def check_splitter():
    from PIL import Image
    from PIL.ExifTags import Base
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets
    from viewview.gui import MainWidget

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(Path('viewview/style.qss').read_text())

    class SplitterTests(unittest.TestCase):
        def setUp(self):
            self.widget = MainWidget()
            self.widget.resize(1440, 900)
            self.widget.show()
            app.processEvents()
            self.widget.file_management._input.setText('Pictures / ' + 'Collection ' * 5)
            self.widget.file_management.update_width_limit()
            self.widget.metadata._descriptionw.setText('A detailed image description ' * 3)
            self.widget.metadata.update_width_limit()
            self.splitter = self.widget._splitter
            self.splitter.setSizes([300, 800, 300])
            app.processEvents()
            self.addCleanup(self.widget.close)

        def click(self, index):
            QtTest.QTest.mouseClick(self.splitter.handle(index), QtCore.Qt.MouseButton.LeftButton)
            app.processEvents()

        def drag(self, index, distance):
            handle = self.splitter.handle(index)
            start = handle.rect().center()
            origin = handle.mapToGlobal(start)
            QtTest.QTest.mousePress(handle, QtCore.Qt.MouseButton.LeftButton, pos=start)
            steps = distance if isinstance(distance, list) else (distance // 2, distance)
            for delta in steps:
                global_pos = origin + QtCore.QPoint(delta, 0)
                local = handle.mapFromGlobal(global_pos)
                event = QtGui.QMouseEvent(
                    QtCore.QEvent.Type.MouseMove, QtCore.QPointF(local),
                    QtCore.QPointF(global_pos), QtCore.Qt.MouseButton.NoButton,
                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                )
                app.sendEvent(handle, event)
                app.processEvents()
            QtTest.QTest.mouseRelease(handle, QtCore.Qt.MouseButton.LeftButton,
                                      pos=handle.mapFromGlobal(global_pos))
            app.processEvents()

        def test_image_does_not_lock_dividers_or_push_opposite_panel(self):
            image = QtGui.QPixmap(1200, 800)
            image.fill(QtCore.Qt.GlobalColor.red)
            self.widget.image_display.setPixmap(image.scaled(self.widget.image_display.size()))
            app.processEvents()
            for index, distance, opposite in ((1, 80, 2), (2, -80, 0)):
                with self.subTest(handle=index):
                    before = self.splitter.sizes()
                    self.drag(index, distance)
                    after = self.splitter.sizes()
                    self.assertAlmostEqual(after[opposite], before[opposite], delta=1,
                                           msg=f'drag pushed opposite panel: {before} -> {after}')
                    self.assertLess(after[1], before[1] - 40)

        def test_long_folder_path_does_not_lock_file_panel(self):
            before = self.splitter.sizes()
            self.widget.file_management._input.setText('/pictures/' + 'long-folder-name/' * 30)
            app.processEvents()
            self.drag(1, -60)
            after = self.splitter.sizes()
            self.assertLess(after[0], before[0] - 30)
            self.assertAlmostEqual(after[2], before[2], delta=1)

        def test_drag_resizes_without_collapsing(self):
            for index, distance, target, opposite in ((1, 80, 0, 2), (2, -80, 2, 0)):
                with self.subTest(handle=index):
                    self.splitter.setSizes([300, 800, 300])
                    before = self.splitter.sizes()
                    self.drag(index, distance)
                    after = self.splitter.sizes()
                    self.assertGreater(after[target], before[target] + 40,
                                       f'drag should expand its panel: {before} -> {after}')
                    self.assertAlmostEqual(after[opposite], before[opposite], delta=1)

        def test_click_does_not_reopen_opposite_panel(self):
            self.click(2)
            self.assertEqual(self.splitter.sizes()[2], 0)
            self.click(1)
            self.assertEqual(self.splitter.sizes()[0], 0)
            self.assertEqual(self.splitter.sizes()[2], 0, 'left click reopened right panel')
            self.click(1)
            self.assertGreater(self.splitter.sizes()[0], 0)
            self.assertEqual(self.splitter.sizes()[2], 0, 'left click reopened right panel')

        def test_click_restores_previous_width_for_each_side(self):
            for index, target, opposite in ((1, 0, 2), (2, 2, 0)):
                with self.subTest(handle=index):
                    self.splitter.setSizes([340, 700, 280])
                    before = self.splitter.sizes()
                    self.click(index)
                    self.assertEqual(self.splitter.sizes()[target], 0)
                    self.assertEqual(self.splitter.sizes()[opposite], before[opposite])
                    self.click(index)
                    self.assertEqual(self.splitter.sizes(), before)

        def test_small_pointer_jitter_counts_as_click(self):
            self.drag(1, [1, 2])
            self.assertEqual(self.splitter.sizes()[0], 0)

        def test_drag_returning_to_origin_does_not_count_as_click(self):
            before = self.splitter.sizes()
            self.drag(1, [80, 0])
            self.assertEqual(self.splitter.sizes(), before)

        def test_drag_at_limit_does_not_push_opposite_panel(self):
            for index, target, opposite, direction in ((1, 0, 2, 1), (2, 2, 0, -1)):
                with self.subTest(handle=index):
                    self.splitter.setSizes([300, 800, 300])
                    before = self.splitter.sizes()
                    self.drag(index, direction * 3000)
                    after = self.splitter.sizes()
                    self.assertEqual(after[opposite], before[opposite])
                    self.assertGreater(after[1], 0)
                    self.drag(index, -direction * 3000)
                    after = self.splitter.sizes()
                    self.assertGreater(after[target], 0)
                    self.assertEqual(after[opposite], before[opposite])

        def test_drag_preserves_collapsed_opposite_panel(self):
            self.click(2)
            self.drag(1, 80)
            self.assertEqual(self.splitter.sizes()[2], 0)
            self.click(2)
            self.click(1)
            self.drag(2, -80)
            self.assertEqual(self.splitter.sizes()[0], 0)

        def test_reshow_preserves_panel_sizes(self):
            self.splitter.setSizes([350, 700, 300])
            before = self.splitter.sizes()
            self.widget.hide()
            self.widget.show()
            app.processEvents()
            self.assertEqual(self.splitter.sizes(), before)

        def test_file_panel_limit_tracks_folder_contents(self):
            panel = self.widget.file_management
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                longest_name = 'A longer photograph filename ' * 3 + '.jpg'
                (root / longest_name).touch()
                panel._selected_folder = root
                panel._input.setText('Pictures')
                panel._update_list()
                app.processEvents()
                limit = panel.maximumWidth()
                text_width = panel._list.fontMetrics().horizontalAdvance(longest_name)
                self.assertGreater(limit, text_width)
                self.assertLess(limit, text_width + 160)
                opposite = self.splitter.sizes()[2]
                self.drag(1, 3000)
                self.assertEqual(panel.width(), limit)
                self.assertEqual(panel._list.horizontalScrollBar().maximum(), 0)
                self.assertEqual(self.splitter.sizes()[2], opposite)

                self.click(1)
                (root / longest_name).unlink()
                (root / 'short.jpg').touch()
                panel._update_list()
                app.processEvents()
                self.assertLess(panel.maximumWidth(), limit - 100)
                self.assertEqual(self.splitter.sizes()[0], 0)
                self.click(1)
                self.assertEqual(panel.width(), panel.maximumWidth())

        def test_metadata_limit_tracks_image_and_fits_both_columns(self):
            panel = self.widget.metadata
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'photo.jpg'
                exif = Image.Exif()
                description = 'A detailed photograph description ' * 2
                exif[Base.ImageDescription] = description
                Image.new('RGB', (24, 16)).save(path, exif=exif)
                self.widget.set_current_image(path)
                app.processEvents()
                limit = panel.maximumWidth()
                opposite = self.splitter.sizes()[0]
                self.drag(2, -3000)
                self.assertEqual(panel.width(), limit)
                self.assertGreaterEqual(panel._descriptionw.width(), panel._descriptionw.sizeHint().width())
                self.assertLess(panel.width() - panel._descriptionw.sizeHint().width(), 200)
                self.assertEqual(self.splitter.sizes()[0], opposite)

                Image.new('RGB', (24, 16)).save(path)
                self.widget.set_current_image(path)
                app.processEvents()
                self.assertLess(panel.maximumWidth(), limit - 100)
                self.assertLessEqual(panel.width(), panel.maximumWidth())
                self.widget.resize(1800, 900)
                app.processEvents()
                self.assertLessEqual(panel.width(), panel.maximumWidth())

        def test_full_path_tooltips_follow_hover_and_hide_in_empty_space(self):
            from html import escape
            from unittest.mock import patch

            panel = self.widget.file_management
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in ('a very long filename <photo&>.jpg', 'another picture.png'):
                    (root / name).touch()
                with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=directory):
                    panel.select_folder()
                app.processEvents()
                self.assertIn(str(root), panel._input.toolTip())
                listing = panel._list
                viewport = listing.viewport()
                first = listing.visualItemRect(panel._image_items[0]).center()
                help_event = QtGui.QHelpEvent(QtCore.QEvent.Type.ToolTip, first,
                                             viewport.mapToGlobal(first))
                app.sendEvent(viewport, help_event)
                self.assertTrue(QtWidgets.QToolTip.isVisible())
                self.assertIn(escape(str(root / panel._image_items[0].text(0))), QtWidgets.QToolTip.text())

                second = listing.visualItemRect(panel._image_items[1]).center()
                QtTest.QTest.mouseMove(viewport, second)
                app.processEvents()
                self.assertIn(escape(str(root / panel._image_items[1].text(0))), QtWidgets.QToolTip.text())

                QtTest.QTest.mouseMove(viewport, QtCore.QPoint(5, viewport.height() - 5))
                QtTest.QTest.qWait(400)
                self.assertFalse(QtWidgets.QToolTip.isVisible())

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SplitterTests))
    return 0 if result.wasSuccessful() else 1


class GuiSplitterProcessTests(unittest.TestCase):
    def test_gui_splitter(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'import runpy; runpy.run_path("tests/test_gui_splitter.py", run_name="__main__")'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    raise SystemExit(check_splitter())
