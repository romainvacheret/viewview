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

    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PIL import Image
    from PySide6 import QtWidgets
    from .gui import MainWidget
    from . import gui

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
    widget.close()
    print('Viewview bundle check passed: Qt, stylesheet, JPEG, PNG, HEIC')
    return 0
