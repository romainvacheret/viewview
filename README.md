# Viewview

The GUI displays JPEG (`.jpg`, `.jpeg`), PNG, and HEIC/HEIF pictures, including
uppercase extensions and pictures in subdirectories. HEIC/HEIF decoding uses
`pillow-heif` (libheif), included in the Nix shell and pip requirements.
The left panel shows a folder tree: single-click a folder to select it and update
the grid; double-click its name to expand or collapse it in either viewer subtab.
Disclosure arrows expand or collapse with a single click. Click a picture to
display it. Full-path tooltips remain
available for folders and pictures.
Use **Open folder…** above the tree to switch libraries without restarting.
The picker starts in the current library; cancelling keeps the current selection.
If `catalogue.sqlite3` is missing, a dialog asks whether to create it. Declining
keeps the current library open. Accepting copies metadata from an existing
`viewview.sqlite3`, leaving that original database untouched.
Wait for any active import or preview to finish before switching libraries.
The app remembers the last successfully opened library using Qt's platform
settings. On startup it reopens that folder if the folder and `catalogue.sqlite3`
still exist; otherwise it shows the folder picker. Cancelling a folder change
or declining catalogue creation leaves the saved library unchanged.

Inside **Viewer**, the center has **Single picture** and **Grid** tabs sharing
the same side panels. The grid follows the folder clicked in the left tree and
includes all pictures in its subfolders, in tree order even when those folders
are collapsed. Scroll vertically to see more previews. Single-click a thumbnail
to select it and edit its rating or deletion mark; double-click to open it in
Single picture. In Grid, **X** toggles the deletion mark and advances within that
grid's pictures. Previews load in the background with a bounded memory cache.

The filter bar above the picture tabs filters both the folder tree and grid by
one library tag, an exact rating (including Unrated) or minimum rating, and
deletion status. Conditions combine: a picture must match every selected filter.
Ratings use the saved app rating when present, otherwise the embedded image
rating. **Reset** restores all pictures; opening another library resets filters.
The count shows matching pictures within the selected folder and its subfolders.
Left/Right, X, and rating shortcuts follow the filtered picture order. Editing
tags, ratings, or deletion marks updates results immediately; if the current
picture stops matching, selection moves to the next matching picture, or the
first remaining match when there is no later one. No matches clears the picture
and shows an empty-results message. Filters do not change files or metadata.

In either viewer subtab, **Left/Right** selects the previous/next picture, stopping
at the first or last picture. **1–5** saves that rating and advances to the next
picture; **0** clears the rating and also advances. Pressing the current rating's
number keeps that rating. Navigation
follows tree order in Single picture and the selected folder's pictures in Grid.
Rating shortcuts stay on the current picture if saving fails. These shortcuts
and **X** are inactive while typing in a text field or using tag suggestions,
and on the Import tab.

In the Viewer tab, the right panel's **To be deleted** checkbox saves a review
mark without deleting the file. Press **X** to toggle the current picture's mark and
select the next picture; on the last picture, it stays selected. Uncheck the box
to remove a mark. Marks reload when selecting pictures after reopening a library
and are stored with tags in the library's `catalogue.sqlite3` database. Image
paths are relative to the library root, so moving the whole library preserves
its metadata.

The right sidebar has two sections: **Image info** shows metadata from the image
file, while **App info** contains its library rating, deletion mark, and tags.
To add a tag, type its full name (spaces are allowed) and press **Enter**. Each
assigned tag appears as a chip; click its **×** to remove it from this picture.
Other pictures keep their tags, and the tag remains in the library vocabulary.
Existing tags are suggested as you type: press **Tab** to complete and add the
highlighted suggestion, or use the arrow keys to choose another suggestion first.
Suggestions belong to the current library. The **X** deletion shortcut is inactive
while editing text, so tag names containing that letter can be typed normally.

The right panel's **Rating** control has five clickable stars. Click the fourth
star for a rating of 4, another star to change it, or the current rating's star
again to clear it. Selected stars are white; unselected stars are transparent
with dark outlines. Ratings are saved in the same database. Existing EXIF ratings are shown
until a library rating is saved. Saved ratings take precedence, including an
explicit Unrated value, and changing a rating leaves the image file untouched.
Older library databases upgrade automatically; dry runs leave them unchanged.

Existing `tags.json` and `review.json` files are migrated automatically on first
metadata access. Both are validated and migrated in one transaction; the
original JSON files remain untouched as backups. Once the database exists,
changes use SQLite and those backups are no longer read. Import previews and
CLI dry runs validate legacy data without creating a database or migrating it.
SQLite is included through Python; users do not need to install a database
server or the `sqlite3` command-line tool.

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
PNG, HEIC encoding/decoding, SQLite tag/review persistence, and background grid
previews. The macOS build also rejects Mach-O dependency
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
`catalogue.sqlite3` at the library root. Paths are relative and associations are
deduplicated. Identical files
already in the library receive the tag too; invalid media are excluded. Tag names
are case-sensitive and cannot be blank. Other tags are preserved. Dry runs validate
the existing database without updating it. SQLite transactions coordinate metadata
writes from multiple app instances. File imports into the same library should
still run one at a time: filesystem copying/moving is separate from the database
transaction. Import reports remain separate JSON diagnostic files.
