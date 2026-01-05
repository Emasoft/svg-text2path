"""Inkscape SVG format handler.

Handles SVG files created by Inkscape with sodipodi/inkscape namespaces.
Can strip Inkscape-specific elements or preserve them.
"""

from __future__ import annotations

import gzip
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element, ElementTree


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
            self._strip_inkscape_content(tree.getroot())

        return tree

    def parse_element(self, source: str | Path) -> Element:
        """Parse and return root element."""
        tree = self.parse(source)
        return tree.getroot()

    def serialize(self, tree: ElementTree, target: str | Path | None = None) -> str | Path:
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
        self._strip_inkscape_content(tree.getroot())

    def _parse_file(self, path: Path) -> ElementTree:
        """Parse SVG file.

        Args:
            path: File path

        Returns:
            ElementTree
        """
        if not path.exists():
            raise FileNotFoundError(f"SVG file not found: {path}")

        try:
            if path.suffix.lower() == ".svgz" or self._is_gzipped(path):
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    return ET.parse(f)
            return ET.parse(str(path))
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
            return ET.ElementTree(root)
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse Inkscape SVG string: {e}") from e

    def _check_file_is_inkscape(self, path: Path) -> bool:
        """Check if file is Inkscape SVG.

        Args:
            path: File path

        Returns:
            True if Inkscape SVG
        """
        if not path.exists():
            return False

        try:
            # Read first 2KB to check for markers
            if path.suffix.lower() == ".svgz":
                with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000)
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
                attr for attr in elem.attrib if INKSCAPE_NS in attr or SODIPODI_NS in attr
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
