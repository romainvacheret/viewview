import sys
import pathlib

from PySide6 import QtCore, QtWidgets
from PySide6 import QtGui




class FileManagementWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        # TODO: should be done after the window has appeared
        self._select_folder()

        self._init_input()
        self._init_list()
        self._init_layout()

        self._update_list()

    def _select_folder(self):
        self._browser = QtWidgets.QFileDialog(self, "Select folder")
        self._selected_folder = pathlib.Path(self._browser.getExistingDirectory())

    def _init_input(self):
        self._input = QtWidgets.QLabel(str(self._selected_folder))

    def _init_list(self):
        def tmp_func():
            print('[Temporary] - List item has been pressed')
        self._list = QtWidgets.QListWidget()
        self._list.itemClicked.connect(tmp_func)

    def _update_list(self):
        self._list.clear()

        # TODO: add other image types later on
        for file in self._selected_folder.glob('**/*.jpg'):
            filename = file.relative_to(self._selected_folder)
            item = QtWidgets.QListWidgetItem(str(filename))

            self._list.addItem(item)

    def _init_layout(self):
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.addWidget(self._input)
        self._layout.addWidget(self._list)
        self.setLayout(self._layout)


class CustomWidget(QtWidgets.QWidget):
    def __init__(self):

        super().__init__()
        layout = QtWidgets.QHBoxLayout(self) 
        img_path = '/Users/romain/Pictures/Wallpaper1.jpg'
        reader = QtGui.QImageReader(img_path)
        loaded_img = reader.read()
        pixel_map = QtGui.QPixmap.fromImage(loaded_img)

        img_label = QtWidgets.QLabel()
        img_label.setPixmap(pixel_map)
        img_label.setScaledContents(True)
         
        file_management = FileManagementWidget()

        layout.addWidget(file_management)
        layout.addWidget(img_label)

        self.setLayout(layout)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])

    widget = CustomWidget()
    widget.showMaximized()

    sys.exit(app.exec())
