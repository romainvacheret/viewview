import pathlib

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PIL import Image
from PIL.ImageFile import ImageFile
from PIL.ExifTags import Base, IFD
from PIL.ImageQt import ImageQt
from pillow_heif import register_heif_opener

from PySide6 import QtCore, QtWidgets, QtGui

register_heif_opener()

HEIF_IMAGE_FORMATS = {'.heic', '.heif'}
DISPLAYED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png'} | HEIF_IMAGE_FORMATS


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
        if image.suffix.lower() not in DISPLAYED_IMAGE_FORMATS:
            return None
        with Image.open(image) as img:
            return ImageInfo(self._read_exif(img), img.width, img.height, image)

    def _read_exif(self, img: ImageFile) -> ImageMetadata:
        exif = img.getexif()
        photo_exif = exif.get_ifd(IFD.Exif)
        return ImageMetadata(
            _read_date(str(photo_exif.get(Base.DateTimeOriginal,
                                         exif.get(Base.DateTimeOriginal)))),
            exif.get(Base.Rating, 0),
            exif.get(Base.ImageDescription, ''),
            exif.get(Base.Model, ''),
            exif.get(Base.Software, ''),
            exif.get(Base.Copyright, '')
        )

    def read_jpeg(self, image: pathlib.Path) -> ImageInfo:
        with Image.open(image) as img:
            return ImageInfo(self._read_exif(img), img.width, img.height, image)

class MetadataWidget(QtWidgets.QGroupBox):
    def __init__(self, parent: 'MainWidget'):
        super().__init__('', parent)
        self._layout = QtWidgets.QFormLayout(self)
        self._layout.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft |
            QtCore.Qt.AlignmentFlag.AlignTop)
        self._layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self._layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._parent = parent
        self._metadata_handler = MetadataHandler()

        def _init_label(text: str, role: str):
            label = QtWidgets.QLabel(text)

            hor_policy = QtWidgets.QSizePolicy.Policy.Ignored \
                if role == 'description' else QtWidgets.QSizePolicy.Policy.Preferred
            label.setSizePolicy(hor_policy, QtWidgets.QSizePolicy.Policy.Preferred)
            label.setMinimumWidth(0)
            # Required define role based style
            label.setProperty('role', role)
            return label

        self._datew = _init_label('', 'description')
        self._ratingw = _init_label('', 'description')
        self._descriptionw = _init_label('', 'description')
        self._cameraw = _init_label('', 'description')
        self._softwarew = _init_label('', 'description')
        self._copyrightw = _init_label('', 'description')
        self._dimensionw = _init_label('', 'description')

        # Need to 'manually' create the title labels to give them a style
        date_title = _init_label('Date', 'title')
        rating_title = _init_label('Rating', 'title')
        description_title = _init_label('Description', 'title')
        camera_title = _init_label('Camera', 'title')
        software_title = _init_label('Software', 'title')
        copyright_title = _init_label('Copyright', 'title')
        dimension_title = _init_label('Dimension', 'title')

        self._layout.addRow(date_title, self._datew)
        self._layout.addRow(rating_title, self._ratingw)
        self._layout.addRow(description_title, self._descriptionw)
        self._layout.addRow(camera_title, self._cameraw)
        self._layout.addRow(software_title, self._softwarew)
        self._layout.addRow(copyright_title, self._copyrightw)
        self._layout.addRow(dimension_title, self._dimensionw)

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

        for file in self._selected_folder.rglob('*'):
            if not file.is_file() or file.suffix.lower() not in DISPLAYED_IMAGE_FORMATS:
                continue
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
        if img_path.suffix.lower() in HEIF_IMAGE_FORMATS:
            # Qt's standard image plugins do not decode HEIC. Pillow uses libheif.
            with Image.open(img_path) as image:
                self._pixel_map = QtGui.QPixmap.fromImage(ImageQt(image.convert('RGBA')))
        else:
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
        self.setToolTip('Click to collapse or expand the panel. Drag to resize.')
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

        # Handles number starts at 1
        target_split = FILE_SPLIT if self.splitter().handle(1) == self else \
            METADATA_SPLIT

        splitter = self.splitter()
        sizes = splitter.sizes()
        target_size = sizes[target_split]

        # Both splits should allow collapse: when using `splitter.setSizes()`
        # the sizes that are passed are not necessariy applied. In particular, 
        # if a split has `collapsible` to False, its size cannot be 0.
        # For that reason it would expand back to its "minimum size" (e.g.
        # the one from a label)
        splitter.setCollapsible(FILE_SPLIT, True)
        splitter.setCollapsible(METADATA_SPLIT, True)

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
        # End of temporary collapsible state
        splitter.setCollapsible(FILE_SPLIT, False)
        splitter.setCollapsible(METADATA_SPLIT, False)


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
        self._splitter.setHandleWidth(12)
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


def main() -> int:
    app = QtWidgets.QApplication([])

    with pathlib.Path(__file__).with_name("style.qss").open(encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    main_widget = MainWidget()
    main_widget.showMaximized()
    main_widget.select_folder()

    return app.exec()
