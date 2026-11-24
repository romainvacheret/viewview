"""Real keyboard interactions and SQLite-backed per-photo tag editing."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


def check_tags_gui():
    import tempfile
    from unittest.mock import patch
    from PIL import Image
    from PySide6 import QtCore, QtTest, QtWidgets
    from viewview.gui import MainWidget
    from viewview.core.tags import add_tags, photo_tags, tag_names
    from viewview.core.review import review_path

    from unittest.mock import patch
    patch.object(QtWidgets.QMessageBox, 'question',
                 return_value=QtWidgets.QMessageBox.StandardButton.Yes).start()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(Path('viewview/style.qss').read_text())

    class TagGuiTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name)
            self.first = self.root / 'first.jpg'
            self.second = self.root / 'second.jpg'
            for path in (self.first, self.second):
                Image.new('RGB', (48, 32), 'red').save(path)
            self.widget = MainWidget()
            self.widget.resize(1300, 850)
            self.widget.show()
            self.addCleanup(self.widget.close)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(self.root)):
                self.widget.select_folder()
            self.editor = self.widget.metadata.tags_editor
            self.widget.activateWindow()
            app.processEvents()

        def type_tag(self, text, key=QtCore.Qt.Key.Key_Return):
            self.editor.input.setFocus()
            app.processEvents()
            self.editor.input.setText(text)
            QtTest.QTest.keyClick(self.editor.input, key)
            app.processEvents()

        def test_sections_and_tag_entry_removal_are_persistent(self):
            self.assertEqual(self.widget.metadata.file_info.title(), 'Image info')
            self.assertEqual(self.widget.metadata.app_info.title(), 'App info')
            self.assertTrue(self.widget.metadata.app_info.isAncestorOf(self.widget.metadata._ratingw))
            self.assertFalse(self.editor.isEnabled())
            self.widget.set_current_image(self.first)
            self.type_tag('  Summer holiday  ')
            self.type_tag('family')
            self.assertEqual(set(self.editor.chips), {'Summer holiday', 'family'})
            self.assertEqual(set(photo_tags(self.root, 'first.jpg')), {'Summer holiday', 'family'})
            self.assertEqual(self.editor.input.text(), '')
            self.widget.set_current_image(self.second)
            self.assertEqual(self.editor.chips, {})
            self.widget.set_current_image(self.first)
            self.editor.chips['family'].remove_button.click()
            self.assertEqual(photo_tags(self.root, 'first.jpg'), ['Summer holiday'])
            self.assertIn('family', tag_names(self.root))
            self.widget.close()
            reopened = MainWidget()
            self.addCleanup(reopened.close)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(self.root)):
                reopened.select_folder()
            reopened.set_current_image(self.first)
            self.assertEqual(list(reopened.metadata.tags_editor.chips), ['Summer holiday'])

        def test_tab_completes_and_validates_existing_tag_without_moving_focus(self):
            add_tags(self.root, ['Summer holiday'], ['second.jpg'])
            self.widget.set_current_image(self.first)
            self.type_tag('sum', QtCore.Qt.Key.Key_Tab)
            self.assertEqual(photo_tags(self.root, 'first.jpg'), ['Summer holiday'])
            self.assertEqual(self.editor.input.text(), '')
            self.assertTrue(self.editor.input.hasFocus())
            self.assertIn('Summer holiday', self.editor.chips)

        def test_tab_accepts_highlighted_suggestion_from_popup(self):
            add_tags(self.root, ['Family', 'Family trip'], ['second.jpg'])
            self.widget.set_current_image(self.first)
            entry = self.editor.input
            entry.setFocus()
            QtTest.QTest.keyClicks(entry, 'Fam')
            completer = entry.completer()
            completer.setCompletionPrefix('Fam')
            completer.complete()
            popup = completer.popup()
            popup.setCurrentIndex(completer.completionModel().index(1, 0))
            QtTest.QTest.keyClick(entry, QtCore.Qt.Key.Key_Tab)
            self.assertEqual(photo_tags(self.root, 'first.jpg'), ['Family trip'])
            self.assertEqual(entry.text(), '')

        def test_enter_adds_new_tag_with_spaces_and_ignores_duplicates(self):
            self.widget.set_current_image(self.first)
            self.type_tag('new family trip')
            self.type_tag('new family trip')
            self.type_tag('   ')
            self.assertEqual(photo_tags(self.root, 'first.jpg'), ['new family trip'])
            self.assertEqual(len(self.editor.chips), 1)

        def test_typing_x_does_not_trigger_review_shortcut(self):
            self.widget.set_current_image(self.first)
            entry = self.editor.input
            entry.setFocus()
            app.processEvents()
            self.assertFalse(self.widget._mark_shortcut.isEnabled())
            QtTest.QTest.keyClicks(entry, 'xmas')
            self.assertEqual(entry.text(), 'xmas')
            self.assertEqual(self.widget.image_path, self.first)
            self.assertFalse(self.widget.metadata.deletion_checkbox.isChecked())
            self.widget.file_management._list.setFocus()
            app.processEvents()
            self.assertTrue(self.widget._mark_shortcut.isEnabled())

        def test_switching_photos_discards_draft_and_loads_correct_chips_in_grid(self):
            add_tags(self.root, ['first tag'], ['first.jpg'])
            add_tags(self.root, ['second tag'], ['second.jpg'])
            self.widget.view_tabs.setCurrentIndex(1)
            self.widget.set_current_image(self.first)
            self.editor.input.setText('draft')
            self.widget.set_current_image(self.second)
            self.assertEqual(self.editor.input.text(), '')
            self.assertEqual(list(self.editor.chips), ['second tag'])
            self.type_tag('another')
            self.assertEqual(set(photo_tags(self.root, 'second.jpg')), {'second tag', 'another'})
            self.assertEqual(photo_tags(self.root, 'first.jpg'), ['first tag'])

        def test_failed_add_and_remove_keep_confirmed_chips_and_draft(self):
            add_tags(self.root, ['family'], ['first.jpg'])
            self.widget.set_current_image(self.first)
            with patch('viewview.gui.add_tags', side_effect=PermissionError('Read-only library')):
                self.type_tag('new tag')
            self.assertEqual(self.editor.input.text(), 'new tag')
            self.assertEqual(list(self.editor.chips), ['family'])
            self.assertIn('Could not save tag', self.widget.metadata.review_error.text())
            with patch('viewview.gui.remove_photo_tag', side_effect=PermissionError('Read-only library')):
                self.editor.chips['family'].remove_button.click()
            self.assertIn('family', self.editor.chips)
            self.assertEqual(photo_tags(self.root, 'first.jpg'), ['family'])

        def test_library_vocabulary_refreshes_on_focus_and_stays_isolated(self):
            self.widget.set_current_image(self.first)
            add_tags(self.root, ['Fresh tag'], ['second.jpg'])
            self.type_tag('Fre', QtCore.Qt.Key.Key_Tab)
            self.assertEqual(photo_tags(self.root, 'first.jpg'), ['Fresh tag'])
            other = self.root / 'other'
            other.mkdir()
            image = other / 'photo.jpg'
            Image.new('RGB', (48, 32)).save(image)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(other)):
                self.widget.select_folder()
            self.widget.set_current_image(image)
            self.assertEqual(self.editor.known_names, ())
            self.assertEqual(self.editor.chips, {})

        def test_many_tags_wrap_and_sidebar_can_scroll(self):
            names = [f'Family collection {index:02}' for index in range(24)]
            add_tags(self.root, names, [review_path(self.root, self.first)])
            self.widget.set_current_image(self.first)
            self.widget.resize(1000, 550)
            self.widget._splitter.set_panel_sizes([230, 450, 300])
            app.processEvents()
            self.assertEqual(len(self.editor.chips), 24)
            self.assertGreater(self.editor.flow.heightForWidth(240), 28)
            self.assertGreater(self.widget.metadata.scroll.verticalScrollBar().maximum(), 0)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TagGuiTests))
    return 0 if result.wasSuccessful() else 1


class GuiTagsProcessTests(unittest.TestCase):
    def test_gui_tags(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'import runpy; runpy.run_path("tests/test_gui_tags.py", run_name="__main__")'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    raise SystemExit(check_tags_gui())
