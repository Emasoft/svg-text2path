"""Base classes for input format handlers.

Provides the abstract base class and format detection utilities
for handling various SVG input formats.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from xml.etree.ElementTree import ElementTree

    from svg_text2path.config import Config


class InputFormat(Enum):
    """Supported input format types."""

    # Core SVG formats
    FILE_PATH = auto()  # Path to .svg file
    SVG_STRING = auto()  # Raw SVG string
    SVG_SNIPPET = auto()  # Partial SVG (no xml declaration)
    ZSVG = auto()  # Gzip-compressed SVG (.svgz)
    INKSCAPE = auto()  # Inkscape .svg with sodipodi namespace

    # Tree objects
    ELEMENT_TREE = auto()  # xml.etree.ElementTree
    LXML_TREE = auto()  # lxml.etree tree
    BEAUTIFULSOUP = auto()  # BeautifulSoup Tag

    # Embedded/escaped formats
    HTML_EMBEDDED = auto()  # SVG embedded in HTML
    CSS_EMBEDDED = auto()  # SVG in CSS (background-image data URIs)
    JSON_ESCAPED = auto()  # SVG string escaped in JSON
    CSV_ESCAPED = auto()  # SVG in CSV cell
    MARKDOWN = auto()  # SVG in Markdown fenced blocks

    # Remote/URI formats
    REMOTE_URL = auto()  # HTTP/HTTPS URL to SVG resource
    DATA_URI = auto()  # data:image/svg+xml;base64,... string

    # Code formats (SVG in source code strings)
    PYTHON_CODE = auto()  # Python file with SVG in strings
    JAVASCRIPT_CODE = auto()  # JS/TS file with SVG in template literals
    RST = auto()  # reStructuredText with raw:: html directives
    PLAINTEXT = auto()  # Plain text file (may contain data URIs)
    EPUB = auto()  # ePub ebook with XHTML containing SVG


@dataclass
class FormatDetectionResult:
    """Result of format detection."""

    format: InputFormat
    confidence: float  # 0.0 to 1.0
    metadata: dict[str, Any]


class FormatHandler(ABC):
    """Abstract base class for input format handlers.

    Subclasses implement handling for specific input formats
    (file, string, tree, embedded, etc.).
    """

    def __init__(self) -> None:
        """Initialize handler with optional config."""
        self._config: Config | None = None

    @property
    def config(self) -> Config | None:
        """Get the configuration object."""
        return self._config

    @config.setter
    def config(self, value: Config | None) -> None:
        """Set the configuration object."""
        self._config = value

    @property
    @abstractmethod
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        ...

    @abstractmethod
    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source (file path, string, tree, etc.)

        Returns:
            True if this handler can process the source
        """
        ...

    @abstractmethod
    def parse(self, source: Any) -> ElementTree:
        """Parse source into an ElementTree.

        Args:
            source: Input source

        Returns:
            Parsed ElementTree

        Raises:
            SVGParseError: If parsing fails
        """
        ...

    @abstractmethod
    def serialize(self, tree: ElementTree, target: Any) -> Any:
        """Serialize ElementTree back to original format.

        Args:
            tree: ElementTree to serialize
            target: Target for serialization (path, buffer, etc.)

        Returns:
            Serialized output in original format
        """
        ...


def detect_format(source: Any) -> FormatDetectionResult:
    """Detect the format of an input source.

    Args:
        source: Input source to analyze

    Returns:
        FormatDetectionResult with detected format and confidence
    """
    metadata: dict[str, Any] = {}

    # Check if it's a Path or path-like string
    if isinstance(source, Path):
        return _detect_file_format(source)

    if isinstance(source, str):
        # Could be a file path or SVG content
        if _looks_like_path(source):
            path = Path(source)
            if path.exists():
                return _detect_file_format(path)

        # Check for SVG content
        return _detect_string_format(source)

    # Check for ElementTree types
    if hasattr(source, "getroot"):
        # It's an ElementTree
        return FormatDetectionResult(
            format=InputFormat.ELEMENT_TREE, confidence=1.0, metadata=metadata
        )

    if hasattr(source, "tag"):
        # It's an Element
        # Check if lxml
        type_name = type(source).__module__
        if "lxml" in type_name:
            return FormatDetectionResult(
                format=InputFormat.LXML_TREE, confidence=1.0, metadata=metadata
            )
        return FormatDetectionResult(
            format=InputFormat.ELEMENT_TREE, confidence=1.0, metadata=metadata
        )

    # Check for BeautifulSoup
    type_name = type(source).__name__
    if type_name in ("Tag", "BeautifulSoup"):
        return FormatDetectionResult(
            format=InputFormat.BEAUTIFULSOUP, confidence=1.0, metadata=metadata
        )

    # Unknown format
    return FormatDetectionResult(
        format=InputFormat.SVG_STRING,
        confidence=0.0,
        metadata={"error": "Unknown format"},
    )


def _looks_like_path(s: str) -> bool:
    """Check if string looks like a file path."""
    # Quick heuristics
    if s.startswith("<"):
        return False
    if "/" in s or "\\" in s:
        return True
    return s.endswith(".svg") or s.endswith(".svgz")


def _detect_file_format(path: Path) -> FormatDetectionResult:
    """Detect format of a file."""
    metadata: dict[str, Any] = {"path": str(path)}

    suffix = path.suffix.lower()

    if suffix == ".svgz" or suffix == ".svg.gz":
        return FormatDetectionResult(
            format=InputFormat.ZSVG, confidence=1.0, metadata=metadata
        )

    if suffix == ".svg":
        # Check for Inkscape format
        try:
            content = path.read_text(errors="ignore")[:2000]
            if "inkscape" in content.lower() or "sodipodi" in content.lower():
                metadata["inkscape"] = True
                return FormatDetectionResult(
                    format=InputFormat.INKSCAPE, confidence=0.9, metadata=metadata
                )
        except Exception:
            pass

        return FormatDetectionResult(
            format=InputFormat.FILE_PATH, confidence=1.0, metadata=metadata
        )

    if suffix in (".html", ".htm"):
        return FormatDetectionResult(
            format=InputFormat.HTML_EMBEDDED, confidence=0.8, metadata=metadata
        )

    if suffix == ".css":
        return FormatDetectionResult(
            format=InputFormat.CSS_EMBEDDED, confidence=0.8, metadata=metadata
        )

    if suffix == ".json":
        return FormatDetectionResult(
            format=InputFormat.JSON_ESCAPED, confidence=0.7, metadata=metadata
        )

    if suffix == ".csv":
        return FormatDetectionResult(
            format=InputFormat.CSV_ESCAPED, confidence=0.7, metadata=metadata
        )

    if suffix in (".md", ".markdown"):
        return FormatDetectionResult(
            format=InputFormat.MARKDOWN, confidence=0.7, metadata=metadata
        )

    if suffix == ".py":
        return FormatDetectionResult(
            format=InputFormat.PYTHON_CODE, confidence=0.7, metadata=metadata
        )

    if suffix in (".js", ".ts", ".jsx", ".tsx"):
        return FormatDetectionResult(
            format=InputFormat.JAVASCRIPT_CODE, confidence=0.7, metadata=metadata
        )

    if suffix == ".rst":
        return FormatDetectionResult(
            format=InputFormat.RST, confidence=0.7, metadata=metadata
        )

    if suffix == ".txt":
        return FormatDetectionResult(
            format=InputFormat.PLAINTEXT, confidence=0.5, metadata=metadata
        )

    if suffix == ".epub":
        return FormatDetectionResult(
            format=InputFormat.EPUB, confidence=0.9, metadata=metadata
        )

    # Default to file path
    return FormatDetectionResult(
        format=InputFormat.FILE_PATH, confidence=0.5, metadata=metadata
    )


def _detect_string_format(content: str) -> FormatDetectionResult:
    """Detect format of string content."""
    metadata: dict[str, Any] = {}
    content_stripped = content.strip()
    content_lower = content_stripped.lower()

    # Check for remote URL first
    if content_lower.startswith("http://") or content_lower.startswith("https://"):
        return FormatDetectionResult(
            format=InputFormat.REMOTE_URL, confidence=1.0, metadata=metadata
        )

    # Check for data URI
    if content_lower.startswith("data:image/svg+xml"):
        return FormatDetectionResult(
            format=InputFormat.DATA_URI, confidence=1.0, metadata=metadata
        )

    # Check for gzip magic bytes (base64 encoded or raw)
    if content.startswith("\x1f\x8b"):
        return FormatDetectionResult(
            format=InputFormat.ZSVG, confidence=1.0, metadata=metadata
        )

    # Check for full SVG document
    if content_lower.startswith("<?xml") or content_lower.startswith("<!doctype"):
        if "inkscape" in content_lower or "sodipodi" in content_lower:
            return FormatDetectionResult(
                format=InputFormat.INKSCAPE, confidence=0.9, metadata=metadata
            )
        return FormatDetectionResult(
            format=InputFormat.SVG_STRING, confidence=1.0, metadata=metadata
        )

    # Check for SVG root element
    if "<svg" in content_lower:
        return FormatDetectionResult(
            format=InputFormat.SVG_STRING, confidence=0.9, metadata=metadata
        )

    # Check for SVG snippet (text, path, etc.)
    svg_tags = [
        "<text",
        "<path",
        "<g ",
        "<rect",
        "<circle",
        "<ellipse",
        "<line",
        "<polygon",
    ]
    for tag in svg_tags:
        if tag in content_lower:
            return FormatDetectionResult(
                format=InputFormat.SVG_SNIPPET, confidence=0.8, metadata=metadata
            )

    # Check for HTML with embedded SVG
    if (
        "<html" in content_lower or "<!doctype html" in content_lower
    ) and "<svg" in content_lower:
        return FormatDetectionResult(
            format=InputFormat.HTML_EMBEDDED, confidence=0.9, metadata=metadata
        )

    # Check for CSS with SVG
    if "url(" in content_lower and "data:image/svg+xml" in content_lower:
        return FormatDetectionResult(
            format=InputFormat.CSS_EMBEDDED, confidence=0.9, metadata=metadata
        )

    # Check for JSON
    if (content.strip().startswith("{") or content.strip().startswith("[")) and (
        "<svg" in content or "\\u003csvg" in content_lower
    ):
        return FormatDetectionResult(
            format=InputFormat.JSON_ESCAPED, confidence=0.8, metadata=metadata
        )

    # Default to unknown string
    return FormatDetectionResult(
        format=InputFormat.SVG_STRING, confidence=0.3, metadata=metadata
    )
