"""Batch regression command implementation."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from svg_text2path import Text2PathConverter
from svg_text2path.config import Config

console = Console()


@click.command("regression")
@click.option(
    "--samples-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory with text*.svg samples",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: tmp/regression_check)",
)
@click.option(
    "--registry",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to regression registry JSON (default: tmp/regression_history.json)",
)
@click.option(
    "--skip",
    multiple=True,
    default=[],
    help="Files to skip",
)
@click.option(
    "--threshold",
    type=int,
    default=20,
    help="Threshold for sbb-compare",
)
@click.option("--scale", type=float, default=4.0, help="Render scale")
@click.option(
    "--resolution",
    default="viewbox",
    type=click.Choice(["nominal", "viewbox", "full", "scale", "stretch", "clip"]),
    help="Resolution mode",
)
@click.option("-p", "--precision", type=int, default=3, help="Path precision")
@click.option("--timeout", type=int, default=300, help="Comparer timeout (seconds)")
@click.pass_context
def batch_regression(
    ctx: click.Context,
    samples_dir: Path | None,
    output_dir: Path | None,
    registry: Path | None,
    skip: tuple[str, ...],
    threshold: int,
    scale: float,
    resolution: str,
    precision: int,
    timeout: int,
) -> None:
    """Run batch compare and track results for regression detection.

    Converts samples, compares against originals, saves results to
    a timestamped registry, and warns if any diff percentage increased
    compared to the previous run with matching settings.
    """
    config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Find repo root (from cli/commands/batch/regression.py -> project root)
    repo_root = Path(__file__).resolve().parents[4]

    # Set defaults
    if samples_dir is None:
        samples_dir = repo_root / "samples" / "reference_objects"
    if output_dir is None:
        output_dir = repo_root / "tmp" / "regression_check"
    if registry is None:
        registry = repo_root / "tmp" / "regression_history.json"

    # Create timestamped run directory
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / timestamp
    conv_dir = run_dir / "converted"
    run_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    # Find text*.svg files
    skip_set = set(skip)
    svg_files = [
        f
        for f in sorted(samples_dir.glob("text*.svg"))
        if f.name not in skip_set and "-paths" not in f.name
    ]

    if not svg_files:
        console.print("[yellow]Warning:[/yellow] No text*.svg files found")
        return

    # Create converter
    converter = Text2PathConverter(
        precision=precision,
        log_level=log_level,
        config=config,
    )

    # Convert files
    pairs: list[tuple[str, str]] = []
    failures: list[tuple[str, str]] = []

    console.print(f"[bold]Converting {len(svg_files)} files...[/bold]")

    for svg in svg_files:
        out_svg = conv_dir / f"{svg.stem}_conv.svg"
        try:
            result = converter.convert_file(svg, out_svg)
            if result.success:
                pairs.append((str(svg), str(out_svg)))
                console.print(f"  [green]OK[/green] {svg.name}")
            else:
                failures.append((svg.name, str(result.errors)))
                console.print(f"  [red]FAIL[/red] {svg.name}")
        except Exception as e:
            failures.append((svg.name, str(e)))
            console.print(f"  [red]ERROR[/red] {svg.name}: {e}")

    if not pairs:
        console.print("[red]Error:[/red] No files converted successfully")
        raise SystemExit(1)

    # Write pairs file for sbb-compare (tab-separated for compatibility)
    pairs_path = run_dir / "pairs.txt"
    pairs_path.write_text("\n".join("\t".join(p) for p in pairs))

    # Run comparison (try sbb-comparer.cjs first, fall back to npx sbb-compare)
    summary_path = run_dir / "summary.json"
    sbb_comparer = repo_root / "SVG-BBOX" / "sbb-comparer.cjs"

    if sbb_comparer.exists():
        cmd = [
            "node",
            str(sbb_comparer),
            "--batch",
            str(pairs_path),
            "--threshold",
            str(threshold),
            "--scale",
            str(scale),
            "--resolution",
            resolution,
            "--json",
        ]
    else:
        # Fall back to npx sbb-compare with JSON pairs
        pairs_json_path = run_dir / "pairs.json"
        pairs_json = [{"a": a, "b": b} for a, b in pairs]
        pairs_json_path.write_text(json.dumps(pairs_json))
        cmd = [
            "npx",
            "sbb-compare",
            "--batch",
            str(pairs_json_path),
            "--threshold",
            str(threshold),
            "--scale",
            str(scale),
            "--resolution",
            resolution,
            "--json",
        ]

    console.print("\n[bold]Running comparison...[/bold]")

    try:
        with summary_path.open("w") as f:
            subprocess.run(cmd, check=True, timeout=timeout, stdout=f)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Comparer failed: {e}")
        raise SystemExit(1) from None
    except FileNotFoundError:
        console.print("[red]Error:[/red] Comparer not found")
        raise SystemExit(1) from None

    # Parse results
    summary = json.loads(summary_path.read_text())
    result_map: dict[str, float] = {}

    for r in summary.get("results", []):
        diff = r.get("diffPercent") or r.get("diffPercentage") or r.get("diff")
        svg_path = r.get("a") or r.get("svg1") or ""
        name = Path(svg_path).name
        if diff is not None:
            result_map[name] = float(diff)

    # Load existing registry
    registry_data: list[dict[str, Any]] = []
    if registry.exists():
        try:
            registry_data = json.loads(registry.read_text())
        except Exception:
            registry_data = []

    # Find previous entry with matching settings for regression comparison
    prev_entry = None
    for entry in reversed(registry_data):
        if (
            entry.get("threshold") == threshold
            and entry.get("scale") == scale
            and entry.get("resolution") == resolution
            and entry.get("precision") == precision
        ):
            prev_entry = entry
            break

    # Detect regressions
    regressions: list[tuple[str, float, float]] = []
    if prev_entry and "results" in prev_entry:
        prev_results = prev_entry["results"]
        for name, diff in result_map.items():
            if name in prev_results and diff > prev_results[name]:
                regressions.append((name, prev_results[name], diff))

    # Append current run to registry
    registry_data.append(
        {
            "timestamp": timestamp,
            "threshold": threshold,
            "scale": scale,
            "resolution": resolution,
            "precision": precision,
            "results": result_map,
            "failures": failures,
        }
    )
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(registry_data, indent=2))

    # Display results
    console.print()
    table = Table(title="Regression Check Results")
    table.add_column("File", style="cyan")
    table.add_column("Diff %", justify="right")
    table.add_column("Change", justify="right")

    for name, diff in sorted(result_map.items()):
        change = ""
        if prev_entry and "results" in prev_entry and name in prev_entry["results"]:
            prev_diff = prev_entry["results"][name]
            delta = diff - prev_diff
            if delta > 0:
                change = f"[red]+{delta:.2f}[/red]"
            elif delta < 0:
                change = f"[green]{delta:.2f}[/green]"
            else:
                change = "[dim]0.00[/dim]"
        table.add_row(name, f"{diff:.2f}", change)

    console.print(table)
    console.print()

    if regressions:
        console.print("[bold red]WARNING: Regression detected![/bold red]")
        for name, old_diff, new_diff in regressions:
            console.print(f"  {name}: {old_diff:.2f}% -> {new_diff:.2f}%")
        console.print()
        console.print("[yellow]Consider reverting recent changes.[/yellow]")
    else:
        console.print("[green]No regression detected.[/green]")

    console.print(f"\n[blue]Registry:[/blue] {registry}")
    console.print(f"[blue]Run output:[/blue] {run_dir}")
