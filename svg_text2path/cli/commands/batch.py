"""Batch command - process multiple SVG files."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, TaskID

from svg_text2path import Text2PathConverter, ConversionResult
from svg_text2path.config import Config

console = Console()


@click.command()
@click.argument("inputs", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), required=True, help="Output directory")
@click.option("--batch-file", type=click.Path(exists=True, path_type=Path), help="File containing list of inputs")
@click.option("-p", "--precision", type=int, default=6, help="Path coordinate precision")
@click.option("--suffix", default="_text2path", help="Output filename suffix")
@click.option("-j", "--jobs", type=int, default=4, help="Parallel jobs")
@click.option("--continue-on-error", is_flag=True, help="Continue processing on errors")
@click.pass_context
def batch(
    ctx: click.Context,
    inputs: tuple[Path, ...],
    output_dir: Path,
    batch_file: Optional[Path],
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
            future_to_path = {
                executor.submit(process_file, p): p for p in all_inputs
            }

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
                            console.print(f"[red]Error in {input_path}:[/red] {result.errors}")
                            raise SystemExit(1)
                except Exception as e:
                    error_count += 1
                    if not continue_on_error:
                        console.print(f"[red]Error processing {input_path}:[/red] {e}")
                        raise SystemExit(1)
                finally:
                    progress.advance(task)

    # Summary
    console.print()
    console.print(f"[bold]Batch complete:[/bold]")
    console.print(f"  [green]Success:[/green] {success_count}")
    console.print(f"  [red]Failed:[/red] {error_count}")
    console.print(f"  [blue]Output:[/blue] {output_dir}")

    if error_count > 0 and not continue_on_error:
        raise SystemExit(1)
