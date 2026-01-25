import sys
import pathlib

from PySide6 import QtCore, QtWidgets, QtGui


class FileManagementWidget(QtWidgets.QWidget):
    def __init__(self, image_display: 'ImageDisplayWidget'):
        super().__init__()
        self._image_display = image_display

        self.setMinimumWidth(200)

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
        def _callback(item: QtWidgets.QListWidgetItem):
            print('[Temporary] - List item has been pressed')
            self._image_display.display_image(item.data(QtCore.Qt.ItemDataRole.UserRole))

        self._list = QtWidgets.QListWidget()
        self._list.itemClicked.connect(_callback)

    def _update_list(self):
        self._list.clear()

        # TODO: add other image types later on
        for file in self._selected_folder.glob('**/*.jpg'):
            filename = file.relative_to(self._selected_folder)
            item = QtWidgets.QListWidgetItem(str(filename))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, file)
            self._list.addItem(item)

    def _init_layout(self):
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.addWidget(self._input)
        self._layout.addWidget(self._list)
        self.setLayout(self._layout)


class ImageDisplayWidget(QtWidgets.QLabel):
    def __init__(self):
        super().__init__()

    def display_image(self, img_path: pathlib.Path):
        reader = QtGui.QImageReader(str(img_path))
        self._pixel_map = QtGui.QPixmap.fromImage(reader.read())

        scaled = self._pixel_map.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )

        self.setPixmap(scaled)


class CustomWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        img_path = pathlib.Path('/Users/romain/Pictures/Wallpaper1.jpg')
        image_display = ImageDisplayWidget()
        image_display.display_image(img_path)

        file_management = FileManagementWidget(image_display)

        self._layout = QtWidgets.QHBoxLayout(self) 
        self._layout.addWidget(file_management)
        self._layout.addWidget(image_display)
        self.setLayout(self._layout)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])

    widget = CustomWidget()
    widget.showMaximized()

    sys.exit(app.exec())
