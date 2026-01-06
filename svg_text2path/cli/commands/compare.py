"""Compare command - visual comparison of SVG files."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

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
@click.pass_context
def compare(
    ctx: click.Context,
    reference: Path,
    converted: Path,
    inkscape_svg: Path | None,
    output_dir: Path | None,
    no_html: bool,
    open_browser: bool,
    threshold: float,
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

    # Check for svg-bbox availability
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
    except FileNotFoundError:
        console.print("[red]Error:[/red] npx not found. Install Node.js first.")
        raise SystemExit(1) from None
    except subprocess.TimeoutExpired:
        console.print("[yellow]Warning:[/yellow] svg-bbox check timed out")

    # Build comparison command
    comparison_name = f"{reference.stem}_vs_{converted.stem}"
    html_output = out_dir / f"{comparison_name}_comparison.html"
    diff_output = out_dir / f"{comparison_name}_diff.png"

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
            console.print("[red]Error:[/red] Comparison timed out after 120 seconds")
            raise SystemExit(1) from None
        except Exception as e:
            console.print(f"[red]Error running comparison:[/red] {e}")
            raise SystemExit(1) from e

    # Parse diff percentage if available
    diff_pct = None
    if diff_output.exists() and "diff:" in result.stdout.lower():
        # Try to extract diff percentage from comparison output
        import re

        match = re.search(r"diff:\s*([\d.]+)%", result.stdout, re.IGNORECASE)
        if match:
            diff_pct = float(match.group(1))

    # Report results
    console.print()
    console.print("[bold]Comparison complete:[/bold]")
    console.print(f"  [blue]Reference:[/blue] {reference}")
    console.print(f"  [blue]Converted:[/blue] {converted}")

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

    # Open in browser if requested
    if open_browser and html_output.exists():
        webbrowser.open(f"file://{html_output.absolute()}")

    # Exit with error if diff exceeds threshold
    if diff_pct is not None and diff_pct > threshold:
        raise SystemExit(1)
