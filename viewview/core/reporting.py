"""Persist import results independently of the command-line endpoint."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from .organization import OrganizationPlan


def write_import_report(plan: OrganizationPlan, destination: Path, *, move: bool) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc)
    report = {
        'created_at': created_at.isoformat(),
        'operation': 'move' if move else 'copy',
        'identical_files': [
            {'source': str(file.source.resolve()), 'destination': str(file.destination.resolve())}
            for file in plan.identical_files
        ],
        'invalid_files': [
            {'path': str(file.path.resolve()), 'reason': file.reason}
            for file in plan.invalid_files
        ],
        'warning': [
            {'path': str(warning.path.resolve()), 'message': warning.message}
            for warning in plan.warnings
        ],
    }
    # Keep reports from previous runs and never overwrite an existing file.
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8',
        prefix=f'import-report-{created_at:%Y%m%dT%H%M%S.%fZ}-', suffix='.json',
        dir=destination, delete=False,
    ) as output:
        json.dump(report, output, indent=2, ensure_ascii=False)
        output.write('\n')
        return Path(output.name).resolve()
