import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from viewview.core.review import read_deletion_marks, set_deletion_mark


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
        (self.root / 'review.json').rename(moved / 'review.json')
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

    def test_failed_atomic_replace_preserves_previous_marks(self):
        set_deletion_mark(self.root, self.first, True)
        before = (self.root / 'review.json').read_bytes()
        with patch('viewview.core.review.os.replace', side_effect=PermissionError('Read-only library')):
            with self.assertRaises(PermissionError):
                set_deletion_mark(self.root, self.second, True)
        self.assertEqual((self.root / 'review.json').read_bytes(), before)
        self.assertEqual(list(self.root.glob('.review-*')), [])

    def test_marks_cannot_escape_the_library_and_do_not_change_tags(self):
        tags = self.root / 'tags.json'
        tags.write_text(json.dumps({'family': ['2026/07/12/first.jpg']}))
        before = tags.read_bytes()
        with self.assertRaises(ValueError):
            set_deletion_mark(self.root, self.root / '../outside.jpg', True)
        self.assertFalse((self.root / 'review.json').exists())
        set_deletion_mark(self.root, self.first, True)
        self.assertEqual(tags.read_bytes(), before)
