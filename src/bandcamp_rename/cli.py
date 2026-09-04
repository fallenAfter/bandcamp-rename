"""Command-line interface for bandcamp-rename."""

from __future__ import annotations

from pathlib import Path

import click

from bandcamp_rename import __version__
from bandcamp_rename.bandcamp import extract_zip, is_bandcamp_zip
from bandcamp_rename.executor import apply_plan
from bandcamp_rename.metadata import read_tracks
from bandcamp_rename.planner import ActionType, build_plan
from bandcamp_rename.plex_rules import check_compliance
from bandcamp_rename.scanner import DEFAULT_AUDIO_EXTENSIONS, scan_directory


def _parse_extensions(value: str | None) -> frozenset[str] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    normalized = []
    for part in parts:
        normalized.append(part if part.startswith(".") else f".{part}")
    return frozenset(normalized)


@click.group()
@click.version_option(__version__, prog_name="bandcamp-rename")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress.")
@click.option(
    "--extensions",
    default=None,
    help="Comma-separated audio extensions (default: flac,mp3,m4a,ogg,wav).",
)
@click.pass_context
def main(ctx: click.Context, verbose: bool, extensions: str | None) -> None:
    """Organize music files into Plex-compatible folder structure."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["extensions"] = _parse_extensions(extensions) or DEFAULT_AUDIO_EXTENSIONS


@main.command()
def version() -> None:
    """Print the installed version."""
    click.echo(__version__)


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.pass_context
def scan(ctx: click.Context, path: Path) -> None:
    """Report files that are not Plex-compliant."""
    extensions = ctx.obj["extensions"]
    verbose = ctx.obj["verbose"]
    result = scan_directory(path, extensions=extensions)
    tracks = read_tracks(result.audio_files)

    issue_count = 0
    compliant = 0
    for track in tracks:
        issues = check_compliance(track, path)
        if not issues:
            compliant += 1
            if verbose:
                click.echo(f"OK {track.path}")
            continue
        issue_count += len(issues)
        for issue in issues:
            click.echo(f"{issue.path}")
            click.echo(f"  [{issue.issue_type.value}] {issue.message}")
            if issue.suggested_path is not None:
                click.echo(f"  -> {issue.suggested_path}")

    click.echo()
    click.echo(
        f"Scanned {len(tracks)} audio files "
        f"({compliant} compliant, {issue_count} issues, "
        f"{len(result.zip_files)} zips)."
    )

    if issue_count:
        raise SystemExit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.pass_context
def unpack(ctx: click.Context, path: Path) -> None:
    """Extract Bandcamp ZIP archives found under PATH."""
    verbose = ctx.obj["verbose"]
    result = scan_directory(path)
    extracted = 0
    for zip_path in result.zip_files:
        if not is_bandcamp_zip(zip_path):
            if verbose:
                click.echo(f"Skipping non-Bandcamp zip: {zip_path}")
            continue
        target = extract_zip(zip_path)
        click.echo(f"Extracted {zip_path.name} -> {target}")
        extracted += 1
    click.echo(f"Extracted {extracted} archive(s).")


@main.command("fix")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Show planned changes without applying them.")
@click.option("--unpack/--no-unpack", default=False, help="Extract Bandcamp ZIPs first.")
@click.option(
    "--backup-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write a JSON audit log of applied changes.",
)
@click.pass_context
def fix_cmd(
    ctx: click.Context,
    path: Path,
    dry_run: bool,
    unpack: bool,
    backup_log: Path | None,
) -> None:
    """Rename/move files in place to match Plex conventions."""
    extensions = ctx.obj["extensions"]
    verbose = ctx.obj["verbose"]

    if unpack:
        scan_result = scan_directory(path)
        for zip_path in scan_result.zip_files:
            if is_bandcamp_zip(zip_path):
                target = extract_zip(zip_path)
                click.echo(f"Extracted {zip_path.name} -> {target}")

    result = scan_directory(path, extensions=extensions)
    tracks = read_tracks(result.audio_files)
    plan = build_plan(tracks, path)

    if plan.has_conflicts:
        for conflict in plan.conflicts:
            click.echo(f"CONFLICT: {conflict}", err=True)
        raise SystemExit(2)

    for action in plan.actions:
        if action.action_type == ActionType.TAG_UPDATE and not verbose:
            continue
        dest = action.destination or action.source
        click.echo(f"{action.action_type.value}: {action.source} -> {dest}")
        if verbose and action.reason:
            click.echo(f"  reason: {action.reason}")

    execution = apply_plan(plan, dry_run=dry_run, backup_log=backup_log)
    if not execution.success:
        click.echo(f"ERROR: {execution.error}", err=True)
        raise SystemExit(1)

    mode = "Would fix" if dry_run else "Fixed"
    file_ops = [
        a
        for a in execution.completed
        if a.action_type in {ActionType.MOVE, ActionType.RENAME}
    ]
    click.echo(
        f"{mode} {len(file_ops)} file(s); "
        f"{len(plan.compliant)} already compliant; "
        f"{len(plan.skipped)} skipped."
    )


if __name__ == "__main__":
    main()
