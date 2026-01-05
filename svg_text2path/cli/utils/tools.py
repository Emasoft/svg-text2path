"""External tool management for CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

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

    # Extract
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest.parent)

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
