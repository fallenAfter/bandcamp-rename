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

## License

MIT
