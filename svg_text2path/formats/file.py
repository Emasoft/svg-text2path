"""File path input handler for SVG files.

Handles .svg, .svgz, and gzip-compressed SVG files.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import ElementTree


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

        if not path.exists():
            raise FileNotFoundError(f"SVG file not found: {path}")

        try:
            # Handle compressed SVG
            if path.suffix.lower() == ".svgz" or self._is_gzipped(path):
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    return ET.parse(f)

            # Regular SVG
            return ET.parse(str(path))

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
