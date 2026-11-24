"""Viewer filter controls shared by the single-picture and grid views."""
from PySide6 import QtCore, QtWidgets


class FilterBar(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tag = QtWidgets.QComboBox()
        self.tag.setMinimumWidth(100)
        self.tag.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                               QtWidgets.QSizePolicy.Policy.Fixed)
        self.tag.addItem('All tags', None)
        self.rating = QtWidgets.QComboBox()
        self.rating.addItem('Any rating', None)
        self.rating.addItem('Unrated', ('exact', 0))
        for number in range(1, 6):
            self.rating.addItem(f'{number} star' + ('s' if number != 1 else ''), ('exact', number))
        for number in range(1, 5):
            self.rating.addItem(f'At least {number} star' + ('s' if number != 1 else ''), ('minimum', number))
        self.deletion = QtWidgets.QComboBox()
        self.deletion.addItem('All pictures', None)
        self.deletion.addItem('Marked for deletion', True)
        self.deletion.addItem('Not marked for deletion', False)
        for column, (label, control) in enumerate((('Tag', self.tag), ('Rating', self.rating),
                                                  ('Deletion', self.deletion))):
            title = QtWidgets.QLabel(label)
            title.setBuddy(control)
            control.setAccessibleName(f'{label} filter')
            layout.addWidget(title, 0, column)
            layout.addWidget(control, 1, column)
            control.currentIndexChanged.connect(self.changed)
        self.reset_button = QtWidgets.QPushButton('Reset')
        self.reset_button.clicked.connect(self.reset)
        layout.addWidget(self.reset_button, 1, 3)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status, 2, 0, 1, 4)

    def reset(self):
        for control in (self.tag, self.rating, self.deletion):
            with QtCore.QSignalBlocker(control):
                control.setCurrentIndex(0)
        self.changed.emit()

    def set_tags(self, names):
        selected = self.tag.currentData()
        with QtCore.QSignalBlocker(self.tag):
            self.tag.clear()
            self.tag.addItem('All tags', None)
            for name in names:
                self.tag.addItem(name, name)
            index = self.tag.findData(selected)
            self.tag.setCurrentIndex(max(0, index))

    def is_active(self):
        return any(control.currentIndex() != 0 for control in (self.tag, self.rating, self.deletion))
