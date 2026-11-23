"""Per-photo tag chips and library-local keyboard completion."""
from html import escape
from PySide6 import QtCore, QtGui, QtWidgets


class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QtCore.QRect(0, 0, width, 0), True)

    def sizeHint(self):
        size = QtCore.QSize(0, 0)
        for item in self.items:
            size = size.expandedTo(item.sizeHint())
        return size

    def minimumSize(self):
        size = QtCore.QSize(0, 0)
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, False)

    def _arrange(self, rect, measure_only):
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self.items:
            size = item.sizeHint()
            width = min(size.width(), max(1, rect.width()))
            if line_height and x + width > rect.x() + rect.width():
                x = rect.x()
                y += line_height + self.spacing()
                line_height = 0
            if not measure_only:
                item.setGeometry(QtCore.QRect(x, y, width, size.height()))
            x += width + self.spacing()
            line_height = max(line_height, size.height())
        return y + line_height - rect.y()


class TagChip(QtWidgets.QFrame):
    remove_requested = QtCore.Signal(str)

    def __init__(self, name, parent):
        super().__init__(parent)
        self.name = name
        self.setObjectName('tag-chip')
        self.setToolTip(f'<qt>{escape(name)}</qt>')
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 4, 4)
        layout.setSpacing(4)
        self.label = QtWidgets.QLabel(name)
        self.label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
        self.remove_button = QtWidgets.QToolButton()
        self.remove_button.setText('×')
        self.remove_button.setAccessibleName(f'Remove tag {name}')
        self.remove_button.setToolTip('Remove from this picture')
        self.remove_button.setFixedSize(20, 20)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(name))
        layout.addWidget(self.label, 1)
        layout.addWidget(self.remove_button)

    def sizeHint(self):
        width = self.label.fontMetrics().horizontalAdvance(self.name) + 40
        return QtCore.QSize(width, max(28, self.label.fontMetrics().height() + 8))


class TagInput(QtWidgets.QLineEdit):
    submitted = QtCore.Signal(str)
    focused = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setPlaceholderText('Add a tag…')
        self.setAccessibleName('Add photo tag')
        self.setToolTip('Enter adds a tag. Tab completes and adds an existing tag. Tag names may contain spaces.')
        self.setMinimumWidth(0)
        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor('#8392a5'))
        self.setPalette(palette)
        self.suggestions = QtCore.QStringListModel(self)
        completer = QtWidgets.QCompleter(self.suggestions, self)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QtWidgets.QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)
        completer.popup().setObjectName('tag-completions')
        completer.activated[str].connect(self._submit_completion)
        # Intercept Tab before normal focus traversal or QCompleter consumes it.
        self.installEventFilter(self)
        completer.popup().installEventFilter(self)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Tab and not event.modifiers():
                popup = self.completer().popup()
                if self.text() and popup.isVisible() and popup.currentIndex().isValid():
                    completion = popup.currentIndex().data()
                else:
                    self.completer().setCompletionPrefix(self.text())
                    completion = self.completer().currentCompletion() if self.text() and self.completer().completionCount() else ''
                if completion:
                    self._submit_completion(completion)
                    return True
            if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                name = self.text().strip()
                self.completer().popup().hide()
                if name:
                    self.submitted.emit(name)
                return True
        return super().eventFilter(watched, event)

    def _submit_completion(self, name):
        self.completer().popup().hide()
        self.setText(name)
        self.submitted.emit(name)


class TagEditor(QtWidgets.QWidget):
    tag_added = QtCore.Signal(str)
    tag_removed = QtCore.Signal(str)
    suggestions_requested = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.names = ()
        self.known_names = ()
        self.chips = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.input = TagInput(self)
        self.input.submitted.connect(self._request_add)
        self.input.focused.connect(self.suggestions_requested)
        self.chip_container = QtWidgets.QWidget()
        self.flow = FlowLayout(self.chip_container)
        self.empty_label = QtWidgets.QLabel('No tags yet')
        self.empty_label.setObjectName('tags-empty')
        layout.addWidget(self.input)
        layout.addWidget(self.chip_container)
        layout.addWidget(self.empty_label)
        self.setEnabled(False)

    def set_tags(self, names, known_names, enabled):
        self.input.completer().popup().hide()
        self.input.clear()
        self.names = tuple(names)
        while self.flow.count():
            item = self.flow.takeAt(0)
            item.widget().hide()
            item.widget().deleteLater()
        self.chips.clear()
        for name in self.names:
            chip = TagChip(name, self.chip_container)
            chip.remove_requested.connect(self.tag_removed)
            self.flow.addWidget(chip)
            self.chips[name] = chip
        self.chip_container.setVisible(bool(self.names))
        self.empty_label.setVisible(not self.names)
        self.flow.invalidate()
        self.chip_container.updateGeometry()
        self.set_suggestions(known_names)
        self.setEnabled(enabled)
        self.updateGeometry()

    def set_suggestions(self, names):
        self.known_names = tuple(names)
        self.input.suggestions.setStringList([name for name in names if name not in self.names])

    def _request_add(self, name):
        if name in self.names:
            self.input.clear()
        elif name.strip():
            self.tag_added.emit(name)

    def content_width(self):
        return max([150] + [chip.sizeHint().width() for chip in self.chips.values()])
