"""Markdown SVG input handler.

Handles SVG content in Markdown files (inline or fenced code blocks).
"""

from __future__ import annotations

import re
from io import StringIO
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import Element, ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    pass


class MarkdownHandler(FormatHandler):
    """Handler for Markdown with embedded SVG content."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.MARKDOWN]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is Markdown with SVG content
        """
        if not isinstance(source, str):
            return False

        content = source.lower()

        # Check for SVG in content
        if "<svg" not in content:
            return False

        # Check for Markdown indicators
        md_markers = [
            "```",  # Code fences
            "# ",  # Headers
            "## ",
            "- ",  # Lists
            "* ",
            "1. ",
            "[",  # Links/images
            "![",
        ]

        return any(marker in source for marker in md_markers)

    def parse(self, source: str) -> ElementTree:
        """Parse Markdown and extract SVG content.

        Handles both inline SVG and SVG in fenced code blocks.

        Args:
            source: Markdown string

        Returns:
            ElementTree containing the SVG

        Raises:
            SVGParseError: If no SVG found
        """
        svg_content = self._extract_svg(source)
        if not svg_content:
            raise SVGParseError("No SVG content found in Markdown")

        try:
            root = ET.fromstring(svg_content)
            return cast(ElementTree, ET.ElementTree(root))  # type: ignore[reportAttributeAccessIssue]
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG from Markdown: {e}") from e

    def parse_element(self, source: str) -> Element:
        """Parse Markdown and return SVG element."""
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Parsed SVG has no root element")
        return root

    def serialize(self, tree: ElementTree, target: str | None = None) -> str:
        """Serialize ElementTree back to Markdown with SVG.

        Args:
            tree: ElementTree to serialize
            target: Original Markdown to update (optional)

        Returns:
            Markdown string with SVG
        """
        self._register_namespaces()

        # Serialize SVG
        buffer = StringIO()
        tree.write(buffer, encoding="unicode")
        svg_string = buffer.getvalue()

        if target:
            return self._update_markdown_svg(target, svg_string)

        # Return SVG in fenced code block
        return f"```xml\n{svg_string}\n```"

    def extract_all_svgs(self, source: str) -> list[str]:
        """Extract all SVG elements from Markdown.

        Args:
            source: Markdown content

        Returns:
            List of SVG strings
        """
        svgs: list[str] = []

        # Extract from code fences first
        fenced_svgs = self._extract_from_fences(source)
        svgs.extend(fenced_svgs)

        # Extract inline SVGs (not in fences)
        inline_svgs = self._extract_inline_svg(source)
        svgs.extend(inline_svgs)

        return svgs

    def _extract_svg(self, markdown: str) -> str | None:
        """Extract first SVG from Markdown.

        Args:
            markdown: Markdown content

        Returns:
            SVG string or None
        """
        svgs = self.extract_all_svgs(markdown)
        return svgs[0] if svgs else None

    def _extract_from_fences(self, markdown: str) -> list[str]:
        """Extract SVG from fenced code blocks.

        Args:
            markdown: Markdown content

        Returns:
            List of SVG strings from code blocks
        """
        svgs: list[str] = []

        # Match fenced code blocks that might contain SVG
        fence_pattern = re.compile(
            r"```(?:xml|svg|html)?\s*\n(.*?)```",
            re.DOTALL | re.IGNORECASE,
        )

        for match in fence_pattern.finditer(markdown):
            content = match.group(1).strip()
            if "<svg" in content.lower():
                # Extract SVG element from content
                svg_match = re.search(
                    r"<svg[^>]*>.*?</svg>",
                    content,
                    re.DOTALL | re.IGNORECASE,
                )
                if svg_match:
                    svgs.append(svg_match.group())

        return svgs

    def _extract_inline_svg(self, markdown: str) -> list[str]:
        """Extract inline SVG elements from Markdown.

        Args:
            markdown: Markdown content

        Returns:
            List of SVG strings
        """
        svgs: list[str] = []

        # Remove fenced code blocks first
        no_fences = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)

        # Find inline SVG elements
        svg_pattern = re.compile(
            r"<svg[^>]*>.*?</svg>",
            re.DOTALL | re.IGNORECASE,
        )

        for match in svg_pattern.finditer(no_fences):
            svgs.append(match.group())

        return svgs

    def _update_markdown_svg(self, markdown: str, new_svg: str) -> str:
        """Update first SVG in Markdown.

        Args:
            markdown: Original Markdown
            new_svg: New SVG string

        Returns:
            Updated Markdown
        """
        # Try updating in fenced code block first
        fence_pattern = re.compile(
            r"(```(?:xml|svg|html)?\s*\n)(.*?)(```)",
            re.DOTALL | re.IGNORECASE,
        )

        def replace_fence(match: re.Match[str]) -> str:
            prefix = match.group(1)
            content = match.group(2)
            suffix = match.group(3)

            if "<svg" in content.lower():
                # Replace SVG in this block
                new_content = re.sub(
                    r"<svg[^>]*>.*?</svg>",
                    new_svg,
                    content,
                    count=1,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                return f"{prefix}{new_content}{suffix}"
            return match.group()

        updated = fence_pattern.sub(replace_fence, markdown, count=1)

        # If no change, try inline SVG
        if updated == markdown:
            updated = re.sub(
                r"<svg[^>]*>.*?</svg>",
                new_svg,
                markdown,
                count=1,
                flags=re.DOTALL | re.IGNORECASE,
            )

        return updated

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
