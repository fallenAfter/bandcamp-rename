"""Command-line interface for bandcamp-rename."""

from __future__ import annotations

import click

from bandcamp_rename import __version__


@click.group()
@click.version_option(__version__, prog_name="bandcamp-rename")
def main() -> None:
    """Organize music files into Plex-compatible folder structure."""


@main.command()
def version() -> None:
    """Print the installed version."""
    click.echo(__version__)


if __name__ == "__main__":
    main()
