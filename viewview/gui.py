import pathlib
from html import escape

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
        self.update_width_limit()

    def update_width_limit(self):
        self.ensurePolished()
        labels = []
        values = []
        for row in range(self._layout.rowCount()):
            labels.append(self._layout.itemAt(row, QtWidgets.QFormLayout.ItemRole.LabelRole)
                          .widget().sizeHint().width())
            values.append(self._layout.itemAt(row, QtWidgets.QFormLayout.ItemRole.FieldRole)
                          .widget().sizeHint().width())
        margins = self._layout.contentsMargins()
        frame = self.width() - self.contentsRect().width()
        width = (max(labels) + max(values) + max(0, self._layout.horizontalSpacing())
                 + margins.left() + margins.right() + frame + 24)
        self.setMaximumWidth(max(self.minimumSizeHint().width(), width))


class PathListWidget(QtWidgets.QListWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)

    def viewportEvent(self, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            self._show_path_tooltip(event.pos(), event.globalPos())
            return True
        if event.type() == QtCore.QEvent.Type.MouseMove and QtWidgets.QToolTip.isVisible():
            self._show_path_tooltip(event.position().toPoint(), event.globalPosition().toPoint())
        elif event.type() == QtCore.QEvent.Type.Leave:
            QtWidgets.QToolTip.hideText()
        return super().viewportEvent(event)

    def _show_path_tooltip(self, position, global_position):
        item = self.itemAt(position)
        if item is None:
            QtWidgets.QToolTip.hideText()
        else:
            QtWidgets.QToolTip.showText(global_position, item.toolTip(),
                                       self.viewport(), self.visualItemRect(item))


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
        self._input.setToolTip(f'<qt>{escape(str(self._selected_folder.resolve()))}</qt>')
        self._update_list()

        # QtWidgets.QWidget objects don't print their style by default
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

    def _init_input(self):
        self._input = QtWidgets.QLabel()
        self._input.setObjectName('filemanager-input')
        self._input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                  QtWidgets.QSizePolicy.Policy.Preferred)
        self._input.setMinimumWidth(0)

    def _init_list(self):
        def _callback(item: QtWidgets.QListWidgetItem):
            self._parent.set_current_image(item.data(QtCore.Qt.ItemDataRole.UserRole))

        self._list = PathListWidget()
        self._list.itemClicked.connect(_callback)

    def _update_list(self):
        self._list.clear()

        for file in self._selected_folder.rglob('*'):
            if not file.is_file() or file.suffix.lower() not in DISPLAYED_IMAGE_FORMATS:
                continue
            filename = file.relative_to(self._selected_folder)
            item = QtWidgets.QListWidgetItem(str(filename))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, file)
            item.setToolTip(f'<qt>{escape(str(file.resolve()))}</qt>')
            self._list.addItem(item)
        self.update_width_limit()

    def update_width_limit(self):
        self.ensurePolished()
        # Delegate hints include item styling; reserve room for a scrollbar
        # so adding more files never makes the longest filename clip.
        list_width = (max(0, self._list.sizeHintForColumn(0)) + 2 * self._list.frameWidth()
                      + self._list.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent))
        margins = self._layout.contentsMargins()
        width = (max(self._input.sizeHint().width(), list_width)
                 + margins.left() + margins.right() + 24)
        self.setMaximumWidth(max(self.minimumSizeHint().width(), width))

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
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                           QtWidgets.QSizePolicy.Policy.Ignored)
        self.setMinimumSize(1, 1)

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
        self._saved_size = 300
        self._press_position = None
        self._press_sizes = None
        self._dragging = False

    def _target_index(self) -> int:
        return 0 if self.splitter().handle(1) == self else 2

    def _minimum_width(self, index: int) -> int:
        widget = self.splitter().widget(index)
        if widget.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Ignored:
            return max(1, widget.minimumWidth())
        return max(1, widget.minimumWidth(), widget.minimumSizeHint().width())

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press_position = event.globalPosition().toPoint()
            self._press_sizes = self.splitter().sizes()
            self._dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._press_position is None:
            super().mouseMoveEvent(event)
            return

        # The handle itself moves during a drag; local coordinates cannot
        # distinguish that movement from a stationary click.
        delta = event.globalPosition().toPoint() - self._press_position
        if delta.manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            self._dragging = True
        if self._dragging:
            target = self._target_index()
            sizes = self._press_sizes.copy()
            available = sizes[target] + sizes[1]
            minimum = self._minimum_width(target)
            maximum = min(available - self._minimum_width(1),
                          self.splitter().widget(target).maximumWidth())
            if maximum >= minimum:
                movement = delta.x() if target == 0 else -delta.x()
                # Stop at the image area's minimum instead of pushing the
                # opposite side panel. Collapse is reserved for a click.
                sizes[target] = max(minimum, min(maximum, sizes[target] + movement))
                sizes[1] = available - sizes[target]
                self.splitter().set_panel_sizes(sizes)
        event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._press_position is not None:
            distance = (event.globalPosition().toPoint() - self._press_position).manhattanLength()
            if not self._dragging and distance < QtWidgets.QApplication.startDragDistance():
                self._collapse_split()
            self._press_position = None
            self._press_sizes = None
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _collapse_split(self):
        splitter = self.splitter()
        target = self._target_index()
        sizes = splitter.sizes()
        available = sizes[target] + sizes[1]
        if sizes[target] == 0:
            minimum = self._minimum_width(target)
            maximum = min(available - self._minimum_width(1),
                          splitter.widget(target).maximumWidth())
            if maximum < minimum:
                return
            sizes[target] = max(minimum, min(self._saved_size, maximum))
        else:
            self._saved_size = sizes[target]
            sizes[target] = 0
        sizes[1] = available - sizes[target]

        splitter.set_panel_sizes(sizes)


class ToggleSplitter(QtWidgets.QSplitter):
    def createHandle(self):
        return ToggleSplitterHandle(self.orientation(), self)

    def set_panel_sizes(self, sizes: list[int]) -> None:
        # Qt otherwise expands an already-collapsed, noncollapsible panel
        # back to its minimum width when any other panel changes size.
        for index in (0, 2):
            self.setCollapsible(index, sizes[index] == 0)
        self.setSizes(sizes)
        for index in (0, 2):
            self.setCollapsible(index, False)


class MainWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._allow_close()
        self._FILE_MANAGEMENT_SIZE = 300
        self._initial_sizes_set = False

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

        # Dragging stops at minimum widths; only clicking collapses panels.
        self._splitter.setChildrenCollapsible(False)

        self._layout = QtWidgets.QHBoxLayout(self) 
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._splitter)
        self.setLayout(self._layout)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        if not self._initial_sizes_set:
            self._initial_sizes_set = True
            self.file_management.update_width_limit()
            self.metadata.update_width_limit()
            side_width = self._FILE_MANAGEMENT_SIZE
            metadata_width = self.metadata.sizeHint().width()
            self._splitter.setSizes([
                side_width,
                max(1, self._splitter.width() - side_width - metadata_width
                    - 2 * self._splitter.handleWidth()),
                metadata_width,
            ])
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
