# Viewview

The GUI displays JPEG (`.jpg`, `.jpeg`), PNG, and HEIC/HEIF pictures, including
uppercase extensions and pictures in subdirectories. HEIC/HEIF decoding uses
`pillow-heif` (libheif), included in the Nix shell and pip requirements.
The left panel shows a folder tree: click a folder or its arrow to expand or
collapse it, and click a picture to display it. Full-path tooltips remain
available for folders and pictures.

In the Viewer tab, the right panel's **To be deleted** checkbox saves a review
mark without deleting the file. Press **X** to toggle the current picture's mark and
select the next picture; on the last picture, it stays selected. Uncheck the box
to remove a mark. Marks reload when selecting pictures after reopening a library
and are stored as relative paths in `review.json` beside `tags.json`.

Run the GUI with its dependencies provided by Nix:

```sh
nix develop path:. --command python -m viewview
```

Or enter the environment with `nix develop path:.` and run `python -m viewview`.
The shell uses Python packages from the nixpkgs revision pinned in `flake.lock`;
their versions may differ from the pip pins in `requirements.txt`.

The GUI has **Viewer** and **Import** tabs. The folder opened in the viewer is
the destination library root. In Import, choose a source folder, select Copy or
Move, and optionally enter comma-separated tags, such as `Summer holiday, family`.
Spaces around commas are removed; spaces inside a tag are preserved.

The automatic preview checks the same files and permissions as the CLI dry run.
Its folder tree shows existing media, additions, resulting totals, and folders
to create; year and month counts include their descendants. Duplicate files,
invalid media, and warnings appear below the tree. Only **Import** copies or
moves files. Results are rechecked when importing; a JSON report is saved in the
library, and the viewer and preview refresh afterward. Identical files are
skipped, including in Move mode, but still receive the requested tags.

Import images and MOV videos into folders by recording date:

```sh
python -m viewview import /path/to/source /path/to/library --tag "Summer holiday"
```

Use `--move` to move files or `--dry-run` to preview without changing either
folder. Tags are optional. Each tagged import merges its destination paths into
`tags.json` at the library root:

```json
{
  "Summer holiday": ["2026/07/12/photo.JPG", "2026/07/12/video.MOV"]
}
```

Paths are relative to the library root, sorted and deduplicated. Identical files
already in the library receive the tag too; invalid media are excluded. Tag names
are case-sensitive and cannot be blank. Other tags are preserved. Dry runs validate
the existing index without updating it. The index is replaced atomically; run
imports into the same library one at a time to avoid concurrent updates losing tags.
