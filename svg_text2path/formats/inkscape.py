"""Inkscape SVG format handler.

Handles SVG files created by Inkscape with sodipodi/inkscape namespaces.
Can strip Inkscape-specific elements or preserve them.
"""

from __future__ import annotations

import gzip
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

# Maximum decompressed size to prevent decompression bombs (100MB)
MAX_DECOMPRESSED_SIZE = 100 * 1024 * 1024

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


def _read_gzip_limited(
    path: Path, max_size: int = MAX_DECOMPRESSED_SIZE, ignore_limits: bool = False
) -> str:
    """Read gzip file with size limit to prevent decompression bombs.

    Args:
        path: Path to gzip-compressed file
        max_size: Maximum allowed decompressed size in bytes
        ignore_limits: If True, bypass size limit checks (for trusted files)

    Returns:
        Decompressed file content as string

    Raises:
        SVGParseError: If decompressed size exceeds limit (unless ignore_limits=True)
    """
    with gzip.open(path, "rb") as gz:
        chunks: list[bytes] = []
        total_size = 0
        while chunk := gz.read(8192):
            total_size += len(chunk)
            if not ignore_limits and total_size > max_size:
                raise SVGParseError(f"Decompressed file exceeds {max_size} bytes limit")
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")


# Inkscape namespaces
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"


class InkscapeHandler(FormatHandler):
    """Handler for Inkscape SVG format.

    Inkscape SVG files contain additional namespaces and elements:
    - sodipodi: Document-level metadata
    - inkscape: Application-specific attributes

    This handler can process these files and optionally strip
    the non-standard content for plain SVG output.
    """

    def __init__(self, strip_inkscape: bool = False) -> None:
        """Initialize handler.

        Args:
            strip_inkscape: If True, remove Inkscape-specific elements
                           and attributes during parsing.
        """
        super().__init__()  # Initialize config support from base class
        self.strip_inkscape = strip_inkscape

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.INKSCAPE]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is Inkscape SVG
        """
        if isinstance(source, Path):
            return self._check_file_is_inkscape(source)

        if isinstance(source, str):
            # Check if it's a file path
            if not source.strip().startswith("<"):
                path = Path(source)
                if path.exists() and path.suffix.lower() in (".svg", ".svgz"):
                    return self._check_file_is_inkscape(path)

            # Check string content
            return self._has_inkscape_markers(source)

        return False

    def parse(self, source: str | Path) -> ElementTree:
        """Parse Inkscape SVG into an ElementTree.

        Args:
            source: File path or SVG string

        Returns:
            Parsed ElementTree

        Raises:
            SVGParseError: If parsing fails
        """
        if isinstance(source, Path) or (
            isinstance(source, str) and not source.strip().startswith("<")
        ):
            tree = self._parse_file(Path(source))
        else:
            tree = self._parse_string(source)

        if self.strip_inkscape:
            root = tree.getroot()
            if root is not None:
                self._strip_inkscape_content(root)

        return tree

    def parse_element(self, source: str | Path) -> Element:
        """Parse and return root element."""
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Parsed SVG has no root element")
        return root

    def serialize(
        self, tree: ElementTree, target: str | Path | None = None
    ) -> str | Path:
        """Serialize ElementTree to SVG.

        Args:
            tree: ElementTree to serialize
            target: Output file path (optional)

        Returns:
            SVG string if no target, else output path
        """
        self._register_namespaces()

        if target:
            path = Path(target)
            if path.suffix.lower() == ".svgz":
                with gzip.open(path, "wt", encoding="utf-8") as f:
                    tree.write(f, encoding="unicode", xml_declaration=True)
            else:
                tree.write(str(path), encoding="unicode", xml_declaration=True)
            return path

        buffer = StringIO()
        tree.write(buffer, encoding="unicode", xml_declaration=True)
        return buffer.getvalue()

    def is_inkscape_svg(self, source: str | Path) -> bool:
        """Check if source is an Inkscape SVG.

        Args:
            source: File path or SVG string

        Returns:
            True if Inkscape SVG
        """
        return self.can_handle(source)

    def get_inkscape_metadata(self, tree: ElementTree) -> dict[str, Any]:
        """Extract Inkscape-specific metadata from SVG.

        Args:
            tree: ElementTree to analyze

        Returns:
            Dictionary of Inkscape metadata
        """
        root = tree.getroot()
        if root is None:
            return {
                "version": None,
                "output_extension": None,
                "layers": [],
                "guides": [],
            }
        metadata: dict[str, Any] = {
            "version": root.get(f"{{{INKSCAPE_NS}}}version"),
            "output_extension": root.get(f"{{{INKSCAPE_NS}}}output_extension"),
            "layers": [],
            "guides": [],
        }

        # Find layers (groups with inkscape:groupmode="layer")
        for elem in root.iter():
            groupmode = elem.get(f"{{{INKSCAPE_NS}}}groupmode")
            if groupmode == "layer":
                layer_info = {
                    "id": elem.get("id"),
                    "label": elem.get(f"{{{INKSCAPE_NS}}}label"),
                }
                metadata["layers"].append(layer_info)

        # Find namedview with guides
        for namedview in root.iter(f"{{{SODIPODI_NS}}}namedview"):
            for guide in namedview.iter(f"{{{SODIPODI_NS}}}guide"):
                guide_info = {
                    "position": guide.get("position"),
                    "orientation": guide.get("orientation"),
                }
                metadata["guides"].append(guide_info)

        return metadata

    def strip_inkscape_elements(self, tree: ElementTree) -> None:
        """Remove all Inkscape-specific content from tree.

        Args:
            tree: ElementTree to modify in place
        """
        root = tree.getroot()
        if root is not None:
            self._strip_inkscape_content(root)

    def _parse_file(self, path: Path) -> ElementTree:
        """Parse SVG file.

        Args:
            path: File path

        Returns:
            ElementTree
        """
        if not path.is_file():
            if path.is_dir():
                raise IsADirectoryError(f"Expected file, got directory: {path}")
            raise FileNotFoundError(f"SVG file not found: {path}")

        try:
            if path.suffix.lower() == ".svgz" or self._is_gzipped(path):
                # Determine size limit settings from config
                ignore_limits = False
                max_size = MAX_DECOMPRESSED_SIZE

                if self.config and hasattr(self.config, "security"):
                    ignore_limits = self.config.security.ignore_size_limits
                    if not ignore_limits:
                        # Respect configured max size (convert MB to bytes)
                        max_size = (
                            self.config.security.max_decompressed_size_mb * 1024 * 1024
                        )

                # Use size-limited reader to prevent decompression bombs
                content = _read_gzip_limited(
                    path, max_size=max_size, ignore_limits=ignore_limits
                )
                root = ET.fromstring(content)
                return cast(ElementTree, ET.ElementTree(root))
            return cast(ElementTree, ET.parse(str(path)))
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse Inkscape SVG: {e}") from e

    def _parse_string(self, svg_str: str) -> ElementTree:
        """Parse SVG string.

        Args:
            svg_str: SVG content

        Returns:
            ElementTree
        """
        try:
            root = ET.fromstring(svg_str)
            return cast(ElementTree, ET.ElementTree(root))
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse Inkscape SVG string: {e}") from e

    def _check_file_is_inkscape(self, path: Path) -> bool:
        """Check if file is Inkscape SVG.

        Args:
            path: File path

        Returns:
            True if Inkscape SVG
        """
        if not path.is_file():
            return False

        try:
            # Read first 2KB to check for markers (safe limit for gzip too)
            if path.suffix.lower() == ".svgz":
                # Use limited read for gzip to prevent decompression bombs
                with gzip.open(path, "rb") as gz:
                    # Read only 2KB max to check for markers
                    raw = gz.read(2048)
                    content = raw.decode("utf-8", errors="ignore")
            else:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000)

            return self._has_inkscape_markers(content)
        except Exception:
            return False

    def _has_inkscape_markers(self, content: str) -> bool:
        """Check if content has Inkscape markers.

        Args:
            content: SVG content

        Returns:
            True if has Inkscape markers
        """
        lower = content.lower()
        return "inkscape" in lower or "sodipodi" in lower

    def _is_gzipped(self, path: Path) -> bool:
        """Check if file is gzip compressed."""
        try:
            with open(path, "rb") as f:
                magic = f.read(2)
                return magic == b"\x1f\x8b"
        except Exception:
            return False

    def _strip_inkscape_content(self, root: Element) -> None:
        """Remove Inkscape-specific elements and attributes.

        Args:
            root: Root element to clean
        """
        # Elements to remove entirely
        elements_to_remove: list[tuple[Element, Element]] = []

        def find_inkscape_elements(parent: Element) -> None:
            for child in list(parent):
                tag = child.tag

                # Check for sodipodi/inkscape namespaced elements
                if INKSCAPE_NS in tag or SODIPODI_NS in tag:
                    elements_to_remove.append((parent, child))
                else:
                    find_inkscape_elements(child)

        find_inkscape_elements(root)

        # Remove elements
        for parent, elem in elements_to_remove:
            parent.remove(elem)

        # Remove Inkscape attributes from all elements
        for elem in root.iter():
            attrs_to_remove = [
                attr
                for attr in elem.attrib
                if INKSCAPE_NS in attr or SODIPODI_NS in attr
            ]
            for attr in attrs_to_remove:
                del elem.attrib[attr]

        # Clean up namespace declarations from root
        # This is tricky with ElementTree - we'll leave xmlns declarations

    def _register_namespaces(self) -> None:
        """Register all relevant namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "svg": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
            "inkscape": INKSCAPE_NS,
            "sodipodi": SODIPODI_NS,
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
