"""Python source code handler for embedded SVG strings.

Extracts and converts SVG content embedded in Python source files,
supporting triple-quoted strings and regular string literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

# File size limits to prevent memory exhaustion
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size

if TYPE_CHECKING:
    pass  # ElementTree imported above for cast()


# Regex patterns for finding SVG strings in Python code
# Pattern for triple-quoted strings containing <svg
_TRIPLE_QUOTE_SVG_PATTERN = re.compile(
    r'("""[\s\S]*?<svg[\s\S]*?</svg>[\s\S]*?"""|'
    r"'''[\s\\S]*?<svg[\\s\\S]*?</svg>[\\s\\S]*?''')",
    re.IGNORECASE,
)

# Pattern for single/double quoted strings containing <svg (single line)
_SINGLE_QUOTE_SVG_PATTERN = re.compile(
    r'("[^"\\]*(?:\\.[^"\\]*)*<svg[^"\\]*(?:\\.[^"\\]*)*</svg>[^"\\]*(?:\\.[^"\\]*)*"|'
    r"'[^'\\]*(?:\\.[^'\\]*)*<svg[^'\\]*(?:\\.[^'\\]*)*</svg>[^'\\]*(?:\\.[^'\\]*)*')",
    re.IGNORECASE,
)

# Combined pattern to find any SVG-containing string
_SVG_STRING_PATTERN = re.compile(
    r'("""[\s\S]*?<svg[\s\S]*?</svg>[\s\S]*?"""|'
    r"'''[\s\S]*?<svg[\s\S]*?</svg>[\s\S]*?'''|"
    r'"[^"\n]*<svg[^"\n]*</svg>[^"\n]*"|'
    r"'[^'\n]*<svg[^'\n]*</svg>[^'\n]*')",
    re.IGNORECASE,
)


class PythonCodeHandler(FormatHandler):
    """Handler for Python source files containing embedded SVG strings.

    Extracts SVG content from Python string literals (single, double, triple-quoted)
    and f-strings. Supports round-trip editing where converted SVG replaces
    original strings in the source file.

    Attributes:
        _all_svgs: List of tuples (svg_content, start_pos, end_pos) for all
            extracted SVGs
        _original_source: Original Python source code for serialization
        _source_path: Path to source file if parsed from file, None otherwise

    Example:
        >>> handler = PythonCodeHandler()
        >>> tree = handler.parse("icons.py")
        >>> # ... convert tree ...
        >>> handler.serialize(converted_tree, "icons_converted.py")
    """

    def __init__(self) -> None:
        """Initialize handler with storage for multiple SVGs.

        Sets up empty storage for SVG extraction and source tracking.
        """
        super().__init__()
        # Store all found SVGs for batch mode processing
        self._all_svgs: list[
            tuple[str, int, int]
        ] = []  # (svg_content, start_pos, end_pos)
        # Store original source for serialization
        self._original_source: str = ""
        # Store original file path
        self._source_path: Path | None = None

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports.

        Returns:
            list[InputFormat]: List containing InputFormat.PYTHON_CODE
        """
        return [InputFormat.PYTHON_CODE]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Validates that the source is a .py file containing SVG content.
        Supports both Path objects and string paths.

        Args:
            source (Any): Input source - can be Path object or string path

        Returns:
            bool: True if source is a valid .py file containing '<svg' tag,
                False otherwise (including on read errors)
        """
        if isinstance(source, Path):
            if source.suffix.lower() != ".py":
                return False
            # Check if file contains SVG
            try:
                content = source.read_text(encoding="utf-8")
                return "<svg" in content.lower()
            except Exception:
                return False

        if isinstance(source, str):
            # Check if it's a path to a .py file
            if source.startswith("<"):
                return False
            path = Path(source)
            if path.is_file() and path.suffix.lower() == ".py":
                try:
                    content = path.read_text(encoding="utf-8")
                    return "<svg" in content.lower()
                except Exception:
                    return False

        return False

    def parse(self, source: str | Path) -> ElementTree:
        """Parse Python file and extract SVG content into an ElementTree.

        Finds ALL SVG strings in the file using regex patterns, stores them
        internally for batch mode processing, and returns the first SVG as
        an ElementTree for single conversion mode.

        Args:
            source (str | Path): File path to Python source file (.py extension)

        Returns:
            ElementTree: Parsed ElementTree of the first SVG found in the file

        Raises:
            SVGParseError: If no SVG found in file or XML parsing fails
            FileNotFoundError: If file doesn't exist at the specified path
        """
        path = Path(source) if isinstance(source, str) else source
        self._source_path = path

        if not path.is_file():
            raise FileNotFoundError(f"Python file not found: {path}")

        # Check file size before reading to prevent memory exhaustion
        file_size = path.stat().st_size
        # Respect config.security.ignore_size_limits if set
        should_check_size = True
        if (
            hasattr(self, "config")
            and self.config is not None
            and hasattr(self.config, "security")
            and self.config.security.ignore_size_limits
        ):
            should_check_size = False

        if should_check_size:
            # Use config max_file_size_mb if available, otherwise default
            max_size = MAX_FILE_SIZE
            if (
                hasattr(self, "config")
                and self.config is not None
                and hasattr(self.config, "security")
                and self.config.security.max_file_size_mb is not None
            ):
                max_size = self.config.security.max_file_size_mb * 1024 * 1024

            if file_size > max_size:
                raise SVGParseError(
                    f"File too large: {file_size} bytes (max: {max_size})"
                )

        try:
            self._original_source = path.read_text(encoding="utf-8")
        except Exception as e:
            raise SVGParseError(f"Error reading Python file: {e}") from e

        # Find all SVG strings in the source
        self._all_svgs = self._extract_all_svgs(self._original_source)

        if not self._all_svgs:
            raise SVGParseError(f"No SVG content found in Python file: {path}")

        # Return the first SVG as ElementTree
        first_svg_content, _, _ = self._all_svgs[0]
        return self._parse_svg_string(first_svg_content)

    def serialize(self, tree: ElementTree, target: str | Path) -> Path:
        """Write modified SVG back into the Python source file.

        Replaces the first SVG string in the original Python code with
        the serialized tree content, preserving Python code structure
        and the original quote style.

        Args:
            tree (ElementTree): ElementTree to serialize (converted SVG)
            target (str | Path): Output file path for the modified Python file

        Returns:
            Path: Path object pointing to the written file

        Raises:
            SVGParseError: If no SVG content was previously parsed
        """
        path = Path(target) if isinstance(target, str) else target

        if not self._all_svgs:
            raise SVGParseError("No SVG content was parsed; cannot serialize")

        # Register namespaces for clean output
        self._register_namespaces()

        # Serialize the tree to SVG string
        from io import StringIO

        buffer = StringIO()
        tree.write(buffer, encoding="unicode", xml_declaration=True)
        new_svg_content = buffer.getvalue()

        # Replace the first SVG in the original source
        first_svg, start_pos, end_pos = self._all_svgs[0]
        original_quote_style = self._detect_quote_style(first_svg)

        # Wrap new SVG in the same quote style as original
        if original_quote_style == '"""':
            new_string = f'"""{new_svg_content}"""'
        elif original_quote_style == "'''":
            new_string = f"'''{new_svg_content}'''"
        elif original_quote_style == '"':
            # Escape for double quotes - single line
            escaped = (
                new_svg_content.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )
            new_string = f'"{escaped}"'
        else:  # single quote
            escaped = (
                new_svg_content.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace("\n", "\\n")
            )
            new_string = f"'{escaped}'"

        # Build the new source by replacing the SVG string
        new_source = (
            self._original_source[:start_pos]
            + new_string
            + self._original_source[end_pos:]
        )

        # Write the modified Python file
        path.write_text(new_source, encoding="utf-8")

        return path

    def serialize_all(self, trees: list[ElementTree], target: str | Path) -> Path:
        """Write all modified SVGs back into the Python source file.

        Replaces each SVG string with its corresponding converted tree,
        preserving the original quote style for each. Replacements are
        applied in reverse order to maintain correct positions.

        Args:
            trees (list[ElementTree]): List of ElementTrees (one for each SVG found)
            target (str | Path): Output file path for the modified Python file

        Returns:
            Path: Path object pointing to the written file

        Raises:
            SVGParseError: If no SVG content was parsed or tree count doesn't
                match SVG count
        """
        path = Path(target) if isinstance(target, str) else target

        if not self._all_svgs:
            raise SVGParseError("No SVG content was parsed; cannot serialize")

        if len(trees) != len(self._all_svgs):
            tree_count = len(trees)
            svg_count = len(self._all_svgs)
            raise SVGParseError(
                f"Tree count ({tree_count}) doesn't match SVG count ({svg_count})"
            )

        # Register namespaces
        self._register_namespaces()

        # Build replacements in reverse order to preserve positions
        replacements: list[tuple[int, int, str]] = []
        from io import StringIO

        for tree, (original_svg, start_pos, end_pos) in zip(
            trees, self._all_svgs, strict=True
        ):
            buffer = StringIO()
            tree.write(buffer, encoding="unicode", xml_declaration=True)
            new_svg_content = buffer.getvalue()

            original_quote_style = self._detect_quote_style(original_svg)

            if original_quote_style == '"""':
                new_string = f'"""{new_svg_content}"""'
            elif original_quote_style == "'''":
                new_string = f"'''{new_svg_content}'''"
            elif original_quote_style == '"':
                escaped = (
                    new_svg_content.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("\n", "\\n")
                )
                new_string = f'"{escaped}"'
            else:
                escaped = (
                    new_svg_content.replace("\\", "\\\\")
                    .replace("'", "\\'")
                    .replace("\n", "\\n")
                )
                new_string = f"'{escaped}'"

            replacements.append((start_pos, end_pos, new_string))

        # Apply replacements in reverse order
        new_source = self._original_source
        for start_pos, end_pos, new_string in reversed(replacements):
            new_source = new_source[:start_pos] + new_string + new_source[end_pos:]

        path.write_text(new_source, encoding="utf-8")
        return path

    def get_all_svgs(self) -> list[ElementTree]:
        """Get all SVGs found in the file as ElementTrees.

        Parses each extracted SVG string into an ElementTree for batch processing.

        Returns:
            list[ElementTree]: List of ElementTrees, one for each SVG found
                during parsing

        Raises:
            SVGParseError: If any SVG string fails to parse
        """
        return [
            self._parse_svg_string(svg_content) for svg_content, _, _ in self._all_svgs
        ]

    def get_svg_count(self) -> int:
        """Get the number of SVGs found in the file.

        Returns:
            int: Count of SVG strings extracted during parsing
        """
        return len(self._all_svgs)

    def _extract_all_svgs(self, source: str) -> list[tuple[str, int, int]]:
        """Extract all SVG-containing strings from Python source.

        Scans Python source code for string literals containing SVG content,
        supporting single/double/triple-quoted strings.

        Args:
            source (str): Python source code to scan

        Returns:
            list[tuple[str, int, int]]: List of tuples containing:
                - svg_content (str): Extracted SVG XML string
                - start_pos (int): Character position where string starts
                - end_pos (int): Character position where string ends
        """
        results: list[tuple[str, int, int]] = []

        # Find all matches using the combined pattern
        for match in _SVG_STRING_PATTERN.finditer(source):
            full_string = match.group(0)
            start_pos = match.start()
            end_pos = match.end()

            # Extract the actual SVG content from the string
            svg_content = self._extract_svg_from_string(full_string)
            if svg_content:
                results.append((svg_content, start_pos, end_pos))

        return results

    def _extract_svg_from_string(self, quoted_string: str) -> str | None:
        """Extract SVG content from a quoted Python string.

        Removes Python string quotes and unescapes escape sequences,
        then extracts the SVG portion using regex.

        Args:
            quoted_string (str): The full quoted string including quotes
                (e.g., triple-quoted or single/double-quoted SVG strings)

        Returns:
            str | None: The SVG content without quotes and unescaped,
                or None if extraction fails or no SVG found
        """
        # Determine quote style and extract content
        if quoted_string.startswith('"""') or quoted_string.startswith("'''"):
            content = quoted_string[3:-3]
        elif quoted_string.startswith('"'):
            content = quoted_string[1:-1]
            # Unescape Python escape sequences
            content = content.encode("utf-8").decode("unicode_escape")
        elif quoted_string.startswith("'"):
            content = quoted_string[1:-1]
            content = content.encode("utf-8").decode("unicode_escape")
        else:
            return None

        # Extract just the SVG portion
        svg_match = re.search(r"<svg[\s\S]*?</svg>", content, re.IGNORECASE)
        if svg_match:
            return svg_match.group(0)

        return None

    def _parse_svg_string(self, svg_content: str) -> ElementTree:
        """Parse SVG string into ElementTree.

        Uses defusedxml for secure XML parsing to prevent XXE attacks.

        Args:
            svg_content (str): Raw SVG XML content string

        Returns:
            ElementTree: Parsed ElementTree with SVG root element

        Raises:
            SVGParseError: If XML parsing fails due to malformed SVG
        """
        try:
            root = ET.fromstring(svg_content)
            return cast(ElementTree, ElementTree(root))
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse embedded SVG: {e}") from e

    def _detect_quote_style(self, original_string: str) -> str:
        """Detect the quote style used in the original string.

        Searches the original source code to determine which quote style
        was used (triple-double, triple-single, double, or single).

        Args:
            original_string (str): The SVG content to match against stored SVGs

        Returns:
            str: Quote style string - triple-double, triple-single, double, or
                single quotes. Defaults to triple-double for multiline or
                double for single-line if not found
        """
        # Check the stored SVG - we need the full match from the source
        # Look backwards from the SVG to find the quote style
        for svg_content, start_pos, _end_pos in self._all_svgs:
            if svg_content == original_string or original_string in svg_content:
                # Get the characters around the SVG in the source
                before = self._original_source[max(0, start_pos) : start_pos + 3]
                if before.startswith('"""'):
                    return '"""'
                elif before.startswith("'''"):
                    return "'''"
                elif before.startswith('"'):
                    return '"'
                elif before.startswith("'"):
                    return "'"

        # Default to triple double quotes for multiline
        if "\n" in original_string:
            return '"""'
        return '"'

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces to avoid ns0: prefixes.

        Registers standard SVG, XLink, Inkscape, and Sodipodi namespaces
        to ensure clean XML serialization without auto-generated prefixes.
        """
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "svg": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
            "inkscape": "http://www.inkscape.org/namespaces/inkscape",
            "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
