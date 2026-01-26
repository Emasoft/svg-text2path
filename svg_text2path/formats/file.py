"""File path input handler for SVG files.

Handles .svg, .svgz, and gzip-compressed SVG files.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

# Maximum decompressed size to prevent decompression bomb attacks
MAX_DECOMPRESSED_SIZE = 100 * 1024 * 1024  # 100MB max decompressed


def _read_gzip_limited(path: Path, max_size: int = MAX_DECOMPRESSED_SIZE) -> str:
    """Read gzip file with size limit to prevent decompression bombs.

    Args:
        path: Path to gzip-compressed file
        max_size: Maximum allowed decompressed size in bytes

    Returns:
        Decompressed content as string

    Raises:
        SVGParseError: If decompressed content exceeds size limit
    """
    with gzip.open(path, "rb") as gz:
        chunks = []
        total_size = 0
        while chunk := gz.read(8192):
            total_size += len(chunk)
            if total_size > max_size:
                raise SVGParseError(f"Decompressed file exceeds {max_size} bytes limit")
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")


if TYPE_CHECKING:
    pass  # ElementTree imported above for cast()


class FileHandler(FormatHandler):
    """Handler for SVG file paths."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.FILE_PATH, InputFormat.ZSVG, InputFormat.INKSCAPE]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is a valid SVG file path
        """
        if isinstance(source, Path):
            return source.suffix.lower() in (".svg", ".svgz")

        if isinstance(source, str):
            # Check if it looks like a path
            if source.startswith("<"):
                return False
            path = Path(source)
            if path.exists() and path.suffix.lower() in (".svg", ".svgz"):
                return True

        return False

    def parse(self, source: str | Path) -> ElementTree:
        """Parse SVG file into an ElementTree.

        Args:
            source: File path to SVG

        Returns:
            Parsed ElementTree

        Raises:
            SVGParseError: If parsing fails
            FileNotFoundError: If file doesn't exist
        """
        path = Path(source) if isinstance(source, str) else source

        # Validate path is a file, not a directory
        if not path.is_file():
            if path.is_dir():
                raise IsADirectoryError(f"Expected file, got directory: {path}")
            raise FileNotFoundError(f"SVG file not found: {path}")

        try:
            # Handle compressed SVG with size limit to prevent decompression bombs
            if path.suffix.lower() == ".svgz" or self._is_gzipped(path):
                # Calculate max size based on config
                max_size = MAX_DECOMPRESSED_SIZE  # default
                if self.config and self.config.security.ignore_size_limits:
                    max_size = 10 * 1024 * 1024 * 1024  # 10GB when ignoring limits
                elif self.config and self.config.security.max_decompressed_size_mb:
                    max_size = (
                        self.config.security.max_decompressed_size_mb * 1024 * 1024
                    )

                content = _read_gzip_limited(path, max_size)
                root = ET.fromstring(content)
                return ElementTree(root)

            # Regular SVG
            return cast(ElementTree, ET.parse(str(path)))

        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG: {e}") from e
        except Exception as e:
            raise SVGParseError(f"Error reading SVG file: {e}") from e

    def serialize(self, tree: ElementTree, target: str | Path) -> Path:
        """Write ElementTree to SVG file.

        Args:
            tree: ElementTree to serialize
            target: Output file path

        Returns:
            Path to written file
        """
        path = Path(target) if isinstance(target, str) else target

        # Register SVG namespaces
        self._register_namespaces()

        # Handle compressed output
        if path.suffix.lower() == ".svgz":
            with gzip.open(path, "wt", encoding="utf-8") as f:
                tree.write(f, encoding="unicode", xml_declaration=True)
        else:
            tree.write(str(path), encoding="unicode", xml_declaration=True)

        return path

    def _is_gzipped(self, path: Path) -> bool:
        """Check if file is gzip compressed by magic bytes."""
        try:
            with open(path, "rb") as f:
                magic = f.read(2)
                return magic == b"\x1f\x8b"
        except Exception:
            return False

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces to avoid ns0: prefixes."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "svg": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
            "inkscape": "http://www.inkscape.org/namespaces/inkscape",
            "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
