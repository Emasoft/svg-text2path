"""Remote SVG resource handler.

Handles fetching SVG content from URLs.
"""

from __future__ import annotations

import urllib.request
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import RemoteResourceError, SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element, ElementTree


class RemoteHandler(FormatHandler):
    """Handler for fetching SVG from remote URLs.

    Supports HTTP/HTTPS URLs pointing to SVG files.
    """

    # Default timeout for requests (seconds)
    DEFAULT_TIMEOUT = 30

    # Maximum file size to download (10MB)
    MAX_SIZE = 10 * 1024 * 1024

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
        """
        self.timeout = timeout
        self.max_size = max_size
        self.cache_dir = cache_dir

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
            return ET.ElementTree(root)
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse remote SVG: {e}") from e

    def parse_element(self, source: str) -> Element:
        """Fetch and return SVG element."""
        tree = self.parse(source)
        return tree.getroot()

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

    def fetch(self, url: str) -> str:
        """Fetch SVG content from URL.

        Args:
            url: URL to fetch

        Returns:
            SVG content as string

        Raises:
            RemoteResourceError: If fetch fails
        """
        # Check cache first
        if self.cache_dir:
            cached = self._get_cached(url)
            if cached:
                return cached

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "svg-text2path/0.2.0",
                    "Accept": "image/svg+xml, application/xml, text/xml, */*",
                },
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                # Check content length
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self.max_size:
                    raise RemoteResourceError(
                        url,
                        details={"error": f"File too large: {content_length} bytes"},
                    )

                # Read response
                content = response.read(self.max_size + 1)
                if len(content) > self.max_size:
                    raise RemoteResourceError(
                        url,
                        details={"error": f"File too large: >{self.max_size} bytes"},
                    )

                # Decode content
                encoding = response.headers.get_content_charset() or "utf-8"
                svg_content = content.decode(encoding)

                # Cache if enabled
                if self.cache_dir:
                    self._cache_content(url, svg_content)

                return svg_content

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
        """
        import hashlib

        # Create hash of URL for filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        parsed = urlparse(url)
        filename = Path(parsed.path).name or "index"

        return self.cache_dir / f"{url_hash}_{filename}"

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
