from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
import shutil
import filecmp

from .metadata import HANDLED_FORMATS, ImageMetadataReader


@dataclass(frozen=True)
class InvalidFile:
    path: Path
    reason: str


@dataclass(frozen=True)
class PlannedFile:
    source: Path
    destination: Path


@dataclass(frozen=True)
class FileWarning:
    path: Path
    message: str


@dataclass(frozen=True)
class OrganizationPlan:
    files: list[PlannedFile]
    invalid_files: list[InvalidFile]
    skipped_files: list[Path] = field(default_factory=list)
    identical_files: list[PlannedFile] = field(default_factory=list)
    warnings: list[FileWarning] = field(default_factory=list)


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
    planned_destinations: dict[Path, Path] = {}
    skipped_files: list[Path] = []
    identical_files: list[PlannedFile] = []
    warnings: list[FileWarning] = []

    for image in images:
        try:
            info = ImageMetadataReader.get_info(image)
        except (OSError, ValueError) as error:
            reason = error.strerror if isinstance(error, OSError) and error.strerror else str(error)
            invalid_files.append(InvalidFile(image, reason))
            continue

        warnings.extend(FileWarning(image, message) for message in info.warnings)

        if info.date is not None:
            target_folder = destination / info.date.strftime('%Y/%m/%d')
        else:
            target_folder = destination / undated_folder

        target = target_folder / image.name

        suffix = 0
        while target in planned_destinations or target.exists() or target.is_symlink():
            existing = planned_destinations.get(target, target)
            if existing.is_file() and filecmp.cmp(image, existing, shallow=False):
                skipped_files.append(image)
                identical_files.append(PlannedFile(image, target))
                break
            suffix += 1
            target = target_folder / f'{image.stem}_{suffix}{image.suffix}'
        else:
            planned_destinations[target] = image
            planned_files.append(PlannedFile(image, target))

    return OrganizationPlan(planned_files, invalid_files, skipped_files, identical_files, warnings)


def apply_plan(plan: OrganizationPlan, move: bool = False) -> None:
    """Apply a previously generated plan by copying or moving files."""
    for planned_file in plan.files:
        planned_file.destination.parent.mkdir(parents=True, exist_ok=True)

        # Exclusive creation protects both copy and move from overwriting files.
        with planned_file.source.open('rb') as source:
            with planned_file.destination.open('xb') as destination:
                shutil.copyfileobj(source, destination)
        shutil.copystat(planned_file.source, planned_file.destination)
        if move:
            # Remove the original only after the copy and metadata transfer succeed.
            planned_file.source.unlink()


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


def import_images(source: Path, destination: Path, *, move: bool = False) -> OrganizationPlan:
    """Recursively copy or move images into date folders; skip identical files."""
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_dir():
        raise ValueError(f'Source is not a directory: {source}')
    if destination == source or source in destination.parents:
        raise ValueError('Destination must be outside the source directory')
    if destination.exists() and not destination.is_dir():
        raise ValueError(f'Destination is not a directory: {destination}')
    return organize_images(list_images(source, HANDLED_FORMATS), destination, move=move, apply=True)
