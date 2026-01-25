"""ElementTree and lxml tree input handler for SVG content.

Handles xml.etree.ElementTree and lxml etree objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element, ElementTree


class TreeHandler(FormatHandler):
    """Handler for ElementTree and lxml tree inputs."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [
            InputFormat.ELEMENT_TREE,
            InputFormat.LXML_TREE,
            InputFormat.BEAUTIFULSOUP,
        ]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is an ElementTree, Element, or lxml tree
        """
        # Check for ElementTree
        if hasattr(source, "getroot"):
            return True

        # Check for Element (has 'tag' attribute)
        if hasattr(source, "tag"):
            return True

        # Check for BeautifulSoup Tag
        type_name = type(source).__name__
        return type_name in ("Tag", "BeautifulSoup")

    def parse(self, source: Any) -> ElementTree:
        """Parse tree source into an ElementTree.

        Args:
            source: ElementTree, Element, or lxml tree

        Returns:
            ElementTree wrapping the source

        Raises:
            SVGParseError: If parsing fails
        """
        import defusedxml.ElementTree as ET

        from svg_text2path.exceptions import SVGParseError

        # Already an ElementTree - source already has correct type
        if hasattr(source, "getroot"):
            return cast("ElementTree", source)

        # Element - wrap in ElementTree
        if hasattr(source, "tag"):
            return cast("ElementTree", ET.ElementTree(source))  # type: ignore[reportAttributeAccessIssue]

        # BeautifulSoup - convert to ElementTree
        type_name = type(source).__name__
        if type_name in ("Tag", "BeautifulSoup"):
            return self._bs4_to_elementtree(source)

        raise SVGParseError(f"Cannot parse source of type: {type(source).__name__}")

    def parse_element(self, source: Any) -> Element:
        """Parse source into a root Element.

        Args:
            source: Tree input

        Returns:
            Root Element

        Raises:
            SVGParseError: If root element is None
        """
        from svg_text2path.exceptions import SVGParseError

        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Tree has no root element")
        return root

    def serialize(self, tree: ElementTree, target: Any = None) -> Any:
        """Serialize ElementTree back to original format.

        Args:
            tree: ElementTree to serialize
            target: Original source type hint (optional)

        Returns:
            Serialized output (ElementTree by default)
        """
        # Just return the tree - caller can convert as needed
        return tree

    def _bs4_to_elementtree(self, soup: Any) -> ElementTree:
        """Convert BeautifulSoup Tag to ElementTree.

        Args:
            soup: BeautifulSoup Tag or BeautifulSoup object

        Returns:
            ElementTree
        """
        import defusedxml.ElementTree as ET

        from svg_text2path.exceptions import SVGParseError

        try:
            # Get the SVG string
            svg_string = str(soup)

            # Parse with defusedxml
            root = ET.fromstring(svg_string)
            return cast("ElementTree", ET.ElementTree(root))  # type: ignore[reportAttributeAccessIssue]
        except Exception as e:
            raise SVGParseError(
                f"Failed to convert BeautifulSoup to ElementTree: {e}"
            ) from e

    def _is_lxml(self, source: Any) -> bool:
        """Check if source is an lxml object."""
        type_module = type(source).__module__
        return "lxml" in type_module
