"""Dependency checking command for text2path CLI."""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.table import Table

from svg_text2path.tools.dependencies import (
    DependencyStatus,
    DependencyType,
    verify_all_dependencies,
)

console = Console()
error_console = Console(stderr=True)


@click.command(name="deps")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show all dependencies including OK ones",
)
@click.option(
    "--python-only",
    is_flag=True,
    help="Only check Python packages",
)
@click.option(
    "--system-only",
    is_flag=True,
    help="Only check system tools",
)
@click.option(
    "--npm-only",
    is_flag=True,
    help="Only check npm packages",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit with error code if any dependency is missing",
)
def deps(
    show_all: bool,
    python_only: bool,
    system_only: bool,
    npm_only: bool,
    output_json: bool,
    strict: bool,
) -> None:
    """Check and report on all dependencies.

    Verifies Python packages, system tools, and npm packages required
    for full functionality of text2path.

    Examples:

        text2path deps              # Show missing dependencies

        text2path deps --all        # Show all dependencies

        text2path deps --strict     # Exit with error if missing

        text2path deps --json       # Output as JSON
    """
    # Determine what to check
    check_python = not (system_only or npm_only)
    check_system = not (python_only or npm_only)
    check_npm = not (python_only or system_only)

    # Run verification
    report = verify_all_dependencies(
        check_python=check_python,
        check_system=check_system,
        check_npm=check_npm,
    )

    if output_json:
        _output_json(report)
    else:
        _output_rich(report, show_all)

    # Exit with error code if strict mode and dependencies missing
    if strict:
        if not report.all_required_ok:
            sys.exit(1)
        elif report.missing_optional:
            sys.exit(2)  # Different code for missing optional


def _output_json(report) -> None:
    """Output report as JSON."""
    import json

    data = {
        "all_required_ok": report.all_required_ok,
        "all_ok": report.all_ok,
        "python_packages": [
            {
                "name": dep.name,
                "status": dep.status.value,
                "required": dep.required,
                "version": dep.version,
                "min_version": dep.min_version,
                "install_hint": dep.install_hint,
                "feature": dep.feature,
                "error": dep.error,
            }
            for dep in report.python_packages
        ],
        "system_tools": [
            {
                "name": dep.name,
                "status": dep.status.value,
                "required": dep.required,
                "version": dep.version,
                "path": str(dep.path) if dep.path else None,
                "install_hint": dep.install_hint,
                "feature": dep.feature,
                "error": dep.error,
            }
            for dep in report.system_tools
        ],
        "npm_packages": [
            {
                "name": dep.name,
                "status": dep.status.value,
                "required": dep.required,
                "version": dep.version,
                "install_hint": dep.install_hint,
                "feature": dep.feature,
                "error": dep.error,
            }
            for dep in report.npm_packages
        ],
    }
    console.print_json(json.dumps(data, indent=2))


def _output_rich(report, show_all: bool) -> None:
    """Output report using rich formatting."""
    # Summary banner
    if report.all_required_ok:
        console.print("[bold green]All required dependencies satisfied.[/bold green]")
        if report.missing_optional:
            n_missing = len(report.missing_optional)
            msg = f"[yellow]{n_missing} optional dependencies missing.[/yellow]"
            console.print(msg)
    else:
        n_missing = len(report.missing_required)
        msg = f"[bold red]Missing {n_missing} required dependencies![/bold red]"
        console.print(msg)

    # Python packages table
    if report.python_packages:
        _print_table(
            "Python Packages",
            report.python_packages,
            show_all,
            DependencyType.PYTHON_PACKAGE,
        )

    # System tools table
    if report.system_tools:
        _print_table(
            "System Tools",
            report.system_tools,
            show_all,
            DependencyType.SYSTEM_TOOL,
        )

    # npm packages table
    if report.npm_packages:
        _print_table(
            "npm Packages",
            report.npm_packages,
            show_all,
            DependencyType.NPM_PACKAGE,
        )

    # Install hints for missing dependencies
    missing = report.missing_required + report.missing_optional
    if missing and not show_all:
        console.print("\n[bold]Installation hints:[/bold]")
        for dep in missing:
            if dep.install_hint:
                req_str = (
                    "[red](required)[/red]"
                    if dep.required
                    else "[yellow](optional)[/yellow]"
                )
                console.print(f"  {dep.name} {req_str}: [dim]{dep.install_hint}[/dim]")


def _print_table(title: str, deps, show_all: bool, dep_type: DependencyType) -> None:
    """Print a table of dependencies."""
    # Filter to show only relevant entries
    if not show_all:
        deps = [d for d in deps if d.status != DependencyStatus.OK]
        if not deps:
            return

    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Version")
    table.add_column("Required", justify="center")
    table.add_column("Feature/Purpose")

    for dep in deps:
        # Status styling
        if dep.status == DependencyStatus.OK:
            status = "[green]OK[/green]"
        elif dep.status == DependencyStatus.MISSING:
            status = (
                "[red]MISSING[/red]" if dep.required else "[yellow]MISSING[/yellow]"
            )
        elif dep.status == DependencyStatus.VERSION_MISMATCH:
            status = "[yellow]VERSION[/yellow]"
        else:
            status = "[red]ERROR[/red]"

        # Version column
        version = dep.version or "-"
        if dep.min_version and dep.status == DependencyStatus.VERSION_MISMATCH:
            version = f"{version} (need {dep.min_version})"

        # Required column
        required = "[green]Yes[/green]" if dep.required else "[dim]No[/dim]"

        # Feature column
        feature = dep.feature or "-"
        if dep.error:
            feature = f"[red]{dep.error}[/red]"

        table.add_row(dep.name, status, version, required, feature)

    console.print(table)
