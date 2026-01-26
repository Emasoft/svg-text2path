"""reStructuredText SVG input handler.

Handles SVG content in RST files via raw:: directives and code blocks.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import ElementTree as StdElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

# Use standard library ElementTree class (defusedxml doesn't export it)
ElementTree = StdElementTree

if TYPE_CHECKING:
    pass


class RSTHandler(FormatHandler):
    """Handler for reStructuredText with embedded SVG content.

    Extracts SVG from:
    - .. raw:: html directives containing <svg>
    - .. raw:: svg directives
    - Inline SVG in code blocks (.. code-block:: xml/html)
    """

    def __init__(self) -> None:
        """Initialize handler with storage for all found SVGs.

        Sets up internal state to track:
        - All SVG elements extracted from RST content
        - Original RST content for serialization
        - Source file path for reference
        """
        self._all_svgs: list[str] = []
        self._original_content: str = ""
        self._source_path: Path | None = None

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports.

        Returns:
            list[InputFormat]: List containing InputFormat.RST
        """
        return [InputFormat.RST]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Determines if the source contains RST content with embedded SVG
        by checking for RST directive markers and SVG elements.

        Args:
            source (Any): Input source (file path or string content)

        Returns:
            bool: True if source is RST with SVG content, False otherwise
        """
        content = self._get_content(source)
        if content is None:
            return False

        # Must have SVG somewhere
        if "<svg" not in content.lower():
            return False

        # Check for RST indicators (raw directives or RST file extension)
        rst_markers = [
            ".. raw::",
            ".. code-block::",
            ".. code::",
            "::\n",
            ".. image::",
            ".. figure::",
        ]

        # Check if it's an RST file path
        if isinstance(source, (str, Path)):
            path = Path(source) if isinstance(source, str) else source
            if path.suffix.lower() in (".rst", ".rest", ".txt") and path.exists():
                return True

        return any(marker in content for marker in rst_markers)

    def parse(self, source: str | Path) -> ElementTree:
        """Parse RST and extract SVG content.

        Reads the RST file/content, finds ALL SVG elements, stores them
        in self._all_svgs, and returns the first SVG as an ElementTree.

        Args:
            source (str | Path): RST file path or string content

        Returns:
            ElementTree: ElementTree containing the first SVG

        Raises:
            SVGParseError: If no SVG found or parsing fails
            FileNotFoundError: If file path doesn't exist
        """
        content = self._get_content(source)
        if content is None:
            raise SVGParseError("Cannot read RST content from source")

        # Store original content for serialization
        self._original_content = content

        # Store source path if provided
        if isinstance(source, Path):
            self._source_path = source
        elif isinstance(source, str) and not source.startswith(".."):
            path = Path(source)
            if path.exists():
                self._source_path = path

        # Extract all SVGs
        self._all_svgs = self._extract_all_svgs(content)

        if not self._all_svgs:
            raise SVGParseError("No SVG content found in RST")

        # Parse first SVG
        try:
            root = ET.fromstring(self._all_svgs[0])
            return cast(ElementTree, StdElementTree(root))
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG from RST: {e}") from e

    def parse_element(self, source: str | Path) -> Element:
        """Parse RST and return SVG element.

        Convenience method that parses RST content and returns the root
        SVG element directly instead of an ElementTree.

        Args:
            source (str | Path): RST file path or string content

        Returns:
            Element: Root SVG element from the first SVG found

        Raises:
            SVGParseError: If no SVG found or root element is None
            FileNotFoundError: If file path doesn't exist
        """
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Parsed SVG has no root element")
        return root

    def serialize(self, tree: ElementTree, target: str | Path) -> Path:
        """Serialize ElementTree back to RST file with updated SVG.

        Converts the ElementTree to SVG string and updates the first
        SVG element in the original RST content, preserving directive
        structure and indentation.

        Args:
            tree (ElementTree): ElementTree to serialize
            target (str | Path): Output file path

        Returns:
            Path: Path to written file

        Raises:
            SVGParseError: If no original content to update
        """
        if not self._original_content:
            raise SVGParseError("No original RST content to update")

        self._register_namespaces()

        # Serialize SVG to string
        buffer = StringIO()
        tree.write(buffer, encoding="unicode")
        new_svg = buffer.getvalue()

        # Update the RST content with new SVG
        updated_content = self._update_rst_svg(self._original_content, new_svg)

        # Write to target file
        path = Path(target) if isinstance(target, str) else target
        path.write_text(updated_content, encoding="utf-8")

        return path

    def get_all_svgs(self) -> list[str]:
        """Return all SVGs found during last parse.

        Returns a copy of the internal list of all SVG elements that
        were extracted during the most recent parse() call.

        Returns:
            list[str]: List of SVG strings (copy of internal list)
        """
        return self._all_svgs.copy()

    def _get_content(self, source: Any) -> str | None:
        """Get string content from source.

        Handles multiple source types:
        - Path objects: reads file content
        - Strings that look like file paths: reads if file exists
        - Strings that look like content: returns as-is

        Args:
            source (Any): File path (str or Path) or string content

        Returns:
            str | None: String content or None if cannot read
        """
        if isinstance(source, Path):
            if source.exists():
                return source.read_text(encoding="utf-8")
            return None

        if isinstance(source, str):
            # Check if it's a file path
            if not source.startswith("..") and not source.startswith("<"):
                path = Path(source)
                if path.exists() and path.suffix.lower() in (".rst", ".rest", ".txt"):
                    return path.read_text(encoding="utf-8")
            # Otherwise treat as content
            return source

        return None

    def _extract_all_svgs(self, content: str) -> list[str]:
        """Extract all SVG elements from RST content.

        Searches for SVG elements in multiple locations:
        1. raw:: html directives
        2. raw:: svg directives
        3. code-block:: directives
        4. Inline SVG (not in directives)

        Args:
            content (str): RST string content

        Returns:
            list[str]: List of all SVG strings found
        """
        svgs: list[str] = []

        # Extract from raw:: html directives
        svgs.extend(self._extract_from_raw_html(content))

        # Extract from raw:: svg directives
        svgs.extend(self._extract_from_raw_svg(content))

        # Extract from code blocks
        svgs.extend(self._extract_from_code_blocks(content))

        # Extract any inline SVGs (not in directives)
        svgs.extend(self._extract_inline_svg(content))

        return svgs

    def _extract_from_raw_html(self, content: str) -> list[str]:
        """Extract SVG from .. raw:: html directives.

        RST raw directive format:
        .. raw:: html

           <svg xmlns="...">...</svg>

        The SVG content is indented under the directive. This method
        detects the minimum indentation and removes it before extracting
        the SVG element.

        Args:
            content (str): RST content to search

        Returns:
            list[str]: List of SVG strings from raw:: html directives
        """
        svgs: list[str] = []

        # Match raw:: html directive and its indented content
        # The directive is followed by a blank line, then indented content
        raw_html_pattern = re.compile(
            r"\.\.\s+raw::\s+html\s*\n\n((?:[ \t]+.+\n)+)",
            re.IGNORECASE,
        )

        for match in raw_html_pattern.finditer(content):
            directive_content = match.group(1)
            # Remove leading indentation
            lines = directive_content.split("\n")
            if lines:
                # Find minimum indentation
                min_indent = float("inf")
                for line in lines:
                    if line.strip():
                        indent = len(line) - len(line.lstrip())
                        min_indent = min(min_indent, indent)
                if min_indent == float("inf"):
                    min_indent = 0
                # Remove that indentation
                dedented = "\n".join(
                    line[int(min_indent) :] if len(line) >= min_indent else line
                    for line in lines
                )
                # Find SVG in the dedented content
                svg_match = re.search(
                    r"<svg[^>]*>.*?</svg>",
                    dedented,
                    re.DOTALL | re.IGNORECASE,
                )
                if svg_match:
                    svgs.append(svg_match.group())

        return svgs

    def _extract_from_raw_svg(self, content: str) -> list[str]:
        """Extract SVG from .. raw:: svg directives.

        Handles RST raw directive format specifically for SVG content:
        .. raw:: svg

           <svg xmlns="...">...</svg>

        The SVG content is indented under the directive. This method
        removes the indentation and extracts the SVG element.

        Args:
            content (str): RST content to search

        Returns:
            list[str]: List of SVG strings from raw:: svg directives
        """
        svgs: list[str] = []

        # Match raw:: svg directive and its indented content
        raw_svg_pattern = re.compile(
            r"\.\.\s+raw::\s+svg\s*\n\n((?:[ \t]+.+\n)+)",
            re.IGNORECASE,
        )

        for match in raw_svg_pattern.finditer(content):
            directive_content = match.group(1)
            # Remove leading indentation
            lines = directive_content.split("\n")
            if lines:
                min_indent = float("inf")
                for line in lines:
                    if line.strip():
                        indent = len(line) - len(line.lstrip())
                        min_indent = min(min_indent, indent)
                if min_indent == float("inf"):
                    min_indent = 0
                dedented = "\n".join(
                    line[int(min_indent) :] if len(line) >= min_indent else line
                    for line in lines
                )
                # Find SVG in the dedented content
                svg_match = re.search(
                    r"<svg[^>]*>.*?</svg>",
                    dedented,
                    re.DOTALL | re.IGNORECASE,
                )
                if svg_match:
                    svgs.append(svg_match.group())

        return svgs

    def _extract_from_code_blocks(self, content: str) -> list[str]:
        """Extract SVG from code-block directives.

        Handles RST code-block directives with xml/html/svg language:
        .. code-block:: xml

           <svg xmlns="...">...</svg>

        Also supports the shorter .. code:: syntax. The SVG content
        is indented under the directive. This method removes the
        indentation and extracts the SVG element.

        Args:
            content (str): RST content to search

        Returns:
            list[str]: List of SVG strings from code blocks
        """
        svgs: list[str] = []

        # Match code-block:: xml/html/svg directives
        code_block_pattern = re.compile(
            r"\.\.\s+code(?:-block)?::\s*(?:xml|html|svg)?\s*\n\n((?:[ \t]+.+\n)+)",
            re.IGNORECASE,
        )

        for match in code_block_pattern.finditer(content):
            block_content = match.group(1)
            # Remove leading indentation
            lines = block_content.split("\n")
            if lines:
                min_indent = float("inf")
                for line in lines:
                    if line.strip():
                        indent = len(line) - len(line.lstrip())
                        min_indent = min(min_indent, indent)
                if min_indent == float("inf"):
                    min_indent = 0
                dedented = "\n".join(
                    line[int(min_indent) :] if len(line) >= min_indent else line
                    for line in lines
                )
                # Find SVG in the block
                if "<svg" in dedented.lower():
                    svg_match = re.search(
                        r"<svg[^>]*>.*?</svg>",
                        dedented,
                        re.DOTALL | re.IGNORECASE,
                    )
                    if svg_match:
                        svgs.append(svg_match.group())

        return svgs

    def _extract_inline_svg(self, content: str) -> list[str]:
        """Extract inline SVG elements not in directives.

        Finds SVG elements that appear directly in the RST content
        without being wrapped in raw:: or code-block:: directives.
        This catches any remaining SVG elements that were not extracted
        by the directive-specific methods.

        To avoid duplicates, this method first removes all directive
        content before searching for SVG elements.

        Args:
            content (str): RST content to search

        Returns:
            list[str]: List of inline SVG strings not in directives
        """
        svgs: list[str] = []

        # Remove directive content first to avoid duplicates
        no_directives = re.sub(
            r"\.\.\s+(?:raw|code(?:-block)?)::[^\n]*\n\n(?:[ \t]+.+\n)+",
            "",
            content,
            flags=re.IGNORECASE,
        )

        # Find any remaining SVG elements
        svg_pattern = re.compile(
            r"<svg[^>]*>.*?</svg>",
            re.DOTALL | re.IGNORECASE,
        )

        for match in svg_pattern.finditer(no_directives):
            svgs.append(match.group())

        return svgs

    def _update_rst_svg(self, rst_content: str, new_svg: str) -> str:
        """Update first SVG in RST content.

        Replaces the first SVG element found in the RST content with
        a new SVG string. The method tries to update in this order:
        1. SVG in raw:: html directive (with proper indentation)
        2. SVG in raw:: svg directive (with proper indentation)
        3. Inline SVG (no indentation)

        When updating directives, the method preserves the original
        indentation level by detecting it from the existing content.

        Args:
            rst_content (str): Original RST content
            new_svg (str): New SVG string to replace the first SVG

        Returns:
            str: Updated RST content with first SVG replaced
        """
        # Try updating in raw:: html directive first
        raw_html_pattern = re.compile(
            r"(\.\.\s+raw::\s+html\s*\n\n)((?:[ \t]+.+\n)+)",
            re.IGNORECASE,
        )

        def replace_in_directive(match: re.Match[str]) -> str:
            directive = match.group(1)
            content = match.group(2)

            if "<svg" not in content.lower():
                return match.group()

            # Get the indentation from the original content
            lines = content.split("\n")
            indent = ""
            for line in lines:
                if line.strip():
                    indent = " " * (len(line) - len(line.lstrip()))
                    break

            # Indent the new SVG
            indented_svg = "\n".join(
                indent + line if line.strip() else line for line in new_svg.split("\n")
            )

            # Replace SVG in content
            new_content = re.sub(
                r"<svg[^>]*>.*?</svg>",
                indented_svg.strip(),
                content,
                count=1,
                flags=re.DOTALL | re.IGNORECASE,
            )
            return f"{directive}{new_content}"

        updated = raw_html_pattern.sub(replace_in_directive, rst_content, count=1)

        # If no change, try raw:: svg directive
        if updated == rst_content:
            raw_svg_pattern = re.compile(
                r"(\.\.\s+raw::\s+svg\s*\n\n)((?:[ \t]+.+\n)+)",
                re.IGNORECASE,
            )
            updated = raw_svg_pattern.sub(replace_in_directive, rst_content, count=1)

        # If still no change, try inline SVG
        if updated == rst_content:
            updated = re.sub(
                r"<svg[^>]*>.*?</svg>",
                new_svg,
                rst_content,
                count=1,
                flags=re.DOTALL | re.IGNORECASE,
            )

        return updated

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces.

        Registers standard SVG namespaces with ElementTree to ensure
        proper namespace handling during serialization. This prevents
        ElementTree from using auto-generated namespace prefixes like
        'ns0', 'ns1', etc.

        Registers:
        - Default namespace: http://www.w3.org/2000/svg
        - xlink namespace: http://www.w3.org/1999/xlink
        """
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
