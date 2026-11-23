"""Executable entry point, including a noninteractive packaging smoke check."""
import sys


def main():
    if sys.argv[1:] == ['--smoke-test']:
        return _smoke_test()
    from .cli import main as cli_main
    return cli_main()


def _smoke_test():
    import os
    from pathlib import Path
    import tempfile
    import time

    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PIL import Image
    from PySide6 import QtCore, QtGui, QtWidgets
    from .gui import MainWidget
    from . import gui
    from .core.review import read_deletion_marks, set_deletion_mark, read_rating, set_rating
    from .core.tags import add_tags, read_tags, photo_tags

    app = QtWidgets.QApplication([])
    stylesheet = Path(gui.__file__).with_name('style.qss')
    app.setStyleSheet(stylesheet.read_text(encoding='utf-8'))
    widget = MainWidget()
    widget.resize(1000, 700)
    widget.show()
    app.processEvents()
    with tempfile.TemporaryDirectory() as directory:
        for extension in ('jpg', 'png', 'heic'):
            path = Path(directory) / f'check.{extension}'
            Image.new('RGB', (32, 24), 'red').save(path)
            widget.set_current_image(path)
            pixmap = widget.image_display.pixmap()
            if pixmap.isNull() or pixmap.toImage().pixelColor(0, 0).red() < 240:
                raise RuntimeError(f'Packaged {extension} decoding failed')
        library = Path(directory)
        set_deletion_mark(library, path, True)
        set_rating(library, path, 4)
        add_tags(library, ['Bundle check'], [path.name])
        if (read_deletion_marks(library) != {path.name} or read_rating(library, path) != 4
                or read_tags(library) != {'Bundle check': [path.name]}):
            raise RuntimeError('Packaged SQLite metadata storage failed')
        add_tags(library, ['Completion test'], ['check.jpg'])
        widget.file_management._selected_folder = library
        widget.file_management._update_list()
        widget.set_current_image(path)
        editor = widget.metadata.tags_editor
        editor.input.setText('Compl')
        app.sendEvent(editor.input, QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                      QtCore.Qt.Key.Key_Tab, QtCore.Qt.KeyboardModifier.NoModifier))
        if 'Completion test' not in photo_tags(library, path.name):
            raise RuntimeError('Packaged tag completion failed')
        editor.chips['Completion test'].remove_button.click()
        if photo_tags(library, path.name) != ['Bundle check']:
            raise RuntimeError('Packaged tag chip removal failed')
        widget.grid.set_folder(library, sorted(library.glob('check.*')))
        widget.view_tabs.setCurrentIndex(1)
        deadline = time.monotonic() + 10
        while len(widget.grid.model.cache) < 3 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if len(widget.grid.model.cache) != 3 or widget.grid.model.errors:
            raise RuntimeError('Packaged grid thumbnail decoding failed')
    widget.close()
    print('Viewview bundle check passed: Qt, stylesheet, JPEG, PNG, HEIC, SQLite, grid previews, tag editor')
    return 0
