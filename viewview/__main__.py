import sys
import pathlib

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PIL import Image
from PIL.ImageFile import ImageFile
from PIL.ExifTags import Base

from PySide6 import QtCore, QtWidgets, QtGui


def _read_date(date_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    # TODO: handle better
    except ValueError:
        return None


@dataclass
class ImageMetadata:
    intial_date: Optional[datetime]
    rating: int
    description: str
    camera: str
    software: str
    copyright: str

@dataclass
class ImageInfo:
    metadata: ImageMetadata
    width: int
    height: int
    path: pathlib.Path

class MetadataHandler:
    def read_metadata(self, image: pathlib.Path) -> Optional[ImageInfo]:
        # TODO: add other image types 
        match image.suffix:
            case '.jpg': return self.read_jpeg(image)
            case _: return None

    def _read_exif(self, img: ImageFile) -> ImageMetadata:
        exif = img.getexif()
        return ImageMetadata(
            _read_date(str(exif.get(Base.DateTimeOriginal))),
            exif.get(Base.Rating, 0),
            exif.get(Base.ImageDescription, ''),
            exif.get(Base.Model, ''),
            exif.get(Base.Software, ''),
            exif.get(Base.Copyright, '')
        )

    def read_jpeg(self, image: pathlib.Path) -> ImageInfo:
        img = Image.open(str(image))

        return ImageInfo(self._read_exif(img), img.width, img.height, image)

class MetadataWidget(QtWidgets.QGroupBox):
    def __init__(self, parent: 'MainWidget'):
        super().__init__('Metadata', parent)
        self._layout = QtWidgets.QFormLayout(self)
        self._parent = parent
        self._metadata_handler = MetadataHandler()

        self._datew = QtWidgets.QLabel('')
        self._ratingw = QtWidgets.QLabel('')
        self._descriptionw = QtWidgets.QLabel('')
        self._cameraw = QtWidgets.QLabel('')
        self._softwarew = QtWidgets.QLabel('')
        self._copyrightw = QtWidgets.QLabel('')
        self._dimensionw = QtWidgets.QLabel('')

        self._layout.addRow('Date', self._datew)
        self._layout.addRow('Rating', self._ratingw)
        self._layout.addRow('Camera', self._descriptionw)
        self._layout.addRow('Description', self._cameraw)
        self._layout.addRow('Software', self._softwarew)
        self._layout.addRow('Copyright', self._copyrightw)
        self._layout.addRow('Dimensions', self._dimensionw)

    def update_info(self, image_path: pathlib.Path):
        print(image_path)
        # TODO: path should never be None but check
        metadata = self._metadata_handler.read_metadata(image_path)
        # TODO: handle case an error occurs
        if metadata is None:
            return

        meta = metadata.metadata

        self._datew.setText(meta.intial_date.strftime("%d/%m/%Y") 
                            if meta.intial_date is not None else '')
        self._ratingw.setText(str(meta.rating))
        self._descriptionw.setText(meta.description)
        self._cameraw.setText(meta.camera)
        self._softwarew.setText(meta.software)
        self._copyrightw.setText(meta.copyright)
        self._dimensionw.setText(f'{metadata.width}x{metadata.height}')


class FileManagementWidget(QtWidgets.QWidget):
    def __init__(self, parent: 'MainWidget'):
        super().__init__(parent)
        self._parent = parent
        self._image_display = self._parent.image_display

        self._init_input()
        self._init_list()
        self._init_layout()

    def select_folder(self):
        self._browser = QtWidgets.QFileDialog(self, 'Select folder')
        self._selected_folder = pathlib.Path(self._browser.getExistingDirectory())

        self._input.setText(str(self._selected_folder))
        self._update_list()

        # QtWidgets.QWidget objects don't print their style by default
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

    def _init_input(self):
        self._input = QtWidgets.QLabel()
        self._input.setObjectName('filemanager-input')

    def _init_list(self):
        def _callback(item: QtWidgets.QListWidgetItem):
            self._parent.set_current_image(item.data(QtCore.Qt.ItemDataRole.UserRole))

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
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._input)
        self._layout.addWidget(self._list)
        self.setLayout(self._layout)


class ImageDisplayWidget(QtWidgets.QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

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

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        current_position = event.position().toPoint()
        if (event.button() == QtCore.Qt.MouseButton.LeftButton and 
            current_position == self._saved_pos):
            self._collapse_split() 
        else:
            super().mouseReleaseEvent(event)

        self._saved_pos = None

    def _collapse_split(self):
        FILE_SPLIT = 0
        DISPLAY_SPLIT = 1
        METADATA_SPLIT = 2

        # Handles number start at 1
        target_split = FILE_SPLIT if self.splitter().handle(1) == self else \
            METADATA_SPLIT

        splitter = self.splitter()
        sizes = splitter.sizes()
        target_size = sizes[target_split]

        # Temporarily allow the split to collapse. If always allowed, will 
        # collapse when drag and drop close to the edge
        splitter.setCollapsible(target_split, True)

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
        splitter.setCollapsible(target_split, False)


class ToggleSplitter(QtWidgets.QSplitter):
    def createHandle(self):
        return ToggleSplitterHandle(self.orientation(), self)


class MainWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._allow_close()
        self._FILE_MANAGEMENT_SIZE = 300

        self.image_path: Optional[pathlib.Path] = None

        self.image_display = ImageDisplayWidget()
        self.file_management = FileManagementWidget(self)
        self.metadata = MetadataWidget(self)

        self._splitter = ToggleSplitter(QtCore.Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.file_management)
        self._splitter.addWidget(self.image_display)
        self._splitter.addWidget(self.metadata)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        # Should not be possible to collapse the splits at any time because would 
        # collapse when resizing close to the edge of the screen
        # Look at `ToggleSplitterHandle._collapse_split` for more details
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(2, False)

        self._layout = QtWidgets.QHBoxLayout(self) 
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._splitter)
        self.setLayout(self._layout)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        self._splitter.setSizes((
            self._FILE_MANAGEMENT_SIZE,
            self._splitter.width() - self._FILE_MANAGEMENT_SIZE))
        return super().showEvent(event)

    def _allow_close(self):
        close_action = QtGui.QAction('Close', self)
        close_action.setShortcut(QtGui.QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)

        self.addAction(close_action)

    def select_folder(self):
        self.file_management.select_folder()

    def set_current_image(self, image: pathlib.Path):
        self.image_path = image
        self.image_display.display_image(image)
        self.metadata.update_info(image)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])

    with open("style.qss", "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    main_widget = MainWidget()
    main_widget.showMaximized()
    main_widget.select_folder()

    sys.exit(app.exec())
