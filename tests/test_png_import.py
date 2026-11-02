from datetime import datetime
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from viewview.core.metadata import ImageMetadataReader
from viewview.core.organization import import_images


def png(dated=True):
    def chunk(kind, payload):
        return (struct.pack('>I', len(payload)) + kind + payload
                + struct.pack('>I', zlib.crc32(kind + payload)))

    data = b'\x89PNG\r\n\x1a\n'
    data += chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    if dated:
        # TIFF IFD0 points to an EXIF IFD containing DateTimeOriginal.
        tiff = b'II' + struct.pack('<HI', 42, 8)
        tiff += struct.pack('<HHHII', 1, 0x8769, 4, 1, 26) + bytes(4)
        tiff += struct.pack('<HHHII', 1, 0x9003, 2, 20, 44) + bytes(4)
        tiff += b'2026:11:02 12:30:00\x00'
        data += chunk(b'eXIf', tiff)
    data += chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00'))
    return data + chunk(b'IEND', b'')


class PngImportTests(unittest.TestCase):
    def test_png_metadata_and_import(self):
        for dated in (False, True):
            for move, extension in ((False, '.png'), (True, '.PNG')):
                with self.subTest(dated=dated, move=move), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source = root / 'source'
                    (source / 'nested').mkdir(parents=True)
                    image = source / 'nested' / f'picture{extension}'
                    contents = png(dated)
                    image.write_bytes(contents)
                    expected = datetime(2026, 11, 2, 12, 30) if dated else None
                    self.assertEqual(ImageMetadataReader.get_info(image).date, expected)
                    destination = root / 'destination'
                    plan = import_images(source, destination, move=move)
                    self.assertEqual(len(plan.files), 1)
                    self.assertEqual(plan.invalid_files, [])
                    folder = '2026/11/02' if dated else '_undated'
                    self.assertEqual((destination / folder / image.name).read_bytes(), contents)
                    self.assertEqual(image.exists(), not move)
                    self.assertEqual(import_images(source, destination).files, [])
