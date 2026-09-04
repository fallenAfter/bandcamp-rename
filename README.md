# bandcamp-rename

Organize Bandcamp downloads and CD rips into a Plex-compatible music library structure.

Scans a target folder recursively, reads embedded audio tags (with Bandcamp filename/folder fallback), and renames/moves files in place to match Plex conventions:

```text
Music/
  AlbumArtist/
    Album Title/
      01 - Track Title.flac
```

## Status

Early development. Phase 1 provides the CLI scaffold; `scan`, `fix`, and `unpack` commands are coming in later phases.

## Requirements

- Python 3.9+ (3.11+ recommended)
- macOS (development) or Ubuntu (production Plex server)

## Install

### macOS (development)

```bash
git clone https://github.com/<your-user>/bandcamp-rename.git
cd bandcamp-rename
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Ubuntu (Plex server)

```bash
pipx install git+https://github.com/<your-user>/bandcamp-rename@v0.1.0
```

Or install from a local checkout:

```bash
git clone https://github.com/<your-user>/bandcamp-rename.git
cd bandcamp-rename
pip install .
```

## Usage

```bash
# Show help
bandcamp-rename --help

# Show version
bandcamp-rename --version
```

## Configuration

Copy [`config.example.yaml`](config.example.yaml) to `~/.config/bandcamp-rename/config.yaml` and adjust paths and options. Configuration loading will be wired up in a later phase.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

### Manual validation checklist

- [ ] macOS: run `pytest` and `bandcamp-rename fix <copied-album> --dry-run`
- [ ] Drop a Bandcamp ZIP in an incoming folder and run `fix --unpack --dry-run`
- [ ] Run `fix --limit 5` on a subset before touching a full library
- [ ] Ubuntu: install from a git tag, `scan` the Plex music root, then fix one album
- [ ] Trigger a Plex library scan and confirm the album appears correctly

## License

MIT
