"""JavaScript/TypeScript code handler for embedded SVG strings.

Extracts and converts SVG content from JS/TS template literals,
strings, and JSX expressions.
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


# Regex patterns for finding SVG content in JavaScript/TypeScript
# Template literal: `<svg>...</svg>`
TEMPLATE_LITERAL_SVG = re.compile(
    r"`([^`]*<svg[^`]*</svg>)[^`]*`",
    re.IGNORECASE | re.DOTALL,
)

# Single-quoted string: '<svg>...</svg>'
SINGLE_QUOTED_SVG = re.compile(
    r"'([^']*<svg[^']*</svg>)[^']*'",
    re.IGNORECASE | re.DOTALL,
)

# Double-quoted string: "<svg>...</svg>"
DOUBLE_QUOTED_SVG = re.compile(
    r'"([^"]*<svg[^"]*</svg>)[^"]*"',
    re.IGNORECASE | re.DOTALL,
)

# JSX inline SVG: return (<svg>...</svg>) or return <svg>...</svg>
JSX_SVG = re.compile(
    r"(?:return\s*\(?|=>\s*\(?)\s*(<svg[\s\S]*?</svg>)\s*\)?",
    re.IGNORECASE,
)

# Generic pattern to catch SVG elements anywhere (fallback)
GENERIC_SVG = re.compile(
    r"(<svg\b[^>]*>[\s\S]*?</svg>)",
    re.IGNORECASE,
)


class JavaScriptCodeHandler(FormatHandler):
    """Handler for SVG embedded in JavaScript/TypeScript code.

    This handler extracts SVG content from various JavaScript/TypeScript
    string formats including template literals, single/double-quoted strings,
    and JSX expressions. It preserves the original code structure when
    writing back modified SVG content.

    Attributes:
        _all_svgs: List of all SVG strings found during parsing.
        _original_content: Original file content for replacement operations.
        _source_path: Path to the source file being processed.
    """

    def __init__(self) -> None:
        """Initialize the JavaScript/TypeScript code handler.

        Sets up internal storage for tracking found SVG elements,
        original file content, and source file path. These are
        populated during parse operations and used for serialization.

        Args:
            None

        Returns:
            None
        """
        super().__init__()
        self._all_svgs: list[str] = []
        self._original_content: str = ""
        self._source_path: Path | None = None

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of input formats this handler can process.

        Returns:
            list[InputFormat]: Single-element list containing JAVASCRIPT_CODE format.
        """
        return [InputFormat.JAVASCRIPT_CODE]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is a JS/TS file with embedded SVG
        """
        if isinstance(source, Path):
            return source.suffix.lower() in (".js", ".ts", ".jsx", ".tsx")

        if isinstance(source, str):
            # Check if it looks like a path to JS/TS file
            if source.startswith("<"):
                return False
            path = Path(source)
            if path.is_file() and path.suffix.lower() in (".js", ".ts", ".jsx", ".tsx"):
                return True

        return False

    def parse(self, source: str | Path) -> ElementTree:
        """Parse JS/TS file and extract first SVG as ElementTree.

        Args:
            source: File path to JS/TS file

        Returns:
            Parsed ElementTree from first SVG found

        Raises:
            SVGParseError: If parsing fails or no SVG found
            FileNotFoundError: If file doesn't exist
        """
        path = Path(source) if isinstance(source, str) else source

        if not path.is_file():
            raise FileNotFoundError(f"JavaScript/TypeScript file not found: {path}")

        # Check file size before reading to prevent memory exhaustion
        file_size = path.stat().st_size

        # Respect config.security.ignore_size_limits if set
        should_check_size = True
        if (
            self.config
            and hasattr(self.config, "security")
            and getattr(self.config.security, "ignore_size_limits", False)
        ):
            should_check_size = False

        if should_check_size:
            # Use config.security.max_file_size_mb if set, otherwise use default
            max_size = MAX_FILE_SIZE
            if self.config and hasattr(self.config, "security"):
                max_file_size_mb = getattr(
                    self.config.security, "max_file_size_mb", None
                )
                if max_file_size_mb is not None:
                    max_size = max_file_size_mb * 1024 * 1024

            if file_size > max_size:
                raise SVGParseError(
                    f"File too large: {file_size} bytes (max: {max_size})"
                )

        self._source_path = path
        self._all_svgs = []

        try:
            self._original_content = path.read_text(encoding="utf-8")
        except Exception as e:
            raise SVGParseError(f"Error reading file: {e}") from e

        # Find all SVG strings using multiple patterns
        self._extract_all_svgs(self._original_content)

        if not self._all_svgs:
            raise SVGParseError(f"No SVG content found in: {path}")

        # Parse first SVG as ElementTree
        first_svg = self._all_svgs[0]
        try:
            return cast(ElementTree, ET.fromstring(first_svg))
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG: {e}") from e

    def _extract_all_svgs(self, content: str) -> None:
        """Extract all SVG strings from JavaScript/TypeScript content.

        Searches the file content using multiple regex patterns in order
        of specificity: template literals, single/double-quoted strings,
        JSX expressions, and finally a generic fallback pattern. Deduplicates
        results and stores them in _all_svgs.

        Args:
            content (str): The complete JS/TS file content to search.

        Returns:
            None: Results are stored in self._all_svgs.
        """
        found_svgs: set[str] = set()

        # Try each pattern in order of specificity
        for pattern in [
            TEMPLATE_LITERAL_SVG,
            SINGLE_QUOTED_SVG,
            DOUBLE_QUOTED_SVG,
            JSX_SVG,
        ]:
            for match in pattern.finditer(content):
                svg_content = match.group(1)
                # Clean up escaped characters from strings
                svg_content = self._unescape_string(svg_content)
                if svg_content and svg_content not in found_svgs:
                    found_svgs.add(svg_content)
                    self._all_svgs.append(svg_content)

        # If no matches, try generic pattern as fallback
        if not self._all_svgs:
            for match in GENERIC_SVG.finditer(content):
                svg_content = match.group(1)
                svg_content = self._unescape_string(svg_content)
                if svg_content and svg_content not in found_svgs:
                    found_svgs.add(svg_content)
                    self._all_svgs.append(svg_content)

    def _unescape_string(self, s: str) -> str:
        """Unescape common JavaScript string escape sequences.

        Args:
            s: Escaped string

        Returns:
            Unescaped string
        """
        # Handle common escape sequences
        s = s.replace("\\'", "'")
        s = s.replace('\\"', '"')
        s = s.replace("\\n", "\n")
        s = s.replace("\\r", "\r")
        s = s.replace("\\t", "\t")
        s = s.replace("\\\\", "\\")
        return s

    def _escape_string(self, s: str, quote_char: str = '"') -> str:
        """Escape string for JavaScript.

        Args:
            s: String to escape
            quote_char: Quote character being used (' or ")

        Returns:
            Escaped string
        """
        s = s.replace("\\", "\\\\")
        s = s.replace('"', '\\"') if quote_char == '"' else s.replace("'", "\\'")
        return s

    def serialize(self, tree: ElementTree, target: str | Path) -> Path:
        """Write modified SVG back to JS/TS file.

        Replaces the first SVG string with the converted tree,
        preserving the original code structure.

        Args:
            tree: ElementTree to serialize
            target: Output file path

        Returns:
            Path to written file
        """
        path = Path(target) if isinstance(target, str) else target

        # Register SVG namespaces
        self._register_namespaces()

        # Serialize tree to string
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Tree has no root element")
        svg_string = ET.tostring(root, encoding="unicode")

        # If we have original content and SVGs, do replacement
        if self._original_content and self._all_svgs:
            new_content = self._replace_svg_in_code(
                self._original_content, self._all_svgs[0], svg_string
            )
        else:
            # No original content, write SVG directly (unusual case)
            new_content = svg_string

        path.write_text(new_content, encoding="utf-8")
        return path

    def _replace_svg_in_code(self, content: str, old_svg: str, new_svg: str) -> str:
        """Replace SVG string in JavaScript/TypeScript code.

        Attempts to find and replace the SVG while preserving
        the surrounding quote style.

        Args:
            content: Original file content
            old_svg: Original SVG string
            new_svg: New SVG string to insert

        Returns:
            Modified content with replaced SVG
        """
        # Try to find the exact context of the old SVG
        # Check template literals first
        template_pattern = re.compile(
            r"`([^`]*)" + re.escape(old_svg) + r"([^`]*)`",
            re.DOTALL,
        )
        match = template_pattern.search(content)
        if match:
            prefix, suffix = match.group(1), match.group(2)
            return template_pattern.sub(
                f"`{prefix}{new_svg}{suffix}`", content, count=1
            )

        # Check double-quoted strings
        double_pattern = re.compile(
            r'"([^"]*?)' + re.escape(self._escape_string(old_svg, '"')) + r'([^"]*?)"',
            re.DOTALL,
        )
        match = double_pattern.search(content)
        if match:
            prefix, suffix = match.group(1), match.group(2)
            escaped_new = self._escape_string(new_svg, '"')
            return double_pattern.sub(
                f'"{prefix}{escaped_new}{suffix}"', content, count=1
            )

        # Check single-quoted strings
        single_pattern = re.compile(
            r"'([^']*?)" + re.escape(self._escape_string(old_svg, "'")) + r"([^']*?)'",
            re.DOTALL,
        )
        match = single_pattern.search(content)
        if match:
            prefix, suffix = match.group(1), match.group(2)
            escaped_new = self._escape_string(new_svg, "'")
            return single_pattern.sub(
                f"'{prefix}{escaped_new}{suffix}'", content, count=1
            )

        # Check JSX (no quotes around SVG)
        jsx_pattern = re.compile(
            r"((?:return\s*\(?|=>\s*\(?))\s*" + re.escape(old_svg) + r"(\s*\)?)",
            re.DOTALL,
        )
        match = jsx_pattern.search(content)
        if match:
            prefix, suffix = match.group(1), match.group(2)
            return jsx_pattern.sub(f"{prefix}{new_svg}{suffix}", content, count=1)

        # Fallback: simple string replacement
        return content.replace(old_svg, new_svg, 1)

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces to avoid ns0: prefixes in output.

        Registers standard SVG, XLink, Inkscape, and Sodipodi namespaces
        with xml.etree.ElementTree to ensure proper namespace prefix
        formatting in serialized output. This prevents generic ns0:, ns1:
        prefixes from appearing in the generated SVG.

        Args:
            None

        Returns:
            None: Namespaces are registered globally in ElementTree.
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

    @property
    def all_svgs(self) -> list[str]:
        """Return all SVGs found during last parse.

        Returns:
            List of SVG strings found in the file
        """
        return self._all_svgs.copy()

    def parse_all(self, source: str | Path) -> list[ElementTree]:
        """Parse all SVGs from JS/TS file.

        Args:
            source: File path to JS/TS file

        Returns:
            List of ElementTrees for all SVGs found

        Raises:
            SVGParseError: If parsing fails
        """
        # First call regular parse to populate _all_svgs
        self.parse(source)

        trees: list[ElementTree] = []
        for svg_str in self._all_svgs:
            try:
                tree = cast(ElementTree, ET.fromstring(svg_str))
                trees.append(tree)
            except ET.ParseError:
                # Skip malformed SVGs in batch mode
                continue

        return trees

    def serialize_all(self, trees: list[ElementTree], target: str | Path) -> Path:
        """Write all modified SVGs back to JS/TS file.

        Args:
            trees: List of ElementTrees to serialize
            target: Output file path

        Returns:
            Path to written file
        """
        path = Path(target) if isinstance(target, str) else target

        if not self._original_content or not self._all_svgs:
            raise SVGParseError(
                "Must call parse() or parse_all() before serialize_all()"
            )

        self._register_namespaces()

        content = self._original_content

        # Replace each SVG in order
        for i, tree in enumerate(trees):
            if i >= len(self._all_svgs):
                break

            old_svg = self._all_svgs[i]
            root = tree.getroot()
            if root is None:
                raise SVGParseError(f"Tree at index {i} has no root element")
            new_svg = ET.tostring(root, encoding="unicode")
            content = self._replace_svg_in_code(content, old_svg, new_svg)

        path.write_text(content, encoding="utf-8")
        return path
