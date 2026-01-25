"""Batch commands - process, compare, and track multiple SVG files."""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from svg_text2path import ConversionResult, Text2PathConverter
from svg_text2path.config import Config

console = Console()


@click.group()
def batch() -> None:
    """Batch processing commands for multiple SVG files."""
    pass


@batch.command("convert")
@click.argument("inputs", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory",
)
@click.option(
    "--batch-file",
    type=click.Path(exists=True, path_type=Path),
    help="File containing list of inputs",
)
@click.option(
    "-p", "--precision", type=int, default=6, help="Path coordinate precision"
)
@click.option("--suffix", default="_text2path", help="Output filename suffix")
@click.option("-j", "--jobs", type=int, default=4, help="Parallel jobs")
@click.option("--continue-on-error", is_flag=True, help="Continue processing on errors")
@click.pass_context
def batch_convert(
    ctx: click.Context,
    inputs: tuple[Path, ...],
    output_dir: Path,
    batch_file: Path | None,
    precision: int,
    suffix: str,
    jobs: int,
    continue_on_error: bool,
) -> None:
    """Convert multiple SVG files to paths.

    INPUTS: Paths to SVG files (supports glob patterns via shell).
    """
    config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Collect all input files
    all_inputs: list[Path] = list(inputs)

    if batch_file:
        with open(batch_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    all_inputs.append(Path(line))

    if not all_inputs:
        console.print("[red]Error:[/red] No input files specified")
        raise SystemExit(1)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create converter
    converter = Text2PathConverter(
        precision=precision,
        log_level=log_level,
        config=config,
    )

    results: list[ConversionResult] = []
    success_count = 0
    error_count = 0

    def process_file(input_path: Path) -> ConversionResult:
        output_path = output_dir / f"{input_path.stem}{suffix}.svg"
        return converter.convert_file(input_path, output_path)

    with Progress(console=console) as progress:
        task = progress.add_task("[green]Converting...", total=len(all_inputs))

        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_to_path = {executor.submit(process_file, p): p for p in all_inputs}

            for future in concurrent.futures.as_completed(future_to_path):
                input_path = future_to_path[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result.success:
                        success_count += 1
                    else:
                        error_count += 1
                        if not continue_on_error:
                            console.print(
                                f"[red]Error in {input_path}:[/red] {result.errors}"
                            )
                            raise SystemExit(1)
                except Exception as e:
                    error_count += 1
                    if not continue_on_error:
                        console.print(f"[red]Error processing {input_path}:[/red] {e}")
                        raise SystemExit(1) from None
                finally:
                    progress.advance(task)

    # Summary
    console.print()
    console.print("[bold]Batch convert complete:[/bold]")
    console.print(f"  [green]Success:[/green] {success_count}")
    console.print(f"  [red]Failed:[/red] {error_count}")
    console.print(f"  [blue]Output:[/blue] {output_dir}")

    if error_count > 0 and not continue_on_error:
        raise SystemExit(1)


@batch.command("compare")
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

    # Find repo root (from cli/commands/batch.py -> project root)
    repo_root = Path(__file__).resolve().parents[3]

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


@batch.command("regression")
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

    # Find repo root
    repo_root = Path(__file__).resolve().parents[3]

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
    registry_data: list[dict] = []
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
