"""Command-line endpoints; image organization lives in core.organization."""

import argparse
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='viewview')
    commands = parser.add_subparsers(dest='command')
    importer = commands.add_parser(
        'import', help='Recursively copy or move images and MOV videos into YYYY/MM/DD folders',
        description='Import images and MOV videos into folders by recording date.',
    )
    importer.add_argument('source', type=Path)
    importer.add_argument('destination', type=Path)
    importer.add_argument('--move', action='store_true', help='Move files instead of copying them')
    importer.add_argument(
        '--dry-run', action='store_true',
        help='Check the import without changing source or destination; save the report in the system temporary directory',
    )
    args = parser.parse_args(argv)

    if args.command is None:
        from .gui import main as gui_main

        return gui_main()

    from .core.organization import import_images
    from .core.reporting import write_import_report

    try:
        plan = import_images(args.source, args.destination, move=args.move, dry_run=args.dry_run)
        report = write_import_report(plan, args.destination, move=args.move, dry_run=args.dry_run)
    except (OSError, ValueError) as error:
        print(f'Import failed: {error}', file=sys.stderr)
        return 1

    for invalid in plan.invalid_files:
        print(f'Skipped {invalid.path}: {invalid.reason}', file=sys.stderr)
    action = 'Moved' if args.move else 'Copied'
    print(f'{action} {len(plan.files)}; identical {len(plan.skipped_files)}; invalid {len(plan.invalid_files)}')
    print(f'Report: {report}')
    return 1 if plan.invalid_files else 0
