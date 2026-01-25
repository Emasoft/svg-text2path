"""String input handler for SVG content.

Handles raw SVG strings and SVG snippets.
"""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element, ElementTree


# SVG template for wrapping snippets
SVG_WRAPPER = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
{content}
</svg>"""


class StringHandler(FormatHandler):
    """Handler for SVG string content."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.SVG_STRING, InputFormat.SVG_SNIPPET]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is SVG string content
        """
        if not isinstance(source, str):
            return False

        content = source.strip()

        # Check for XML/SVG markers
        if content.startswith("<?xml") or content.startswith("<!DOCTYPE"):
            return True

        # Check for SVG root
        if "<svg" in content.lower():
            return True

        # Check for SVG element tags (snippet)
        svg_tags = ["<text", "<path", "<g ", "<rect", "<circle", "<ellipse", "<polygon"]
        return any(tag in content.lower() for tag in svg_tags)

    def parse(self, source: str) -> ElementTree:
        """Parse SVG string into an ElementTree.

        Args:
            source: SVG content string

        Returns:
            Parsed ElementTree

        Raises:
            SVGParseError: If parsing fails
        """
        content = source.strip()

        try:
            # Check if it's a complete SVG document
            if self._is_complete_svg(content):
                return cast("ElementTree", ET.parse(StringIO(content)))

            # Wrap snippet in SVG container
            wrapped = SVG_WRAPPER.format(content=content)
            return cast("ElementTree", ET.parse(StringIO(wrapped)))

        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG string: {e}") from e
        except Exception as e:
            raise SVGParseError(f"Error parsing SVG content: {e}") from e

    def parse_element(self, source: str) -> Element:
        """Parse SVG string into a root Element.

        Args:
            source: SVG content string

        Returns:
            Root Element

        Raises:
            SVGParseError: If parsing fails
        """
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Failed to get root element from parsed SVG")
        return root

    def serialize(self, tree: ElementTree, target: Any = None) -> str:
        """Serialize ElementTree to SVG string.

        Args:
            tree: ElementTree to serialize
            target: Ignored for string output

        Returns:
            SVG content as string
        """
        # Register namespaces
        self._register_namespaces()

        # Write to string buffer
        buffer = StringIO()
        tree.write(buffer, encoding="unicode", xml_declaration=True)
        return buffer.getvalue()

    def _is_complete_svg(self, content: str) -> bool:
        """Check if content is a complete SVG document."""
        lower = content.lower()

        # Has XML declaration or DOCTYPE
        if lower.startswith("<?xml") or lower.startswith("<!doctype"):
            return True

        # Has SVG root element at start
        return lower.lstrip().startswith("<svg")

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "svg": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
            "inkscape": "http://www.inkscape.org/namespaces/inkscape",
            "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
