"""Persistent review marks, stored alongside the library's tag index."""
import json
import os
from pathlib import Path, PurePosixPath
import tempfile


def read_deletion_marks(library: Path) -> set[str]:
    path = library / 'review.json'
    try:
        with path.open(encoding='utf-8') as source:
            data = json.load(source)
    except FileNotFoundError:
        return set()
    except (ValueError, UnicodeError) as error:
        raise ValueError(f'Invalid review index {path}: {error}') from error
    if not isinstance(data, dict) or not isinstance(data.get('to_be_deleted'), list):
        raise ValueError(f'Invalid review index {path}: expected a to_be_deleted list')
    marks = data['to_be_deleted']
    if any(not isinstance(value, str) or not value or PurePosixPath(value).is_absolute()
           or '..' in PurePosixPath(value).parts for value in marks):
        raise ValueError(f'Invalid review index {path}: expected relative image paths')
    return set(marks)


def review_path(library: Path, image: Path) -> str:
    return Path(os.path.abspath(image)).relative_to(Path(os.path.abspath(library))).as_posix()


def set_deletion_mark(library: Path, image: Path, marked: bool) -> None:
    relative = review_path(library, image)
    marks = read_deletion_marks(library)
    if marked:
        marks.add(relative)
    else:
        marks.discard(relative)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=library,
                                         prefix='.review-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            json.dump({'to_be_deleted': sorted(marks)}, output, indent=2, ensure_ascii=False)
            output.write('\n')
        os.replace(temporary, library / 'review.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
