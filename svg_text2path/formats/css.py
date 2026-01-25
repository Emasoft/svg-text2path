"""CSS embedded SVG input handler.

Handles SVG content embedded in CSS (background-image, mask, etc.).
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from io import StringIO
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


class CSSHandler(FormatHandler):
    """Handler for CSS with embedded SVG content (data URIs)."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.CSS_EMBEDDED]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is CSS with embedded SVG data URIs
        """
        if not isinstance(source, str):
            return False

        content = source.lower()

        # Check for CSS url() with SVG data URI
        return "url(" in content and "data:image/svg+xml" in content

    def parse(self, source: str) -> ElementTree:
        """Parse CSS and extract first SVG from data URI.

        Args:
            source: CSS content string

        Returns:
            ElementTree containing the SVG

        Raises:
            SVGParseError: If no SVG found or parsing fails
        """
        svg_content = self._extract_first_svg(source)
        if not svg_content:
            raise SVGParseError("No SVG data URI found in CSS")

        try:
            root = ET.fromstring(svg_content)
            return cast(ElementTree, ET.ElementTree(root))
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG from CSS data URI: {e}") from e

    def parse_element(self, source: str) -> Element:
        """Parse CSS and return first SVG element.

        Args:
            source: CSS content string

        Returns:
            First SVG Element found
        """
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Parsed SVG has no root element")
        return root

    def serialize(self, tree: ElementTree, target: str | None = None) -> str:
        """Serialize ElementTree back to CSS with SVG data URI.

        Args:
            tree: ElementTree to serialize
            target: Original CSS to embed SVG into (optional)

        Returns:
            CSS string with embedded SVG data URI
        """
        self._register_namespaces()

        # Serialize SVG
        buffer = StringIO()
        tree.write(buffer, encoding="unicode")
        svg_string = buffer.getvalue()

        # Create data URI
        # URL-encode the SVG (more compatible than base64 for SVG)
        encoded = urllib.parse.quote(svg_string, safe="")
        data_uri = f'url("data:image/svg+xml,{encoded}")'

        if target:
            # Replace first SVG data URI in original CSS
            return self._replace_first_svg_uri(target, data_uri)

        # Return minimal CSS with SVG
        return f".svg-background {{ background-image: {data_uri}; }}"

    def extract_all_svgs(self, source: str) -> list[str]:
        """Extract all SVG content from CSS data URIs.

        Args:
            source: CSS content

        Returns:
            List of SVG strings
        """
        svgs: list[str] = []

        # Find all data:image/svg+xml URIs
        pattern = re.compile(
            r'url\s*\(\s*["\']?(data:image/svg\+xml[^)]+)["\']?\s*\)',
            re.IGNORECASE,
        )

        for match in pattern.finditer(source):
            data_uri = match.group(1)
            svg = self._decode_data_uri(data_uri)
            if svg:
                svgs.append(svg)

        return svgs

    def _extract_first_svg(self, css: str) -> str | None:
        """Extract first SVG from CSS data URIs.

        Args:
            css: CSS content

        Returns:
            SVG string or None
        """
        svgs = self.extract_all_svgs(css)
        return svgs[0] if svgs else None

    def _decode_data_uri(self, data_uri: str) -> str | None:
        """Decode SVG from data URI.

        Handles both base64 and URL-encoded formats.

        Args:
            data_uri: Data URI string

        Returns:
            Decoded SVG string or None
        """
        # Remove data:image/svg+xml prefix
        if not data_uri.startswith("data:image/svg+xml"):
            return None

        content = data_uri[len("data:image/svg+xml") :]

        # Check for base64 encoding
        if content.startswith(";base64,"):
            encoded = content[len(";base64,") :]
            try:
                return base64.b64decode(encoded).decode("utf-8")
            except Exception:
                return None

        # URL-encoded (after comma or semicolon)
        if "," in content:
            encoded = content.split(",", 1)[1]
        elif ";" in content:
            # Handle charset specifier: ;charset=utf-8,<svg...
            parts = content.split(",", 1)
            encoded = parts[1] if len(parts) > 1 else parts[0]
        else:
            encoded = content

        try:
            return urllib.parse.unquote(encoded)
        except Exception:
            return None

    def _replace_first_svg_uri(self, css: str, new_uri: str) -> str:
        """Replace first SVG data URI in CSS.

        Args:
            css: Original CSS
            new_uri: New url() value

        Returns:
            CSS with first SVG URI replaced
        """
        pattern = re.compile(
            r'url\s*\(\s*["\']?(data:image/svg\+xml[^)]+)["\']?\s*\)',
            re.IGNORECASE,
        )

        return pattern.sub(new_uri, css, count=1)

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
