# PIL does not handle CR2 files, so EXIF data is read with ExifRead.
import exifread
import logging

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final


# TODO: add more formats
HANDLED_FORMATS: Final[set[str]] = {'.jpeg', '.jpg', '.cr2', '.heic', '.mov', '.png'}


@dataclass(frozen=True)
class FileInfo:
    path: Path
    size: int
    date: datetime | None
    warnings: tuple[str, ...] = ()


class ImageMetadataReader:
    @staticmethod
    def get_info(filepath: Path) -> FileInfo:
        if filepath.suffix.lower() == '.mov':
            from .video_metadata import read_mov_date

            messages: list[str] = []
            date = read_mov_date(filepath, warnings=messages)
            return FileInfo(filepath, filepath.stat().st_size, date, tuple(messages))

        with open(filepath, 'rb') as file:
            diagnostics = _MetadataDiagnostics(filepath)
            logger = logging.getLogger('exifread')
            logger.addFilter(diagnostics)
            # Only read the necessary tag to save time.
            try:
                tags = exifread.process_file(
                    file,
                    stop_tag='EXIF DateTimeOriginal',
                    details=False,
                )
            finally:
                logger.removeFilter(diagnostics)
            if diagnostics.invalid_reason:
                raise ValueError(diagnostics.invalid_reason)

        date = tags.get('EXIF DateTimeOriginal', '')
        parsed_date = (
            datetime.strptime(str(date), '%Y:%m:%d %H:%M:%S')
            if date != ''
            else None
        )

        return FileInfo(filepath, filepath.stat().st_size, parsed_date, tuple(diagnostics.warnings))


class _MetadataDiagnostics(logging.Filter):
    """Give ExifRead messages a source path and retain format failures."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.invalid_reason = None
        self.warnings: list[str] = []

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # Missing optional metadata is normal: these images go to _undated.
        if message == 'PNG file does not have exif data.':
            return False
        if message == 'File format not recognized.':
            self.invalid_reason = message
        elif record.levelno >= logging.WARNING and message not in self.warnings:
            self.warnings.append(message)
        record.msg = f'{self.path}: {message}'
        record.args = ()
        return True


class ImageIndex:
    def __init__(self, images: Iterable[Path]) -> None:
        self._files = {
            self._key(ImageMetadataReader.get_info(image))
            for image in images
        }

    @staticmethod
    def _key(info: FileInfo) -> tuple[str, int, datetime | None]:
        return info.path.name, info.size, info.date

    def contains(self, filepath: Path) -> bool:
        info = ImageMetadataReader.get_info(filepath)
        return self._key(info) in self._files
