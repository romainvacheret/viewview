"""Root-level tag index for imported media."""

import json
import os
from pathlib import Path
import tempfile


def read_tags(destination: Path) -> dict[str, list[str]]:
    path = destination / 'tags.json'
    try:
        with path.open(encoding='utf-8') as source:
            tags = json.load(source)
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError) as error:
        raise ValueError(f'Invalid tag index {path}: {error}') from error
    if not isinstance(tags, dict) or any(
        not isinstance(tag, str) or not isinstance(paths, list)
        or any(not isinstance(value, str) for value in paths)
        for tag, paths in tags.items()
    ):
        raise ValueError(f'Invalid tag index {path}: expected tag names mapped to lists of paths')
    return tags


def write_tags(destination: Path, tags: dict[str, list[str]]) -> None:
    """Replace the index atomically so interrupted writes cannot truncate it."""
    destination.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=destination,
            prefix='.tags-', suffix='.tmp', delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump(tags, output, indent=2, ensure_ascii=False, sort_keys=True)
            output.write('\n')
        os.replace(temporary, destination / 'tags.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
