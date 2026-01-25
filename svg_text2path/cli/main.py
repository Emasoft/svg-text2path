"""Text2Path CLI - Convert SVG text elements to paths."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from svg_text2path import __version__
from svg_text2path.cli.commands.batch import batch
from svg_text2path.cli.commands.compare import compare
from svg_text2path.cli.commands.convert import convert
from svg_text2path.cli.commands.deps import deps
from svg_text2path.cli.commands.fonts import fonts
from svg_text2path.cli.utils.banner import print_banner
from svg_text2path.config import Config

console = Console()
error_console = Console(stderr=True)


class BannerGroup(click.Group):
    """Custom Click group that prints banner before help."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Print banner before help text (unless --quiet)."""
        # Check argv directly since ctx.params not populated when help triggers
        quiet = "-q" in sys.argv or "--quiet" in sys.argv
        if not quiet:
            print_banner(console, force=True)
        super().format_help(ctx, formatter)


@click.group(cls=BannerGroup, invoke_without_command=True)
@click.version_option(__version__, prog_name="text2path")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-error output")
@click.option(
    "--config", "config_path", type=click.Path(exists=True), help="Path to config file"
)
@click.pass_context
def cli(
    ctx: click.Context, verbose: bool, quiet: bool, config_path: str | None
) -> None:
    """Convert SVG text elements to vector path outlines."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet

    # Print banner unless quiet mode or help will be shown (format_help handles help)
    if not quiet and not ctx.resilient_parsing and ctx.invoked_subcommand is not None:
        print_banner(console, force=True)

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

    # Show help if no command given
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Add commands to CLI group
cli.add_command(convert)
cli.add_command(batch)
cli.add_command(fonts)
cli.add_command(compare)
cli.add_command(deps)


def main() -> None:
    """Entry point for the CLI."""
    try:
        cli()
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
