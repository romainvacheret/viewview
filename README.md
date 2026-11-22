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
make run
```

This runs `nix develop path:. --command python -m viewview`. Use `make shell` to
enter the environment, or `make run ARGS="--help"` to pass CLI arguments.
The shell uses Python packages from the nixpkgs revision pinned in `flake.lock`;
their versions may differ from the pip pins in `requirements.txt`.

## Build an application

Build on the target operating system using the same pinned Nix dependencies as
the development shell:

```sh
make build
```

This runs `nix build path:.#bundle`. `make dist` also copies the AppImage into
`dist/Viewview.AppImage` on Linux, or creates `dist/Viewview-macos-arm64.zip` on
macOS. Use `make test` to run the tests and `make help` to list commands.

On **Linux**, `result` points to a self-contained AppImage. Copy it out of the
Nix store to share it:

```sh
mkdir -p dist
cp -L result dist/Viewview.AppImage
chmod +x dist/Viewview.AppImage
./dist/Viewview.AppImage
```

The AppImage includes Python, Qt, image codecs, and fallback fonts. Its launcher
requires unprivileged Linux user namespaces. If FUSE is unavailable, run it with
`APPIMAGE_EXTRACT_AND_RUN=1 ./dist/Viewview.AppImage`. Extraction avoids the FUSE
requirement; user namespaces are still required.

On an **Apple Silicon Mac**, the same build command produces
`result/Viewview.app`. Copy it to Applications or create a ZIP that preserves the
app's internal symlinks:

```sh
ditto result/Viewview.app /Applications/Viewview.app
ditto -c -k --sequesterRsrc --keepParent result/Viewview.app Viewview-macos-arm64.zip
```

The macOS bundle is produced by PyInstaller and includes its Python runtime,
Qt libraries/plugins, image codecs, and stylesheet. It is ad-hoc signed. Public
distribution with Developer ID signing and notarization requires a separate
release-signing step and Apple credentials. Intel Macs are not targeted.

The Linux artifact can be selected explicitly with `.#appimage`, and the macOS
artifact with `.#macos-app`. `nix build path:.#viewview` builds a regular Nix
package; that output requires its Nix store dependencies and is not the portable
distribution. `nix run path:.#viewview` runs it without entering a development shell.

The portable executables also support a noninteractive packaging check:

```sh
# Linux, including machines without FUSE:
APPIMAGE_EXTRACT_AND_RUN=1 ./dist/Viewview.AppImage --smoke-test
# macOS:
result/Viewview.app/Contents/MacOS/Viewview --smoke-test
```

The check starts Qt offscreen, loads the bundled stylesheet, and exercises JPEG,
PNG, and HEIC encoding/decoding. The macOS build also rejects Mach-O dependency
paths and RPATHs that still point into `/nix/store`.

[Build portable applications](.github/workflows/build.yml) runs tests and native
builds on Linux x86_64 and Apple Silicon macOS, then uploads the AppImage or ZIP
as workflow artifacts. It can also be started manually from GitHub Actions.

## Import media

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
