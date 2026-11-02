"""Read MOV dates using Hachoir's pure Python QuickTime parser."""

from datetime import datetime
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys

from hachoir.field import FieldError
from hachoir.stream import InputStreamError
from hachoir.parser import createParser


def _atoms(container):
    """Visit metadata containers without parsing video samples or media payloads."""
    containers = {'moov': 'movie', 'trak': 'track', 'mdia': 'media', 'udta': 'udta'}
    for atom in container:
        tag = atom['tag'].value
        yield tag, atom
        if tag in containers and containers[tag] in atom:
            yield from _atoms(atom[containers[tag]])


def _apple_date(meta) -> datetime | None:
    atoms = {tag: atom for tag, atom in _atoms(meta['tags'])}
    if 'keys' not in atoms or 'ilst' not in atoms:
        return None
    keys = atoms['keys']['keys']
    index = None
    for number, key in enumerate(keys.array('key'), start=1):
        if key['tag'].value == 'mdta' and key['data'].value == b'com.apple.quicktime.creationdate':
            index = number
            break
    if index is None:
        return None
    for item in atoms['ilst']['ilst'].array('item'):
        if item['index'].value == index:
            # QuickTime data payload: type (4 bytes), locale (4 bytes), UTF-8 value.
            payload = item['value/data'].value
            value = payload[8:].decode('utf-8').rstrip('\x00')
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
    return None


def read_mov_date(filepath: Path, *, warnings: list[str] | None = None) -> datetime | None:
    # Hachoir writes diagnostics directly to stderr rather than Python logging.
    diagnostics = io.StringIO()
    try:
        with redirect_stderr(diagnostics):
            return _read_mov_date(filepath)
    finally:
        for message in diagnostics.getvalue().splitlines():
            print(f'{filepath}: {message}', file=sys.stderr)
            if warnings is not None and message not in warnings:
                warnings.append(message)


def _read_mov_date(filepath: Path) -> datetime | None:
    parser = createParser(str(filepath))
    if parser is None:
        raise ValueError('Cannot read MOV metadata: invalid or unsupported file')
    try:
        if parser.PARSER_TAGS['id'] != 'mov':
            raise ValueError('Not a QuickTime MOV file')
        fallback = None
        for tag, atom in _atoms(parser):
            if tag == 'meta':
                date = _apple_date(atom['meta'])
                if date is not None:
                    # Keep the date in the recording timezone, including near midnight.
                    return date
            elif tag in {'mvhd', 'mdhd', 'tkhd'} and fallback is None:
                header = {'mvhd': 'movie_hdr', 'mdhd': 'media_hdr', 'tkhd': 'track_hdr'}[tag]
                date = atom[f'{header}/creation_date'].value
                # Zero means no usable timestamp, rather than a recording in 1904.
                if date != datetime(1904, 1, 1):
                    fallback = date
        return fallback
    except (FieldError, InputStreamError, UnicodeError, OverflowError) as error:
        raise ValueError(f'Cannot read MOV metadata: {error}') from error
    finally:
        parser.stream.close()
