"""Auto-installer for external font tools.

Provides automatic installation of font discovery and conversion tools:
- fnt: Font finder utility (Linux/macOS bash script)
- nerdconvert: Nerd Fonts patcher (Node.js tool)
- FontGet: Font downloader (Windows only, binary)

Tools are installed to ~/.text2path/tools/{tool_name}/
"""

from __future__ import annotations

import shutil
from pathlib import Path

from svg_text2path.tools.external import (
    check_git_installed,
    check_npm_installed,
    run_command,
)


def get_tools_dir() -> Path:
    """Return ~/.text2path/tools/, creating if needed.

    Returns:
        Path to tools directory
    """
    tools_dir = Path.home() / ".text2path" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return tools_dir


def is_tool_available(tool_name: str) -> bool:
    """Check if tool is installed and executable.

    Args:
        tool_name: Name of tool to check ("fnt", "nerdconvert", "fontget")

    Returns:
        True if tool is installed and executable
    """
    tool_path = get_tool_path(tool_name)
    if tool_path is None:
        return False
    return tool_path.exists() and tool_path.is_file()


def get_tool_path(tool_name: str) -> Path | None:
    """Get expected path for installed tool.

    Args:
        tool_name: Name of tool

    Returns:
        Path to tool executable if installed, None if unknown tool
    """
    tools_dir = get_tools_dir()
    tool_name_lower = tool_name.lower()

    if tool_name_lower == "fnt":
        # fnt is a bash script in the repo root
        return tools_dir / "fnt" / "fnt"
    elif tool_name_lower == "nerdconvert":
        # nerdconvert uses npm, executable in node_modules/.bin
        return tools_dir / "nerdconvert" / "node_modules" / ".bin" / "nerdconvert"
    elif tool_name_lower == "fontget":
        # FontGet is Windows only, would be an .exe
        return tools_dir / "fontget" / "fontget.exe"
    else:
        return None


def install_fnt(target_dir: Path | None = None) -> Path | None:
    """Clone and install fnt (font finder utility).

    Args:
        target_dir: Directory to install to (default: ~/.text2path/tools/fnt)

    Returns:
        Path to fnt script if successful, None if failed

    Why: fnt is a simple bash script that can be cloned from GitHub
    """
    if not check_git_installed():
        return None

    if target_dir is None:
        target_dir = get_tools_dir() / "fnt"

    # If already installed, return path
    fnt_script = target_dir / "fnt"
    if fnt_script.exists():
        return fnt_script

    # Clone the repository
    repo_url = "https://github.com/alexmyczko/fnt.git"

    # Remove existing directory if it exists but is incomplete
    if target_dir.exists():
        shutil.rmtree(target_dir)

    result = run_command(
        ["git", "clone", "--depth=1", repo_url, str(target_dir)],
        timeout=120,
    )

    if not result.success:
        return None

    # Make the script executable
    if fnt_script.exists():
        fnt_script.chmod(0o755)
        return fnt_script

    return None


def install_nerdconvert(target_dir: Path | None = None) -> Path | None:
    """Install nerdconvert via npm.

    Args:
        target_dir: Directory to install to (default: ~/.text2path/tools/nerdconvert)

    Returns:
        Path to nerdconvert executable if successful, None if failed

    Why: nerdconvert is a Node.js tool installed via npm
    """
    if not check_npm_installed():
        return None

    if target_dir is None:
        target_dir = get_tools_dir() / "nerdconvert"

    target_dir.mkdir(parents=True, exist_ok=True)

    # Check if already installed
    nerdconvert_bin = target_dir / "node_modules" / ".bin" / "nerdconvert"
    if nerdconvert_bin.exists():
        return nerdconvert_bin

    # Initialize npm project if needed
    package_json = target_dir / "package.json"
    if not package_json.exists():
        result = run_command(
            ["npm", "init", "-y"],
            cwd=target_dir,
            timeout=60,
        )
        if not result.success:
            return None

    # Install nerdconvert
    result = run_command(
        ["npm", "install", "nerdconvert"],
        cwd=target_dir,
        timeout=300,
    )

    if result.success and nerdconvert_bin.exists():
        return nerdconvert_bin

    return None


def install_fontget(target_dir: Path | None = None) -> Path | None:
    """Install FontGet (Windows only).

    Args:
        target_dir: Directory to install to (default: ~/.text2path/tools/fontget)

    Returns:
        Path to fontget executable if successful, None if failed

    Why: FontGet is a Windows-only tool. On other platforms, returns None.
    """
    import platform

    if platform.system() != "Windows":
        # FontGet is Windows-only
        return None

    if target_dir is None:
        target_dir = get_tools_dir() / "fontget"

    target_dir.mkdir(parents=True, exist_ok=True)

    fontget_exe = target_dir / "fontget.exe"
    if fontget_exe.exists():
        return fontget_exe

    # Download from GitHub releases
    # Using curl or wget to download the latest release
    release_url = (
        "https://github.com/Graphixa/FontGet/releases/latest/download/fontget.exe"
    )

    # Try curl first
    result = run_command(
        ["curl", "-L", "-o", str(fontget_exe), release_url],
        timeout=120,
    )

    if result.success and fontget_exe.exists():
        return fontget_exe

    # Try wget as fallback
    result = run_command(
        ["wget", "-O", str(fontget_exe), release_url],
        timeout=120,
    )

    if result.success and fontget_exe.exists():
        return fontget_exe

    return None


def ensure_tool_installed(tool_name: str) -> Path | None:
    """Install tool if missing, return path to executable.

    Args:
        tool_name: Name of tool ("fnt", "nerdconvert", "fontget")

    Returns:
        Path to tool executable if available/installed, None if unavailable

    Why: Provides single entry point for tool installation
    """
    tool_name_lower = tool_name.lower()

    # Check if already installed
    if is_tool_available(tool_name):
        return get_tool_path(tool_name)

    # Install based on tool name
    if tool_name_lower == "fnt":
        return install_fnt()
    elif tool_name_lower == "nerdconvert":
        return install_nerdconvert()
    elif tool_name_lower == "fontget":
        return install_fontget()
    else:
        return None


def list_installed_tools() -> dict[str, Path | None]:
    """List all installed tools and their paths.

    Returns:
        Dictionary mapping tool name to path (None if not installed)
    """
    tools = ["fnt", "nerdconvert", "fontget"]
    return {
        tool: get_tool_path(tool) if is_tool_available(tool) else None for tool in tools
    }
