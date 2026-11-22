"""Import controls and background jobs, sharing the CLI's import pipeline."""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from .core.metadata import HANDLED_FORMATS
from .core.organization import OrganizationPlan, import_images
from .core.reporting import write_import_report


def parse_tags(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tag.strip() for tag in text.split(',') if tag.strip()))


@dataclass(frozen=True)
class FolderPreview:
    path: Path
    existing: int
    added: int
    created: bool


def preview_folders(destination: Path, plan: OrganizationPlan) -> list[FolderPreview]:
    """Include existing folders and all ancestors needed by new date folders."""
    existing = Counter()
    added = Counter()
    folders = {destination}
    for path in destination.rglob('*'):
        if path.is_dir() and not path.is_symlink():
            folders.add(path)
        elif path.is_file() and path.suffix.lower() in HANDLED_FORMATS:
            existing[path.parent] += 1
    for file in plan.files:
        added[file.destination.parent] += 1
        folders.add(file.destination.parent)
    for folder in tuple(folders):
        parent = folder
        while parent != destination:
            parent = parent.parent
            folders.add(parent)
    # Counts include descendants, so year/month rows describe their whole branch.
    for counts in (existing, added):
        for folder, count in tuple(counts.items()):
            while folder != destination:
                folder = folder.parent
                counts[folder] += count
    return [FolderPreview(folder, existing[folder], added[folder], not folder.exists())
            for folder in sorted(folders)]


class ImportJob(QtCore.QObject):
    succeeded = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    done = QtCore.Signal()

    def __init__(self, source: Path, destination: Path, move: bool,
                 tags: tuple[str, ...], execute: bool):
        super().__init__()
        self.source = source
        self.destination = destination
        self.move = move
        self.tags = tags
        self.execute = execute

    @QtCore.Slot()
    def run(self):
        try:
            plan = import_images(self.source, self.destination, move=self.move,
                                 tags=self.tags, dry_run=not self.execute)
            if self.execute:
                report = write_import_report(plan, self.destination, move=self.move)
                self.succeeded.emit((plan, None, report))
            else:
                self.succeeded.emit((plan, preview_folders(self.destination, plan), None))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.done.emit()


class ImportWidget(QtWidgets.QWidget):
    imported = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._destination = None
        self._source = None
        self._plan = None
        self._thread = None
        self._worker = None
        self._revision = 0
        self._job_revision = 0
        self._executing = False
        self._pending_preview = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._start_preview)
        self._build_ui()

    @property
    def is_busy(self):
        return self._thread is not None

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        title = QtWidgets.QLabel('Import into your library')
        title.setObjectName('import-title')
        layout.addWidget(title)
        description = QtWidgets.QLabel('Choose a source folder to preview its media in the current library. '
                                      'Nothing changes until you click Import.')
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        self.destination_label = QtWidgets.QLineEdit()
        self.destination_label.setReadOnly(True)
        self.destination_label.setPlaceholderText('Open a folder in the viewer to set the destination')
        form.addRow('Destination library', self.destination_label)
        source_row = QtWidgets.QHBoxLayout()
        self.source_label = QtWidgets.QLineEdit()
        self.source_label.setReadOnly(True)
        self.source_label.setPlaceholderText('Select the folder to import from')
        self.source_button = QtWidgets.QPushButton('Choose source…')
        self.source_button.clicked.connect(self.choose_source)
        source_row.addWidget(self.source_label, 1)
        source_row.addWidget(self.source_button)
        form.addRow('Source folder', source_row)

        operation = QtWidgets.QHBoxLayout()
        self.copy_button = QtWidgets.QPushButton('Copy')
        self.move_button = QtWidgets.QPushButton('Move')
        self.operation_group = QtWidgets.QButtonGroup(self)
        for button in (self.copy_button, self.move_button):
            button.setCheckable(True)
            self.operation_group.addButton(button)
            operation.addWidget(button)
        self.copy_button.setChecked(True)
        operation.addStretch()
        self.move_note = QtWidgets.QLabel('Copy keeps the original files in the source folder.')
        self.move_note.setWordWrap(True)
        operation.addWidget(self.move_note, 1)
        self.operation_group.buttonToggled.connect(self._operation_changed)
        form.addRow('Operation', operation)
        self.tags_input = QtWidgets.QLineEdit()
        self.tags_input.setPlaceholderText('Summer holiday, family, favorites')
        self.tags_input.setToolTip('Separate tags with commas. Spaces within a tag are preserved.')
        self.tags_input.textChanged.connect(self._schedule_preview)
        form.addRow('Tags (optional)', self.tags_input)
        layout.addLayout(form)

        preview_heading = QtWidgets.QHBoxLayout()
        heading = QtWidgets.QLabel('Destination after import')
        heading.setObjectName('import-preview-title')
        preview_heading.addWidget(heading)
        preview_heading.addStretch()
        self.refresh_button = QtWidgets.QPushButton('Refresh preview')
        self.refresh_button.clicked.connect(self._schedule_preview)
        preview_heading.addWidget(self.refresh_button)
        layout.addLayout(preview_heading)
        self.summary = QtWidgets.QLabel('Choose a source folder to see the preview.')
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Folder', 'Existing', 'To add', 'After import', 'Folder status'])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            self.tree.header().setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('Warnings, errors, and duplicate files will appear here.')
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)
        footer = QtWidgets.QHBoxLayout()
        self.result_label = QtWidgets.QLabel()
        self.result_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.result_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_label.setWordWrap(True)
        footer.addWidget(self.result_label, 1)
        self.import_button = QtWidgets.QPushButton('Import')
        self.import_button.setObjectName('import-action')
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.start_import)
        footer.addWidget(self.import_button)
        layout.addLayout(footer)

    def set_destination(self, destination: Path):
        self._destination = destination.resolve()
        self.destination_label.setText(str(self._destination))
        self.destination_label.setToolTip(str(self._destination))
        self._schedule_preview()

    def choose_source(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Choose import source')
        if folder:
            self.set_source(Path(folder))

    def set_source(self, source: Path):
        self._source = source.resolve()
        self.source_label.setText(str(self._source))
        self.source_label.setToolTip(str(self._source))
        self.result_label.clear()
        self._schedule_preview()

    def _operation_changed(self, button, checked):
        if checked:
            self.move_note.setText('Move removes successfully imported files from the source folder.'
                                   if self.move_button.isChecked() else
                                   'Copy keeps the original files in the source folder.')
            self._schedule_preview()

    def _schedule_preview(self, *_):
        self._revision += 1
        self._plan = None
        self.import_button.setEnabled(False)
        self.tree.clear()
        self.details.clear()
        if self._source is None or self._destination is None:
            self.summary.setText('Choose a source folder and open a destination library in the viewer.')
            return
        self.summary.setText('Checking import…')
        self._pending_preview = True
        self._timer.start(350)

    def _start_preview(self):
        if self.is_busy or not self._pending_preview:
            return
        self._pending_preview = False
        self._start_job(execute=False)

    def start_import(self):
        if self._plan is None or self.is_busy:
            return
        self._timer.stop()
        self._pending_preview = False
        self.result_label.clear()
        self.summary.setText('Importing…')
        self._start_job(execute=True)

    def _start_job(self, *, execute):
        self._executing = execute
        self._job_revision = self._revision
        self.import_button.setEnabled(False)
        self._set_controls_enabled(not execute)
        self._thread = QtCore.QThread(self)
        self._worker = ImportJob(self._source, self._destination, self.move_button.isChecked(),
                                 parse_tags(self.tags_input.text()), execute)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._succeeded)
        self._worker.failed.connect(self._failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.done.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _set_controls_enabled(self, enabled):
        for widget in (self.source_button, self.tags_input, self.copy_button,
                       self.move_button, self.refresh_button):
            widget.setEnabled(enabled)

    @QtCore.Slot(object)
    def _succeeded(self, result):
        plan, folders, report = result
        if self._executing:
            action = 'Moved' if self.move_button.isChecked() else 'Copied'
            self.result_label.setText(f'{action} {len(plan.files)} files. '
                                      f'{len(plan.invalid_files)} invalid files skipped. Report: {report}')
            self.imported.emit()
            self._schedule_preview()
        elif self._job_revision == self._revision:
            self._plan = plan
            self._render_preview(plan, folders)

    @QtCore.Slot(str)
    def _failed(self, message):
        if self._job_revision != self._revision and not self._executing:
            return
        self._plan = None
        self.tree.clear()
        self.summary.setText('Import stopped.' if self._executing else 'Preview unavailable.')
        self.details.setPlainText(message)
        if self._executing:
            self.result_label.setText('Some files may already have been imported. Refresh the preview before retrying.')
            self.imported.emit()

    @QtCore.Slot()
    def _finished(self):
        # finished() precedes the last deferred QObject deletions. Keep the
        # Python worker alive until Qt has completed its thread-side cleanup.
        self._thread.wait()
        self._thread = None
        self._worker = None
        self._executing = False
        self._set_controls_enabled(True)
        has_tags = bool(parse_tags(self.tags_input.text()))
        self.import_button.setEnabled(self._plan is not None and
                                      bool(self._plan.files or (has_tags and self._plan.identical_files)))
        if self._pending_preview:
            self._timer.start(0)

    def _render_preview(self, plan, folders):
        self.tree.clear()
        items = {}
        created = sum(folder.created for folder in folders)
        for folder in folders:
            parent = self.tree if folder.path == self._destination else items[folder.path.parent]
            name = str(self._destination) if parent is self.tree else folder.path.name
            item = QtWidgets.QTreeWidgetItem(parent, [name, str(folder.existing), str(folder.added),
                str(folder.existing + folder.added), 'Create' if folder.created else 'Existing'])
            item.setToolTip(0, str(folder.path))
            for column in range(1, 4):
                item.setTextAlignment(column, QtCore.Qt.AlignmentFlag.AlignRight)
            items[folder.path] = item
        self.tree.expandToDepth(2)
        self.summary.setText(f'{len(plan.files)} files to add · {created} folders to create · '
                             f'{len(plan.skipped_files)} identical files skipped · '
                             f'{len(plan.invalid_files)} errors · {len(plan.warnings)} warnings')
        messages = [f'Error — {file.path}: {file.reason}' for file in plan.invalid_files]
        messages += [f'Warning — {warning.path}: {warning.message}' for warning in plan.warnings]
        messages += [f'Already present — {file.source} → {file.destination}' for file in plan.identical_files]
        self.details.setPlainText('\n'.join(messages))
