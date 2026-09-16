from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import shutil

from .metadata import ImageMetadataReader


@dataclass(frozen=True)
class InvalidFile:
    path: Path
    reason: str


@dataclass(frozen=True)
class PlannedFile:
    source: Path
    destination: Path


@dataclass(frozen=True)
class OrganizationPlan:
    files: list[PlannedFile]
    invalid_files: list[InvalidFile]


def list_images(folder: Path, extensions: Iterable[str]) -> list[Path]:
    """List matching files recursively without changing anything."""
    normalized_extensions = {
        extension.lower()
        if extension.startswith('.')
        else f'.{extension.lower()}'
        for extension in extensions
    }

    return sorted(
        file
        for file in folder.rglob('*')
        if file.is_file() and file.suffix.lower() in normalized_extensions
    )


def plan_organization(
    images: Iterable[Path],
    destination: Path,
    undated_folder: str = '_undated',
) -> OrganizationPlan:
    """Build an organization plan without copying or moving files."""
    planned_files: list[PlannedFile] = []
    invalid_files: list[InvalidFile] = []
    planned_destinations: set[Path] = set()

    for image in images:
        try:
            info = ImageMetadataReader.get_info(image)
        except (OSError, ValueError) as error:
            invalid_files.append(InvalidFile(image, str(error)))
            continue

        if info.date is not None:
            target_folder = destination / info.date.strftime('%Y/%m/%d')
        else:
            target_folder = destination / undated_folder

        target = target_folder / image.name

        if target in planned_destinations:
            invalid_files.append(
                InvalidFile(image, f'duplicate destination: {target}')
            )
            continue

        if target.exists():
            invalid_files.append(
                InvalidFile(image, f'destination already exists: {target}')
            )
            continue

        planned_destinations.add(target)
        planned_files.append(PlannedFile(image, target))

    return OrganizationPlan(planned_files, invalid_files)


def apply_plan(plan: OrganizationPlan, move: bool = False) -> None:
    """Apply a previously generated plan by copying or moving files."""
    for planned_file in plan.files:
        planned_file.destination.parent.mkdir(parents=True, exist_ok=True)

        if move:
            shutil.move(planned_file.source, planned_file.destination)
        else:
            shutil.copy2(planned_file.source, planned_file.destination)


def organize_images(
    images: Iterable[Path],
    destination: Path,
    *,
    move: bool = False,
    apply: bool = False,
    undated_folder: str = '_undated',
) -> OrganizationPlan:
    """Plan image organization and optionally apply it."""
    plan = plan_organization(
        images,
        destination,
        undated_folder=undated_folder,
    )

    if apply:
        apply_plan(plan, move=move)

    return plan
