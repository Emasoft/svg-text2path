"""Batch convert command implementation."""

from __future__ import annotations

import concurrent.futures
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from svg_text2path import Text2PathConverter
from svg_text2path.config import Config

from .config import (
    ConversionLogEntry,
    find_files_for_conversion,
    get_enabled_extensions,
    load_batch_config,
    run_verification,
)
from .validation import _check_path_accessibility, _is_remote_path

if TYPE_CHECKING:
    from .validation import PathAccessResult

console = Console()


@click.command("convert")
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def batch_convert(
    ctx: click.Context,
    config_file: Path,
) -> None:
    """Convert multiple SVG files using YAML configuration.

    CONFIG_FILE: Path to YAML configuration file.

    \b
    YAML config structure:
      settings:           # Conversion settings (all optional)
        precision: 6
        preserve_styles: false
        system_fonts_only: false
        font_dirs: []
        no_remote_fonts: false
        no_size_limit: false
        auto_download: false
        validate: false
        verify: false
        verify_pixel_threshold: 10
        verify_image_threshold: 5.0
        jobs: 4
        continue_on_error: true

      inputs:             # List of files or folders to convert
        # Folder mode (auto-detected when path is a directory)
        - path: samples/icons/
          output_dir: converted/icons/
          suffix: _converted

        # File mode (auto-detected when path is a file)
        - path: samples/logo.svg
          output: converted/brand/company_logo.svg

      log_file: batch_log.json  # Optional, defaults to batch_conversion_log.json

    \b
    Example:
      text2path batch convert batch_config.yaml
    """
    app_config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Load batch config
    try:
        batch_cfg = load_batch_config(config_file)
    except Exception as e:
        console.print(f"[red]Error loading config:[/red] {e}")
        raise SystemExit(1) from None

    settings = batch_cfg.settings

    # Apply config settings to app config
    if settings.system_fonts_only:
        app_config.fonts.system_only = True
    if settings.font_dirs:
        app_config.fonts.custom_dirs = [Path(d) for d in settings.font_dirs]
    if settings.no_remote_fonts:
        app_config.fonts.remote = False
    if settings.no_size_limit:
        app_config.security.ignore_size_limits = True

    # Create converter
    converter = Text2PathConverter(
        precision=settings.precision,
        preserve_styles=settings.preserve_styles,
        log_level=log_level,
        config=app_config,
        auto_download_fonts=settings.auto_download,
        validate_svg=settings.validate,
    )

    # Show enabled formats
    enabled_exts = get_enabled_extensions(settings.formats)
    console.print(f"[dim]Enabled formats:[/dim] {', '.join(enabled_exts)}")

    # Collect all file pairs (input, output) - supports both Path and str (remote)
    file_pairs: list[tuple[Path | str, Path | str]] = []

    console.print("[bold]Collecting input files...[/bold]")

    for entry in batch_cfg.inputs:
        if entry.is_folder:
            # Remote folder mode not supported yet - skip with warning
            if entry.is_remote_input:
                console.print(
                    f"[yellow]Warning:[/yellow] Remote folder mode not supported: "
                    f"{entry.path}"
                )
                continue

            # Local folder - entry.path is Path
            input_path = entry.path
            assert isinstance(input_path, Path)
            if not input_path.exists():
                console.print(
                    f"[yellow]Warning:[/yellow] Folder not found: {input_path}"
                )
                continue

            # Find files matching enabled formats
            matching_files = find_files_for_conversion(input_path, settings.formats)
            console.print(
                f"  [dim]{input_path}[/dim]: {len(matching_files)} files to convert"
            )

            # Ensure output dir exists (only for local outputs)
            if entry.output_dir and not entry.is_remote_output:
                assert isinstance(entry.output_dir, Path)
                entry.output_dir.mkdir(parents=True, exist_ok=True)

            for input_file in matching_files:
                # Determine output extension - preserve original
                out_ext = input_file.suffix
                out_name = f"{input_file.stem}{entry.suffix}{out_ext}"
                if entry.output_dir:
                    if entry.is_remote_output:
                        # Remote output: construct string path
                        out_path: Path | str = f"{entry.output_dir}/{out_name}"
                    else:
                        # Local output: use Path
                        assert isinstance(entry.output_dir, Path)
                        out_path = entry.output_dir / out_name
                    file_pairs.append((input_file, out_path))
        else:
            # Single file mode
            input_path = entry.path

            # Check if input exists (only for local files)
            if not entry.is_remote_input:
                assert isinstance(input_path, Path)
                if not input_path.exists():
                    console.print(
                        f"[yellow]Warning:[/yellow] File not found: {input_path}"
                    )
                    continue

            if entry.output:
                output_path = entry.output

                # Handle allow_overwrite with .bak backup (only for local files)
                is_same_path = str(input_path) == str(output_path)
                can_backup = is_same_path and settings.allow_overwrite
                if can_backup and not entry.is_remote_input:
                    assert isinstance(input_path, Path)
                    bak_path = input_path.with_suffix(input_path.suffix + ".bak")
                    import shutil

                    shutil.copy2(input_path, bak_path)
                    console.print(f"  [dim]Backup created:[/dim] {bak_path.name}")

                # Ensure output directory exists (only for local outputs)
                if not entry.is_remote_output:
                    assert isinstance(output_path, Path)
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                file_pairs.append((input_path, output_path))

    if not file_pairs:
        console.print("[red]Error:[/red] No valid input files found")
        raise SystemExit(1)

    # Initialize preflight errors list (used in log report even if checks disabled)
    preflight_errors: list[tuple[str, PathAccessResult]] = []

    # Run preflight accessibility checks if enabled
    if settings.preflight_check:
        console.print("\n[bold]Running preflight checks...[/bold]")

        for input_path, output_path in file_pairs:
            # Check input accessibility
            input_result = _check_path_accessibility(str(input_path), check_write=False)
            if not input_result.accessible:
                preflight_errors.append((str(input_path), input_result))
                continue

            # Check output accessibility (write permission, disk space)
            out_str = str(output_path)
            output_result = _check_path_accessibility(out_str, check_write=True)
            if not output_result.accessible:
                preflight_errors.append((str(output_path), output_result))

        if preflight_errors:
            console.print(
                f"\n[red]Preflight check failed:[/red] "
                f"{len(preflight_errors)} path(s) have issues\n"
            )

            # Group errors by type for cleaner display
            error_types: dict[str, list[tuple[str, PathAccessResult]]] = {}
            for path, result in preflight_errors:
                error_type = result.error_type or "unknown"
                if error_type not in error_types:
                    error_types[error_type] = []
                error_types[error_type].append((path, result))

            type_labels = {
                "auth": "Authentication Issues",
                "permission": "Permission Issues",
                "network": "Network Issues",
                "disk": "Disk Space Issues",
                "not_found": "Paths Not Found",
                "ssh": "SSH Issues",
                "config": "Configuration Issues",
            }

            for error_type, errors_list in error_types.items():
                label = type_labels.get(error_type, error_type.title())
                console.print(f"[yellow]{label}:[/yellow]")
                for path, result in errors_list:
                    console.print(f"  * {path}")
                    console.print(f"    [dim]{result.error_message}[/dim]")
                    if result.suggestion:
                        console.print(f"    [cyan]Tip:[/cyan] {result.suggestion}")
                console.print()

            if not settings.continue_on_error:
                console.print(
                    "[red]Aborting.[/red] Fix issues above or set "
                    "'continue_on_error: true' to proceed anyway."
                )
                raise SystemExit(1)

            # Filter out paths with errors
            failed_paths = {path for path, _ in preflight_errors}
            original_count = len(file_pairs)
            file_pairs = [
                (inp, out)
                for inp, out in file_pairs
                if str(inp) not in failed_paths and str(out) not in failed_paths
            ]
            console.print(
                f"[yellow]Continuing with {len(file_pairs)}/{original_count} "
                f"accessible files...[/yellow]\n"
            )

            if not file_pairs:
                console.print("[red]Error:[/red] No accessible files to process")
                raise SystemExit(1)
        else:
            console.print("[green]All paths accessible[/green]")

    console.print(f"\n[bold]Converting {len(file_pairs)} files...[/bold]")

    # Process files
    log_entries: list[ConversionLogEntry] = []
    success_count = 0
    skipped_count = 0
    error_count = 0
    verify_pass_count = 0
    verify_fail_count = 0

    def process_file(pair: tuple[Path | str, Path | str]) -> ConversionLogEntry:
        """Process a single file using format handlers for all types."""
        from svg_text2path.formats import match_handler
        from svg_text2path.svg.parser import find_text_elements

        input_path, output_path = pair

        try:
            # Use format handler to detect and parse the file
            match = match_handler(str(input_path))
            match.handler.config = app_config  # Pass config for size limits

            # Parse input using the appropriate handler
            tree = match.handler.parse(str(input_path))

            # Count text elements before conversion
            root = tree.getroot()
            if root is None:
                return ConversionLogEntry(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    status="error",
                    reason="Could not parse SVG root element",
                )

            text_count = len(find_text_elements(root))
            if text_count == 0:
                return ConversionLogEntry(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    status="skipped",
                    reason="No text elements found",
                )

            # Convert using the converter
            converted_tree = converter.convert_tree(tree)

            # Count paths after conversion
            path_count = len(root.findall(".//{http://www.w3.org/2000/svg}path"))
            path_count += len(root.findall(".//path"))

            # Serialize output using the handler (preserves HTML/CSS/etc structure)
            match.handler.serialize(converted_tree, output_path)

            log_entry = ConversionLogEntry(
                input_path=str(input_path),
                output_path=str(output_path),
                status="success",
                text_elements=text_count,
                path_elements=path_count,
            )

            # Run verification if enabled (only for SVG outputs, local files only)
            output_str = str(output_path)
            is_svg_output = output_str.lower().endswith((".svg", ".svgz"))
            is_local = not _is_remote_path(str(input_path))
            if settings.verify and is_svg_output and is_local:
                # Convert to Path for verification (local files only)
                diff_pct, passed = run_verification(
                    Path(input_path) if isinstance(input_path, str) else input_path,
                    Path(output_path) if isinstance(output_path, str) else output_path,
                    settings.verify_pixel_threshold,
                    settings.verify_image_threshold,
                )
                log_entry.diff_percent = diff_pct
                log_entry.verify_passed = passed

            return log_entry

        except PermissionError as e:
            return ConversionLogEntry(
                input_path=str(input_path),
                output_path=str(output_path),
                status="error",
                reason=f"Permission denied: {e}",
            )
        except OSError as e:
            return ConversionLogEntry(
                input_path=str(input_path),
                output_path=str(output_path),
                status="error",
                reason=f"I/O error: {e}",
            )
        except Exception as e:
            return ConversionLogEntry(
                input_path=str(input_path),
                output_path=str(output_path),
                status="error",
                reason=str(e),
            )

    with Progress(console=console) as progress:
        task = progress.add_task("[green]Converting...", total=len(file_pairs))

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.jobs
        ) as executor:
            future_to_pair = {
                executor.submit(process_file, pair): pair for pair in file_pairs
            }

            for future in concurrent.futures.as_completed(future_to_pair):
                pair = future_to_pair[future]
                try:
                    log_entry = future.result()
                    log_entries.append(log_entry)

                    if log_entry.status == "success":
                        success_count += 1
                        if log_entry.verify_passed is True:
                            verify_pass_count += 1
                        elif log_entry.verify_passed is False:
                            verify_fail_count += 1
                    elif log_entry.status == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1
                        if not settings.continue_on_error:
                            console.print(
                                f"[red]Error in {pair[0]}:[/red] {log_entry.reason}"
                            )
                            raise SystemExit(1)
                except Exception as e:
                    error_count += 1
                    log_entries.append(
                        ConversionLogEntry(
                            input_path=str(pair[0]),
                            output_path=str(pair[1]),
                            status="error",
                            reason=str(e),
                        )
                    )
                    if not settings.continue_on_error:
                        console.print(f"[red]Error processing {pair[0]}:[/red] {e}")
                        raise SystemExit(1) from None
                finally:
                    progress.advance(task)

    # Write log file
    log_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "config_file": str(config_file),
        "settings": {
            "precision": settings.precision,
            "preserve_styles": settings.preserve_styles,
            "auto_download": settings.auto_download,
            "validate": settings.validate,
            "verify": settings.verify,
            "verify_pixel_threshold": settings.verify_pixel_threshold,
            "verify_image_threshold": settings.verify_image_threshold,
        },
        "summary": {
            "total": len(file_pairs),
            "success": success_count,
            "skipped": skipped_count,
            "errors": error_count,
            "preflight_errors": len(preflight_errors),
            "verify_passed": verify_pass_count if settings.verify else None,
            "verify_failed": verify_fail_count if settings.verify else None,
        },
        "preflight_errors": [
            {
                "path": path,
                "error_type": result.error_type,
                "error_message": result.error_message,
                "suggestion": result.suggestion,
            }
            for path, result in preflight_errors
        ],
        "files": [
            {
                "input": e.input_path,
                "output": e.output_path,
                "status": e.status,
                "reason": e.reason if e.reason else None,
                "text_elements": e.text_elements if e.text_elements else None,
                "path_elements": e.path_elements if e.path_elements else None,
                "diff_percent": e.diff_percent,
                "verify_passed": e.verify_passed,
            }
            for e in log_entries
        ],
    }

    batch_cfg.log_file.write_text(json.dumps(log_data, indent=2))

    # Summary table
    console.print()
    table = Table(title="Batch Conversion Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Total files", str(len(file_pairs)))
    table.add_row("[green]Converted[/green]", str(success_count))
    table.add_row("[yellow]Skipped (no text)[/yellow]", str(skipped_count))
    table.add_row("[red]Errors[/red]", str(error_count))

    if settings.verify:
        table.add_row("", "")
        table.add_row("[green]Verify passed[/green]", str(verify_pass_count))
        table.add_row("[red]Verify failed[/red]", str(verify_fail_count))

    console.print(table)
    console.print()
    console.print(f"[blue]Log file:[/blue] {batch_cfg.log_file}")

    if error_count > 0:
        console.print(
            f"\n[yellow]Warning:[/yellow] {error_count} files had errors. "
            f"Check {batch_cfg.log_file} for details."
        )

    if error_count > 0 and not settings.continue_on_error:
        raise SystemExit(1)
