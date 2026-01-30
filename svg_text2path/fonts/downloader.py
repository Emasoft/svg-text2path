"""Font download functionality using fontget and fnt tools.

Provides automatic font download when local fonts are missing.
Uses fontget (https://github.com/Graphixa/FontGet) as primary tool,
with fnt (https://github.com/alexmyczko/fnt) as fallback.

Both tools can install fonts from Google Fonts and other repositories.

Note: Requires network connectivity. Gracefully skips when offline.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
from dataclasses import dataclass


def is_network_available(timeout: float = 2.0) -> bool:
    """Check if network connectivity is available.

    Args:
        timeout: Connection timeout in seconds

    Returns:
        True if network is available, False otherwise
    """
    # Try multiple DNS servers for reliability
    test_hosts = [
        ("8.8.8.8", 53),  # Google DNS
        ("1.1.1.1", 53),  # Cloudflare DNS
    ]

    for host, port in test_hosts:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            return True
        except (OSError, TimeoutError):
            continue

    return False


@dataclass
class FontDownloadResult:
    """Result of a font download attempt."""

    success: bool
    font_family: str
    package_name: str | None = None
    tool_used: str | None = None
    message: str = ""


def is_fontget_available() -> bool:
    """Check if fontget tool is available on PATH."""
    return shutil.which("fontget") is not None


def is_fnt_available() -> bool:
    """Check if fnt tool is available on PATH."""
    return shutil.which("fnt") is not None


def get_available_tools() -> list[str]:
    """Get list of available font download tools."""
    tools = []
    if is_fontget_available():
        tools.append("fontget")
    if is_fnt_available():
        tools.append("fnt")
    return tools


# ============================================================================
# FontGet functions (primary tool)
# ============================================================================


def fontget_search(font_family: str) -> list[str]:
    """Search for fonts using fontget.

    Args:
        font_family: Font family name to search for (e.g., "EB Garamond")

    Returns:
        List of matching font names
    """
    if not is_fontget_available():
        return []

    try:
        result = subprocess.run(
            ["fontget", "search", font_family],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        # Parse output - fontget returns font names
        fonts = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            # Skip header lines and empty lines
            if line and not line.startswith("Loading") and not line.startswith("---"):
                # Extract font name from the output
                fonts.append(line)

        return fonts

    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return []


def fontget_install(font_name: str) -> FontDownloadResult:
    """Install a font using fontget.

    Args:
        font_name: Font name to install (e.g., "EB Garamond")

    Returns:
        FontDownloadResult indicating success or failure
    """
    if not is_fontget_available():
        url = "https://raw.githubusercontent.com/Graphixa/FontGet"
        install_cmd = f"curl -fsSL {url}/main/scripts/install.sh | sh"
        return FontDownloadResult(
            success=False,
            font_family=font_name,
            tool_used="fontget",
            message=f"fontget not available. Install with: {install_cmd}",
        )

    try:
        result = subprocess.run(
            ["fontget", "install", font_name],
            capture_output=True,
            text=True,
            timeout=120,  # Font downloads can take time
        )

        if result.returncode == 0:
            return FontDownloadResult(
                success=True,
                font_family=font_name,
                tool_used="fontget",
                message=f"Successfully installed '{font_name}' via fontget",
            )
        else:
            return FontDownloadResult(
                success=False,
                font_family=font_name,
                tool_used="fontget",
                message=f"fontget failed to install '{font_name}': {result.stderr}",
            )

    except subprocess.TimeoutExpired:
        return FontDownloadResult(
            success=False,
            font_family=font_name,
            tool_used="fontget",
            message=f"Timeout installing '{font_name}' via fontget",
        )
    except subprocess.SubprocessError as e:
        return FontDownloadResult(
            success=False,
            font_family=font_name,
            tool_used="fontget",
            message=f"Error installing '{font_name}' via fontget: {e}",
        )


# ============================================================================
# fnt functions (fallback tool)
# ============================================================================


def fnt_search(font_family: str) -> list[str]:
    """Search for font packages using fnt.

    Args:
        font_family: Font family name to search for (e.g., "EB Garamond")

    Returns:
        List of matching package names (e.g., ["fonts-ebgaramond", "google-ebgaramond"])
    """
    if not is_fnt_available():
        return []

    # Normalize search term - remove spaces, lowercase
    search_term = font_family.lower().replace(" ", "").replace("-", "")

    try:
        result = subprocess.run(
            ["fnt", "search", search_term],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        # Parse output - each line is a package name
        packages = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("Loading"):
                packages.append(line)

        return packages

    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return []


def fnt_install(package_name: str) -> FontDownloadResult:
    """Install a font package using fnt.

    Args:
        package_name: Package name from fnt search (e.g., "fonts-ebgaramond")

    Returns:
        FontDownloadResult indicating success or failure
    """
    if not is_fnt_available():
        return FontDownloadResult(
            success=False,
            font_family="",
            package_name=package_name,
            tool_used="fnt",
            message="fnt not available. Install with: brew install fnt",
        )

    try:
        result = subprocess.run(
            ["fnt", "install", package_name],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            return FontDownloadResult(
                success=True,
                font_family="",
                package_name=package_name,
                tool_used="fnt",
                message=f"Successfully installed '{package_name}' via fnt",
            )
        else:
            return FontDownloadResult(
                success=False,
                font_family="",
                package_name=package_name,
                tool_used="fnt",
                message=f"fnt failed to install '{package_name}': {result.stderr}",
            )

    except subprocess.TimeoutExpired:
        return FontDownloadResult(
            success=False,
            font_family="",
            package_name=package_name,
            tool_used="fnt",
            message=f"Timeout installing '{package_name}' via fnt",
        )
    except subprocess.SubprocessError as e:
        return FontDownloadResult(
            success=False,
            font_family="",
            package_name=package_name,
            tool_used="fnt",
            message=f"Error installing '{package_name}' via fnt: {e}",
        )


# ============================================================================
# Main auto-download function
# ============================================================================


def auto_download_font(font_family: str) -> FontDownloadResult:
    """Attempt to automatically download a missing font.

    Tries fontget first (better tool), then falls back to fnt.
    Gracefully skips when no network connectivity is available.

    Args:
        font_family: Font family name (e.g., "EB Garamond")

    Returns:
        FontDownloadResult indicating success or failure
    """
    # Check network availability first
    if not is_network_available():
        return FontDownloadResult(
            success=False,
            font_family=font_family,
            message=f"Cannot download '{font_family}': no network (offline)",
        )

    available_tools = get_available_tools()

    if not available_tools:
        fontget_url = "https://raw.githubusercontent.com/Graphixa/FontGet"
        msg = (
            "No font download tools available. Install fontget or fnt:\n"
            f"  fontget: curl -fsSL {fontget_url}/main/scripts/install.sh | sh\n"
            "  fnt: brew install fnt"
        )
        return FontDownloadResult(
            success=False,
            font_family=font_family,
            message=msg,
        )

    # Try fontget first (preferred)
    if is_fontget_available():
        # fontget can install by font name directly
        result = fontget_install(font_family)
        if result.success:
            return result
        # If failed, continue to try fnt

    # Fallback to fnt
    if is_fnt_available():
        # fnt needs package names, so search first
        packages = fnt_search(font_family)

        if not packages:
            return FontDownloadResult(
                success=False,
                font_family=font_family,
                tool_used="fnt",
                message=f"No font packages found for '{font_family}' in fnt",
            )

        # Score packages by relevance
        normalized = font_family.lower().replace(" ", "").replace("-", "")
        scored = []
        for pkg in packages:
            pkg_normalized = pkg.lower().replace("-", "").replace("_", "")
            score = 0
            if normalized in pkg_normalized:
                score += 10
            if pkg.startswith("google-"):
                score += 5  # Prefer Google Fonts
            if pkg.startswith("fonts-"):
                score += 3  # Then system fonts
            if "extra" not in pkg.lower():
                score += 2  # Prefer non-extra packages
            scored.append((score, pkg))

        # Sort by score descending
        scored.sort(key=lambda x: -x[0])

        # Try installing highest scored package first
        for _, package in scored[:3]:  # Try top 3 matches
            result = fnt_install(package)
            if result.success:
                result.font_family = font_family
                return result

        return FontDownloadResult(
            success=False,
            font_family=font_family,
            tool_used="fnt",
            message=f"Failed to install any matching package for '{font_family}'",
        )

    return FontDownloadResult(
        success=False,
        font_family=font_family,
        message=f"Could not install '{font_family}' - all tools failed",
    )


def refresh_font_cache() -> bool:
    """Refresh the system font cache after installing new fonts.

    Returns:
        True if refresh succeeded, False otherwise
    """
    # Try fc-cache first (fontconfig)
    fc_cache = shutil.which("fc-cache")
    if fc_cache:
        try:
            subprocess.run([fc_cache, "-f"], timeout=60, check=False)
            return True
        except subprocess.SubprocessError:
            pass

    return False
