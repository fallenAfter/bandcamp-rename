# bandcamp-rename

Organize Bandcamp downloads and CD rips into a Plex-compatible music library structure.

Scans a target folder recursively, reads embedded audio tags (with Bandcamp filename/folder fallback), and renames/moves files in place to match Plex conventions:

```text
Music/
  AlbumArtist/
    Album Title/
      01 - Track Title.flac
```

## Features

- Recursively scan a music library (or an incoming folder)
- Unpack Bandcamp ZIP downloads
- Parse metadata from tags, Bandcamp filenames, and folder names
- Plan and apply in-place renames/moves with dry-run support
- Move cover art, clean empty folders, and handle case-only renames
- Configure naming templates via YAML

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.9+ (3.11+ recommended)
- macOS (development) or Ubuntu (production Plex server)

## Install

### macOS (development)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # if you don't have uv
git clone https://github.com/fallenAfter/bandcamp-rename.git
cd bandcamp-rename
uv sync --extra dev
```

### Ubuntu (Plex server)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # if you don't have uv
git clone https://github.com/fallenAfter/bandcamp-rename.git
cd bandcamp-rename
git checkout v0.1.0   # pin to a release tag when available
uv sync
```

Or run without a persistent install via:

```bash
uvx --from git+https://github.com/fallenAfter/bandcamp-rename@v0.1.0 bandcamp-rename --help
```

## Quick start

```bash
# Show help / version
uv run bandcamp-rename --help
uv run bandcamp-rename --version

# Report problems without changing anything
uv run bandcamp-rename scan /path/to/Music

# Preview fixes
uv run bandcamp-rename fix /path/to/Music --dry-run

# Apply fixes in place
uv run bandcamp-rename fix /path/to/Music

# Unpack Bandcamp ZIPs, then fix
uv run bandcamp-rename fix /path/to/Music/incoming --unpack --dry-run
uv run bandcamp-rename fix /path/to/Music/incoming --unpack
```

## Bandcamp workflow

1. Download an album from Bandcamp (ZIP or extracted folder).
2. Drop it into an incoming folder on your Plex host, for example `Music/incoming/`.
3. Preview:

   ```bash
   uv run bandcamp-rename fix Music/incoming --unpack --dry-run
   ```

4. Apply:

   ```bash
   uv run bandcamp-rename fix Music/incoming --unpack
   ```

5. Trigger a Plex library scan and confirm the album appears under the correct artist.

Bandcamp downloads usually look like:

```text
Artist - Album.zip
  Artist - Album/
    Artist - Album - 01 Track One.flac
    Artist - Album - 02 Track Two.flac
    cover.jpg
```

The tool reads tags when present, then falls back to filename/folder parsing.

## Plex naming rules

Plex works best with:

| Piece | Convention |
|-------|------------|
| Folders | `AlbumArtist / Album Title / tracks` |
| Track files | `01 - Track Title.ext` |
| Multi-disc | `205 - Track Title.ext` (disc 2, track 5) |
| Compilations | Album artist folder `Various Artists` |

Embedded `albumartist` should match the artist folder name.

## Configuration

Copy [`config.example.yaml`](config.example.yaml) to `~/.config/bandcamp-rename/config.yaml` (or pass `--config`):

```yaml
root: /mnt/plex/Music
audio_extensions: [.flac, .mp3, .m4a]
compilation_album_artist: "Various Artists"
track_filename_template: "{track:02d} - {title}"
multi_disc_filename_template: "{disc}{track:02d} - {title}"
skip_files: [cover.jpg, folder.jpg, .DS_Store]
update_tags_after_move: true
treat_missing_albumartist_as_artist: true
auto_unpack_zips: false
delete_zip_after_unpack: false
move_cover_art: true
```

CLI flags override config values. If `root` is set, `scan` / `fix` / `unpack` can omit the path argument.

### Config reference

| Option | Purpose |
|--------|---------|
| `root` | Default music library path |
| `audio_extensions` | Extensions treated as audio |
| `compilation_album_artist` | Folder/tag name for compilations |
| `track_filename_template` | Single-disc filename format |
| `multi_disc_filename_template` | Multi-disc filename format |
| `skip_files` | Companion files discovered with albums |
| `update_tags_after_move` | Write tags after rename/move |
| `treat_missing_albumartist_as_artist` | Fall back to track artist |
| `auto_unpack_zips` | Unpack during `fix` by default |
| `delete_zip_after_unpack` | Delete ZIP after successful extract |
| `move_cover_art` | Move `cover.jpg` into album folder |

## Commands

| Command | Description |
|---------|-------------|
| `scan PATH` | Report non-compliant files (exit 1 if issues found) |
| `unpack PATH` | Extract Bandcamp ZIP archives |
| `fix PATH` | Rename/move files to Plex layout |
| `version` | Print package version |

Useful flags:

- `--dry-run` — preview only
- `--unpack` / `--no-unpack` — control ZIP extraction during `fix`
- `--limit N` — process only the first N audio files
- `--backup-log FILE` — write a JSON audit trail
- `--verbose` — show reasons and compliant files
- `--extensions flac,mp3` — override audio extensions
- `--config FILE` — load an alternate config file

## Troubleshooting

- **Nothing moves**: run `scan` first; missing metadata causes skips.
- **Conflicts**: two tracks targeting the same destination are auto-suffixed (`(2)`); hard conflicts still abort.
- **Plex looks wrong after rename**: rescan the library; prefer running during low use.
- **macOS case renames**: the tool uses a two-step rename when only letter case changes.
- **Don't delete ZIPs early**: keep `delete_zip_after_unpack: false` until you trust a run.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
```

CI runs `pytest` and `ruff` on macOS and Ubuntu for Python 3.11 and 3.12 via uv.

### Manual validation checklist

- [ ] macOS: run `uv run pytest` and `uv run bandcamp-rename fix <copied-album> --dry-run`
- [ ] Drop a Bandcamp ZIP in an incoming folder and run `fix --unpack --dry-run`
- [ ] Run `fix --limit 5` on a subset before touching a full library
- [ ] Ubuntu: `uv sync`, `scan` the Plex music root, then fix one album
- [ ] Trigger a Plex library scan and confirm the album appears correctly

## Future ideas

Out of current scope, but possible later:

- `watch` mode for new downloads
- MusicBrainz lookup for untagged rips
- GUI or Plex plugin

## License

MIT
