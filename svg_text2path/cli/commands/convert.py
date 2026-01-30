"""Convert command - single file text-to-path conversion.

Supports multiple input formats:
- SVG files (.svg, .svgz)
- HTML with embedded SVG
- CSS with data URIs
- Remote URLs (http://, https://)
- Data URI strings
- Python/JavaScript code with SVG strings
- Markdown, RST, JSON, CSV with SVG
- ePub ebooks
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.console import Console

from svg_text2path import Text2PathConverter
from svg_text2path.config import Config
from svg_text2path.formats import InputFormat, match_handler

console = Console()


# Map format names to InputFormat enum for --format option
FORMAT_CHOICES: dict[str, InputFormat | None] = {
    "auto": None,  # Auto-detect
    "svg": InputFormat.FILE_PATH,
    "svgz": InputFormat.ZSVG,
    "html": InputFormat.HTML_EMBEDDED,
    "css": InputFormat.CSS_EMBEDDED,
    "json": InputFormat.JSON_ESCAPED,
    "csv": InputFormat.CSV_ESCAPED,
    "markdown": InputFormat.MARKDOWN,
    "md": InputFormat.MARKDOWN,
    "url": InputFormat.REMOTE_URL,
    "data-uri": InputFormat.DATA_URI,
    "python": InputFormat.PYTHON_CODE,
    "py": InputFormat.PYTHON_CODE,
    "javascript": InputFormat.JAVASCRIPT_CODE,
    "js": InputFormat.JAVASCRIPT_CODE,
    "typescript": InputFormat.JAVASCRIPT_CODE,
    "ts": InputFormat.JAVASCRIPT_CODE,
    "rst": InputFormat.RST,
    "txt": InputFormat.PLAINTEXT,
    "epub": InputFormat.EPUB,
    "inkscape": InputFormat.INKSCAPE,
}


def _resolve_output_path(
    source: str,
    output_path: Path | None,
    output_dir: Path | None,
    suffix: str,
    source_type: str,
) -> Path:
    """Determine the output file path based on source and options."""
    if output_path:
        return output_path

    # For URLs and data URIs, use a default name
    if source_type in ("url", "data_uri"):
        base_name = "converted"
        if source_type == "url":
            # Extract filename from URL if possible
            from urllib.parse import urlparse

            parsed = urlparse(source)
            path_part = parsed.path.split("/")[-1]
            if path_part and "." in path_part:
                base_name = path_part.rsplit(".", 1)[0]
    else:
        # Source is a file path
        base_name = Path(source).stem

    out_name = f"{base_name}{suffix}.svg"

    if output_dir:
        return output_dir / out_name

    # Default to current directory for non-file sources
    if source_type in ("url", "data_uri", "string"):
        return Path.cwd() / out_name

    # For files, use same directory as input
    return Path(source).parent / out_name


@click.command()
@click.argument("input_source", type=str)
@click.argument("output_file", type=click.Path(path_type=Path), required=False)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    help="Output file path",
)
@click.option("--output-dir", type=click.Path(path_type=Path), help="Output directory")
@click.option(
    "-p", "--precision", type=int, default=6, help="Path coordinate precision"
)
@click.option("--preserve-styles", is_flag=True, help="Keep style metadata on paths")
@click.option("--suffix", default="_text2path", help="Output filename suffix")
@click.option("--system-fonts-only", is_flag=True, help="Only use system fonts")
@click.option(
    "--font-dir",
    type=click.Path(exists=True, path_type=Path),
    multiple=True,
    help="Additional font directories",
)
@click.option("--no-remote-fonts", is_flag=True, help="Disable remote font fetching")
@click.option("--print-fonts", is_flag=True, help="Print fonts used in SVG")
@click.option(
    "--format",
    "input_format",
    type=click.Choice(list(FORMAT_CHOICES.keys()), case_sensitive=False),
    default="auto",
    help="Force input format (default: auto-detect)",
)
@click.option(
    "--base64",
    "output_base64",
    is_flag=True,
    help="Output as base64-encoded data URI",
)
@click.option(
    "--all-svgs",
    "all_svgs",
    is_flag=True,
    hidden=True,  # Reserved for future batch conversion within single file
    help="Convert ALL SVGs in file (not just first) [not yet implemented]",
)
@click.option(
    "--no-size-limit",
    "no_size_limit",
    is_flag=True,
    help="Bypass file size limits (WARNING: may allow decompression bombs)",
)
@click.option(
    "--auto-download",
    "auto_download",
    is_flag=True,
    help="Auto-download missing fonts using fontget or fnt",
)
@click.option(
    "--validate",
    "validate_svg",
    is_flag=True,
    help="Validate input and output SVG using svg-matrix (requires Bun)",
)
@click.pass_context
def convert(
    ctx: click.Context,
    input_source: str,
    output_file: Path | None,
    output_path: Path | None,
    output_dir: Path | None,
    precision: int,
    preserve_styles: bool,
    suffix: str,
    system_fonts_only: bool,
    font_dir: tuple[Path, ...],
    no_remote_fonts: bool,
    print_fonts: bool,
    input_format: str,
    output_base64: bool,
    all_svgs: bool,
    no_size_limit: bool,
    auto_download: bool,
    validate_svg: bool,
) -> None:
    """Convert SVG text elements to paths.

    INPUT_SOURCE: Path to file, URL, or data URI string to convert.

    \b
    Supported input formats:
      - SVG files (.svg, .svgz)
      - HTML files with embedded SVG (.html, .htm)
      - CSS files with data URIs (.css)
      - Remote URLs (http://, https://)
      - Data URI strings (data:image/svg+xml;base64,...)
      - Python code with SVG strings (.py)
      - JavaScript/TypeScript code (.js, .ts, .jsx, .tsx)
      - Markdown with SVG blocks (.md)
      - reStructuredText (.rst)
      - JSON/CSV with escaped SVG
      - ePub ebooks (.epub)

    \b
    Examples:
      text2path convert input.svg -o output.svg
      text2path convert page.html -o page_converted.html
      text2path convert styles.css -o styles_converted.css
      text2path convert "https://example.com/icon.svg" -o icon.svg
      text2path convert 'data:image/svg+xml;base64,PHN2...' -o out.svg
    """
    config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Note: all_svgs is reserved for future batch conversion within single file
    _ = all_svgs  # Suppress unused variable warning

    # Get format hint if specified
    format_hint = FORMAT_CHOICES.get(input_format.lower())

    # Match input to handler using registry
    try:
        match = match_handler(input_source, format_hint)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None

    # Resolve output path
    out = _resolve_output_path(
        input_source,
        output_path or output_file,
        output_dir,
        suffix,
        match.source_type,
    )

    # Update config with CLI options
    if system_fonts_only:
        config.fonts.system_only = True
    if font_dir:
        config.fonts.custom_dirs = list(font_dir)
    if no_remote_fonts:
        config.fonts.remote = False
    if no_size_limit:
        config.security.ignore_size_limits = True

    # Create converter with optional auto-download and validation
    converter = Text2PathConverter(
        precision=precision,
        preserve_styles=preserve_styles,
        log_level=log_level,
        config=config,
        auto_download_fonts=auto_download,
        validate_svg=validate_svg,
    )

    # Show what we detected
    quiet = ctx.obj.get("quiet", False)
    if not quiet:
        console.print(
            f"[dim]Detected format:[/dim] {match.detected_format.name} "
            f"[dim](confidence: {match.confidence:.0%})[/dim]"
        )

    if print_fonts:
        # Just analyze fonts without converting
        _print_fonts_used(match.handler, input_source)
        return

    # Validate input if requested (only for file sources)
    input_valid = None
    if validate_svg and match.source_type == "file":
        with console.status("[bold green]Validating input SVG..."):
            from svg_text2path.tools.svg_validator import validate_svg_file

            input_validation = validate_svg_file(input_source)
            input_valid = input_validation.valid
            if not quiet:
                # Check if validation was skipped due to offline mode
                if input_validation.error and "offline mode" in input_validation.error:
                    console.print("[dim]⊘ Validation skipped (offline mode)[/dim]")
                elif input_valid:
                    console.print("[green]✓[/green] Input SVG is valid")
                else:
                    console.print("[yellow]⚠[/yellow] Input SVG has issues:")
                    for issue in input_validation.issues:
                        console.print(f"  - {issue.get('reason', str(issue))}")
                    if input_validation.error:
                        console.print(f"  - {input_validation.error}")

    # Parse input using handler
    with console.status("[bold green]Parsing input..."):
        try:
            # Set config on handler for size limit checking
            match.handler.config = config
            tree = match.handler.parse(input_source)
        except Exception as e:
            console.print(f"[red]Parse error:[/red] {e}")
            raise SystemExit(1) from None

    # Count text elements before conversion for reporting
    from svg_text2path.svg.parser import find_text_elements

    root = tree.getroot()
    if root is None:
        console.print("[red]Failed:[/red] Could not parse SVG root element")
        raise SystemExit(1)

    text_count = len(find_text_elements(root))

    # Perform conversion (convert_tree modifies tree in-place and returns it)
    with console.status("[bold green]Converting text to paths..."):
        try:
            converted_tree = converter.convert_tree(tree)
        except Exception as e:
            console.print(f"[red]Conversion error:[/red] {e}")
            raise SystemExit(1) from None

    # Count paths after conversion
    path_count = len(root.findall(".//{http://www.w3.org/2000/svg}path")) + len(
        root.findall(".//path")
    )

    # Serialize output
    with console.status("[bold green]Writing output..."):
        try:
            if output_base64:
                # Output as base64 data URI
                _write_base64_output(converted_tree, out)
            else:
                # Use handler's serialize for round-trip (HTML->HTML, CSS->CSS)
                match.handler.serialize(converted_tree, out)
        except Exception as e:
            console.print(f"[red]Write error:[/red] {e}")
            raise SystemExit(1) from None

    console.print(
        f"[green]Success:[/green] Converted {text_count} "
        f"text elements to {path_count} paths"
    )
    console.print(f"[blue]Output:[/blue] {out}")

    # Validate output if requested (only for SVG file outputs)
    if validate_svg and out.suffix.lower() in (".svg", ".svgz"):
        with console.status("[bold green]Validating output SVG..."):
            from svg_text2path.tools.svg_validator import validate_svg_file

            output_validation = validate_svg_file(out)
            if not quiet:
                # Check if validation was skipped due to offline mode
                if (
                    output_validation.error
                    and "offline mode" in output_validation.error
                ):
                    console.print(
                        "[dim]⊘ Output validation skipped (offline mode)[/dim]"
                    )
                elif output_validation.valid:
                    console.print("[green]✓[/green] Output SVG is valid")
                else:
                    console.print("[yellow]⚠[/yellow] Output SVG has issues:")
                    for issue in output_validation.issues:
                        console.print(f"  - {issue.get('reason', str(issue))}")
                    if output_validation.error:
                        console.print(f"  - {output_validation.error}")


def _print_fonts_used(handler: Any, source: str) -> None:
    """Analyze and print fonts used in SVG."""
    from svg_text2path.svg.parser import find_text_elements

    try:
        tree = handler.parse(source)
        root = tree.getroot()
        if root is None:
            console.print("[red]Failed:[/red] Could not parse SVG root element")
            raise SystemExit(1)

        text_elements = find_text_elements(root)
        fonts_used: set[str] = set()
        for elem in text_elements:
            font_family = elem.get("font-family", "sans-serif")
            fonts_used.add(font_family)

        console.print("[bold]Fonts used:[/bold]")
        for font in sorted(fonts_used):
            console.print(f"  - {font}")
    except Exception as e:
        console.print(f"[red]Error analyzing fonts:[/red] {e}")
        raise SystemExit(1) from None


def _write_base64_output(tree: Any, output_path: Path) -> None:
    """Write tree as base64 data URI to file."""
    import base64
    from io import BytesIO

    # Serialize to bytes
    buffer = BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    svg_bytes = buffer.getvalue()

    # Encode as base64 data URI
    b64 = base64.b64encode(svg_bytes).decode("ascii")
    data_uri = f"data:image/svg+xml;base64,{b64}"

    # Write to file
    output_path.write_text(data_uri)
