"""Centralized dependency verification for svg-text2path.

This module provides comprehensive dependency checking for both
Python packages and external system tools. It can be used from
both CLI and programmatic contexts.

Example:
    >>> from svg_text2path.tools.dependencies import verify_all_dependencies
    >>> status = verify_all_dependencies()
    >>> if not status.all_required_ok:
    ...     print("Missing required dependencies!")
    ...     for dep in status.missing_required:
    ...         print(f"  - {dep.name}: {dep.install_hint}")
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DependencyType(Enum):
    """Type of dependency."""

    PYTHON_PACKAGE = "python"
    SYSTEM_TOOL = "system"
    NPM_PACKAGE = "npm"


class DependencyStatus(Enum):
    """Status of a dependency check."""

    OK = "ok"
    MISSING = "missing"
    VERSION_MISMATCH = "version_mismatch"
    ERROR = "error"


@dataclass
class DependencyInfo:
    """Information about a single dependency."""

    name: str
    """Name of the dependency."""

    dep_type: DependencyType
    """Type of dependency (python, system, npm)."""

    required: bool
    """Whether this dependency is required (vs optional)."""

    status: DependencyStatus = DependencyStatus.MISSING
    """Current status of the dependency."""

    version: str | None = None
    """Detected version if available."""

    min_version: str | None = None
    """Minimum required version if applicable."""

    path: Path | None = None
    """Path to the dependency if applicable."""

    error: str | None = None
    """Error message if status is ERROR."""

    install_hint: str = ""
    """Hint for installing the dependency."""

    feature: str = ""
    """Feature that requires this dependency."""


@dataclass
class DependencyReport:
    """Full report of all dependency checks."""

    python_packages: list[DependencyInfo] = field(default_factory=list)
    """Status of Python package dependencies."""

    system_tools: list[DependencyInfo] = field(default_factory=list)
    """Status of system tool dependencies."""

    npm_packages: list[DependencyInfo] = field(default_factory=list)
    """Status of npm package dependencies."""

    @property
    def all_dependencies(self) -> list[DependencyInfo]:
        """Get all dependencies as a flat list."""
        return self.python_packages + self.system_tools + self.npm_packages

    @property
    def missing_required(self) -> list[DependencyInfo]:
        """Get list of missing required dependencies."""
        return [
            dep
            for dep in self.all_dependencies
            if dep.required and dep.status != DependencyStatus.OK
        ]

    @property
    def missing_optional(self) -> list[DependencyInfo]:
        """Get list of missing optional dependencies."""
        return [
            dep
            for dep in self.all_dependencies
            if not dep.required and dep.status != DependencyStatus.OK
        ]

    @property
    def all_required_ok(self) -> bool:
        """Check if all required dependencies are satisfied."""
        return len(self.missing_required) == 0

    @property
    def all_ok(self) -> bool:
        """Check if all dependencies (required and optional) are satisfied."""
        return all(dep.status == DependencyStatus.OK for dep in self.all_dependencies)


# =============================================================================
# Python Package Checking
# =============================================================================


def check_python_package(
    name: str,
    import_name: str | None = None,
    min_version: str | None = None,
) -> DependencyInfo:
    """Check if a Python package is installed.

    Args:
        name: Package name (as in pip/pyproject.toml).
        import_name: Import name if different from package name.
        min_version: Minimum required version.

    Returns:
        DependencyInfo with status and version details.
    """
    import_name = import_name or name.replace("-", "_")

    info = DependencyInfo(
        name=name,
        dep_type=DependencyType.PYTHON_PACKAGE,
        required=True,  # Will be set by caller
        min_version=min_version,
        install_hint=f"pip install {name}",
    )

    # Check if module can be found
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        info.status = DependencyStatus.MISSING
        return info

    # Module found, try to get version
    try:
        module = importlib.import_module(import_name)
        version = getattr(module, "__version__", None)
        if version is None:
            # Try importlib.metadata as fallback
            try:
                from importlib.metadata import version as get_version

                version = get_version(name)
            except Exception:
                pass

        info.version = version
        info.status = DependencyStatus.OK

        # Check version if required
        if min_version and version and not _version_satisfies(version, min_version):
            info.status = DependencyStatus.VERSION_MISMATCH
            info.error = f"Version {version} < {min_version}"

    except Exception as e:
        info.status = DependencyStatus.ERROR
        info.error = str(e)

    return info


def _version_satisfies(current: str, minimum: str) -> bool:
    """Check if current version satisfies minimum requirement.

    Simple version comparison - handles semver-like versions.
    """
    try:
        # Strip any non-numeric prefixes (e.g., 'v1.0.0' -> '1.0.0')
        current = current.lstrip("v")
        minimum = minimum.lstrip("v")

        # Split into parts
        current_parts = [int(x) for x in current.split(".")[:3]]
        min_parts = [int(x) for x in minimum.split(".")[:3]]

        # Pad to same length
        while len(current_parts) < 3:
            current_parts.append(0)
        while len(min_parts) < 3:
            min_parts.append(0)

        return current_parts >= min_parts
    except (ValueError, AttributeError):
        # Can't parse, assume OK
        return True


# =============================================================================
# System Tool Checking
# =============================================================================


def check_system_tool(
    name: str,
    command: str | None = None,
    version_flag: str = "--version",
    version_parser: Callable[[str], str | None] | None = None,
) -> DependencyInfo:
    """Check if a system tool is installed and available.

    Args:
        name: Display name of the tool.
        command: Command to check (defaults to name).
        version_flag: Flag to get version (default: --version).
        version_parser: Optional function to extract version from output.

    Returns:
        DependencyInfo with status and path details.
    """
    command = command or name

    info = DependencyInfo(
        name=name,
        dep_type=DependencyType.SYSTEM_TOOL,
        required=False,  # Will be set by caller
    )

    # Check if command exists in PATH
    path = shutil.which(command)
    if path is None:
        info.status = DependencyStatus.MISSING
        _set_tool_install_hint(info, name)
        return info

    info.path = Path(path)
    info.status = DependencyStatus.OK

    # Try to get version
    try:
        result = subprocess.run(
            [command, version_flag],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout or result.stderr

        if version_parser:
            info.version = version_parser(output)
        else:
            # Try to extract first version-like string
            import re

            match = re.search(r"(\d+\.\d+(?:\.\d+)?)", output)
            if match:
                info.version = match.group(1)

    except Exception:
        # Version detection failed, but tool exists
        pass

    return info


def _set_tool_install_hint(info: DependencyInfo, name: str) -> None:
    """Set appropriate install hint based on platform and tool."""
    platform = sys.platform

    hints = {
        "fc-match": {
            "darwin": "brew install fontconfig",
            "linux": "apt install fontconfig  # or yum install fontconfig",
            "win32": "Download from freedesktop.org or use WSL",
        },
        "fc-list": {
            "darwin": "brew install fontconfig",
            "linux": "apt install fontconfig",
            "win32": "Download from freedesktop.org or use WSL",
        },
        "node": {
            "darwin": "brew install node  # or: nvm install --lts",
            "linux": "apt install nodejs  # or: nvm install --lts",
            "win32": "Download from nodejs.org or: winget install OpenJS.NodeJS",
        },
        "npm": {
            "darwin": "Comes with Node.js installation",
            "linux": "Comes with Node.js installation",
            "win32": "Comes with Node.js installation",
        },
        "npx": {
            "darwin": "Comes with npm (Node.js installation)",
            "linux": "Comes with npm (Node.js installation)",
            "win32": "Comes with npm (Node.js installation)",
        },
        "inkscape": {
            "darwin": "brew install --cask inkscape",
            "linux": "apt install inkscape  # or flatpak install inkscape",
            "win32": "Download from inkscape.org or: winget install Inkscape.Inkscape",
        },
        "git": {
            "darwin": "brew install git  # or: xcode-select --install",
            "linux": "apt install git",
            "win32": "Download from git-scm.com or: winget install Git.Git",
        },
        "magick": {
            "darwin": "brew install imagemagick",
            "linux": "apt install imagemagick",
            "win32": "Download from imagemagick.org",
        },
    }

    tool_hints = hints.get(name, {})
    info.install_hint = tool_hints.get(platform, f"Install {name} for your platform")


# =============================================================================
# npm Package Checking
# =============================================================================


def check_npm_package(
    name: str,
    global_check: bool = False,
) -> DependencyInfo:
    """Check if an npm package is installed.

    Args:
        name: npm package name.
        global_check: Check global installation instead of local.

    Returns:
        DependencyInfo with status details.
    """
    info = DependencyInfo(
        name=name,
        dep_type=DependencyType.NPM_PACKAGE,
        required=False,
        install_hint=f"npm install {'--global ' if global_check else ''}{name}",
    )

    # First check if npm is available
    if shutil.which("npm") is None:
        info.status = DependencyStatus.ERROR
        info.error = "npm not installed"
        return info

    try:
        cmd = ["npm", "list", name]
        if global_check:
            cmd.append("--global")
        cmd.append("--depth=0")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and name in result.stdout:
            info.status = DependencyStatus.OK
            # Try to extract version
            import re

            match = re.search(rf"{name}@([\d.]+)", result.stdout)
            if match:
                info.version = match.group(1)
        else:
            info.status = DependencyStatus.MISSING

    except Exception as e:
        info.status = DependencyStatus.ERROR
        info.error = str(e)

    return info


# =============================================================================
# Main Verification Functions
# =============================================================================

# Define required and optional dependencies
REQUIRED_PYTHON_PACKAGES = [
    ("fonttools", "fontTools", "4.60.0"),
    ("uharfbuzz", None, "0.52.0"),
    ("python-bidi", "bidi", "0.6.0"),
    ("numpy", None, "2.0.0"),
    ("pillow", "PIL", "12.0.0"),
    ("svg-path", "svg.path", "7.0"),
    ("defusedxml", None, "0.7.0"),
    ("pyyaml", "yaml", "6.0"),
    ("click", None, "8.0"),
    ("rich", None, "13.0"),
]

OPTIONAL_PYTHON_PACKAGES = [
    ("lxml", None, "5.0", "Faster XML parsing"),
    ("beautifulsoup4", "bs4", "4.12", "HTML parsing"),
]

REQUIRED_SYSTEM_TOOLS: list[tuple[str, str, str]] = []  # All tools are optional

OPTIONAL_SYSTEM_TOOLS = [
    ("fc-match", "Font matching (fontconfig)", "Font resolution"),
    ("fc-list", "Font listing (fontconfig)", "Font discovery"),
    ("node", "Node.js runtime", "Visual comparison (Chrome rendering)"),
    ("npm", "Node package manager", "npm package installation"),
    ("npx", "npm package executor", "Running svg-bbox"),
    ("inkscape", "Inkscape vector editor", "Reference rendering"),
    ("git", "Git version control", "Tool installation"),
    ("magick", "ImageMagick", "Image processing"),
]

OPTIONAL_NPM_PACKAGES = [
    ("svg-bbox", "SVG bounding box comparison"),
]


def verify_python_dependencies() -> list[DependencyInfo]:
    """Verify all Python package dependencies.

    Returns:
        List of DependencyInfo for each Python package.
    """
    results: list[DependencyInfo] = []

    # Check required packages
    for pkg_name, import_name, min_version in REQUIRED_PYTHON_PACKAGES:
        info = check_python_package(pkg_name, import_name, min_version)
        info.required = True
        results.append(info)

    # Check optional packages
    for pkg_name, import_name, min_version, feature in OPTIONAL_PYTHON_PACKAGES:
        info = check_python_package(pkg_name, import_name, min_version)
        info.required = False
        info.feature = feature
        results.append(info)

    return results


def verify_system_dependencies() -> list[DependencyInfo]:
    """Verify all system tool dependencies.

    Returns:
        List of DependencyInfo for each system tool.
    """
    results: list[DependencyInfo] = []

    # Check required tools
    for tool_name, _description, feature in REQUIRED_SYSTEM_TOOLS:
        info = check_system_tool(tool_name)
        info.required = True
        info.feature = feature
        results.append(info)

    # Check optional tools
    for tool_name, _description, feature in OPTIONAL_SYSTEM_TOOLS:
        info = check_system_tool(tool_name)
        info.required = False
        info.feature = feature
        results.append(info)

    return results


def verify_npm_dependencies() -> list[DependencyInfo]:
    """Verify all npm package dependencies.

    Returns:
        List of DependencyInfo for each npm package.
    """
    results: list[DependencyInfo] = []

    for pkg_name, feature in OPTIONAL_NPM_PACKAGES:
        info = check_npm_package(pkg_name)
        info.required = False
        info.feature = feature
        results.append(info)

    return results


def verify_all_dependencies(
    check_python: bool = True,
    check_system: bool = True,
    check_npm: bool = True,
) -> DependencyReport:
    """Verify all dependencies and return comprehensive report.

    Args:
        check_python: Check Python packages (default: True).
        check_system: Check system tools (default: True).
        check_npm: Check npm packages (default: True).

    Returns:
        DependencyReport with all dependency statuses.

    Example:
        >>> report = verify_all_dependencies()
        >>> if not report.all_required_ok:
        ...     for dep in report.missing_required:
        ...         print(f"Missing: {dep.name} - {dep.install_hint}")
    """
    report = DependencyReport()

    if check_python:
        report.python_packages = verify_python_dependencies()

    if check_system:
        report.system_tools = verify_system_dependencies()

    if check_npm:
        report.npm_packages = verify_npm_dependencies()

    return report


def format_dependency_report(
    report: DependencyReport,
    show_ok: bool = False,
    use_color: bool = True,
) -> str:
    """Format dependency report as human-readable string.

    Args:
        report: DependencyReport to format.
        show_ok: Include OK dependencies in output.
        use_color: Use ANSI colors in output.

    Returns:
        Formatted string report.
    """
    lines: list[str] = []

    # Color codes
    if use_color:
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        RESET = "\033[0m"
        BOLD = "\033[1m"
    else:
        GREEN = YELLOW = RED = RESET = BOLD = ""

    def status_icon(dep: DependencyInfo) -> str:
        if dep.status == DependencyStatus.OK:
            return f"{GREEN}[OK]{RESET}"
        elif dep.status == DependencyStatus.MISSING:
            return (
                f"{RED}[MISSING]{RESET}"
                if dep.required
                else f"{YELLOW}[MISSING]{RESET}"
            )
        elif dep.status == DependencyStatus.VERSION_MISMATCH:
            return f"{YELLOW}[VERSION]{RESET}"
        else:
            return f"{RED}[ERROR]{RESET}"

    def format_section(title: str, deps: list[DependencyInfo]) -> None:
        if not deps:
            return

        relevant = [d for d in deps if show_ok or d.status != DependencyStatus.OK]
        if not relevant:
            if show_ok:
                lines.append(f"\n{BOLD}{title}:{RESET} All OK")
            return

        lines.append(f"\n{BOLD}{title}:{RESET}")
        for dep in relevant:
            icon = status_icon(dep)
            version_str = f" v{dep.version}" if dep.version else ""
            req_str = " (required)" if dep.required else " (optional)"

            line = f"  {icon} {dep.name}{version_str}{req_str}"

            if dep.feature:
                line += f" - {dep.feature}"

            lines.append(line)

            if dep.status != DependencyStatus.OK and dep.install_hint:
                lines.append(f"       Install: {dep.install_hint}")

            if dep.error:
                lines.append(f"       Error: {dep.error}")

    # Summary
    if report.all_required_ok:
        lines.append(f"{GREEN}{BOLD}All required dependencies satisfied.{RESET}")
    else:
        missing_count = len(report.missing_required)
        lines.append(
            f"{RED}{BOLD}Missing {missing_count} required dependencies!{RESET}"
        )

    # Sections
    format_section("Python Packages", report.python_packages)
    format_section("System Tools", report.system_tools)
    format_section("npm Packages", report.npm_packages)

    return "\n".join(lines)


def print_dependency_report(
    report: DependencyReport | None = None,
    show_ok: bool = False,
) -> None:
    """Print dependency report to stdout.

    Args:
        report: DependencyReport to print. If None, runs verification first.
        show_ok: Include OK dependencies in output.
    """
    if report is None:
        report = verify_all_dependencies()

    # Detect if terminal supports colors
    use_color = sys.stdout.isatty()

    print(format_dependency_report(report, show_ok=show_ok, use_color=use_color))


# =============================================================================
# Convenience Functions for Feature-Specific Checks
# =============================================================================


def check_visual_comparison_deps() -> tuple[bool, list[str]]:
    """Check dependencies needed for visual comparison feature.

    Returns:
        Tuple of (all_ok, list_of_missing_tool_names).
    """
    missing: list[str] = []

    # Node.js is required for Chrome rendering
    if shutil.which("node") is None:
        missing.append("node")

    # npx for running svg-bbox
    if shutil.which("npx") is None:
        missing.append("npx")

    return (len(missing) == 0, missing)


def check_font_resolution_deps() -> tuple[bool, list[str]]:
    """Check dependencies needed for advanced font resolution.

    Returns:
        Tuple of (all_ok, list_of_missing_tool_names).
    """
    missing: list[str] = []

    # fontconfig tools are optional but recommended
    if shutil.which("fc-match") is None:
        missing.append("fc-match")
    if shutil.which("fc-list") is None:
        missing.append("fc-list")

    # These are optional, so always return True
    return (True, missing)


def check_reference_rendering_deps() -> tuple[bool, list[str]]:
    """Check dependencies needed for Inkscape reference rendering.

    Returns:
        Tuple of (all_ok, list_of_missing_tool_names).
    """
    missing: list[str] = []

    if shutil.which("inkscape") is None:
        missing.append("inkscape")

    return (len(missing) == 0, missing)
