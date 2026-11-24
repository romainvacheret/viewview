import pathlib
import math
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

from .import_gui import ImportWidget
from .grid import GridWidget
from .tag_editor import TagEditor
from .core.tags import add_tags, photo_tags, tag_names, remove_photo_tag
from .core.review import review_path
from .core.library_db import DATABASE_NAME, initialize_catalogue
from .core.review import is_marked_for_deletion, set_deletion_mark, read_rating, set_rating

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

class RatingStar(QtWidgets.QAbstractButton):
    def __init__(self, number: int, parent):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(28, 30)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f'{number} stars')

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        if self.hasFocus():
            painter.setPen(QtGui.QPen(QtGui.QColor('#68b6a7'), 1))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)
        star = QtGui.QPainterPath()
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        for point in range(10):
            angle = -math.pi / 2 + point * math.pi / 5
            radius = 11 if point % 2 == 0 else 4.8
            position = center + QtCore.QPointF(math.cos(angle) * radius, math.sin(angle) * radius)
            if point == 0:
                star.moveTo(position)
            else:
                star.lineTo(position)
        star.closeSubpath()
        color = '#ffffff' if self.isChecked() else '#080b10'
        if self.underMouse() and not self.isChecked():
            color = '#8f9eaf'
        painter.setPen(QtGui.QPen(QtGui.QColor(color), 1.5))
        painter.setBrush(QtGui.QColor('#ffffff') if self.isChecked() else QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(star)


class StarRatingWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(int)

    def __init__(self):
        super().__init__()
        self._value = 0
        self.setAccessibleName('Photo rating')
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.stars = []
        for number in range(1, 6):
            star = RatingStar(number, self)
            star.clicked.connect(lambda _checked, rating=number:
                                 self.setValue(0 if rating == self._value else rating))
            layout.addWidget(star)
            self.stars.append(star)
        self._refresh_stars()

    def value(self) -> int:
        return self._value

    def setValue(self, rating: int):
        if type(rating) is not int or not 0 <= rating <= 5:
            raise ValueError('Rating must be an integer between 0 and 5')
        changed = self._value != rating
        self._value = rating
        self._refresh_stars()
        if changed:
            self.valueChanged.emit(rating)

    def _refresh_stars(self):
        self.setAccessibleDescription(f'{self._value} out of 5 stars' if self._value else 'Unrated')
        for number, star in enumerate(self.stars, 1):
            star.setChecked(number <= self._value)
            star.setToolTip('Clear rating' if number == self._value else f'Set rating to {number} stars')
            star.update()


def _metadata_label(text, role):
    label = QtWidgets.QLabel(text)
    label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
    label.setProperty('role', role)
    label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored if role == 'description'
                        else QtWidgets.QSizePolicy.Policy.Preferred,
                        QtWidgets.QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def _form_width(widget, form):
    labels, values = [], []
    for row in range(form.rowCount()):
        labels.append(form.itemAt(row, QtWidgets.QFormLayout.ItemRole.LabelRole).widget().sizeHint().width())
        values.append(form.itemAt(row, QtWidgets.QFormLayout.ItemRole.FieldRole).widget().sizeHint().width())
    margins = form.contentsMargins()
    frame = widget.width() - widget.contentsRect().width()
    return (max(labels) + max(values) + max(0, form.horizontalSpacing())
            + margins.left() + margins.right() + frame + 24)


class ImageInfoWidget(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__('Image info')
        self.form = QtWidgets.QFormLayout(self)
        self.form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.handler = MetadataHandler()
        self.fields = {}
        for name, title in (('_datew', 'Date'), ('_descriptionw', 'Description'), ('_cameraw', 'Camera'),
                            ('_softwarew', 'Software'), ('_copyrightw', 'Copyright'), ('_dimensionw', 'Dimension')):
            label = _metadata_label('', 'description')
            self.fields[name] = label
            self.form.addRow(_metadata_label(title, 'title'), label)

    def update_info(self, image_path):
        info = self.handler.read_metadata(image_path)
        if info is None:
            return 0
        meta = info.metadata
        values = {'_datew': meta.intial_date.strftime('%d/%m/%Y') if meta.intial_date else '',
                  '_descriptionw': meta.description, '_cameraw': meta.camera, '_softwarew': meta.software,
                  '_copyrightw': meta.copyright, '_dimensionw': f'{info.width}x{info.height}'}
        for name, value in values.items():
            self.fields[name].setText(str(value))
        try:
            return max(0, min(5, int(meta.rating)))
        except (ValueError, TypeError, OverflowError):
            return 0

    def content_width(self):
        return _form_width(self, self.form)


class AppInfoWidget(QtWidgets.QGroupBox):
    def __init__(self, controller):
        super().__init__('App info')
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        self.form = QtWidgets.QFormLayout()
        self.form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.rating = StarRatingWidget()
        self.rating.setEnabled(False)
        self.rating.valueChanged.connect(controller.set_rating)
        self.deletion_checkbox = QtWidgets.QCheckBox('To be deleted')
        self.deletion_checkbox.setEnabled(False)
        self.deletion_checkbox.setToolTip('Press X to toggle the deletion mark and advance.')
        self.deletion_checkbox.clicked.connect(controller.set_deletion_mark)
        self.form.addRow(_metadata_label('Rating', 'title'), self.rating)
        self.form.addRow(_metadata_label('Review', 'title'), self.deletion_checkbox)
        layout.addLayout(self.form)
        layout.addWidget(_metadata_label('Tags', 'title'))
        self.tags = TagEditor()
        self.tags.tag_added.connect(controller.add_photo_tag)
        self.tags.tag_removed.connect(controller.remove_photo_tag)
        self.tags.suggestions_requested.connect(controller.refresh_tag_suggestions)
        layout.addWidget(self.tags)
        self.error = QtWidgets.QLabel()
        self.error.setObjectName('review-error')
        self.error.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

    def content_width(self):
        margins = self.layout().contentsMargins()
        frame = self.width() - self.contentsRect().width()
        return max(_form_width(self, self.form),
                   self.tags.content_width() + margins.left() + margins.right() + frame + 24)


class MetadataWidget(QtWidgets.QWidget):
    """Shared sidebar coordinating file-derived and library-owned information."""
    def __init__(self, parent: 'MainWidget'):
        super().__init__(parent)
        self._image_rating = 0
        self.file_info = ImageInfoWidget()
        self.app_info = AppInfoWidget(parent)
        # Keep the sidebar's existing field interface for selection/review logic.
        for name, field in self.file_info.fields.items():
            setattr(self, name, field)
        self._ratingw = self.app_info.rating
        self.deletion_checkbox = self.app_info.deletion_checkbox
        self.review_error = self.app_info.error
        self.tags_editor = self.app_info.tags
        content = QtWidgets.QWidget()
        content.setObjectName('metadata-content')
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(self.file_info)
        content_layout.addWidget(self.app_info)
        content_layout.addStretch()
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setWidget(content)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

    def set_review_state(self, marked: bool, enabled: bool, error: str = ''):
        self.deletion_checkbox.setChecked(marked)
        self.deletion_checkbox.setEnabled(enabled)
        self.review_error.setText(error)
        self.review_error.setVisible(bool(error))
        self.update_width_limit()

    def set_rating_state(self, rating: int, enabled: bool):
        with QtCore.QSignalBlocker(self._ratingw):
            self._ratingw.setValue(rating)
        self._ratingw.setEnabled(enabled)

    def update_info(self, image_path: pathlib.Path):
        self._image_rating = self.file_info.update_info(image_path)
        self.set_rating_state(self._image_rating, False)
        self.update_width_limit()

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        if hasattr(self, 'app_info'):
            scrollbar = self.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent)
            size.setWidth(max(self.file_info.minimumSizeHint().width(),
                              self.app_info.minimumSizeHint().width()) + scrollbar)
        return size

    def update_width_limit(self):
        self.ensurePolished()
        self.file_info.ensurePolished()
        self.app_info.ensurePolished()
        scrollbar = self.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent)
        width = max(self.file_info.content_width(), self.app_info.content_width()) + scrollbar
        self.setMaximumWidth(max(self.minimumSizeHint().width(), width))


class PathTreeWidget(QtWidgets.QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setHeaderHidden(True)
        self.setIndentation(18)
        self.setUniformRowHeights(True)
        self.setExpandsOnDoubleClick(True)

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
            QtWidgets.QToolTip.showText(global_position, item.toolTip(0),
                                       self.viewport(), self.visualItemRect(item))


class FileManagementWidget(QtWidgets.QWidget):
    folder_selected = QtCore.Signal(object)
    contents_changed = QtCore.Signal()

    def __init__(self, parent: 'MainWidget'):
        super().__init__(parent)
        self._parent = parent
        self._image_display = self._parent.image_display

        self._init_input()
        self._init_list()
        self._init_layout()

    def select_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, 'Select folder', str(getattr(self, '_selected_folder', '')))
        if not folder:
            return
        self.open_folder(pathlib.Path(folder))

    def open_folder(self, selected):
        if not (selected / DATABASE_NAME).exists():
            message = f'Create {DATABASE_NAME} in this folder?\n\n{selected}'
            if (selected / 'viewview.sqlite3').exists():
                message += '\n\nExisting ratings, tags, and deletion marks will be copied from viewview.sqlite3.'
            answer = QtWidgets.QMessageBox.question(
                self, 'Create catalogue?', message,
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No)
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            try:
                initialize_catalogue(selected)
            except (OSError, ValueError) as error:
                QtWidgets.QMessageBox.warning(self, 'Could not create catalogue', str(error))
                return
        self._selected_folder = selected

        self._input.setText(str(self._selected_folder))
        self._input.setToolTip(f'<qt>{escape(str(self._selected_folder.resolve()))}</qt>')
        self._update_list()
        self.folder_selected.emit(self._selected_folder)

        # QtWidgets.QWidget objects don't print their style by default
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

    def _init_input(self):
        self.open_folder_button = QtWidgets.QPushButton('Open folder…')
        self.open_folder_button.setToolTip('Choose a different library folder')
        self.open_folder_button.clicked.connect(self._parent.select_folder)
        self._input = QtWidgets.QLabel()
        self._input.setObjectName('filemanager-input')
        self._input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                  QtWidgets.QSizePolicy.Policy.Preferred)
        self._input.setMinimumWidth(0)

    def _init_list(self):
        self._list = PathTreeWidget()
        self._folder_items = {}
        self._image_items = []
        self._tree_root = None
        self._list.itemClicked.connect(self._item_clicked)
        self._list.itemExpanded.connect(lambda item: self._set_folder_icon(item, True))
        self._list.itemCollapsed.connect(lambda item: self._set_folder_icon(item, False))

    def _set_folder_icon(self, item, expanded):
        if item.data(0, QtCore.Qt.ItemDataRole.UserRole) not in self._folder_items:
            return
        icon = (QtWidgets.QStyle.StandardPixmap.SP_DirOpenIcon if expanded
                else QtWidgets.QStyle.StandardPixmap.SP_DirClosedIcon)
        item.setIcon(0, self.style().standardIcon(icon))

    def _item_clicked(self, item, _column):
        path = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if path in self._folder_items:
            self._parent.select_grid_folder(path)
        else:
            self._parent.set_current_image(path)

    def _update_list(self):
        same_root = self._tree_root == self._selected_folder
        expanded = {path for path, item in self._folder_items.items() if item.isExpanded()}
        selected = self._list.currentItem()
        selected_path = selected.data(0, QtCore.Qt.ItemDataRole.UserRole) if selected else None
        self._list.clear()
        self._folder_items = {}
        self._image_items = []
        self._tree_root = self._selected_folder
        file_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileIcon)

        def add_folder(folder, parent):
            item = QtWidgets.QTreeWidgetItem(parent, [folder.name or str(folder)])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, folder)
            item.setToolTip(0, f'<qt>{escape(str(folder.absolute()))}</qt>')
            self._folder_items[folder] = item
            self._set_folder_icon(item, False)
            font = item.font(0)
            font.setWeight(QtGui.QFont.Weight.DemiBold)
            item.setFont(0, font)
            if not folder.is_symlink() or folder == self._selected_folder:
                try:
                    entries = sorted(folder.iterdir(), key=lambda path:
                                     (not path.is_dir(), path.name.casefold(), path.name))
                except OSError as error:
                    item.setToolTip(0, f'<qt>{escape(str(folder.absolute()))}<br>{escape(str(error))}</qt>')
                    entries = []
                for path in entries:
                    if path.is_dir():
                        add_folder(path, item)
                    elif path.is_file() and path.suffix.lower() in DISPLAYED_IMAGE_FORMATS:
                        child = QtWidgets.QTreeWidgetItem(item, [path.name])
                        child.setData(0, QtCore.Qt.ItemDataRole.UserRole, path)
                        child.setToolTip(0, f'<qt>{escape(str(path.absolute()))}</qt>')
                        child.setIcon(0, file_icon)
                        self._image_items.append(child)
            item.setExpanded(folder in expanded if same_root else folder == self._selected_folder)
            return item

        add_folder(self._selected_folder, self._list)
        if same_root and selected_path is not None:
            for item in [*self._folder_items.values(), *self._image_items]:
                if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == selected_path:
                    self._list.setCurrentItem(item)
                    break
        self.update_width_limit()

        self.contents_changed.emit()

    def update_width_limit(self):
        self.ensurePolished()
        option = QtWidgets.QStyleOptionViewItem()
        option.initFrom(self._list)
        content_width = 0
        for item in [*self._folder_items.values(), *self._image_items]:
            depth = 1
            ancestor = item.parent()
            while ancestor is not None:
                depth += 1
                ancestor = ancestor.parent()
            hint = self._list.itemDelegate().sizeHint(option, self._list.indexFromItem(item))
            content_width = max(content_width, hint.width() + depth * self._list.indentation())
        list_width = (content_width + 2 * self._list.frameWidth()
                      + self._list.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent))
        margins = self._layout.contentsMargins()
        width = (max(self._input.sizeHint().width(), list_width,
                     self.open_folder_button.sizeHint().width())
                 + margins.left() + margins.right() + 24)
        self.setMaximumWidth(max(self.minimumSizeHint().width(), width))

    def _init_layout(self):
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.open_folder_button)
        self._layout.addWidget(self._input)
        self._layout.addWidget(self._list)
        self.setLayout(self._layout)

    def select_image(self, image: pathlib.Path):
        for row, item in enumerate(self._image_items):
            if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == image:
                ancestor = item.parent()
                while ancestor is not None:
                    ancestor.setExpanded(True)
                    ancestor = ancestor.parent()
                self._list.setCurrentItem(item)
                self._list.scrollToItem(item)
                return row
        return None

    def select_next_image(self, image: pathlib.Path):
        for row, item in enumerate(self._image_items):
            if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == image:
                if row + 1 < len(self._image_items):
                    next_item = self._image_items[row + 1]
                    self._parent.set_current_image(next_item.data(0, QtCore.Qt.ItemDataRole.UserRole))
                return


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
            reader.setAutoTransform(True)
            self._pixel_map = QtGui.QPixmap.fromImage(reader.read())
            if self._pixel_map.isNull():
                raise ValueError(reader.errorString())

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
    def __init__(self, settings=None):
        super().__init__()
        self._settings = settings
        self._allow_close()
        self._FILE_MANAGEMENT_SIZE = 300
        self._initial_sizes_set = False

        self.image_path: Optional[pathlib.Path] = None
        self._displayed_image = None
        self._grid_folder = None
        self._marked_for_deletion = False

        self.image_display = ImageDisplayWidget()
        self.file_management = FileManagementWidget(self)
        self.metadata = MetadataWidget(self)

        self.grid = GridWidget()
        self.view_tabs = QtWidgets.QTabWidget()
        self.view_tabs.setObjectName('picture-views')
        self.view_tabs.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                     QtWidgets.QSizePolicy.Policy.Ignored)
        self.view_tabs.setMinimumSize(1, 1)
        self.view_tabs.addTab(self.image_display, 'Single picture')
        self.view_tabs.addTab(self.grid, 'Grid')
        self.view_tabs.currentChanged.connect(self._view_changed)
        self.grid.image_selected.connect(self.set_current_image)
        self.grid.image_activated.connect(self._open_grid_image)
        self.file_management.contents_changed.connect(self._refresh_grid_paths)

        self._splitter = ToggleSplitter(QtCore.Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(12)
        self._splitter.addWidget(self.file_management)
        self._splitter.addWidget(self.view_tabs)
        self._splitter.addWidget(self.metadata)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        # Dragging stops at minimum widths; only clicking collapses panels.
        self._splitter.setChildrenCollapsible(False)

        self.import_widget = ImportWidget()
        self.file_management.folder_selected.connect(self.import_widget.set_destination)
        self.file_management.folder_selected.connect(self._library_changed)
        self.import_widget.imported.connect(self._refresh_library)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._splitter, 'Viewer')
        self.tabs.addTab(self.import_widget, 'Import')
        self._mark_shortcut = QtGui.QShortcut(QtGui.QKeySequence('X'), self)
        self._mark_shortcut.setAutoRepeat(False)
        self._mark_shortcut.activated.connect(self.mark_and_advance)
        self._mark_shortcut.setEnabled(False)
        self._navigation_shortcuts = []
        self._rating_shortcuts = []
        for key, offset in (('Left', -1), ('Right', 1)):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda offset=offset: self.navigate_image(offset))
            shortcut.setEnabled(False)
            self._navigation_shortcuts.append(shortcut)
        for rating in range(6):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(str(rating)), self)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda rating=rating: self.rate_and_advance(rating))
            shortcut.setEnabled(False)
            self._rating_shortcuts.append(shortcut)
        self.tabs.currentChanged.connect(self._update_mark_shortcut)
        QtWidgets.QApplication.instance().focusChanged.connect(self._update_mark_shortcut)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.tabs)
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

    def _refresh_library(self):
        if hasattr(self.file_management, '_selected_folder'):
            self.file_management._update_list()
            if self.image_path is not None:
                self._load_review_state()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.import_widget.is_busy:
            self.import_widget.result_label.setText('Please wait for the current import check or operation to finish before closing.')
            event.ignore()
        else:
            self.grid.shutdown()
            super().closeEvent(event)

    def select_folder(self):
        if self.import_widget.is_busy:
            self.import_widget.result_label.setText(
                'Please wait for the current import check or operation to finish before changing folders.')
            return
        self.file_management.select_folder()

    def restore_last_library(self):
        saved = self._settings.value('library/lastPath', '') if self._settings is not None else ''
        if isinstance(saved, str) and saved:
            folder = pathlib.Path(saved)
            if folder.is_absolute() and folder.is_dir() and (folder / DATABASE_NAME).is_file():
                self.file_management.open_folder(folder)
                return
        self.select_folder()

    def set_current_image(self, image: pathlib.Path):
        self.image_path = image
        error = ''
        try:
            self.metadata.update_info(image)
        except (OSError, ValueError) as failure:
            self._clear_metadata()
            error = f'Unable to read picture: {failure}'
        self._displayed_image = None
        if self.view_tabs.currentIndex() == 0:
            self._display_current_image()
        self.file_management.select_image(image)
        if image not in self.grid.model.rows and hasattr(self.file_management, '_selected_folder'):
            self.select_grid_folder(image.parent)
        self.grid.select_image(image)
        self._load_review_state()
        if error:
            self.metadata.review_error.setText(error)
            self.metadata.review_error.show()

    def _display_current_image(self):
        if self.image_path is None:
            return
        try:
            self.image_display.display_image(self.image_path)
        except (OSError, ValueError) as failure:
            self.image_display.clear()
            self.image_display.setText(f'Unable to display this picture.\n{failure}')
        self._displayed_image = self.image_path

    def _view_changed(self, index):
        if index == 0 and self._displayed_image != self.image_path:
            self._display_current_image()

    def _open_grid_image(self, image):
        if self.image_path != image:
            self.set_current_image(image)
        self.view_tabs.setCurrentIndex(0)

    def _clear_metadata(self):
        for field in ('_datew', '_descriptionw', '_cameraw', '_softwarew', '_copyrightw', '_dimensionw'):
            getattr(self.metadata, field).clear()
        self.metadata._image_rating = 0
        self.metadata.set_rating_state(0, False)

    def _clear_current_image(self):
        self.image_path = None
        self._displayed_image = None
        self.image_display.clear()
        self._clear_metadata()
        self.metadata.tags_editor.set_tags([], [], False)
        self._marked_for_deletion = False
        self.metadata.set_review_state(False, False)
        self._update_mark_shortcut()

    def select_grid_folder(self, folder, *, refresh=False):
        self._grid_folder = folder
        paths = [item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                 for item in self.file_management._image_items
                 if item.data(0, QtCore.Qt.ItemDataRole.UserRole).is_relative_to(folder)]
        self.grid.set_folder(folder, paths, refresh=refresh)
        if self.image_path is not None and self.image_path not in self.grid.model.rows:
            self._clear_current_image()
        elif self.image_path is not None:
            self.grid.select_image(self.image_path)

    def _refresh_grid_paths(self):
        root = getattr(self.file_management, '_selected_folder', None)
        if root is None:
            return
        folder = self._grid_folder
        if folder not in self.file_management._folder_items:
            folder = root
        self.select_grid_folder(folder, refresh=True)

    def _library_changed(self, _folder):
        self._clear_current_image()
        self.select_grid_folder(_folder)
        if self._settings is not None:
            self._settings.setValue('library/lastPath', str(_folder.absolute()))
            self._settings.sync()

    def _update_mark_shortcut(self, *_):
        focus = QtWidgets.QApplication.focusWidget()
        editing = (isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit))
                   or self.metadata.tags_editor.input.completer().popup().isVisible())
        self._mark_shortcut.setEnabled(self.tabs.currentIndex() == 0
                                      and not editing
                                      and self.metadata.deletion_checkbox.isEnabled())
        viewing = self.tabs.currentIndex() == 0 and not editing and self.image_path is not None
        for shortcut in self._navigation_shortcuts:
            shortcut.setEnabled(viewing)
        for shortcut in self._rating_shortcuts:
            shortcut.setEnabled(viewing and self.metadata._ratingw.isEnabled())

    def _load_review_state(self):
        library = getattr(self.file_management, '_selected_folder', None)
        self._marked_for_deletion = False
        self._saved_rating = self.metadata._image_rating
        enabled = library is not None and self.image_path is not None
        error = ''
        if enabled:
            try:
                self._marked_for_deletion = is_marked_for_deletion(library, self.image_path)
                rating = read_rating(library, self.image_path)
                if rating is not None:
                    self._saved_rating = rating
            except (OSError, ValueError) as failure:
                enabled = False
                error = f'Could not load review marks: {failure}'
        self.metadata.set_review_state(self._marked_for_deletion, enabled, error)
        self.metadata.set_rating_state(self._saved_rating, enabled)
        self._load_tags(enabled)
        self._update_mark_shortcut()

    def set_deletion_mark(self, marked: bool) -> bool:
        library = getattr(self.file_management, '_selected_folder', None)
        if library is None or self.image_path is None or not self.metadata.deletion_checkbox.isEnabled():
            return False
        try:
            set_deletion_mark(library, self.image_path, marked)
        except (OSError, ValueError) as failure:
            self.metadata.set_review_state(self._marked_for_deletion, True,
                                           f'Could not save review mark: {failure}')
            return False
        self._marked_for_deletion = marked
        self.metadata.set_review_state(marked, True)
        return True

    def _load_tags(self, enabled=True):
        library = getattr(self.file_management, '_selected_folder', None)
        if not enabled or library is None or self.image_path is None:
            self.metadata.tags_editor.set_tags([], [], False)
            return
        try:
            names = photo_tags(library, review_path(library, self.image_path))
            known = tag_names(library)
        except (OSError, ValueError) as failure:
            self.metadata.tags_editor.set_tags([], [], False)
            self.metadata.review_error.setText(f'Could not load tags: {failure}')
            self.metadata.review_error.show()
        else:
            self.metadata.tags_editor.set_tags(names, known, True)
        self.metadata.update_width_limit()

    def refresh_tag_suggestions(self):
        library = getattr(self.file_management, '_selected_folder', None)
        if library is not None and self.metadata.tags_editor.isEnabled():
            try:
                self.metadata.tags_editor.set_suggestions(tag_names(library))
            except (OSError, ValueError) as failure:
                self.metadata.review_error.setText(f'Could not load tag suggestions: {failure}')
                self.metadata.review_error.show()

    def _change_photo_tag(self, name, remove=False):
        library = getattr(self.file_management, '_selected_folder', None)
        if library is None or self.image_path is None or not self.metadata.tags_editor.isEnabled():
            return
        try:
            path = review_path(library, self.image_path)
            if remove:
                remove_photo_tag(library, path, name)
            else:
                add_tags(library, [name], [path])
        except (OSError, ValueError) as failure:
            self.metadata.review_error.setText(f'Could not save tag: {failure}')
            self.metadata.review_error.show()
            return
        self._load_tags()
        self.metadata.set_review_state(self._marked_for_deletion, True)

    def add_photo_tag(self, name):
        self._change_photo_tag(name)

    def remove_photo_tag(self, name):
        self._change_photo_tag(name, remove=True)

    def mark_and_advance(self):
        if self.tabs.currentIndex() == 0 and self.set_deletion_mark(not self._marked_for_deletion):
            self.navigate_image(1)

    def navigate_image(self, offset):
        if self.tabs.currentIndex() != 0 or self.image_path is None:
            return
        paths = (self.grid.model.paths if self.view_tabs.currentIndex() == 1 else
                 [item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                  for item in self.file_management._image_items])
        if self.image_path in paths:
            index = paths.index(self.image_path) + offset
            if 0 <= index < len(paths):
                self.set_current_image(paths[index])

    def rate_and_advance(self, rating):
        if self.tabs.currentIndex() == 0 and self.set_rating(rating):
            self.navigate_image(1)

    def set_rating(self, rating: int):
        library = getattr(self.file_management, '_selected_folder', None)
        if library is None or self.image_path is None or not self.metadata._ratingw.isEnabled():
            return False
        try:
            set_rating(library, self.image_path, rating)
        except (OSError, ValueError) as failure:
            self.metadata.set_rating_state(self._saved_rating, True)
            self.metadata.set_review_state(self._marked_for_deletion, True,
                                           f'Could not save rating: {failure}')
            return False
        self._saved_rating = rating
        self.metadata.set_rating_state(rating, True)
        self.metadata.set_review_state(self._marked_for_deletion, True)
        return True


def main() -> int:
    app = QtWidgets.QApplication([])

    with pathlib.Path(__file__).with_name("style.qss").open(encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    main_widget = MainWidget(settings=QtCore.QSettings('Viewview', 'Viewview'))
    main_widget.showMaximized()
    main_widget.restore_last_library()

    return app.exec()
