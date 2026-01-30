"""Path validation and accessibility checking for batch operations."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse


@dataclass
class PathAccessResult:
    """Result of path accessibility check."""

    accessible: bool
    error_type: str | None = None  # auth, permission, network, disk, not_found, etc.
    error_message: str | None = None
    suggestion: str | None = None


def _is_remote_path(path_str: str) -> bool:
    """Check if path is a remote path (SSH, FTP, HTTP/HTTPS, or SFTP)."""
    # SSH format: user@host:path
    if "@" in path_str and ":" in path_str:
        at_pos = path_str.index("@")
        colon_pos = path_str.index(":")
        # SSH: @ comes before : and no // after :
        if at_pos < colon_pos and not path_str[colon_pos:].startswith("://"):
            return True
    # URL schemes
    return any(
        path_str.startswith(scheme)
        for scheme in ["http://", "https://", "ftp://", "sftp://"]
    )


def _check_path_accessibility(
    path_str: str, check_write: bool = False
) -> PathAccessResult:
    """Check if a path is accessible and diagnose any issues.

    Handles:
    - Local paths: permission, disk space, existence
    - Network drives: mount status, connectivity, timeouts
    - SSH paths: key auth, host reachability, permissions
    - URLs: connectivity, auth, timeouts

    Args:
        path_str: Path to check
        check_write: If True, also check write permission (for output paths)

    Returns:
        PathAccessResult with accessibility status and diagnostic info
    """
    from pathlib import Path

    # Handle remote paths (SSH, URLs) - basic connectivity check
    if _is_remote_path(path_str):
        # SSH path: user@host:/path
        if "@" in path_str and ":" in path_str:
            at_pos = path_str.index("@")
            colon_pos = path_str.index(":")
            if at_pos < colon_pos and not path_str[colon_pos:].startswith("://"):
                # Extract host from SSH path
                host_part = path_str[at_pos + 1 : colon_pos]

                # Check if host is reachable
                try:
                    socket.setdefaulttimeout(5.0)
                    socket.gethostbyname(host_part)
                except socket.gaierror:
                    return PathAccessResult(
                        accessible=False,
                        error_type="network",
                        error_message=f"Cannot resolve hostname: {host_part}",
                        suggestion="Check hostname spelling, DNS settings, or "
                        "try using IP address directly",
                    )
                except TimeoutError:
                    return PathAccessResult(
                        accessible=False,
                        error_type="network",
                        error_message=f"Timeout resolving hostname: {host_part}",
                        suggestion="Check network connection, firewall, or VPN",
                    )

                # Check SSH connectivity with timeout
                try:
                    result = subprocess.run(
                        [
                            "ssh",
                            "-o",
                            "ConnectTimeout=5",
                            "-o",
                            "BatchMode=yes",
                            "-o",
                            "StrictHostKeyChecking=accept-new",
                            f"{path_str[:at_pos]}@{host_part}",
                            "exit",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode != 0:
                        stderr = result.stderr.lower()
                        if "permission denied" in stderr:
                            return PathAccessResult(
                                accessible=False,
                                error_type="auth",
                                error_message="SSH authentication failed",
                                suggestion="Check SSH key (ssh-add), password, or "
                                "~/.ssh/config. Try: ssh-add -l",
                            )
                        elif "host key verification" in stderr:
                            return PathAccessResult(
                                accessible=False,
                                error_type="auth",
                                error_message="SSH host key verification failed",
                                suggestion="Run: ssh-keyscan -H {host} >> "
                                "~/.ssh/known_hosts",
                            )
                        elif "connection refused" in stderr:
                            return PathAccessResult(
                                accessible=False,
                                error_type="network",
                                error_message=f"SSH connection refused by {host_part}",
                                suggestion="Check if SSH server is running, "
                                "port 22 open, firewall rules",
                            )
                        elif "connection timed out" in stderr or "timed out" in stderr:
                            return PathAccessResult(
                                accessible=False,
                                error_type="network",
                                error_message=f"SSH connection timeout to {host_part}",
                                suggestion="Check network, firewall, NAT rules, or "
                                "try different port with -p",
                            )
                        elif "no route to host" in stderr:
                            return PathAccessResult(
                                accessible=False,
                                error_type="network",
                                error_message=f"No route to host: {host_part}",
                                suggestion="Check if host is on same network, "
                                "VPN connected, gateway reachable",
                            )
                        else:
                            return PathAccessResult(
                                accessible=False,
                                error_type="ssh",
                                error_message=f"SSH error: {result.stderr.strip()}",
                                suggestion="Check SSH configuration and logs",
                            )
                except subprocess.TimeoutExpired:
                    return PathAccessResult(
                        accessible=False,
                        error_type="network",
                        error_message=f"SSH connection timeout to {host_part}",
                        suggestion="Host may be behind NAT/firewall, check "
                        "port forwarding and gateway",
                    )
                except FileNotFoundError:
                    return PathAccessResult(
                        accessible=False,
                        error_type="config",
                        error_message="SSH client not found",
                        suggestion="Install OpenSSH: brew install openssh (macOS) or "
                        "apt install openssh-client (Linux)",
                    )

                return PathAccessResult(accessible=True)

        # URL path
        if any(path_str.startswith(s) for s in ["http://", "https://", "ftp://"]):
            parsed = urlparse(path_str)
            try:
                socket.setdefaulttimeout(5.0)
                socket.gethostbyname(parsed.netloc.split(":")[0])
            except socket.gaierror:
                return PathAccessResult(
                    accessible=False,
                    error_type="network",
                    error_message=f"Cannot resolve URL host: {parsed.netloc}",
                    suggestion="Check URL spelling, DNS, or internet connection",
                )
            except TimeoutError:
                return PathAccessResult(
                    accessible=False,
                    error_type="network",
                    error_message=f"Timeout connecting to: {parsed.netloc}",
                    suggestion="Server may be slow or unreachable",
                )
            return PathAccessResult(accessible=True)

    # Local path handling
    path = Path(path_str).expanduser().resolve()

    # Check if it's a network mount (NAS, SMB, NFS, etc.)
    try:
        # On Unix, check mount points
        if os.name != "nt":
            mount_result = subprocess.run(
                ["df", str(path.parent if not path.exists() else path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if mount_result.returncode == 0:
                output = mount_result.stdout.lower()
                is_network = any(
                    x in output
                    for x in ["nfs", "smb", "cifs", "afp", "//", ":", "fuse"]
                )
                if is_network and "stale" in output:
                    return PathAccessResult(
                        accessible=False,
                        error_type="network",
                        error_message="Network drive has stale mount",
                        suggestion="Remount the network drive: umount -f <mount> && "
                        "mount <mount>",
                    )
    except subprocess.TimeoutExpired:
        return PathAccessResult(
            accessible=False,
            error_type="network",
            error_message="Network drive not responding (timeout)",
            suggestion="Check if NAS/server is online, network connected, "
            "try remounting",
        )
    except Exception:
        pass  # Ignore df errors

    # Check if path exists
    if not path.exists() and not path.parent.exists():
        return PathAccessResult(
            accessible=False,
            error_type="not_found",
            error_message=f"Path does not exist: {path}",
            suggestion="Create parent directories first or check path spelling",
        )

    # Check read permission
    try:
        if path.exists():
            os.access(path, os.R_OK)
    except PermissionError:
        return PathAccessResult(
            accessible=False,
            error_type="permission",
            error_message=f"No read permission: {path}",
            suggestion="Check file ownership: ls -la {path}. "
            "May need: chmod +r or chown",
        )
    except OSError as e:
        if e.errno == 116:  # Stale NFS handle
            return PathAccessResult(
                accessible=False,
                error_type="network",
                error_message="Stale NFS file handle",
                suggestion="Remount the NFS share or restart NFS client",
            )
        raise

    # Check write permission if needed
    if check_write:
        write_check_path = path if path.exists() else path.parent
        if not os.access(write_check_path, os.W_OK):
            return PathAccessResult(
                accessible=False,
                error_type="permission",
                error_message=f"No write permission: {write_check_path}",
                suggestion="Check directory permissions. May need: chmod +w or "
                "run as different user",
            )

        # Check disk space (only for local paths)
        try:
            usage = shutil.disk_usage(write_check_path)
            free_mb = usage.free / (1024 * 1024)
            if free_mb < 100:  # Less than 100MB free
                return PathAccessResult(
                    accessible=False,
                    error_type="disk",
                    error_message=f"Low disk space: {free_mb:.1f}MB free",
                    suggestion="Free up disk space or use different output location",
                )
        except OSError:
            pass  # Can't check disk space (maybe network drive)

    return PathAccessResult(accessible=True)


def _validate_path_format(path_str: str) -> list[str]:
    """Validate path format and return list of errors.

    Supports:
    - Local paths: relative (./path), absolute (/path), home (~/)
    - SSH: user@host:/path or user@host:path
    - URLs: http://, https://, ftp://, sftp://
    """
    errors: list[str] = []

    if not path_str or not path_str.strip():
        errors.append("path cannot be empty")
        return errors

    path_str = path_str.strip()

    # Check for URL schemes
    if any(
        path_str.startswith(s) for s in ["http://", "https://", "ftp://", "sftp://"]
    ):
        try:
            parsed = urlparse(path_str)
            if not parsed.netloc:
                errors.append(f"invalid URL (missing host): {path_str}")
            elif not parsed.path or parsed.path == "/":
                # Allow root path for URLs, but warn if no file specified
                pass  # URLs to directories are valid
        except Exception as e:
            errors.append(f"invalid URL format: {e}")
        return errors

    # Check for SSH format: user@host:path
    if "@" in path_str and ":" in path_str:
        at_pos = path_str.index("@")
        colon_pos = path_str.index(":")
        if at_pos < colon_pos and not path_str[colon_pos:].startswith("://"):
            # SSH format validation
            user = path_str[:at_pos]
            host_and_path = path_str[at_pos + 1 :]
            if ":" not in host_and_path:
                errors.append(f"invalid SSH path (missing colon): {path_str}")
                return errors
            host, remote_path = host_and_path.split(":", 1)

            # Validate user (alphanumeric, underscore, dash)
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*$", user):
                errors.append(f"invalid SSH user '{user}': must be alphanumeric")

            # Validate host (hostname or IP)
            if not host:
                errors.append("SSH host cannot be empty")
            elif not re.match(
                r"^([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)*"
                r"[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$|"
                r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$|"
                r"^\[?[a-fA-F0-9:]+\]?$",  # IPv6
                host,
            ):
                errors.append(f"invalid SSH host '{host}': must be hostname or IP")

            # Remote path can be relative or absolute
            if not remote_path:
                errors.append("SSH remote path cannot be empty")

            return errors

    # Local path validation
    # Check for obviously invalid characters (null byte, etc.)
    if "\x00" in path_str:
        errors.append("path contains null byte")
        return errors

    # Windows UNC paths
    if path_str.startswith("\\\\"):
        # Basic UNC validation: \\server\share\path
        parts = path_str[2:].split("\\", 2)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            errors.append(f"invalid UNC path: {path_str}")
        return errors

    # Windows drive letters
    if len(path_str) >= 2 and path_str[1] == ":":
        if not path_str[0].isalpha():
            errors.append(f"invalid drive letter: {path_str[0]}")
        return errors

    # Unix paths (relative, absolute, home)
    # These are generally permissive - just check for basic validity
    if path_str.startswith("~") and len(path_str) > 1 and path_str[1] not in "/\\":
        # ~username expansion - valid
        pass

    return errors


def _parse_compact_entry(entry_str: str) -> dict[str, Any]:
    """Parse a compact semicolon-delimited input entry string.

    Formats:
        FILE MODE:   input_path;output_path
        FOLDER MODE: input_folder/;output_folder/;suffix

    Paths can be:
        - Local: ./path/to/file.svg, ~/Documents/file.svg
        - SSH: user@host:/path/to/file.svg
        - URL: https://example.com/file.svg, ftp://example.com/file.svg

    Escaping special characters:
        - Use \\; for literal semicolons in paths
        - Use %3B (URL encoding) for semicolons
        - Use %20 for spaces
        - YAML quoted strings preserve semicolons: "path;with;semicolons;out.svg"

    Returns a dict matching the old dict format for compatibility.
    """
    # Replace escaped semicolons with a placeholder before splitting
    # \; -> placeholder, then split by unescaped ;, then restore
    placeholder = "\x00SEMICOLON\x00"  # unlikely to appear in paths
    escaped = entry_str.replace("\\;", placeholder)

    # Split by unescaped semicolons
    raw_parts = escaped.split(";")

    # Restore semicolons and URL-decode
    parts = [unquote(p.strip().replace(placeholder, ";")) for p in raw_parts]

    if len(parts) < 2:
        raise ValueError(
            f"Invalid format: '{entry_str}'. Expected 'input;output' or "
            "'input/;output/;suffix'"
        )

    input_path = parts[0]
    output_path = parts[1]
    suffix = parts[2] if len(parts) > 2 else "_text2path"

    # Determine if folder mode (paths end with /)
    is_folder = input_path.endswith("/") or output_path.endswith("/")

    if is_folder:
        # Strip trailing slashes for Path construction
        return {
            "path": input_path.rstrip("/"),
            "output_dir": output_path.rstrip("/"),
            "suffix": suffix,
            "_is_folder": True,
        }
    else:
        return {
            "path": input_path,
            "output": output_path,
            "_is_folder": False,
        }
