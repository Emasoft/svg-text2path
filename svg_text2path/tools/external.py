"""External tool execution utilities.

Provides subprocess wrappers and tool availability checks.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    """Result of a command execution.

    Attributes:
        returncode: Process return code
        stdout: Standard output (decoded)
        stderr: Standard error (decoded)
        success: True if returncode is 0
    """

    returncode: int
    stdout: str
    stderr: str
    success: bool

    @property
    def output(self) -> str:
        """Get primary output (stdout if available, else stderr)."""
        return self.stdout if self.stdout else self.stderr


def run_command(
    cmd: list[str],
    cwd: Path | str | None = None,
    timeout: int = 300,
    capture_output: bool = True,
) -> CommandResult:
    """Run a command with timeout and capture output.

    Args:
        cmd: Command and arguments as list
        cwd: Working directory for command execution
        timeout: Timeout in seconds (default: 300)
        capture_output: Whether to capture stdout/stderr (default: True)

    Returns:
        CommandResult with returncode, stdout, stderr, success

    Raises:
        No exceptions - all errors are captured in CommandResult
    """
    try:
        # Convert Path to str if needed - why: subprocess requires str for cwd
        cwd_str = str(cwd) if isinstance(cwd, Path) else cwd

        # Run command with timeout - why: prevent hanging processes
        result = subprocess.run(
            cmd,
            cwd=cwd_str,
            timeout=timeout,
            capture_output=capture_output,
            text=True,  # Decode output as text - why: easier to work with strings
            check=False,  # Don't raise on non-zero exit - why: handle via CommandResult
        )

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout if capture_output else "",
            stderr=result.stderr if capture_output else "",
            success=(result.returncode == 0),
        )

    except subprocess.TimeoutExpired as e:
        # Command timed out - why: return failure with timeout info
        return CommandResult(
            returncode=-1,
            stdout=e.stdout.decode() if e.stdout else "",
            stderr=f"Command timed out after {timeout}s",
            success=False,
        )

    except FileNotFoundError:
        # Command not found - why: return failure with not found info
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Command not found: {cmd[0]}",
            success=False,
        )

    except Exception as e:
        # Unexpected error - why: capture all failures in CommandResult
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Unexpected error: {e}",
            success=False,
        )


def which(program: str) -> Path | None:
    """Find program in PATH, return path or None.

    Args:
        program: Program name to search for

    Returns:
        Path to program if found, None otherwise
    """
    # Use shutil.which for cross-platform PATH search - why: handles Windows
    result = shutil.which(program)
    return Path(result) if result else None


def check_node_installed() -> bool:
    """Check if Node.js is installed and available.

    Returns:
        True if node is in PATH and executable
    """
    return which("node") is not None


def check_npm_installed() -> bool:
    """Check if npm is installed and available.

    Returns:
        True if npm is in PATH and executable
    """
    return which("npm") is not None


def check_git_installed() -> bool:
    """Check if git is installed and available.

    Returns:
        True if git is in PATH and executable
    """
    return which("git") is not None
