"""Scrollable photo grid with bounded, background thumbnail decoding."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from pillow_heif import register_heif_opener

register_heif_opener()


def load_thumbnail(path: Path, size: tuple[int, int]) -> QtGui.QImage:
    # QImage is safe to create in a worker; QPixmap/QIcon stay on the GUI thread.
    with Image.open(path) as image:
        image.draft('RGB', size)
        oriented = ImageOps.exif_transpose(image)
        oriented.thumbnail(size, Image.Resampling.LANCZOS)
        return ImageQt(oriented.convert('RGBA')).copy()


class ThumbnailModel(QtCore.QAbstractListModel):
    def __init__(self, placeholder, error_icon, parent=None):
        super().__init__(parent)
        self.paths = ()
        self.rows = {}
        self.cache = OrderedDict()
        self.errors = {}
        self.cache_limit = 128
        self.placeholder = placeholder
        self.error_icon = error_icon

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.paths)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.paths):
            return None
        path = self.paths[index.row()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return path.name
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return path
        if role == QtCore.Qt.ItemDataRole.DecorationRole:
            if path in self.cache:
                self.cache.move_to_end(path)
                return self.cache[path]
            return self.error_icon if path in self.errors else self.placeholder
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            text = escape(str(path))
            if path in self.errors:
                text += '<br>Preview unavailable: ' + escape(self.errors[path])
            return f'<qt>{text}</qt>'
        return None

    def set_paths(self, paths):
        self.beginResetModel()
        self.paths = tuple(paths)
        self.rows = {path: row for row, path in enumerate(self.paths)}
        self.cache.clear()
        self.errors.clear()
        self.endResetModel()

    def store_thumbnail(self, path, image=None, error=None):
        row = self.rows.get(path)
        if row is None:
            return
        if error:
            self.errors[path] = error
        else:
            self.cache[path] = QtGui.QIcon(QtGui.QPixmap.fromImage(image))
            while len(self.cache) > self.cache_limit:
                self.cache.popitem(last=False)
        index = self.index(row)
        self.dataChanged.emit(index, index, [QtCore.Qt.ItemDataRole.DecorationRole,
                                            QtCore.Qt.ItemDataRole.ToolTipRole])


class ThumbnailView(QtWidgets.QListView):
    viewport_changed = QtCore.Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewport_changed.emit()


class GridWidget(QtWidgets.QWidget):
    image_selected = QtCore.Signal(object)
    image_activated = QtCore.Signal(object)
    selection_changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.folder = None
        self.generation = 0
        self._closed = False
        self._syncing_selection = False
        self._jobs = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='viewview-thumbnails')
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._pump)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        heading = QtWidgets.QHBoxLayout()
        self.folder_label = QtWidgets.QLabel('Select a folder in the left panel')
        self.folder_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.folder_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                        QtWidgets.QSizePolicy.Policy.Preferred)
        self.folder_label.setMinimumWidth(0)
        self.count_label = QtWidgets.QLabel('0 pictures')
        self.delete_button = QtWidgets.QPushButton('Delete')
        self.delete_button.setToolTip('Move selected pictures to trash (Delete or Backspace)')
        self.delete_button.setEnabled(False)
        heading.addWidget(self.folder_label, 1)
        heading.addWidget(self.count_label)
        heading.addWidget(self.delete_button)
        layout.addLayout(heading)
        self.view = ThumbnailView()
        self.view.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.view.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.view.setMovement(QtWidgets.QListView.Movement.Static)
        self.view.setWrapping(True)
        self.view.setUniformItemSizes(True)
        self.view.setWordWrap(False)
        self.view.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.view.setIconSize(QtCore.QSize(176, 132))
        self.view.setGridSize(QtCore.QSize(200, 170))
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.model = ThumbnailModel(
            self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileIcon),
            self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning), self)
        self.view.setModel(self.model)
        self.view.selectionModel().currentChanged.connect(self._selection_changed)
        self.view.selectionModel().selectionChanged.connect(self._update_selection_count)
        self._select_all = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+A'), self.view)
        self._select_all.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._select_all.activated.connect(self.view.selectAll)
        self.view.doubleClicked.connect(lambda index: self.image_activated.emit(self.model.paths[index.row()]))
        self.view.verticalScrollBar().valueChanged.connect(self._wake)
        self.view.viewport_changed.connect(self._wake)
        self.empty_label = QtWidgets.QLabel('Select a folder in the left panel.')
        self.empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self._stack = QtWidgets.QStackedLayout()
        self._stack.addWidget(self.empty_label)
        self._stack.addWidget(self.view)
        layout.addLayout(self._stack, 1)
        self.result_label = QtWidgets.QLabel()
        self.result_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.result_label.setWordWrap(True)
        self.result_label.hide()
        layout.addWidget(self.result_label)

    def set_folder(self, folder, paths, *, refresh=False):
        paths = tuple(paths)
        if not refresh and folder == self.folder and paths == self.model.paths:
            return
        selected = set(self.selected_images()) if folder == self.folder else set()
        self.folder = folder
        self.generation += 1
        for future in self._jobs:
            future.cancel()
        self._syncing_selection = True
        try:
            self.model.set_paths(paths)
            selection = QtCore.QItemSelection()
            for row, path in enumerate(paths):
                if path in selected:
                    index = self.model.index(row)
                    selection.select(index, index)
            self.view.selectionModel().select(selection, QtCore.QItemSelectionModel.SelectionFlag.Select)
        finally:
            self._syncing_selection = False
        self.folder_label.setText(str(folder))
        self.folder_label.setToolTip(f'<qt>{escape(str(folder))}</qt>')
        self._update_selection_count()
        self.result_label.hide()
        self.empty_label.setText('No pictures in this folder or its subfolders.')
        self._stack.setCurrentIndex(1 if paths else 0)
        self.view.scrollToTop()
        self._wake()

    def select_image(self, image):
        if self._syncing_selection:
            return
        row = self.model.rows.get(image)
        if row is None:
            return
        self._syncing_selection = True
        try:
            index = self.model.index(row)
            if self.view.selectionModel().isSelected(index):
                self.view.selectionModel().setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
            else:
                self.view.setCurrentIndex(index)
            self.view.scrollTo(index)
        finally:
            self._syncing_selection = False
        self._wake()

    def next_image(self, image):
        row = self.model.rows.get(image)
        if row is not None and row + 1 < len(self.model.paths):
            return self.model.paths[row + 1]
        return None

    def _selection_changed(self, current, previous):
        if current.isValid() and not self._syncing_selection:
            self._syncing_selection = True
            try:
                self.image_selected.emit(self.model.paths[current.row()])
            finally:
                self._syncing_selection = False

    def selected_images(self):
        return [self.model.paths[index.row()] for index in
                sorted(self.view.selectionModel().selectedRows(), key=lambda index: index.row())]

    def _update_selection_count(self, *_):
        count = len(self.selected_images())
        self.count_label.setText(f'{len(self.model.paths)} pictures · {count} selected')
        self.delete_button.setEnabled(count > 0)
        self.selection_changed.emit()

    def visible_rows(self):
        # Rows have monotonically increasing y coordinates in the wrapping grid.
        # Binary search avoids scanning the full library on every scroll.
        count = self.model.rowCount()
        lower, upper = 0, count
        while lower < upper:
            middle = (lower + upper) // 2
            if self.view.visualRect(self.model.index(middle)).bottom() < 0:
                lower = middle + 1
            else:
                upper = middle
        viewport = self.view.viewport().rect()
        rows = []
        for row in range(lower, count):
            rect = self.view.visualRect(self.model.index(row))
            if rect.top() > viewport.bottom():
                break
            if rect.intersects(viewport):
                rows.append(row)
        return rows

    def _wake(self, *_):
        if not self._closed and self.isVisible():
            self._timer.start()

    def _pump(self):
        for future, (generation, path, ratio) in tuple(self._jobs.items()):
            if not future.done():
                continue
            del self._jobs[future]
            if future.cancelled() or generation != self.generation:
                continue
            try:
                image = future.result()
                image.setDevicePixelRatio(ratio)
                self.model.store_thumbnail(path, image=image)
            except Exception as error:
                self.model.store_thumbnail(path, error=str(error) or 'Unable to decode image')
        if not self.isVisible() or not self.view.isVisible():
            if not self._jobs:
                self._timer.stop()
            return
        rows = self.visible_rows()
        self.model.cache_limit = max(128, len(rows) + 8)
        pending = {path for generation, path, _ratio in self._jobs.values() if generation == self.generation}
        for row in rows:
            if len(self._jobs) >= 2:
                break
            path = self.model.paths[row]
            if path in self.model.cache or path in self.model.errors or path in pending:
                continue
            size = self.view.iconSize()
            ratio = self.view.devicePixelRatioF()
            pixels = (max(1, round(size.width() * ratio)), max(1, round(size.height() * ratio)))
            future = self._executor.submit(load_thumbnail, path, pixels)
            self._jobs[future] = (self.generation, path, ratio)
        if not self._jobs:
            self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._wake()

    def shutdown(self):
        self._closed = True
        self._timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
