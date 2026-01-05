"""Convert command - single file text-to-path conversion."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from svg_text2path import Text2PathConverter, ConversionResult
from svg_text2path.config import Config

console = Console()


@click.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.argument("output_file", type=click.Path(path_type=Path), required=False)
@click.option("-o", "--output", "output_path", type=click.Path(path_type=Path), help="Output file path")
@click.option("--output-dir", type=click.Path(path_type=Path), help="Output directory")
@click.option("-p", "--precision", type=int, default=6, help="Path coordinate precision")
@click.option("--preserve-styles", is_flag=True, help="Keep style metadata on paths")
@click.option("--suffix", default="_text2path", help="Output filename suffix")
@click.option("--system-fonts-only", is_flag=True, help="Only use system fonts")
@click.option("--font-dir", type=click.Path(exists=True, path_type=Path), multiple=True, help="Additional font directories")
@click.option("--no-remote-fonts", is_flag=True, help="Disable remote font fetching")
@click.option("--print-fonts", is_flag=True, help="Print fonts used in SVG")
@click.pass_context
def convert(
    ctx: click.Context,
    input_file: Path,
    output_file: Optional[Path],
    output_path: Optional[Path],
    output_dir: Optional[Path],
    precision: int,
    preserve_styles: bool,
    suffix: str,
    system_fonts_only: bool,
    font_dir: tuple[Path, ...],
    no_remote_fonts: bool,
    print_fonts: bool,
) -> None:
    """Convert SVG text elements to paths.

    INPUT_FILE: Path to SVG file to convert.
    OUTPUT_FILE: Optional output path (defaults to INPUT_FILE with suffix).
    """
    config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Determine output path
    if output_path:
        out = output_path
    elif output_file:
        out = output_file
    elif output_dir:
        out = output_dir / f"{input_file.stem}{suffix}.svg"
    else:
        out = input_file.parent / f"{input_file.stem}{suffix}.svg"

    # Update config with CLI options
    if system_fonts_only:
        config.fonts.system_only = True
    if font_dir:
        config.fonts.custom_dirs = list(font_dir)
    if no_remote_fonts:
        config.fonts.remote = False

    # Create converter
    converter = Text2PathConverter(
        precision=precision,
        preserve_styles=preserve_styles,
        log_level=log_level,
        config=config,
    )

    if print_fonts:
        # Just analyze fonts without converting
        from svg_text2path.svg.parser import parse_svg, find_text_elements
        tree = parse_svg(input_file)
        text_elements = find_text_elements(tree.getroot())
        fonts_used = set()
        for elem in text_elements:
            font_family = elem.get("font-family", "sans-serif")
            fonts_used.add(font_family)
        console.print("[bold]Fonts used:[/bold]")
        for font in sorted(fonts_used):
            console.print(f"  - {font}")
        return

    # Perform conversion
    with console.status("[bold green]Converting..."):
        result = converter.convert_file(input_file, out)

    if result.success:
        console.print(f"[green]Success:[/green] Converted {result.text_count} text elements to {result.path_count} paths")
        console.print(f"[blue]Output:[/blue] {result.output}")
    else:
        console.print(f"[red]Failed:[/red] {result.errors}")
        raise SystemExit(1)

    if result.warnings:
        for warning in result.warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")
