# PIL does not handle CR2 files, need an additional library
import exifread

from pathlib import Path
from collections import namedtuple
from datetime import datetime
from typing import Final


# TODO: add more formats
HANDLED_FORMATS: Final[set[str]] = {'.jpeg', '.jpg', '.CR2'}


FileInfo = namedtuple('FileInfo', ['size', 'date'])
FileInfoMapping = dict[str, FileInfo]


class FileManager:
    def __init__(self, folder: Path) -> None:
        self.folder: Final[Path] = folder
        self._mapping = self._generate_mapping()

    @staticmethod
    def get_info(filepath: Path) -> FileInfo:
        with open(filepath, 'rb') as file:
            # Only read the necessary tag to save time
            tags = exifread.process_file(file, 
                                         stop_tag="EXIF DateTimeOriginal", 
                                         details=False)
            date = tags.get('EXIF DateTimeOriginal', '')
            # Date format used by the library
            date = datetime.strptime(str(date), "%Y:%m:%d %H:%M:%S") if date != '' else ''

        # TODO: How to handle different files with same name but in different folders?
        return FileInfo(filepath.stat().st_size, date) 

    @staticmethod
    def map_files(folder: Path) -> FileInfoMapping:
        return {file.name: FileManager.get_info(file) for file in folder.rglob('*') 
            if file.is_file() and file.suffix in HANDLED_FORMATS}

    def _generate_mapping(self) -> FileInfoMapping:
        return FileManager.map_files(self.folder)

    def is_already_present(self, filepath: Path) -> bool:
        return (name := filepath.name) in self._mapping and \
            self._mapping.get(name) == FileManager.get_info(filepath)

