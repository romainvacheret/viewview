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
