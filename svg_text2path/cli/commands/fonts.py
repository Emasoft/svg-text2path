"""Fonts command - font management utilities."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from svg_text2path.fonts import FontCache

console = Console()


@click.group()
def fonts() -> None:
    """Font management commands."""
    pass


@fonts.command("list")
@click.option("--family", help="Filter by font family name")
@click.option("--style", help="Filter by style (normal, italic)")
@click.option("--weight", type=int, help="Filter by weight (400, 700, etc)")
def list_fonts(family: str | None, style: str | None, weight: int | None) -> None:
    """List available fonts."""
    cache = FontCache()

    with console.status("[bold green]Loading fonts..."):
        cache.prewarm()

    table = Table(title="Available Fonts")
    table.add_column("Family", style="cyan")
    table.add_column("Style", style="green")
    table.add_column("Weight", style="yellow")
    table.add_column("Path", style="dim")

    count = 0
    # _fc_cache is list of (path, font_index, families, styles, postscript, weight)
    for path, _font_index, families, styles, _postscript, font_weight in (
        cache._fc_cache or []
    ):
        font_family = families[0] if families else "Unknown"
        font_style = styles[0] if styles else "normal"
        font_path = str(path)

        # Apply filters
        if family and family.lower() not in font_family.lower():
            continue
        if style and style.lower() != font_style.lower():
            continue
        if weight and weight != font_weight:
            continue

        table.add_row(
            font_family,
            font_style,
            str(font_weight),
            font_path[:50] + "..." if len(font_path) > 50 else font_path,
        )
        count += 1

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {count} fonts")


@fonts.command("cache")
@click.option("--refresh", is_flag=True, help="Force cache refresh")
@click.option("--clear", is_flag=True, help="Clear the cache")
def manage_cache(refresh: bool, clear: bool) -> None:
    """Manage font cache."""
    cache = FontCache()
    cache_path = cache._cache_path()

    if clear:
        if cache_path.exists():
            cache_path.unlink()
            console.print("[green]Cache cleared[/green]")
        else:
            console.print("[yellow]No cache to clear[/yellow]")
        return

    if refresh:
        # Delete existing cache and rebuild
        if cache_path.exists():
            cache_path.unlink()
        with console.status("[bold green]Refreshing cache..."):
            count = cache.prewarm()
        console.print(f"[green]Cache refreshed:[/green] {count} fonts indexed")
        return

    # Show cache info
    if cache_path.exists():
        size = cache_path.stat().st_size
        console.print(f"[bold]Cache location:[/bold] {cache_path}")
        console.print(f"[bold]Cache size:[/bold] {size / 1024:.1f} KB")
    else:
        console.print("[yellow]No cache file exists[/yellow]")


@fonts.command("find")
@click.argument("name")
def find_font(name: str) -> None:
    """Find a specific font by name."""
    cache = FontCache()

    with console.status(f"[bold green]Searching for '{name}'..."):
        cache.prewarm()
        try:
            font_path, font_data, face_idx = cache.get_font(name)
            console.print(f"[green]Found:[/green] {font_path}")
            console.print(f"[dim]Face index:[/dim] {face_idx}")
        except Exception as e:
            console.print(f"[red]Not found:[/red] {e}")
            raise SystemExit(1) from e


@fonts.command("report")
@click.argument("svg_file", type=click.Path(exists=True, path_type=Path))
def font_report(svg_file: Path) -> None:
    """Report fonts used in an SVG file."""
    from svg_text2path.svg.parser import find_text_elements, parse_svg

    tree = parse_svg(svg_file)
    root = tree.getroot()
    if root is None:
        console.print("[red]Error: Could not parse SVG file[/red]")
        raise SystemExit(1)
    text_elements = find_text_elements(root)

    fonts_used: dict[tuple[str, str, str], list[str]] = {}
    for elem in text_elements:
        font_family = elem.get("font-family", "sans-serif")
        font_weight = elem.get("font-weight", "400")
        font_style = elem.get("font-style", "normal")

        key = (font_family, font_weight, font_style)
        if key not in fonts_used:
            fonts_used[key] = []
        fonts_used[key].append(elem.get("id", "unnamed"))

    table = Table(title=f"Fonts in {svg_file.name}")
    table.add_column("Family", style="cyan")
    table.add_column("Weight", style="yellow")
    table.add_column("Style", style="green")
    table.add_column("Elements", style="dim")

    for (family, weight, style), elements in sorted(fonts_used.items()):
        table.add_row(family, weight, style, f"{len(elements)} elements")

    console.print(table)
