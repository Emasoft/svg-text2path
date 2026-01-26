"""HTML embedded SVG input handler.

Handles SVG elements embedded in HTML documents.
"""

from __future__ import annotations

import re
from io import StringIO
from typing import Any, cast
from xml.etree.ElementTree import Element, ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat


class HTMLHandler(FormatHandler):
    """Handler for HTML with embedded SVG content."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.HTML_EMBEDDED]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is HTML with embedded SVG
        """
        if not isinstance(source, str):
            return False

        content = source.strip().lower()

        # Check for HTML markers
        has_html = (
            content.startswith("<!doctype html")
            or content.startswith("<html")
            or "<html" in content[:500]
        )

        # Must also contain SVG
        has_svg = "<svg" in content

        return has_html and has_svg

    def parse(self, source: str) -> ElementTree:
        """Parse HTML and extract SVG elements into an ElementTree.

        If multiple SVG elements exist, they are wrapped in a container.

        Args:
            source: HTML content string

        Returns:
            ElementTree containing SVG elements

        Raises:
            SVGParseError: If parsing fails or no SVG found
        """
        svg_elements = self._extract_svg_elements(source)

        if not svg_elements:
            raise SVGParseError("No SVG elements found in HTML")

        # If single SVG, return it directly
        if len(svg_elements) == 1:
            return cast(ElementTree, ET.ElementTree(svg_elements[0]))

        # Multiple SVGs - wrap in container
        container = cast(Element, ET.Element("{http://www.w3.org/2000/svg}svg"))
        container.set("xmlns", "http://www.w3.org/2000/svg")
        for svg in svg_elements:
            container.append(svg)

        return cast(ElementTree, ET.ElementTree(container))

    def parse_element(self, source: str) -> Element:
        """Parse HTML and return first SVG element.

        Args:
            source: HTML content string

        Returns:
            First SVG Element found

        Raises:
            SVGParseError: If no SVG found
        """
        svg_elements = self._extract_svg_elements(source)
        if not svg_elements:
            raise SVGParseError("No SVG elements found in HTML")
        return svg_elements[0]

    def serialize(self, tree: ElementTree, target: str | None = None) -> str:
        """Serialize ElementTree back to HTML with embedded SVG.

        Args:
            tree: ElementTree to serialize
            target: Original HTML to embed SVG into (optional)

        Returns:
            HTML string with embedded SVG
        """
        self._register_namespaces()

        # Serialize SVG
        buffer = StringIO()
        tree.write(buffer, encoding="unicode")
        svg_string = buffer.getvalue()

        if target:
            # Replace first SVG in original HTML
            return self._replace_first_svg(target, svg_string)

        # Return SVG wrapped in minimal HTML
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
{svg_string}
</body>
</html>"""

    def _extract_svg_elements(self, html: str) -> list[Element]:
        """Extract all SVG elements from HTML.

        Args:
            html: HTML content

        Returns:
            List of SVG Element objects
        """
        svg_elements: list[Element] = []

        # Find all SVG tags using regex
        svg_pattern = re.compile(
            r"<svg[^>]*>.*?</svg>",
            re.IGNORECASE | re.DOTALL,
        )

        for match in svg_pattern.finditer(html):
            svg_str = match.group()
            try:
                # Add namespace if missing
                if "xmlns" not in svg_str[:100]:
                    svg_str = svg_str.replace(
                        "<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1
                    )
                elem = cast(Element, ET.fromstring(svg_str))
                svg_elements.append(elem)
            except ET.ParseError:
                continue

        return svg_elements

    def _replace_first_svg(self, html: str, new_svg: str) -> str:
        """Replace first SVG in HTML with new SVG.

        Args:
            html: Original HTML
            new_svg: New SVG string

        Returns:
            HTML with first SVG replaced
        """
        svg_pattern = re.compile(
            r"<svg[^>]*>.*?</svg>",
            re.IGNORECASE | re.DOTALL,
        )

        return svg_pattern.sub(new_svg, html, count=1)

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "svg": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
