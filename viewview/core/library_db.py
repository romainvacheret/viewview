"""One transactional metadata database per library, with legacy JSON migration."""
from contextlib import contextmanager
import json
from pathlib import Path, PurePosixPath
import sqlite3

DATABASE_NAME = 'viewview.sqlite3'
SCHEMA_VERSION = 2

RATING_COLUMN = "rating INTEGER CHECK (rating IS NULL OR (typeof(rating) = 'integer' AND rating BETWEEN 0 AND 5))"


def _valid_path(value):
    return (isinstance(value, str) and value not in ('', '.')
            and not PurePosixPath(value).is_absolute() and '..' not in PurePosixPath(value).parts)


def _legacy_metadata(library):
    tags = {}
    marks = set()
    tag_path = library / 'tags.json'
    review_path = library / 'review.json'
    if tag_path.exists():
        try:
            tags = json.loads(tag_path.read_text(encoding='utf-8'))
            if not isinstance(tags, dict) or any(
                not isinstance(name, str) or not name.strip() or not isinstance(paths, list)
                or any(not _valid_path(path) for path in paths)
                for name, paths in tags.items()
            ):
                raise ValueError('expected tag names mapped to lists of relative paths')
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'Invalid tag index {tag_path}: {error}') from error
    if review_path.exists():
        try:
            review = json.loads(review_path.read_text(encoding='utf-8'))
            if (not isinstance(review, dict) or not isinstance(review.get('to_be_deleted'), list)
                    or any(not _valid_path(path) for path in review['to_be_deleted'])):
                raise ValueError('expected a to_be_deleted list of relative paths')
            marks = set(review['to_be_deleted'])
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'Invalid review index {review_path}: {error}') from error
    return tags, marks


def _create_schema(connection):
    # Individual statements keep schema creation inside the same transaction as
    # migration. executescript() would implicitly commit an existing transaction.
    connection.execute(f'''CREATE TABLE photos (
        path TEXT PRIMARY KEY NOT NULL,
        to_be_deleted INTEGER NOT NULL DEFAULT 0 CHECK (to_be_deleted IN (0, 1)),
        {RATING_COLUMN}
    )''')
    connection.execute('''CREATE TABLE tags (
        name TEXT PRIMARY KEY NOT NULL CHECK (length(trim(name)) > 0)
    )''')
    connection.execute('''CREATE TABLE photo_tags (
        photo_path TEXT NOT NULL REFERENCES photos(path),
        tag_name TEXT NOT NULL REFERENCES tags(name),
        PRIMARY KEY (tag_name, photo_path)
    )''')
    connection.execute('CREATE INDEX photo_tags_by_photo ON photo_tags(photo_path)')
    connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')


def _check_schema(connection):
    version = connection.execute('PRAGMA user_version').fetchone()[0]
    if version not in (1, SCHEMA_VERSION):
        raise ValueError(f'Unsupported library database version: {version}')
    connection.execute('SELECT path, to_be_deleted FROM photos LIMIT 0')
    if version == SCHEMA_VERSION:
        connection.execute('SELECT rating FROM photos LIMIT 0')
    connection.execute('SELECT name FROM tags LIMIT 0')
    connection.execute('SELECT photo_path, tag_name FROM photo_tags LIMIT 0')


def insert_tags(connection, names, paths):
    connection.executemany('INSERT OR IGNORE INTO photos(path) VALUES (?)', [(path,) for path in paths])
    connection.executemany('INSERT OR IGNORE INTO tags(name) VALUES (?)', [(name,) for name in names])
    connection.executemany('INSERT OR IGNORE INTO photo_tags(photo_path, tag_name) VALUES (?, ?)',
                           ((path, name) for name in names for path in paths))


@contextmanager
def database(library: Path, *, write: bool = False, migrate: bool = True):
    """Reads/previews need not create files; writes/migrations commit atomically.

    The original JSON files remain untouched as backups. Once the database
    exists they are no longer read, so removed marks cannot reappear on restart.
    Each operation owns its connection, including when called from GUI workers.
    """
    path = library / DATABASE_NAME
    exists = path.exists()
    legacy = _legacy_metadata(library) if not exists else None
    has_legacy = (library / 'tags.json').exists() or (library / 'review.json').exists()
    persist = write or (migrate and not exists and has_legacy)
    connection = None
    try:
        if persist:
            library.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=5, isolation_level=None)
        elif exists:
            connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True,
                                         timeout=5, isolation_level=None)
        else:
            connection = sqlite3.connect(':memory:', isolation_level=None)
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('BEGIN IMMEDIATE' if persist else 'BEGIN')
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        if version == 0 and not tables and exists and not persist:
            # A failed first transaction may leave an empty SQLite file. Retry
            # migration on normal access, or validate in memory for a preview.
            connection.close()
            connection = None
            if migrate:
                with database(library, write=True) as initialized:
                    yield initialized
                return
            connection = sqlite3.connect(':memory:', isolation_level=None)
            connection.execute('PRAGMA foreign_keys = ON')
            connection.execute('BEGIN')
            exists = False
        if version == 0 and not tables and (persist or not exists):
            # Schema and legacy rows share a transaction; concurrent initializers
            # reaching an existing version above skip the JSON entirely.
            if legacy is None:
                legacy = _legacy_metadata(library)
            _create_schema(connection)
            tags, marks = legacy
            for name, paths in tags.items():
                insert_tags(connection, [name], paths)
            connection.executemany('''INSERT INTO photos(path, to_be_deleted) VALUES (?, 1)
                ON CONFLICT(path) DO UPDATE SET to_be_deleted = 1''', [(path,) for path in marks])
        else:
            _check_schema(connection)
            if version == 1:
                if persist:
                    connection.execute(f'ALTER TABLE photos ADD COLUMN {RATING_COLUMN}')
                    connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
                elif migrate:
                    connection.close()
                    connection = None
                    with database(library, write=True) as upgraded:
                        yield upgraded
                    return
        yield connection
        if persist:
            connection.commit()
        else:
            connection.rollback()
    except sqlite3.Error as error:
        raise ValueError(f'Library database error in {path}: {error}') from error
    finally:
        if connection is not None:
            # Closing also rolls back incomplete transactions on any exception.
            connection.close()


def validate_paths(paths):
    paths = tuple(dict.fromkeys(paths))
    if any(not _valid_path(path) for path in paths):
        raise ValueError('Metadata paths must be relative to the library root')
    return paths


def validate_database(library: Path) -> None:
    """Check schema/legacy data without creating files or performing migration."""
    with database(library, migrate=False):
        pass
