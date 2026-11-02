import contextlib
from datetime import datetime
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from viewview.cli import main
from viewview.core.metadata import FileInfo
from viewview.core.organization import import_images, plan_organization, apply_plan


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.destination = self.root / 'destination'
        self.date = datetime(2026, 11, 2, 12, 30)
        reader = patch('viewview.core.organization.ImageMetadataReader.get_info',
                       side_effect=lambda p: FileInfo(p, p.stat().st_size, self.date))
        reader.start()
        self.addCleanup(reader.stop)

    def image(self, folder, content):
        path = self.source / folder / 'photo.JPG'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_recursive_collisions_and_repeat_import(self):
        self.image('a', b'abc')
        self.image('b', b'abc')
        self.image('c', b'xyz')  # Equal size alone does not establish equality.
        self.image('d', b'longer')
        plan = import_images(self.source, self.destination)
        self.assertEqual(len(plan.files), 3)
        self.assertEqual(len(plan.skipped_files), 1)
        self.assertEqual(plan.invalid_files, [])
        target = self.destination / '2026/11/02'
        self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, {
            'photo.JPG': b'abc', 'photo_1.JPG': b'xyz', 'photo_2.JPG': b'longer'})
        again = import_images(self.source, self.destination)
        self.assertEqual(again.files, [])
        self.assertEqual(len(again.skipped_files), 4)
        self.assertEqual(len(list(self.source.rglob('*.JPG'))), 4)

    def test_undated(self):
        self.date = None
        self.image('nested', b'abc')
        import_images(self.source, self.destination)
        self.assertTrue((self.destination / '_undated/photo.JPG').is_file())

    def test_heic_copy_and_move(self):
        for move, extension in [(False, '.heic'), (True, '.HEIC')]:
            with self.subTest(move=move, extension=extension):
                image = self.source / 'nested' / f'apple{extension}'
                image.parent.mkdir(exist_ok=True)
                image.write_bytes(b'heic contents')
                plan = import_images(self.source, self.destination, move=move)
                target = self.destination / '2026/11/02' / image.name
                self.assertEqual(target.read_bytes(), b'heic contents')
                self.assertEqual(image.exists(), not move)
                self.assertIn(image, [file.source for file in plan.files])

    def test_destination_inside_source_is_rejected(self):
        with self.assertRaises(ValueError):
            import_images(self.source, self.source / 'output')

    def test_copy_does_not_overwrite_file_created_after_planning(self):
        image = self.image('a', b'abc')
        plan = plan_organization([image], self.destination)
        target = plan.files[0].destination
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            apply_plan(plan)
        self.assertEqual(target.read_bytes(), b'existing')

    def test_cli_import(self):
        self.image('nested', b'abc')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(['import', str(self.source), str(self.destination)])
        self.assertEqual(result, 0)
        self.assertIn('Copied 1', output.getvalue())
        self.assertNotIn('PySide6', sys.modules)

    def test_cli_invalid_source(self):
        with contextlib.redirect_stderr(io.StringIO()):
            result = main(['import', str(self.root / 'missing'), str(self.destination)])
        self.assertEqual(result, 1)

    def test_cli_move_preserves_conflicts_and_skips_identical(self):
        first = self.image('a', b'abc')
        duplicate = self.image('b', b'abc')
        different = self.image('c', b'xyz')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(['import', str(self.source), str(self.destination), '--move'])
        self.assertEqual(result, 0)
        self.assertIn('Moved 2; identical 1', output.getvalue())
        self.assertFalse(first.exists())
        self.assertFalse(different.exists())
        self.assertEqual(duplicate.read_bytes(), b'abc')
        target = self.destination / '2026/11/02'
        self.assertEqual((target / 'photo.JPG').read_bytes(), b'abc')
        self.assertEqual((target / 'photo_1.JPG').read_bytes(), b'xyz')

    def test_move_failure_keeps_source_and_existing_destination(self):
        image = self.image('a', b'abc')
        plan = plan_organization([image], self.destination)
        target = plan.files[0].destination
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            apply_plan(plan, move=True)
        self.assertEqual(image.read_bytes(), b'abc')
        self.assertEqual(target.read_bytes(), b'existing')

    def test_invalid_metadata_does_not_block_valid_images(self):
        bad = self.image('bad', b'bad')
        good = self.image('good', b'good')
        def metadata(path):
            if path == bad:
                raise ValueError('Invalid EXIF date')
            return FileInfo(path, path.stat().st_size, self.date)
        with patch('viewview.core.organization.ImageMetadataReader.get_info',
                   side_effect=metadata):
            plan = import_images(self.source, self.destination)
        self.assertEqual([file.source for file in plan.files], [good])
        self.assertEqual([file.path for file in plan.invalid_files], [bad])

    def test_module_help_without_gui(self):
        result = subprocess.run([sys.executable, '-m', 'viewview', 'import', '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('source', result.stdout)


if __name__ == '__main__':
    unittest.main()
