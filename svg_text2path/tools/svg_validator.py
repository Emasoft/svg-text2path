"""SVG validation using @emasoft/svg-matrix via bunx.

This module provides SVG validation functionality by calling the svg-matrix
npm package through bunx (Bun's package runner).

Features:
- SVG 1.1 and SVG 2.0 compliance checking
- Automatic Bun installation if not present
- Both programmatic and CLI integration
- Graceful offline mode (skips validation when no network)
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def is_network_available(timeout: float = 2.0) -> bool:
    """Check if network connectivity is available.

    Attempts to connect to common DNS servers to verify network access.
    This is needed because bunx may need to download packages.

    Args:
        timeout: Connection timeout in seconds

    Returns:
        True if network is available, False otherwise
    """
    # Try multiple DNS servers for reliability
    test_hosts = [
        ("8.8.8.8", 53),  # Google DNS
        ("1.1.1.1", 53),  # Cloudflare DNS
        ("208.67.222.222", 53),  # OpenDNS
    ]

    for host, port in test_hosts:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            return True
        except (TimeoutError, OSError):
            continue

    return False


@dataclass
class SVGValidationResult:
    """Result of SVG validation."""

    valid: bool
    file_path: str | None = None
    issues: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.valid

    def __str__(self) -> str:
        """Human-readable representation."""
        if self.error:
            return f"Validation error: {self.error}"
        if self.valid:
            return "SVG is valid"
        issues_str = ", ".join(i.get("reason", str(i)) for i in self.issues)
        return f"SVG has issues: {issues_str}"


def is_bun_available() -> bool:
    """Check if Bun is available on PATH."""
    return shutil.which("bun") is not None


def ensure_bun_installed() -> bool:
    """Install Bun if not already installed.

    Returns:
        True if Bun is available (was already installed or installation succeeded)
    """
    if is_bun_available():
        return True

    print("Bun not found. Installing...")
    try:
        subprocess.run(
            "curl -fsSL https://bun.sh/install | bash",
            shell=True,
            check=True,
            capture_output=True,
        )
        print("Bun installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install Bun: {e}")
        return False


def validate_svg_file(
    svg_path: str | Path, skip_if_offline: bool = True
) -> SVGValidationResult:
    """Validate an SVG file using svg-matrix.

    Args:
        svg_path: Path to the SVG file
        skip_if_offline: If True, skip validation when no network is available
            (bunx may need to download packages). Default True.

    Returns:
        SVGValidationResult with validation status and any issues.
        If offline and skip_if_offline=True, returns valid=True with a note.
    """
    svg_path = Path(svg_path).resolve()

    if not svg_path.exists():
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error=f"File not found: {svg_path}",
        )

    # Check network availability (bunx may need to download packages)
    if skip_if_offline and not is_network_available():
        return SVGValidationResult(
            valid=True,  # Assume valid when offline
            file_path=str(svg_path),
            error="Validation skipped: no network available (offline mode)",
        )

    if not ensure_bun_installed():
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error="Bun installation failed - cannot run svg-matrix",
        )

    # Use CLI approach (more reliable than inline script)
    return _validate_with_cli(svg_path)


def validate_svg_string(
    svg_content: str, skip_if_offline: bool = True
) -> SVGValidationResult:
    """Validate SVG content from a string.

    Args:
        svg_content: SVG content as string
        skip_if_offline: If True, skip validation when no network is available
            (bunx may need to download packages). Default True.

    Returns:
        SVGValidationResult with validation status and any issues.
        If offline and skip_if_offline=True, returns valid=True with a note.
    """
    # Check network availability (bunx may need to download packages)
    if skip_if_offline and not is_network_available():
        return SVGValidationResult(
            valid=True,  # Assume valid when offline
            error="Validation skipped: no network available (offline mode)",
        )

    if not ensure_bun_installed():
        return SVGValidationResult(
            valid=False,
            error="Bun installation failed - cannot run svg-matrix",
        )

    # Write to temp file and validate
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as tmp:
        tmp.write(svg_content)
        tmp_path = Path(tmp.name)

    try:
        result = _validate_with_cli(tmp_path)
        result.file_path = None  # Clear temp file path
        return result
    finally:
        tmp_path.unlink(missing_ok=True)


def _validate_with_cli(svg_path: Path) -> SVGValidationResult:
    """Validate using svg-matrix CLI.

    Args:
        svg_path: Path to the SVG file

    Returns:
        SVGValidationResult
    """
    try:
        # Use svg-matrix info command - succeeds if SVG is parseable
        result = subprocess.run(
            ["bunx", "@emasoft/svg-matrix", "svg-matrix", "info", str(svg_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return SVGValidationResult(
                valid=True,
                file_path=str(svg_path),
            )
        else:
            # Parse error message from stderr
            error_msg = result.stderr.strip() or result.stdout.strip()
            issues = []
            if error_msg:
                issues.append({"reason": error_msg})

            return SVGValidationResult(
                valid=False,
                file_path=str(svg_path),
                issues=issues,
            )

    except subprocess.TimeoutExpired:
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error="Validation timed out (30s)",
        )
    except FileNotFoundError:
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error="bunx command not found - is Bun installed?",
        )
    except Exception as e:
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error=str(e),
        )


def _validate_with_script(svg_path: Path) -> SVGValidationResult:
    """Validate using inline JS script (alternative method).

    Args:
        svg_path: Path to the SVG file

    Returns:
        SVGValidationResult
    """
    # Escape path for JS string
    escaped_path = str(svg_path).replace("\\", "\\\\").replace('"', '\\"')

    validate_script = f'''
const {{ validateSVGAsync }} = await import("@emasoft/svg-matrix");
const fs = await import("fs");
const svg = fs.readFileSync("{escaped_path}", "utf8");
const result = await validateSVGAsync(svg);
console.log(JSON.stringify(result));
'''

    try:
        result = subprocess.run(
            ["bunx", "--bun", "-e", validate_script],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return _validate_with_cli(svg_path)

        output = result.stdout.strip()
        if output:
            data = json.loads(output)
            return SVGValidationResult(
                valid=data.get("valid", False),
                file_path=str(svg_path),
                issues=data.get("issues", []),
            )

    except subprocess.TimeoutExpired:
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error="Validation timed out",
        )
    except json.JSONDecodeError as e:
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error=f"JSON parse error: {e}",
        )
    except Exception as e:
        return SVGValidationResult(
            valid=False,
            file_path=str(svg_path),
            error=str(e),
        )

    return SVGValidationResult(
        valid=False,
        file_path=str(svg_path),
        error="Unknown validation error",
    )


def validate_svg_batch(
    svg_paths: list[str | Path],
) -> dict[str, SVGValidationResult]:
    """Validate multiple SVG files.

    Args:
        svg_paths: List of paths to SVG files

    Returns:
        Dict mapping file paths to their validation results
    """
    results: dict[str, SVGValidationResult] = {}
    for path in svg_paths:
        path_str = str(Path(path).resolve())
        results[path_str] = validate_svg_file(path)
    return results
