# Viewview

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
