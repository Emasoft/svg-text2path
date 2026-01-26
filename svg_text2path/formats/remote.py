"""Remote SVG resource handler.

Handles fetching SVG content from URLs.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse
from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path import __version__
from svg_text2path.exceptions import RemoteResourceError, SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


class RemoteHandler(FormatHandler):
    """Handler for fetching SVG from remote URLs.

    Supports HTTP/HTTPS URLs pointing to SVG files.
    """

    # Default timeout for requests (seconds)
    DEFAULT_TIMEOUT = 30

    # Maximum file size to download (10MB)
    MAX_SIZE = 10 * 1024 * 1024

    # Blocked IP networks to prevent SSRF attacks
    BLOCKED_NETWORKS = [
        # IPv4
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        # IPv6
        ipaddress.ip_network("::1/128"),  # Loopback
        ipaddress.ip_network("fc00::/7"),  # Unique local
        ipaddress.ip_network("fe80::/10"),  # Link-local
        ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped
    ]

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_size: int = MAX_SIZE,
        cache_dir: Path | None = None,
    ) -> None:
        """Initialize handler.

        Args:
            timeout: Request timeout in seconds.
            max_size: Maximum file size to download.
            cache_dir: Optional directory to cache downloaded files.

        Raises:
            ValueError: If timeout or max_size are not positive.
        """
        super().__init__()
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        if max_size <= 0:
            raise ValueError(f"max_size must be positive, got {max_size}")
        self.timeout = timeout
        self.max_size = max_size
        self.cache_dir = cache_dir

    def _get_effective_max_size(self) -> int | None:
        """Get effective max download size based on config.

        Returns:
            int | None: Max size in bytes, or None if limits are disabled.
        """
        if self.config and self.config.security.ignore_size_limits:
            return None
        if self.config and self.config.security.max_file_size_mb:
            return self.config.security.max_file_size_mb * 1024 * 1024
        return self.max_size

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        # Remote isn't a separate InputFormat, but handler can process URLs
        return []

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is a URL pointing to SVG
        """
        if not isinstance(source, str):
            return False

        source = source.strip()

        # Check for URL schemes
        if not (source.startswith("http://") or source.startswith("https://")):
            return False

        # Check if URL likely points to SVG
        parsed = urlparse(source)
        path_lower = parsed.path.lower()

        return (
            path_lower.endswith(".svg")
            or path_lower.endswith(".svgz")
            or "svg" in parsed.query.lower()
            or "image/svg" in source.lower()
        )

    def parse(self, source: str) -> ElementTree:
        """Fetch and parse SVG from URL.

        Args:
            source: URL to SVG resource

        Returns:
            Parsed ElementTree

        Raises:
            RemoteResourceError: If fetch fails
            SVGParseError: If parsing fails
        """
        svg_content = self.fetch(source)

        try:
            root = ET.fromstring(svg_content)
            return ElementTree(root)
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse remote SVG: {e}") from e

    def parse_element(self, source: str) -> Element:
        """Fetch and return SVG element."""
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Parsed SVG has no root element")
        return root

    def serialize(self, tree: ElementTree, target: str | None = None) -> str:
        """Serialize ElementTree to SVG string.

        Note: This handler doesn't upload - just returns string.

        Args:
            tree: ElementTree to serialize
            target: Ignored

        Returns:
            SVG string
        """
        self._register_namespaces()

        buffer = StringIO()
        tree.write(buffer, encoding="unicode", xml_declaration=True)
        return buffer.getvalue()

    def _is_private_ip(self, hostname: str) -> bool:
        """Check if hostname resolves to a private/blocked IP address.

        Args:
            hostname: Hostname to check

        Returns:
            True if hostname resolves to a blocked IP range

        Note:
            This prevents SSRF attacks by blocking private networks.
        """
        try:
            # Resolve hostname to IP address
            ip_str = socket.gethostbyname(hostname)
            ip_addr = ipaddress.ip_address(ip_str)

            # Check if IP is in any blocked network
            return any(ip_addr in network for network in self.BLOCKED_NETWORKS)
        except (socket.gaierror, ValueError):
            # DNS resolution failed or invalid IP - let urllib handle the error
            return False

    def fetch(self, url: str) -> str:
        """Fetch SVG content from URL.

        Args:
            url: URL to fetch

        Returns:
            SVG content as string

        Raises:
            RemoteResourceError: If fetch fails or hostname is blocked (SSRF protection)
        """
        # Check cache first
        if self.cache_dir:
            cached = self._get_cached(url)
            if cached:
                return cached

        # SSRF protection: Check if hostname resolves to private IP
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname and self._is_private_ip(hostname):
            raise RemoteResourceError(
                url,
                details={
                    "error": f"Access to private IPs blocked (hostname: {hostname})"
                },
            )

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": f"svg-text2path/{__version__}",
                    "Accept": "image/svg+xml, application/xml, text/xml, */*",
                },
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                # Get effective max size based on config
                effective_max_size = self._get_effective_max_size()

                # Check content length (skip if size limits are disabled)
                if effective_max_size is not None:
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > effective_max_size:
                        raise RemoteResourceError(
                            url,
                            details={
                                "error": f"File too large: {content_length} bytes"
                            },
                        )

                # Read response
                if effective_max_size is not None:
                    content = response.read(effective_max_size + 1)
                    if len(content) > effective_max_size:
                        raise RemoteResourceError(
                            url,
                            details={
                                "error": f"File too large: >{effective_max_size} bytes"
                            },
                        )
                else:
                    # No size limit - read all content
                    content = response.read()

                # Decode content
                encoding = response.headers.get_content_charset() or "utf-8"
                svg_content = content.decode(encoding)

                # Cache if enabled
                if self.cache_dir:
                    self._cache_content(url, svg_content)

                return cast(str, svg_content)

        except urllib.error.HTTPError as e:
            raise RemoteResourceError(url, status_code=e.code) from e
        except urllib.error.URLError as e:
            raise RemoteResourceError(url, details={"error": str(e.reason)}) from e
        except Exception as e:
            raise RemoteResourceError(url, details={"error": str(e)}) from e

    def _get_cached(self, url: str) -> str | None:
        """Get cached content for URL.

        Args:
            url: URL to look up

        Returns:
            Cached content or None
        """
        if not self.cache_dir:
            return None

        cache_file = self._cache_path(url)
        if cache_file.exists():
            try:
                return cache_file.read_text(encoding="utf-8")
            except Exception:
                return None

        return None

    def _cache_content(self, url: str, content: str) -> None:
        """Cache content for URL.

        Args:
            url: URL being cached
            content: Content to cache
        """
        if not self.cache_dir:
            return

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_path(url)
            cache_file.write_text(content, encoding="utf-8")
        except Exception:
            pass  # Caching is optional, don't fail

    def _cache_path(self, url: str) -> Path:
        """Get cache file path for URL.

        Args:
            url: URL to cache

        Returns:
            Path to cache file

        Raises:
            ValueError: If cache_dir is not set.
        """
        import hashlib

        if self.cache_dir is None:
            raise ValueError("cache_dir must be set")
        # Sanitize filename to prevent path traversal
        parsed = urlparse(url)
        raw_filename = Path(parsed.path).name or "index"
        safe_filename = "".join(c for c in raw_filename if c.isalnum() or c in "._-")
        # Create hash of URL for filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]

        return self.cache_dir / f"{url_hash}_{safe_filename}"

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
