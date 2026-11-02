from datetime import datetime
from pathlib import Path
import struct
import tempfile
import unittest

from viewview.core.organization import import_images
from viewview.core.video_metadata import read_mov_date


def atom(tag, payload):
    return struct.pack('>I4s', 8 + len(payload), tag) + payload


def movie(date=None, apple_date=None, version=0):
    content = b''
    if date is not None:
        timestamp = int((date - datetime(1904, 1, 1)).total_seconds())
        fmt = '>QQIQ' if version else '>IIII'
        header = bytes([version, 0, 0, 0]) + struct.pack(fmt, timestamp, timestamp, 1000, 0)
        content += atom(b'mvhd', header + bytes(80))
    if apple_date is not None:
        handler = atom(b'hdlr', bytes(8) + b'mdta' + bytes(13))
        keys = atom(b'keys', bytes(4) + struct.pack('>I', 1) +
                    atom(b'mdta', b'com.apple.quicktime.creationdate'))
        data = atom(b'data', struct.pack('>II', 1, 0) + apple_date.encode())
        items = atom(b'ilst', atom(b'\x00\x00\x00\x01', data))
        content += atom(b'meta', handler + keys + items)
    # ftyp allows even an empty moov to be recognized as a QuickTime container.
    return atom(b'ftyp', b'qt  ' + bytes(4) + b'qt  ') + atom(b'moov', content)


class VideoMetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def read(self, contents):
        path = self.root / 'clip.MOV'
        path.write_bytes(contents)
        return read_mov_date(path)

    def test_prefers_apple_recording_date_and_retains_timezone(self):
        date = self.read(movie(datetime(2026, 11, 1, 22, 30), '2026-11-02T00:30:00+0200'))
        self.assertEqual(date.day, 2)
        self.assertEqual(date.utcoffset().total_seconds(), 7200)

    def test_movie_header_versions(self):
        for version, date in [(0, datetime(2026, 11, 2)), (1, datetime(2050, 11, 2))]:
            with self.subTest(version=version):
                self.assertEqual(self.read(movie(date, version=version)), date)

    def test_missing_date(self):
        self.assertIsNone(self.read(movie()))
        self.assertIsNone(self.read(movie(datetime(1904, 1, 1))))

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            self.read(movie(apple_date='invalid'))

    def test_invalid_file(self):
        with self.assertRaises(ValueError):
            self.read(b'not a movie')

    def test_metadata_dispatch_copy_move_and_repeat(self):
        for move, extension in [(False, '.mov'), (True, '.MOV')]:
            with self.subTest(move=move):
                source = self.root / str(move)
                source.mkdir()
                destination = self.root / f'out-{move}'
                video = source / f'clip{extension}'
                contents = movie(datetime(2026, 11, 2))
                video.write_bytes(contents)
                plan = import_images(source, destination, move=move)
                again = import_images(source, destination, move=move)
                self.assertEqual(len(plan.files), 1)
                self.assertEqual(again.files, [])
                self.assertEqual(video.exists(), not move)
                self.assertEqual((destination / '2026/11/02' / video.name).read_bytes(), contents)

    def test_undated_import(self):
        source = self.root / 'source'
        source.mkdir()
        (source / 'clip.mov').write_bytes(movie())
        destination = self.root / 'output'
        import_images(source, destination)
        self.assertTrue((destination / '_undated/clip.mov').is_file())
