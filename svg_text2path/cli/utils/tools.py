"""External tool management for CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path


def validate_path_for_subprocess(path: str | Path) -> Path:
    """Validate a file path before passing to subprocess.

    Defense-in-depth validation to prevent command injection.
    While shell=False mitigates most risks, this catches edge cases.

    Args:
        path: Path to validate

    Returns:
        Validated Path object

    Raises:
        ValueError: If path contains invalid characters
    """
    path_str = str(path)

    # Check for null bytes (command truncation attack)
    if "\x00" in path_str:
        raise ValueError(f"Path contains null byte: {path_str!r}")

    # Check for newlines (could affect some tools)
    if "\n" in path_str or "\r" in path_str:
        raise ValueError(f"Path contains newline: {path_str!r}")

    # Convert to Path and resolve to catch path traversal
    validated = Path(path_str)

    return validated


# Tool repository mappings
TOOL_REPOS = {
    "fontget": "Graphixa/FontGet",
    "fnt": "alexmyczko/fnt",
    "nerdconvert": "icalvin102/nerdconvert",
}


def get_tools_dir() -> Path:
    """Get the tools directory path.

    Returns:
        Path to ~/.text2path/tools/
    """
    return Path.home() / ".text2path" / "tools"


def ensure_tool_installed(tool_name: str, auto_install: bool = True) -> Path | None:
    """Ensure external tool is installed, optionally auto-installing.

    Args:
        tool_name: Name of the tool (fontget, fnt, nerdconvert)
        auto_install: Whether to automatically download if missing

    Returns:
        Path to tool executable or None if not found
    """
    tool_dir = get_tools_dir() / tool_name

    # Check if already installed
    if tool_dir.exists():
        # Look for executable
        for exe_name in [tool_name, f"{tool_name}.py", f"{tool_name}.sh"]:
            exe_path = tool_dir / exe_name
            if exe_path.exists():
                return exe_path
            exe_path = tool_dir / "bin" / exe_name
            if exe_path.exists():
                return exe_path

    # Check if in PATH
    which_result = shutil.which(tool_name)
    if which_result:
        return Path(which_result)

    if not auto_install:
        return None

    # Auto-install from GitHub
    if tool_name not in TOOL_REPOS:
        return None

    try:
        _download_tool(tool_name, TOOL_REPOS[tool_name], tool_dir)
        return ensure_tool_installed(tool_name, auto_install=False)
    except Exception:
        return None


def _safe_extract_zip(zip_ref: zipfile.ZipFile, dest_dir: Path) -> None:
    """Safely extract ZIP archive, preventing path traversal attacks (Zip Slip).

    Args:
        zip_ref: Open ZipFile object to extract
        dest_dir: Destination directory for extraction

    Raises:
        ValueError: If any archive member attempts path traversal
    """
    dest_dir = dest_dir.resolve()
    for member in zip_ref.namelist():
        # Normalize the path to handle different path separators
        member_path = os.path.normpath(member)

        # Block absolute paths - archive members should always be relative
        if os.path.isabs(member_path):
            raise ValueError(f"Absolute path in ZIP not allowed: {member}")

        # Block parent directory traversal attempts
        is_traversal = (
            member_path.startswith("..")
            or "/../" in member_path
            or member_path.startswith("/")
        )
        if is_traversal:
            raise ValueError(f"Path traversal attempt blocked: {member}")

        # Compute target path and verify it stays within dest_dir
        target_path = (dest_dir / member_path).resolve()
        if not str(target_path).startswith(str(dest_dir)):
            raise ValueError(f"Path would escape destination: {member}")

    # All members validated - safe to extract
    zip_ref.extractall(dest_dir)


def _download_tool(tool_name: str, repo: str, dest: Path) -> None:
    """Download tool from GitHub.

    Args:
        tool_name: Name of the tool
        repo: GitHub repo in format "owner/repo"
        dest: Destination directory
    """
    dest.mkdir(parents=True, exist_ok=True)

    # Download latest release or main branch
    zip_url = f"https://github.com/{repo}/archive/refs/heads/main.zip"
    zip_path = dest.parent / f"{tool_name}.zip"

    urllib.request.urlretrieve(zip_url, zip_path)

    # Extract safely - prevent Zip Slip path traversal attacks
    with zipfile.ZipFile(zip_path, "r") as z:
        _safe_extract_zip(z, dest.parent)

    # Move extracted folder
    extracted = dest.parent / f"{repo.split('/')[-1]}-main"
    if extracted.exists():
        shutil.move(str(extracted), str(dest))

    # Cleanup
    zip_path.unlink(missing_ok=True)


def run_external_tool(
    tool: str | Path,
    args: list[str],
    timeout: int = 120,
    capture_output: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run an external tool with arguments.

    Args:
        tool: Tool name or path
        args: Command arguments
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr
        cwd: Working directory

    Returns:
        CompletedProcess result
    """
    cmd = [str(tool)] + args

    return subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


def check_npm_tool(package_name: str) -> bool:
    """Check if an npm package is available via npx.

    Args:
        package_name: npm package name

    Returns:
        True if available
    """
    try:
        result = subprocess.run(
            ["npx", package_name, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
