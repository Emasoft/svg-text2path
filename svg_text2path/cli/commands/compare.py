"""Compare command - visual comparison of SVG files."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from svg_text2path.tools.dependencies import check_visual_comparison_deps
from svg_text2path.tools.visual_comparison import (
    ImageComparator,
    SVGRenderer,
    generate_diff_image,
    generate_grayscale_diff_map,
)

console = Console()


@click.command()
@click.argument("reference", type=click.Path(exists=True, path_type=Path))
@click.argument("converted", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--inkscape-svg",
    type=click.Path(exists=True, path_type=Path),
    help="Inkscape reference for 3-way comparison",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    help="Output directory for comparison files",
)
@click.option("--no-html", is_flag=True, help="Skip HTML comparison page generation")
@click.option("--open", "open_browser", is_flag=True, help="Open comparison in browser")
@click.option(
    "--threshold",
    type=float,
    default=0.5,
    help="Diff threshold percentage for pass/fail",
)
@click.option(
    "--pixel-perfect",
    is_flag=True,
    help="Use ImageComparator for pixel-perfect comparison instead of svg-bbox",
)
@click.option(
    "--pixel-tolerance",
    type=float,
    default=0.0,
    help="Pixel color difference tolerance (0-1, 0=exact match)",
)
@click.option(
    "--generate-diff",
    is_flag=True,
    help="Generate red-overlay diff image highlighting differences",
)
@click.option(
    "--grayscale-diff",
    is_flag=True,
    help="Generate grayscale magnitude diff map",
)
def compare(
    reference: Path,
    converted: Path,
    inkscape_svg: Path | None,
    output_dir: Path | None,
    no_html: bool,
    open_browser: bool,
    threshold: float,
    pixel_perfect: bool,
    pixel_tolerance: float,
    generate_diff: bool,
    grayscale_diff: bool,
) -> None:
    """Compare original SVG with converted version.

    REFERENCE: Original SVG file with text elements.
    CONVERTED: Converted SVG file with paths.

    Uses svg-bbox (npm) for accurate Chrome-based rendering comparison.
    """
    import subprocess
    import webbrowser

    # Determine output directory
    out_dir = output_dir or Path("./diffs")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Check for required tools using centralized dependency checker
    deps_ok, missing_tools = check_visual_comparison_deps()
    if not deps_ok:
        console.print("[red]Error:[/red] Missing required tools for visual comparison:")
        for tool in missing_tools:
            if tool == "node":
                console.print(f"  - {tool}: Install Node.js from nodejs.org")
            elif tool == "npx":
                console.print(f"  - {tool}: Included with Node.js (npm >= 5.2)")
        console.print()
        console.print("Run [bold]text2path deps[/bold] for full dependency status.")
        raise SystemExit(1)

    # Build output paths
    comparison_name = f"{reference.stem}_vs_{converted.stem}"
    html_output = out_dir / f"{comparison_name}_comparison.html"
    diff_output = out_dir / f"{comparison_name}_diff.png"
    grayscale_output = out_dir / f"{comparison_name}_grayscale_diff.png"

    # Initialize result tracking
    diff_pct = None
    pixel_stats = None

    if pixel_perfect:
        # Pixel-perfect comparison using ImageComparator
        with console.status("[bold green]Running pixel-perfect comparison..."):
            # Render SVGs to PNG
            ref_png = out_dir / f"{reference.stem}_rendered.png"
            conv_png = out_dir / f"{converted.stem}_rendered.png"

            # Use static method directly
            SVGRenderer.render_svg_to_png(reference, ref_png)
            SVGRenderer.render_svg_to_png(converted, conv_png)

            # Compare images - returns tuple[bool, dict]
            _is_match, pixel_stats = ImageComparator.compare_images_pixel_perfect(
                ref_png, conv_png, pixel_tolerance=pixel_tolerance
            )

            # Get diff percentage from stats dict
            if pixel_stats.get("total_pixels", 0) > 0:
                diff_pct = pixel_stats.get("diff_percentage", 0.0)

            # Generate diff images if requested
            if generate_diff and ref_png.exists() and conv_png.exists():
                generate_diff_image(ref_png, conv_png, diff_output)

            if grayscale_diff and ref_png.exists() and conv_png.exists():
                generate_grayscale_diff_map(ref_png, conv_png, grayscale_output)

    else:
        # Check for svg-bbox availability (only needed for non-pixel-perfect mode)
        try:
            result = subprocess.run(
                ["npx", "svg-bbox", "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                console.print(
                    "[yellow]Warning:[/yellow] svg-bbox not installed. "
                    "Install with: npm install svg-bbox"
                )
                console.print("Run [bold]text2path deps[/bold] for installation hints.")
        except FileNotFoundError:
            console.print("[red]Error:[/red] npx not found. Install Node.js first.")
            console.print("Run [bold]text2path deps[/bold] for installation hints.")
            raise SystemExit(1) from None
        except subprocess.TimeoutExpired:
            console.print("[yellow]Warning:[/yellow] svg-bbox check timed out")

        with console.status("[bold green]Rendering comparison..."):
            # Run svg-bbox comparison
            cmd = [
                "npx",
                "svg-bbox",
                "compare",
                str(reference.absolute()),
                str(converted.absolute()),
                "--output",
                str(html_output),
                "--diff",
                str(diff_output),
            ]

            if inkscape_svg:
                cmd.extend(["--inkscape", str(inkscape_svg.absolute())])

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=out_dir,
                )

                if result.returncode != 0:
                    console.print(
                        "[yellow]Warning:[/yellow] Comparison returned non-zero: "
                        f"{result.stderr}"
                    )
            except subprocess.TimeoutExpired:
                console.print(
                    "[red]Error:[/red] Comparison timed out after 120 seconds"
                )
                raise SystemExit(1) from None
            except Exception as e:
                console.print(f"[red]Error running comparison:[/red] {e}")
                raise SystemExit(1) from e

        # Parse diff percentage from svg-bbox output
        if diff_output.exists() and "diff:" in result.stdout.lower():
            import re

            match = re.search(r"diff:\s*([\d.]+)%", result.stdout, re.IGNORECASE)
            if match:
                diff_pct = float(match.group(1))

    # Report results
    console.print()
    console.print("[bold]Comparison complete:[/bold]")
    console.print(f"  [blue]Reference:[/blue] {reference}")
    console.print(f"  [blue]Converted:[/blue] {converted}")

    if pixel_perfect:
        console.print(
            f"  [blue]Mode:[/blue] Pixel-perfect (tolerance: {pixel_tolerance})"
        )
        if pixel_stats:
            total_px = pixel_stats.get("total_pixels", "N/A")
            diff_px = pixel_stats.get("diff_pixels", "N/A")
            diff_pct_val = pixel_stats.get("diff_percentage", 0.0)
            console.print(f"  [blue]Total pixels:[/blue] {total_px}")
            console.print(f"  [blue]Different pixels:[/blue] {diff_px}")
            console.print(f"  [blue]Match rate:[/blue] {100.0 - diff_pct_val:.2f}%")

    if diff_pct is not None:
        if diff_pct <= threshold:
            console.print(
                f"  [green]Diff:[/green] {diff_pct:.2f}% (PASS, threshold {threshold}%)"
            )
        else:
            console.print(
                f"  [red]Diff:[/red] {diff_pct:.2f}% (FAIL, threshold {threshold}%)"
            )

    if not no_html and html_output.exists():
        console.print(f"  [blue]HTML:[/blue] {html_output}")

    if diff_output.exists():
        console.print(f"  [blue]Diff image:[/blue] {diff_output}")

    if grayscale_diff and grayscale_output.exists():
        console.print(f"  [blue]Grayscale diff:[/blue] {grayscale_output}")

    # Open in browser if requested
    if open_browser and html_output.exists():
        webbrowser.open(f"file://{html_output.absolute()}")

    # Exit with error if diff exceeds threshold
    if diff_pct is not None and diff_pct > threshold:
        raise SystemExit(1)
