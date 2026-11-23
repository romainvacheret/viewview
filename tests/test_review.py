import json
from pathlib import Path
import tempfile
import unittest

from viewview.core.review import read_deletion_marks, set_deletion_mark
from viewview.core.library_db import DATABASE_NAME, database


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root / '2026/07/12/first.jpg'
        self.second = self.root / '2026/07/12/second.jpg'

    def test_marks_are_relative_deduplicated_and_can_be_removed(self):
        self.assertEqual(read_deletion_marks(self.root), set())
        set_deletion_mark(self.root, self.first, True)
        set_deletion_mark(self.root, self.second, True)
        set_deletion_mark(self.root, self.first, True)
        self.assertEqual(read_deletion_marks(self.root),
                         {'2026/07/12/first.jpg', '2026/07/12/second.jpg'})
        set_deletion_mark(self.root, self.first, False)
        self.assertEqual(read_deletion_marks(self.root), {'2026/07/12/second.jpg'})
        moved = self.root / 'relocated'
        moved.mkdir()
        (self.root / DATABASE_NAME).rename(moved / DATABASE_NAME)
        self.assertEqual(read_deletion_marks(moved), {'2026/07/12/second.jpg'})

    def test_invalid_indexes_are_not_overwritten(self):
        path = self.root / 'review.json'
        for data in ('broken', '[]', '{}', '{"to_be_deleted": [123]}',
                     '{"to_be_deleted": ["../outside.jpg"]}'):
            with self.subTest(data=data):
                path.write_text(data)
                with self.assertRaisesRegex(ValueError, 'Invalid review index'):
                    set_deletion_mark(self.root, self.first, True)
                self.assertEqual(path.read_text(), data)

    def test_failed_transaction_preserves_previous_marks(self):
        set_deletion_mark(self.root, self.first, True)
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            with database(self.root, write=True) as connection:
                connection.execute("UPDATE photos SET to_be_deleted = 0")
                raise RuntimeError('interrupted')
        self.assertEqual(read_deletion_marks(self.root), {'2026/07/12/first.jpg'})

    def test_marks_cannot_escape_the_library_and_do_not_change_tags(self):
        tags = self.root / 'tags.json'
        tags.write_text(json.dumps({'family': ['2026/07/12/first.jpg']}))
        before = tags.read_bytes()
        with self.assertRaises(ValueError):
            set_deletion_mark(self.root, self.root / '../outside.jpg', True)
        self.assertFalse((self.root / DATABASE_NAME).exists())
        set_deletion_mark(self.root, self.first, True)
        self.assertEqual(tags.read_bytes(), before)
