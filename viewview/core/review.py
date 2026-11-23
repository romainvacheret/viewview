"""Persistent photo ratings and review marks in the library's SQLite database."""
import os
from pathlib import Path

from .library_db import database, validate_paths


def read_deletion_marks(library: Path) -> set[str]:
    with database(library) as connection:
        return {row[0] for row in connection.execute('SELECT path FROM photos WHERE to_be_deleted = 1')}


def review_path(library: Path, image: Path) -> str:
    return Path(os.path.abspath(image)).relative_to(Path(os.path.abspath(library))).as_posix()


def is_marked_for_deletion(library: Path, image: Path) -> bool:
    relative = validate_paths([review_path(library, image)])[0]
    with database(library) as connection:
        row = connection.execute('SELECT to_be_deleted FROM photos WHERE path = ?', (relative,)).fetchone()
        return bool(row and row[0])


def set_deletion_mark(library: Path, image: Path, marked: bool) -> None:
    relative = validate_paths([review_path(library, image)])[0]
    with database(library, write=True) as connection:
        connection.execute('''INSERT INTO photos(path, to_be_deleted) VALUES (?, ?)
            ON CONFLICT(path) DO UPDATE SET to_be_deleted = excluded.to_be_deleted''',
                           (relative, int(marked)))


def read_rating(library: Path, image: Path) -> int | None:
    """None means no library override; zero is an explicitly unrated photo."""
    relative = validate_paths([review_path(library, image)])[0]
    with database(library) as connection:
        row = connection.execute('SELECT rating FROM photos WHERE path = ?', (relative,)).fetchone()
        return row[0] if row else None


def set_rating(library: Path, image: Path, rating: int) -> None:
    if type(rating) is not int or not 0 <= rating <= 5:
        raise ValueError('Rating must be an integer between 0 and 5')
    relative = validate_paths([review_path(library, image)])[0]
    with database(library, write=True) as connection:
        connection.execute('''INSERT INTO photos(path, rating) VALUES (?, ?)
            ON CONFLICT(path) DO UPDATE SET rating = excluded.rating''', (relative, rating))
