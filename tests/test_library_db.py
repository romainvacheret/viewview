from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from viewview.core.library_db import DATABASE_NAME, database, insert_tags
from viewview.core.review import read_deletion_marks, set_deletion_mark, read_rating, set_rating
from viewview.core.tags import add_tags, read_tags


class LibraryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / DATABASE_NAME
        self.photo = '2026/07/12/photo.jpg'

    def legacy(self):
        tags = {'Summer holiday': [self.photo, self.photo], 'family': [self.photo], 'empty': []}
        (self.root / 'tags.json').write_text(json.dumps(tags))
        (self.root / 'review.json').write_text(json.dumps({'to_be_deleted': [self.photo]}))

    def test_migration_preserves_tags_marks_and_original_backups(self):
        self.legacy()
        originals = {name: (self.root / name).read_bytes() for name in ('tags.json', 'review.json')}
        self.assertEqual(read_tags(self.root), {
            'Summer holiday': [self.photo], 'family': [self.photo], 'empty': []})
        self.assertTrue(self.database.exists())
        self.assertEqual(read_deletion_marks(self.root), {self.photo})
        for name, contents in originals.items():
            self.assertEqual((self.root / name).read_bytes(), contents)
        # Clearing a migrated mark must survive future reads and restarts.
        set_deletion_mark(self.root, self.root / self.photo, False)
        (self.root / 'review.json').write_text('now an obsolete backup')
        self.assertEqual(read_deletion_marks(self.root), set())
        self.assertEqual(read_tags(self.root)['family'], [self.photo])

    def test_preview_validates_legacy_without_creating_database(self):
        self.legacy()
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        self.assertEqual(read_tags(self.root, read_only=True)['family'], [self.photo])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})
        self.assertFalse(self.database.exists())

    def test_invalid_legacy_review_blocks_entire_migration(self):
        self.legacy()
        (self.root / 'review.json').write_text('broken')
        with self.assertRaisesRegex(ValueError, 'Invalid review index'):
            add_tags(self.root, ['new'], [self.photo])
        self.assertFalse(self.database.exists())
        self.assertIn('Summer holiday', (self.root / 'tags.json').read_text())
        (self.root / 'review.json').write_text('{"to_be_deleted": []}')
        self.assertIn('Summer holiday', read_tags(self.root))

    def test_transaction_failure_rolls_back_tags_and_review_together(self):
        add_tags(self.root, ['family'], [self.photo])
        with self.assertRaises(RuntimeError):
            with database(self.root, write=True) as connection:
                connection.execute('UPDATE photos SET to_be_deleted = 1')
                connection.execute('DELETE FROM photo_tags')
                connection.execute('DELETE FROM tags')
                raise RuntimeError('interrupted')
        self.assertEqual(read_deletion_marks(self.root), set())
        self.assertEqual(read_tags(self.root), {'family': [self.photo]})

    def test_interrupted_migration_can_retry_without_partial_data(self):
        self.legacy()
        def interrupted(connection, names, paths):
            insert_tags(connection, names, paths)
            if names == ['family']:
                raise sqlite3.OperationalError('interrupted migration')
        with patch('viewview.core.library_db.insert_tags', side_effect=interrupted):
            with self.assertRaisesRegex(ValueError, 'interrupted migration'):
                read_tags(self.root)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall(), [])
        before = self.database.read_bytes()
        self.assertIn('family', read_tags(self.root, read_only=True))
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(read_deletion_marks(self.root), {self.photo})
        self.assertEqual(read_tags(self.root)['Summer holiday'], [self.photo])

    def test_concurrent_writers_merge_tags_and_preserve_review_marks(self):
        self.legacy()
        def update(index):
            add_tags(self.root, [f'tag-{index}'], [self.photo, f'other-{index}.png'])
            set_deletion_mark(self.root, self.root / f'other-{index}.png', True)
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(update, range(16)))
        tags = read_tags(self.root)
        self.assertEqual(len(tags), 19)
        for index in range(16):
            self.assertEqual(tags[f'tag-{index}'], [self.photo, f'other-{index}.png'])
        self.assertEqual(read_deletion_marks(self.root),
                         {self.photo} | {f'other-{index}.png' for index in range(16)})

    def test_schema_enforces_unique_associations_and_foreign_keys(self):
        add_tags(self.root, ['family', 'family'], [self.photo, self.photo])
        with database(self.root) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM photo_tags').fetchone()[0], 1)
        with self.assertRaisesRegex(ValueError, 'FOREIGN KEY constraint failed'):
            with database(self.root, write=True) as connection:
                connection.execute('INSERT INTO photo_tags VALUES (?, ?)', ('missing.jpg', 'family'))
        self.assertEqual(read_tags(self.root), {'family': [self.photo]})

    def test_new_libraries_do_not_create_files_on_read(self):
        missing = self.root / 'not-created'
        self.assertEqual(read_tags(missing), {})
        self.assertEqual(read_deletion_marks(missing), set())
        self.assertFalse(missing.exists())

    def test_existing_database_preview_is_read_only(self):
        add_tags(self.root, ['family'], [self.photo])
        before = self.database.read_bytes()
        self.assertEqual(read_tags(self.root, read_only=True), {'family': [self.photo]})
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual([path.name for path in self.root.iterdir()], [DATABASE_NAME])

    def test_invalid_or_newer_databases_are_not_overwritten(self):
        self.database.write_bytes(b'not sqlite')
        before = self.database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Library database error'):
            add_tags(self.root, ['family'], [self.photo])
        self.assertEqual(self.database.read_bytes(), before)
        self.database.unlink()
        add_tags(self.root, ['family'], [self.photo])
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('PRAGMA user_version = 99')
        before = self.database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unsupported library database version: 99'):
            read_deletion_marks(self.root)
        self.assertEqual(self.database.read_bytes(), before)

    def test_ratings_persist_without_overwriting_tags_or_review(self):
        image = self.root / self.photo
        self.assertIsNone(read_rating(self.root, image))
        self.assertFalse(self.database.exists())
        add_tags(self.root, ['family'], [self.photo])
        set_deletion_mark(self.root, image, True)
        set_rating(self.root, image, 5)
        self.assertEqual(read_rating(self.root, image), 5)
        set_deletion_mark(self.root, image, False)
        add_tags(self.root, ['holiday'], [self.photo])
        self.assertEqual(read_rating(self.root, image), 5)
        set_rating(self.root, image, 0)
        self.assertEqual(read_rating(self.root, image), 0)
        self.assertEqual(read_tags(self.root), {'family': [self.photo], 'holiday': [self.photo]})

    def test_rating_validation_and_database_constraint(self):
        for invalid in (-1, 6, 2.5, '4', True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                set_rating(self.root, self.root / self.photo, invalid)
        self.assertFalse(self.database.exists())
        set_rating(self.root, self.root / self.photo, 3)
        with self.assertRaises(ValueError):
            with database(self.root, write=True) as connection:
                connection.execute('UPDATE photos SET rating = 8')
        self.assertEqual(read_rating(self.root, self.root / self.photo), 3)

    def test_version_one_database_upgrades_without_changing_existing_metadata(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executescript('''
                CREATE TABLE photos(path TEXT PRIMARY KEY, to_be_deleted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE tags(name TEXT PRIMARY KEY);
                CREATE TABLE photo_tags(photo_path TEXT, tag_name TEXT, PRIMARY KEY(tag_name, photo_path));
                PRAGMA user_version = 1;
            ''')
            connection.execute('INSERT INTO photos VALUES (?, 1)', (self.photo,))
            connection.execute("INSERT INTO tags VALUES ('family')")
            connection.execute("INSERT INTO photo_tags VALUES (?, 'family')", (self.photo,))
        before = self.database.read_bytes()
        self.assertEqual(read_tags(self.root, read_only=True), {'family': [self.photo]})
        self.assertEqual(self.database.read_bytes(), before)
        self.assertIsNone(read_rating(self.root, self.root / self.photo))
        self.assertEqual(read_tags(self.root), {'family': [self.photo]})
        self.assertEqual(read_deletion_marks(self.root), {self.photo})
        set_rating(self.root, self.root / self.photo, 4)
        self.assertEqual(read_rating(self.root, self.root / self.photo), 4)
