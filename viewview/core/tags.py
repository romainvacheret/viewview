"""Tag associations in the library's SQLite database."""
from pathlib import Path

from .library_db import database, insert_tags, validate_paths


def read_tags(destination: Path, *, read_only: bool = False) -> dict[str, list[str]]:
    with database(destination, migrate=not read_only) as connection:
        tags = {row[0]: [] for row in connection.execute('SELECT name FROM tags ORDER BY name')}
        for name, path in connection.execute('SELECT tag_name, photo_path FROM photo_tags ORDER BY tag_name, photo_path'):
            tags[name].append(path)
        return tags


def add_tags(destination: Path, names, paths) -> None:
    """Merge associations in one transaction without overwriting other writers."""
    names = tuple(dict.fromkeys(names))
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError('Tag must not be empty or whitespace')
    paths = validate_paths(paths)
    with database(destination, write=True) as connection:
        insert_tags(connection, names, paths)


def photo_tags(library: Path, path: str) -> list[str]:
    path = validate_paths([path])[0]
    with database(library) as connection:
        return [row[0] for row in connection.execute(
            'SELECT tag_name FROM photo_tags WHERE photo_path = ? ORDER BY tag_name COLLATE NOCASE, tag_name',
            (path,))]


def tag_names(library: Path) -> list[str]:
    with database(library) as connection:
        return [row[0] for row in connection.execute('SELECT name FROM tags ORDER BY name COLLATE NOCASE, name')]


def remove_photo_tag(library: Path, path: str, name: str) -> None:
    """Remove only this photo's association; keep the library's tag vocabulary."""
    path = validate_paths([path])[0]
    with database(library, write=True) as connection:
        connection.execute('DELETE FROM photo_tags WHERE photo_path = ? AND tag_name = ?', (path, name))
