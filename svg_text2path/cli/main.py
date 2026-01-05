"""Text2Path CLI - Convert SVG text elements to paths."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from svg_text2path import __version__
from svg_text2path.config import Config

console = Console()
error_console = Console(stderr=True)


@click.group()
@click.version_option(__version__, prog_name="text2path")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-error output")
@click.option("--config", "config_path", type=click.Path(exists=True), help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool, config_path: Optional[str]) -> None:
    """Convert SVG text elements to vector path outlines."""
    ctx.ensure_object(dict)

    # Set up logging level
    if quiet:
        ctx.obj["log_level"] = "ERROR"
    elif verbose:
        ctx.obj["log_level"] = "DEBUG"
    else:
        ctx.obj["log_level"] = "WARNING"

    # Load config (from file if provided, otherwise auto-discover)
    if config_path:
        ctx.obj["config"] = Config.load(Path(config_path))
    else:
        ctx.obj["config"] = Config.load()


# Import and add commands
from svg_text2path.cli.commands.convert import convert
from svg_text2path.cli.commands.batch import batch
from svg_text2path.cli.commands.fonts import fonts
from svg_text2path.cli.commands.compare import compare

cli.add_command(convert)
cli.add_command(batch)
cli.add_command(fonts)
cli.add_command(compare)


def main() -> None:
    """Entry point for the CLI."""
    try:
        cli()
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
