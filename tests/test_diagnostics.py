import contextlib
from datetime import datetime, timezone
import io
import json
import logging
import struct
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_png_import import png
from viewview.cli import main
from viewview.core.metadata import ImageMetadataReader
from viewview.core.video_metadata import read_mov_date
from viewview.core.organization import OrganizationPlan, import_images
from viewview.core.reporting import write_import_report


class DiagnosticTests(unittest.TestCase):
    def test_corrupt_software_tag_does_not_prevent_dated_import(self):
        # A Software string containing invalid UTF-8 triggers ExifRead's warning.
        tiff = b'II' + struct.pack('<HIH', 42, 8, 2)
        tiff += struct.pack('<HHI', 0x0131, 2, 2) + b'\xff\x00\x00\x00'
        tiff += struct.pack('<HHII', 0x8769, 4, 1, 38) + bytes(4)
        tiff += struct.pack('<HHHII', 1, 0x9003, 2, 20, 56) + bytes(4)
        tiff += b'2026:11:02 12:30:00\x00'
        exif = b'Exif\x00\x00' + tiff
        contents = b'\xff\xd8\xff\xe1' + struct.pack('>H', len(exif) + 2) + exif + b'\xff\xd9'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            image = source / 'software.jpg'
            image.write_bytes(contents)
            with self.assertLogs('exifread', level=logging.WARNING) as logs:
                plan = import_images(source, root / 'destination')
            self.assertTrue(any('Possibly corrupted field Software in Image IFD' in line
                                and str(image) in line for line in logs.output))
            self.assertEqual(plan.invalid_files, [])
            self.assertEqual(plan.files[0].destination.parent,
                             root / 'destination/2026/11/02')
            self.assertEqual(plan.files[0].destination.read_bytes(), contents)
            report_path = write_import_report(plan, root / 'destination', move=False)
            report = json.loads(report_path.read_text())
            self.assertEqual(report['warning'], [{
                'path': str(image),
                'message': 'Possibly corrupted field Software in Image IFD',
            }])
            self.assertEqual(report['invalid_files'], [])

    def test_cli_undated_png_has_no_warnings_for_import_and_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            image = source / 'undated.png'
            image.write_bytes(png(False))
            destination = root / 'destination'
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                for _ in range(2):
                    self.assertEqual(main(['import', str(source), str(destination)]), 0)
            reports = list(destination.glob('import-report-*.json'))
            self.assertEqual(len(reports), 2)
            for path in reports:
                report = json.loads(path.read_text())
                self.assertEqual(report['warning'], [])
                self.assertTrue((destination / '_undated/undated.png').is_file())
                self.assertEqual(report['invalid_files'], [])

    def test_mov_nonfatal_diagnostics_are_collected_and_printed(self):
        def parse(path):
            print('Recoverable metadata warning', file=sys.stderr)
            return datetime(2026, 11, 2)

        messages = []
        output = io.StringIO()
        with patch('viewview.core.video_metadata._read_mov_date', side_effect=parse):
            with contextlib.redirect_stderr(output):
                date = read_mov_date(Path('clip.mov'), warnings=messages)
        self.assertEqual(date, datetime(2026, 11, 2))
        self.assertEqual(messages, ['Recoverable metadata warning'])
        self.assertIn('clip.mov: Recoverable metadata warning', output.getvalue())

    def test_report_filename_timestamp_and_collision_safety(self):
        moment = datetime(2026, 11, 2, 12, 30, 45, 123456, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            with patch('viewview.core.reporting.datetime') as clock:
                clock.now.return_value = moment
                first = write_import_report(OrganizationPlan([], []), Path(temporary), move=False)
                second = write_import_report(OrganizationPlan([], []), Path(temporary), move=False)
            self.assertTrue(first.name.startswith('import-report-20261102T123045.123456Z-'))
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())
            self.assertEqual(json.loads(first.read_text())['created_at'], moment.isoformat())
            self.assertEqual(json.loads(first.read_text())['warning'], [])

    def test_mov_diagnostics_have_file_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'broken.mov'
            path.write_bytes(b'not a movie')
            output = io.StringIO()
            with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
                read_mov_date(path)
            self.assertIn(str(path), output.getvalue())

    def test_unrecognized_format_error_contains_only_message(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'broken.jpg'
            path.write_bytes(b'not an image')
            with self.assertRaisesRegex(ValueError, r'^File format not recognized\.$'):
                ImageMetadataReader.get_info(path)

    def test_missing_png_exif_is_not_a_warning(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'undated.png'
            path.write_bytes(png(False))
            with self.assertNoLogs('exifread', level=logging.WARNING):
                info = ImageMetadataReader.get_info(path)
            self.assertIsNone(info.date)
            self.assertEqual(info.warnings, ())

    def test_cli_report_records_duplicate_pairs_and_invalids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            destination = root / 'destination'
            for name in ('a', 'b'):
                (source / name).mkdir()
                (source / name / 'same.png').write_bytes(png())
            bad = source / 'broken.jpg'
            bad.write_bytes(b'not an image')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = main(['import', str(source), str(destination)])
            self.assertEqual(status, 1)
            reports = list(destination.glob('import-report-*.json'))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertEqual(report['identical_files'], [{
                'source': str(source / 'b/same.png'),
                'destination': str(destination / '2026/11/02/same.png'),
            }])
            self.assertEqual(report['invalid_files'][0]['path'], str(bad))
            self.assertEqual(report['invalid_files'][0]['reason'], 'File format not recognized.')
            self.assertEqual(report['warning'], [])

    def test_move_report_for_existing_duplicate_and_preserves_prior_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            image = source / 'same.png'
            image.write_bytes(png())
            destination = root / 'destination'
            target = destination / '2026/11/02/same.png'
            target.parent.mkdir(parents=True)
            target.write_bytes(png())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['import', str(source), str(destination), '--move']), 0)
                self.assertEqual(main(['import', str(source), str(destination), '--move']), 0)
            reports = list(destination.glob('import-report-*.json'))
            self.assertEqual(len(reports), 2)
            for report_path in reports:
                report = json.loads(report_path.read_text())
                self.assertEqual(report['operation'], 'move')
                self.assertEqual(report['identical_files'], [
                    {'source': str(image), 'destination': str(target)}])
                self.assertEqual(report['invalid_files'], [])
            self.assertTrue(image.exists())
