# PIL does not handle CR2 files, so EXIF data is read with ExifRead.
import exifread

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


class ImageMetadataReader:
    @staticmethod
    def get_info(filepath: Path) -> FileInfo:
        if filepath.suffix.lower() == '.mov':
            from .video_metadata import read_mov_date

            return FileInfo(filepath, filepath.stat().st_size, read_mov_date(filepath))

        with open(filepath, 'rb') as file:
            # Only read the necessary tag to save time.
            tags = exifread.process_file(
                file,
                stop_tag='EXIF DateTimeOriginal',
                details=False,
            )

        date = tags.get('EXIF DateTimeOriginal', '')
        parsed_date = (
            datetime.strptime(str(date), '%Y:%m:%d %H:%M:%S')
            if date != ''
            else None
        )

        return FileInfo(filepath, filepath.stat().st_size, parsed_date)


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
