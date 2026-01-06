"""Auto-installer for external font tools.

This module handles automatic installation of external font tools to
~/.text2path/tools/. Supports FontGet (Windows), fnt (Linux/macOS), and
nerdconvert (Node.js).
"""

import os
import platform
import shutil
import subprocess
from pathlib import Path


def get_tools_dir() -> Path:
    """Return ~/.text2path/tools/, creating if needed.

    Returns:
        Path: Path to the tools directory (~/.text2path/tools/)
    """
    tools_dir = Path.home() / ".text2path" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return tools_dir


def is_tool_available(tool_name: str) -> bool:
    """Check if tool is installed and executable.

    Args:
        tool_name: Name of the tool to check (fontget, fnt, nerdconvert)

    Returns:
        bool: True if tool is installed and executable, False otherwise
    """
    tools_dir = get_tools_dir()
    tool_dir = tools_dir / tool_name

    if not tool_dir.exists():
        return False

    # Check for executable based on tool type
    if tool_name == "fontget":
        # FontGet is Windows only
        if platform.system() != "Windows":
            return False
        exe_path = tool_dir / "FontGet.exe"
        return exe_path.exists() and exe_path.is_file()
    elif tool_name == "fnt":
        # fnt is a bash script
        script_path = tool_dir / "fnt"
        return (
            script_path.exists()
            and script_path.is_file()
            and os.access(script_path, os.X_OK)
        )
    elif tool_name == "nerdconvert":
        # nerdconvert is a Node.js tool
        exe_path = tool_dir / "node_modules" / ".bin" / "nerdconvert"
        return exe_path.exists() and exe_path.is_file()

    return False


def install_fnt(target_dir: Path) -> Path | None:
    """Clone fnt repo, it's a bash script. Returns path to fnt script.

    Args:
        target_dir: Directory to install fnt into

    Returns:
        Optional[Path]: Path to fnt script if successful, None if installation failed
    """
    # fnt is Linux/macOS only
    if platform.system() == "Windows":
        return None

    # Check if git is available
    if shutil.which("git") is None:
        return None

    try:
        # Clone the repository
        subprocess.run(
            ["git", "clone", "https://github.com/alexmyczko/fnt.git", str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # The fnt script should be in the root of the cloned repo
        fnt_script = target_dir / "fnt"

        if not fnt_script.exists():
            return None

        # Make it executable
        fnt_script.chmod(0o755)

        return fnt_script

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


def install_nerdconvert(target_dir: Path) -> Path | None:
    """Install nerdconvert via npm in target_dir. Returns path to nerdconvert.

    Args:
        target_dir: Directory to install nerdconvert into

    Returns:
        Optional[Path]: Path to nerdconvert executable if successful,
            None if installation failed
    """
    # Check if npm is available
    if shutil.which("npm") is None:
        return None

    try:
        # Create package.json in target_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Install nerdconvert as a local package
        subprocess.run(
            ["npm", "install", "nerdconvert"],
            cwd=str(target_dir),
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Path to the nerdconvert executable
        nerdconvert_path = target_dir / "node_modules" / ".bin" / "nerdconvert"

        if not nerdconvert_path.exists():
            return None

        return nerdconvert_path

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


def install_fontget(target_dir: Path) -> Path | None:
    """Download and extract FontGet from GitHub releases (Windows only).

    Args:
        target_dir: Directory to install FontGet into

    Returns:
        Optional[Path]: Path to FontGet.exe if successful, None if installation failed
    """
    # FontGet is Windows only
    if platform.system() != "Windows":
        return None

    # This would require downloading from GitHub releases
    # Since we don't have a reliable way to download and extract
    # without additional dependencies, we return None for now.
    # This can be implemented later with requests/urllib.
    return None


def ensure_tool_installed(tool_name: str) -> Path | None:
    """Install tool if missing, return path to executable or None if unavailable.

    Args:
        tool_name: Name of the tool to install (fontget, fnt, nerdconvert)

    Returns:
        Optional[Path]: Path to the tool executable if installed successfully,
            None if unavailable
    """
    # Check if already installed
    if is_tool_available(tool_name):
        tools_dir = get_tools_dir()
        tool_dir = tools_dir / tool_name

        # Return path to executable
        if tool_name == "fontget":
            return tool_dir / "FontGet.exe"
        elif tool_name == "fnt":
            return tool_dir / "fnt"
        elif tool_name == "nerdconvert":
            return tool_dir / "node_modules" / ".bin" / "nerdconvert"

    # Not installed, try to install
    tools_dir = get_tools_dir()
    target_dir = tools_dir / tool_name

    if tool_name == "fnt":
        return install_fnt(target_dir)
    elif tool_name == "nerdconvert":
        return install_nerdconvert(target_dir)
    elif tool_name == "fontget":
        return install_fontget(target_dir)

    return None
