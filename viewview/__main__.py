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


class ToggleSplitterHandle(QtWidgets.QSplitterHandle):
    def __init__(self, orientation: QtCore.Qt.Orientation, 
                 parent: QtWidgets.QSplitter) -> None:
        super().__init__(orientation, parent)
        # TODO: choose default
        self._saved_size = 300
        self._saved_pos = None

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._saved_pos = event.position().toPoint()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent, /) -> None:
        current_position = event.position().toPoint()
        if (event.button() == QtCore.Qt.MouseButton.LeftButton and 
            current_position == self._saved_pos):
            self._collapse_split() 
        else:
            super().mouseReleaseEvent(event)

        self._saved_pos = None

    def _collapse_split(self):
        DISPLAY_SPLIT = 1
        # TODO: choose the target dynamically
        target_split = 0
        splitter = self.splitter()
        sizes = splitter.sizes()
        target_size = sizes[target_split]

        is_collapsed = target_size == 0

        # TODO: could improve safety
        if is_collapsed:
            sizes[target_split] = self._saved_size
            sizes[DISPLAY_SPLIT] -= self._saved_size
            self._saved_size = 0
        else:
            self._saved_size = target_size
            sizes[target_split] = 0
            sizes[DISPLAY_SPLIT] += target_size

        splitter.setSizes(sizes)


class ToggleSplitter(QtWidgets.QSplitter):
    def createHandle(self):
        return ToggleSplitterHandle(self.orientation(), self)


class CustomWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        img_path = pathlib.Path('/Users/romain/Pictures/Wallpaper1.jpg')
        image_display = ImageDisplayWidget()
        image_display.display_image(img_path)

        file_management = FileManagementWidget(image_display)


        self._splitter = ToggleSplitter(QtCore.Qt.Orientation.Horizontal)
        self._splitter.addWidget(file_management)
        self._splitter.addWidget(image_display)
        self._splitter.setSizes((300, 900))
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setCollapsible(0, True)

        self._layout = QtWidgets.QHBoxLayout(self) 
        self._layout.addWidget(self._splitter)
        self.setLayout(self._layout)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])

    widget = CustomWidget()
    widget.showMaximized()

    sys.exit(app.exec())
