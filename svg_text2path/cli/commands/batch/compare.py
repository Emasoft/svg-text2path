"""Batch compare command implementation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from svg_text2path import Text2PathConverter
from svg_text2path.config import Config

console = Console()


@click.command("compare")
@click.option(
    "--samples-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory with text*.svg samples (default: samples/reference_objects)",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: tmp/batch_compare)",
)
@click.option(
    "--skip",
    multiple=True,
    default=["text4.svg"],
    help="Files to skip (can be specified multiple times)",
)
@click.option(
    "--threshold",
    type=float,
    default=3.0,
    help="Diff percentage threshold for pass/fail",
)
@click.option("--scale", type=float, default=1.0, help="Render scale for comparison")
@click.option(
    "--resolution",
    default="nominal",
    type=click.Choice(["nominal", "viewbox", "full", "scale", "stretch", "clip"]),
    help="Resolution mode for sbb-compare",
)
@click.option("-p", "--precision", type=int, default=6, help="Path precision")
@click.option("--timeout", type=int, default=60, help="Per-command timeout (seconds)")
@click.option("--csv", "csv_output", is_flag=True, help="Output CSV format only")
@click.pass_context
def batch_compare(
    ctx: click.Context,
    samples_dir: Path | None,
    output_dir: Path | None,
    skip: tuple[str, ...],
    threshold: float,
    scale: float,
    resolution: str,
    precision: int,
    timeout: int,
    csv_output: bool,
) -> None:
    """Convert and compare text*.svg samples in one step.

    Converts all matching SVG files, then runs visual comparison
    using svg-bbox's sbb-compare batch mode.
    """
    config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Find repo root (from cli/commands/batch/compare.py -> project root)
    repo_root = Path(__file__).resolve().parents[4]

    # Set defaults relative to repo root
    if samples_dir is None:
        samples_dir = repo_root / "samples" / "reference_objects"
    if output_dir is None:
        output_dir = repo_root / "tmp" / "batch_compare"

    conv_dir = output_dir / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    # Find text*.svg files
    skip_set = set(skip)
    svg_files = [
        f for f in sorted(samples_dir.glob("text*.svg")) if f.name not in skip_set
    ]

    if not svg_files:
        console.print(f"[yellow]Warning:[/yellow] No text*.svg in {samples_dir}")
        return

    # Create converter
    converter = Text2PathConverter(
        precision=precision,
        log_level=log_level,
        config=config,
    )

    # Convert files and build pairs
    pairs: list[dict[str, str]] = []
    conversion_errors: list[tuple[str, str]] = []

    if not csv_output:
        console.print(f"[bold]Converting {len(svg_files)} files...[/bold]")

    for svg in svg_files:
        out_svg = conv_dir / f"{svg.stem}_conv.svg"
        try:
            result = converter.convert_file(svg, out_svg)
            if result.success:
                pairs.append({"a": str(svg), "b": str(out_svg)})
                if not csv_output:
                    console.print(f"  [green]OK[/green] {svg.name}")
            else:
                conversion_errors.append((svg.name, str(result.errors)))
                if not csv_output:
                    console.print(f"  [red]FAIL[/red] {svg.name}: {result.errors}")
        except Exception as e:
            conversion_errors.append((svg.name, str(e)))
            if not csv_output:
                console.print(f"  [red]ERROR[/red] {svg.name}: {e}")

    if not pairs:
        console.print("[red]Error:[/red] No files converted successfully")
        raise SystemExit(1)

    # Write pairs JSON for sbb-compare batch mode
    pairs_path = output_dir / "pairs.json"
    pairs_path.write_text(json.dumps(pairs))

    # Run sbb-compare in batch mode
    summary_path = output_dir / "summary.json"
    cmd = [
        "npx",
        "sbb-compare",
        "--batch",
        str(pairs_path),
        "--threshold",
        str(int(threshold * 10)),  # sbb-compare uses integer threshold
        "--scale",
        str(scale),
        "--resolution",
        resolution,
        "--json",
    ]

    if not csv_output:
        console.print("\n[bold]Running visual comparison...[/bold]")

    try:
        with summary_path.open("w") as f:
            batch_timeout = timeout * max(1, len(pairs))
            subprocess.run(cmd, check=True, timeout=batch_timeout, stdout=f)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] sbb-compare failed: {e}")
        raise SystemExit(1) from None
    except FileNotFoundError:
        console.print("[red]Error:[/red] sbb-compare not found. npm install svg-bbox")
        raise SystemExit(1) from None

    # Parse and display results
    summary = json.loads(summary_path.read_text())
    results = summary.get("results", [])

    pass_count = 0
    fail_count = 0

    if csv_output:
        # CSV output mode
        print("file,diff_percent,status")
        for r in results:
            diff = float(r.get("diffPercent") or r.get("diff") or 0)
            name = Path(r.get("a", "")).name
            status = "pass" if diff < threshold else "FAIL"
            print(f"{name},{diff:.2f},{status}")
            if status == "pass":
                pass_count += 1
            else:
                fail_count += 1
    else:
        # Rich table output
        table = Table(title="Comparison Results")
        table.add_column("File", style="cyan")
        table.add_column("Diff %", justify="right")
        table.add_column("Status", justify="center")

        for r in results:
            diff = float(r.get("diffPercent") or r.get("diff") or 0)
            name = Path(r.get("a", "")).name
            if diff < threshold:
                status = "[green]PASS[/green]"
                pass_count += 1
            else:
                status = "[red]FAIL[/red]"
                fail_count += 1
            table.add_row(name, f"{diff:.2f}", status)

        console.print(table)
        console.print()
        console.print(f"[bold]Summary:[/bold] {pass_count} passed, {fail_count} failed")
        console.print(f"[blue]Results:[/blue] {summary_path}")

    if fail_count > 0:
        raise SystemExit(1)
