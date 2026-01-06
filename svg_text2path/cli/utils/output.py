"""Output formatting utilities for CLI."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from svg_text2path import ConversionResult

console = Console()
error_console = Console(stderr=True)


def format_result(result: ConversionResult, verbose: bool = False) -> None:
    """Format and print conversion result.

    Args:
        result: ConversionResult to format
        verbose: Whether to show detailed output
    """
    if result.success:
        console.print("[green]Success[/green]")
        console.print(f"  Text elements: {result.text_count}")
        console.print(f"  Path elements: {result.path_count}")
        console.print(f"  Output: {result.output}")
    else:
        error_console.print("[red]Failed[/red]")
        for error in result.errors:
            error_console.print(f"  [red]Error:[/red] {error}")

    if result.warnings:
        for warning in result.warnings:
            console.print(f"  [yellow]Warning:[/yellow] {warning}")


def format_error(message: str, exception: Exception | None = None) -> None:
    """Format and print an error message.

    Args:
        message: Error message
        exception: Optional exception
    """
    error_console.print(f"[red]Error:[/red] {message}")
    if exception:
        error_console.print(f"[dim]{type(exception).__name__}: {exception}[/dim]")


def format_table(
    title: str,
    columns: list[tuple[str, str]],
    rows: list[list[Any]],
) -> None:
    """Create and print a formatted table.

    Args:
        title: Table title
        columns: List of (name, style) tuples for columns
        rows: List of row data
    """
    table = Table(title=title)

    for name, style in columns:
        table.add_column(name, style=style)

    for row in rows:
        table.add_row(*[str(cell) for cell in row])

    console.print(table)


def print_panel(content: str, title: str = "", style: str = "blue") -> None:
    """Print content in a panel.

    Args:
        content: Panel content
        title: Panel title
        style: Border style color
    """
    console.print(Panel(content, title=title, border_style=style))


def print_progress_summary(
    total: int,
    success: int,
    failed: int,
    skipped: int = 0,
) -> None:
    """Print batch processing summary.

    Args:
        total: Total items processed
        success: Successful items
        failed: Failed items
        skipped: Skipped items
    """
    console.print()
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Total: {total}")
    console.print(f"  [green]Success:[/green] {success}")
    if failed:
        console.print(f"  [red]Failed:[/red] {failed}")
    if skipped:
        console.print(f"  [yellow]Skipped:[/yellow] {skipped}")
