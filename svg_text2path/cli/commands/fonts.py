"""Fonts command - font management utilities."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import click
import defusedxml.ElementTree as ET
from rich.console import Console
from rich.table import Table

from svg_text2path.fonts import FontCache

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

console = Console()


def parse_style(style_str: str | None) -> dict[str, str]:
    """Parse CSS style string into a dictionary.

    Args:
        style_str: CSS style string (e.g., "font-family: Arial; font-weight: bold")

    Returns:
        Dictionary mapping property names to values.
    """
    if not style_str:
        return {}
    out: dict[str, str] = {}
    for part in style_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


# Type alias for font report row data
FontRow = tuple[str, str | None, str | None, str | None, str | None, str, str]


def collect_font_inheritance(
    svg_path: Path,
    cache: FontCache,
    include_variation: bool = False,
    resolve_files: bool = False,
) -> list[FontRow]:
    """Collect font information from all text elements with CSS inheritance.

    Walks the SVG tree and tracks inherited font properties, resolving
    final values for each text element.

    Args:
        svg_path: Path to the SVG file.
        cache: FontCache instance for resolving font files.
        include_variation: Whether to include font-variation-settings.
        resolve_files: Whether to resolve actual font file paths.

    Returns:
        List of tuples: (id, family, weight, style, stretch, variation, resolved_file)
    """
    root = ET.parse(svg_path).getroot()
    keys = [
        "font-family",
        "font-weight",
        "font-style",
        "font-stretch",
        "font-variation-settings",
    ]
    # Default inherited values (CSS initial values)
    inherit: dict[str, str | None] = {
        "font-family": "sans-serif",
        "font-weight": "400",
        "font-style": "normal",
        "font-stretch": "normal",
        "font-variation-settings": None,
    }
    rows: list[FontRow] = []
    auto_id = 0

    def walk(elem: Element, inherited: dict[str, str | None]) -> None:
        """Recursively walk SVG tree collecting font attributes with inheritance."""
        nonlocal auto_id
        # Start with inherited values
        attrs = dict(inherited)
        # Parse inline style attribute
        style_map = parse_style(elem.get("style", ""))
        # Override with explicit attributes or style values
        for k in keys:
            if k in elem.attrib:
                attrs[k] = elem.get(k)
            elif k in style_map:
                attrs[k] = style_map[k]

        # Strip namespace from tag
        tag = elem.tag.split("}")[-1]
        if tag in ("text", "tspan", "textPath"):
            # Get or generate element ID
            tid = elem.get("id")
            if not tid:
                auto_id += 1
                tid = f"{tag}_auto_{auto_id}"

            # Extract font properties
            fam = attrs["font-family"]
            # Normalize family: take first in comma list, strip quotes
            if fam:
                fam = fam.split(",")[0].strip().strip("'\"")
            weight = attrs["font-weight"]
            style = attrs["font-style"]
            stretch = attrs["font-stretch"]
            var_setting = attrs.get("font-variation-settings") or ""
            var = var_setting if include_variation else ""

            # Resolve font file if requested
            resolved = ""
            if resolve_files:
                try:
                    # Convert weight string to int
                    if weight == "bold":
                        w_int = 700
                    elif weight == "normal" or weight is None:
                        w_int = 400
                    else:
                        m = re.search(r"(\d+)", weight or "")
                        w_int = int(m.group(1)) if m else 400

                    res = cache.get_font(
                        fam or "sans-serif",
                        weight=w_int,
                        style=style or "normal",
                        stretch=stretch or "normal",
                    )
                    if res:
                        ttfont, _blob, _idx = res
                        # Get path from TTFont reader (null checks for reader and file)
                        reader = getattr(ttfont, "reader", None)
                        if reader is not None:
                            reader_file = getattr(reader, "file", None)
                            if reader_file is not None:
                                resolved = Path(reader_file.name).name
                except Exception as e:
                    resolved = f"err:{e}"

            rows.append((tid, fam, weight, style, stretch, var, resolved))

        # Recurse into children with current attrs as new inherited
        for child in elem:
            walk(child, attrs)

    if root is not None:
        walk(root, inherit)
    return rows


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
            result = cache.get_font(name)
            if result is None:
                console.print(f"[red]Not found:[/red] Font '{name}' not available")
                raise SystemExit(1)
            _font_data, _font_blob, face_idx = result
            # Get path from cache's font info
            console.print(f"[green]Found:[/green] {name}")
            console.print(f"[dim]Face index:[/dim] {face_idx}")
        except Exception as e:
            console.print(f"[red]Not found:[/red] {e}")
            raise SystemExit(1) from e


@fonts.command("report")
@click.argument("svg_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--detailed", is_flag=True, help="Show resolved font files and full inheritance"
)
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Save as markdown"
)
@click.option(
    "--variation", is_flag=True, help="Include font-variation-settings column"
)
def font_report(
    svg_file: Path,
    detailed: bool,
    output: Path | None,
    variation: bool,
) -> None:
    """Report fonts used in an SVG file with inheritance resolution.

    Shows font properties for each text element, tracking CSS inheritance
    through the SVG tree. Use --detailed to resolve actual font file paths.
    """
    cache = FontCache()

    # Prewarm cache if we need to resolve files
    if detailed:
        with console.status("[bold green]Loading font cache..."):
            cache.prewarm()

    # Collect font data with inheritance
    with console.status(f"[bold green]Analyzing {svg_file.name}..."):
        rows = collect_font_inheritance(
            svg_file,
            cache,
            include_variation=variation,
            resolve_files=detailed,
        )

    if not rows:
        console.print("[yellow]No text elements found in SVG[/yellow]")
        return

    # Build table for console output
    table = Table(title=f"Font Report: {svg_file.name}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("font-family", style="green")
    table.add_column("weight", style="yellow")
    table.add_column("style", style="magenta")
    table.add_column("stretch", style="blue")
    if variation:
        table.add_column("variation", style="dim")
    if detailed:
        table.add_column("resolved file", style="dim")

    for row in rows:
        tid, fam, weight, style, stretch, var, resolved = row
        row_data = [
            tid or "-",
            fam or "-",
            weight or "-",
            style or "-",
            stretch or "-",
        ]
        if variation:
            row_data.append(var or "-")
        if detailed:
            row_data.append(resolved or "-")
        table.add_row(*row_data)

    console.print(table)
    console.print(f"\n[bold]Total text elements:[/bold] {len(rows)}")

    # Save markdown output if requested
    if output:
        lines: list[str] = []
        # Build markdown header
        header_cols = ["id", "font-family", "weight", "style", "stretch"]
        if variation:
            header_cols.append("variation")
        if detailed:
            header_cols.append("resolved file")
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("|" + "|".join(["---"] * len(header_cols)) + "|")

        # Add rows
        for row in rows:
            tid, fam, weight, style, stretch, var, resolved = row
            row_vals = [
                tid or "-",
                fam or "-",
                weight or "-",
                style or "-",
                stretch or "-",
            ]
            if variation:
                row_vals.append(var or "-")
            if detailed:
                row_vals.append(resolved or "-")
            lines.append("| " + " | ".join(str(v) for v in row_vals) + " |")

        output.write_text("\n".join(lines))
        console.print(f"[green]Saved report to:[/green] {output}")
