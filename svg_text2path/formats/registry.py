"""Handler registry for routing inputs to correct format handlers.

Provides auto-detection and dispatching of input sources to appropriate
format handlers based on file extension, content inspection, and URL patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from svg_text2path.formats.base import FormatHandler, InputFormat


@dataclass
class HandlerMatch:
    """Result of handler matching.

    Represents the outcome of matching an input source to a format handler,
    including metadata about the detection process.

    Attributes:
        handler: FormatHandler instance capable of processing the source.
        detected_format: InputFormat enum value identifying the format.
        source_type: Classification of source origin. One of:
            - "file": Local file path
            - "url": Remote HTTP/HTTPS resource
            - "data_uri": Embedded data URI (data:image/svg+xml...)
            - "string": SVG content string
            - "tree": Pre-parsed ElementTree object
        confidence: Detection confidence score from 0.0 (uncertain) to 1.0 (certain).
            Higher values indicate more reliable format detection.
    """

    handler: FormatHandler
    detected_format: InputFormat
    source_type: str  # "file", "url", "data_uri", "string", "tree"
    confidence: float  # 0.0 to 1.0


class HandlerRegistry:
    """Routes inputs to correct handler based on auto-detection.

    The registry maintains a list of format handlers and provides
    methods to find the appropriate handler for any given input source.

    Example:
        >>> registry = HandlerRegistry()
        >>> match = registry.match("input.svg")
        >>> tree = match.handler.parse("input.svg")
    """

    # URL pattern for detecting remote resources
    URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)

    # Data URI pattern for detecting embedded SVG
    DATA_URI_PATTERN = re.compile(r"^data:image/svg\+xml[;,]", re.IGNORECASE)

    # File extensions mapped to InputFormat
    EXTENSION_MAP: dict[str, InputFormat] = {
        ".svg": InputFormat.FILE_PATH,
        ".svgz": InputFormat.ZSVG,
        ".html": InputFormat.HTML_EMBEDDED,
        ".htm": InputFormat.HTML_EMBEDDED,
        ".xhtml": InputFormat.HTML_EMBEDDED,
        ".css": InputFormat.CSS_EMBEDDED,
        ".json": InputFormat.JSON_ESCAPED,
        ".csv": InputFormat.CSV_ESCAPED,
        ".md": InputFormat.MARKDOWN,
        ".markdown": InputFormat.MARKDOWN,
        ".py": InputFormat.PYTHON_CODE,
        ".js": InputFormat.JAVASCRIPT_CODE,
        ".ts": InputFormat.JAVASCRIPT_CODE,
        ".jsx": InputFormat.JAVASCRIPT_CODE,
        ".tsx": InputFormat.JAVASCRIPT_CODE,
        ".rst": InputFormat.RST,
        ".txt": InputFormat.PLAINTEXT,
        ".epub": InputFormat.EPUB,
    }

    def __init__(self) -> None:
        """Initialize registry with default handlers.

        Creates a new handler registry and populates it with all built-in
        format handlers in priority order (more specific handlers first).

        Example:
            >>> registry = HandlerRegistry()
            >>> len(registry._handlers) > 0
            True
        """
        self._handlers: list[FormatHandler] = []
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register all built-in format handlers.

        Populates the handler list with instances of all built-in format handlers
        in priority order. More specific handlers (URLs, ePub) are registered before
        generic handlers (file, string) to ensure correct auto-detection.

        Handler registration order:
            1. RemoteHandler - HTTP/HTTPS URLs
            2. EpubHandler - .epub archive files
            3. InkscapeHandler - Inkscape-specific SVG files
            4. FileHandler - .svg, .svgz files
            5. HTMLHandler - HTML with embedded SVG
            6. CSSHandler - CSS with data URIs
            7. PythonCodeHandler - Python source with SVG strings
            8. JavaScriptCodeHandler - JS/TS source with SVG strings
            9. RSTHandler - reStructuredText with SVG
            10. JSONHandler - JSON with escaped SVG
            11. CSVHandler - CSV with escaped SVG
            12. MarkdownHandler - Markdown with SVG blocks
            13. PlaintextHandler - Plain text / data URIs
            14. StringHandler - SVG content strings (fallback)
            15. TreeHandler - Pre-parsed ElementTree objects (last resort)

        Note:
            Handlers are imported locally to avoid circular import issues.
        """
        # Import handlers here to avoid circular imports
        from svg_text2path.formats.css import CSSHandler
        from svg_text2path.formats.epub import EpubHandler
        from svg_text2path.formats.file import FileHandler
        from svg_text2path.formats.html import HTMLHandler
        from svg_text2path.formats.inkscape import InkscapeHandler
        from svg_text2path.formats.javascript_code import JavaScriptCodeHandler
        from svg_text2path.formats.json_csv import CSVHandler, JSONHandler
        from svg_text2path.formats.markdown import MarkdownHandler
        from svg_text2path.formats.plaintext import PlaintextHandler
        from svg_text2path.formats.python_code import PythonCodeHandler
        from svg_text2path.formats.remote import RemoteHandler
        from svg_text2path.formats.rst import RSTHandler
        from svg_text2path.formats.string import StringHandler
        from svg_text2path.formats.tree import TreeHandler

        # Order matters - more specific handlers first
        self._handlers = [
            RemoteHandler(),  # URLs first (before FileHandler checks paths)
            EpubHandler(),  # ePub archives (before FileHandler)
            InkscapeHandler(),  # Before FileHandler (more specific)
            FileHandler(),  # .svg, .svgz files
            HTMLHandler(),  # HTML with embedded SVG
            CSSHandler(),  # CSS with data URIs
            PythonCodeHandler(),  # Python code with SVG strings
            JavaScriptCodeHandler(),  # JS/TS code with SVG strings
            RSTHandler(),  # reStructuredText with SVG
            JSONHandler(),  # JSON with escaped SVG
            CSVHandler(),  # CSV with escaped SVG
            MarkdownHandler(),  # Markdown with SVG blocks
            PlaintextHandler(),  # Plain text / data URIs
            StringHandler(),  # SVG strings (fallback for string content)
            TreeHandler(),  # ElementTree objects (last resort)
        ]

    def register(self, handler: FormatHandler) -> None:
        """Register a custom handler.

        Adds a custom format handler to the registry at highest priority,
        allowing it to override built-in handlers during auto-detection.

        Args:
            handler: FormatHandler instance to register. Will be inserted
                at the beginning of the handler list for highest priority
                during matching.

        Example:
            >>> from svg_text2path.formats.base import FormatHandler, InputFormat
            >>> class CustomHandler(FormatHandler):
            ...     supported_formats = [InputFormat.FILE_PATH]
            ...     def can_handle(self, source): return True
            ...     def parse(self, source): pass
            >>> registry = HandlerRegistry()
            >>> registry.register(CustomHandler())
        """
        # Insert at beginning for highest priority
        self._handlers.insert(0, handler)

    def match(
        self, source: Any, format_hint: InputFormat | None = None
    ) -> HandlerMatch:
        """Find the appropriate handler for the given source.

        Detection priority:
        1. If format_hint provided, find handler supporting that format
        2. Check if URL (http://, https://)
        3. Check if data URI (data:image/svg+xml)
        4. Check file extension
        5. Try each handler's can_handle() method

        Args:
            source: Input source (file path, URL, string, tree, etc.)
            format_hint: Optional format hint to force specific handler

        Returns:
            HandlerMatch with handler, detected format, and confidence

        Raises:
            ValueError: If no handler found for source
        """
        # If format hint provided, find handler directly
        if format_hint is not None:
            for handler in self._handlers:
                if format_hint in handler.supported_formats:
                    return HandlerMatch(
                        handler=handler,
                        detected_format=format_hint,
                        source_type=self._classify_source_type(source),
                        confidence=1.0,
                    )
            raise ValueError(f"No handler supports format: {format_hint}")

        # Check for URL
        if self._is_url(source):
            url_handler = self._find_handler_for_format(InputFormat.REMOTE_URL)
            if url_handler:
                return HandlerMatch(
                    handler=url_handler,
                    detected_format=InputFormat.REMOTE_URL,
                    source_type="url",
                    confidence=1.0,
                )

        # Check for data URI
        if self._is_data_uri(source):
            # Data URIs are handled by CSSHandler (it knows base64/url-encoded)
            data_uri_handler = self._find_handler_for_format(InputFormat.CSS_EMBEDDED)
            if data_uri_handler:
                return HandlerMatch(
                    handler=data_uri_handler,
                    detected_format=InputFormat.DATA_URI,
                    source_type="data_uri",
                    confidence=1.0,
                )

        # Check file extension
        if isinstance(source, (str, Path)):
            detected = self._detect_by_extension(source)
            if detected:
                ext_handler = self._find_handler_for_format(detected)
                if ext_handler:
                    return HandlerMatch(
                        handler=ext_handler,
                        detected_format=detected,
                        source_type="file",
                        confidence=0.9,
                    )

        # Try each handler's can_handle()
        for handler in self._handlers:
            if handler.can_handle(source):
                # Use first supported format as detected format
                detected_format = handler.supported_formats[0]
                return HandlerMatch(
                    handler=handler,
                    detected_format=detected_format,
                    source_type=self._classify_source_type(source),
                    confidence=0.7,
                )

        # Build error message with truncated source preview if it's a string
        preview = ""
        if isinstance(source, str) and len(source) > 50:
            preview = f" ({source[:50]}...)"
        raise ValueError(
            f"No handler found for source: {type(source).__name__}{preview}"
        )

    def _is_url(self, source: Any) -> bool:
        """Check if source is an HTTP/HTTPS URL.

        Tests whether the source string starts with 'http://' or 'https://'
        (case-insensitive).

        Args:
            source: Input source to check. Can be any type, but only strings
                are considered URLs.

        Returns:
            bool: True if source is a string starting with http:// or https://,
                False otherwise.

        Example:
            >>> registry = HandlerRegistry()
            >>> registry._is_url("https://example.com/file.svg")
            True
            >>> registry._is_url("/path/to/file.svg")
            False
        """
        if not isinstance(source, str):
            return False
        return bool(self.URL_PATTERN.match(source))

    def _is_data_uri(self, source: Any) -> bool:
        """Check if source is an SVG data URI.

        Tests whether the source string starts with 'data:image/svg+xml'
        followed by encoding specification (;base64, etc.) or immediate data.

        Args:
            source: Input source to check. Can be any type, but only strings
                are considered data URIs.

        Returns:
            bool: True if source is a string matching the SVG data URI pattern,
                False otherwise.

        Example:
            >>> registry = HandlerRegistry()
            >>> registry._is_data_uri("data:image/svg+xml;base64,PHN2Zy8+")
            True
            >>> registry._is_data_uri("data:image/svg+xml,<svg/>")
            True
            >>> registry._is_data_uri("<svg/>")
            False
        """
        if not isinstance(source, str):
            return False
        return bool(self.DATA_URI_PATTERN.match(source))

    def _detect_by_extension(self, source: str | Path) -> InputFormat | None:
        """Detect format by file extension.

        Maps file extensions to InputFormat enum values using EXTENSION_MAP.
        Skips sources that appear to be SVG content strings or URLs.

        Args:
            source: File path as string or Path object. If string starts with
                '<' (SVG content) or matches URL pattern, returns None.

        Returns:
            InputFormat | None: Detected format based on file extension, or None
                if extension is unrecognized or source is not a file path.

        Example:
            >>> registry = HandlerRegistry()
            >>> registry._detect_by_extension("file.svg")
            <InputFormat.FILE_PATH: 'file_path'>
            >>> registry._detect_by_extension("file.html")
            <InputFormat.HTML_EMBEDDED: 'html_embedded'>
            >>> registry._detect_by_extension("<svg/>")
            None
        """
        path = Path(source) if isinstance(source, str) else source

        # Skip if source looks like SVG content, not a path
        if isinstance(source, str) and source.strip().startswith("<"):
            return None

        # Skip if source is a URL (handled separately)
        if isinstance(source, str) and self._is_url(source):
            return None

        suffix = path.suffix.lower()
        return self.EXTENSION_MAP.get(suffix)

    def _find_handler_for_format(self, fmt: InputFormat) -> FormatHandler | None:
        """Find first handler that supports the given format.

        Searches the handler list in priority order for a handler that declares
        support for the specified format.

        Args:
            fmt: InputFormat enum value to find handler for.

        Returns:
            FormatHandler | None: First handler supporting the format, or None
                if no matching handler found.

        Example:
            >>> registry = HandlerRegistry()
            >>> handler = registry._find_handler_for_format(InputFormat.FILE_PATH)
            >>> handler.__class__.__name__
            'FileHandler'
        """
        for handler in self._handlers:
            if fmt in handler.supported_formats:
                return handler
        return None

    def _classify_source_type(self, source: Any) -> str:
        """Classify the source type for reporting.

        Determines the category of the input source for inclusion in HandlerMatch
        metadata. Used for debugging and logging purposes.

        Args:
            source: Input source to classify. Can be str, Path, ElementTree, or
                other types.

        Returns:
            str: Classification label, one of:
                - "url": HTTP/HTTPS URL
                - "data_uri": SVG data URI
                - "string": SVG content string (starts with '<')
                - "file": File path (Path object or non-SVG string)
                - "tree": Pre-parsed ElementTree or unknown type

        Example:
            >>> registry = HandlerRegistry()
            >>> registry._classify_source_type("https://example.com/file.svg")
            'url'
            >>> registry._classify_source_type("<svg/>")
            'string'
            >>> registry._classify_source_type(Path("file.svg"))
            'file'
        """
        if isinstance(source, str):
            if self._is_url(source):
                return "url"
            if self._is_data_uri(source):
                return "data_uri"
            if source.strip().startswith("<"):
                return "string"
            return "file"
        if isinstance(source, Path):
            return "file"
        # ElementTree or similar
        return "tree"

    def get_handler(self, fmt: InputFormat) -> FormatHandler | None:
        """Get handler for specific format.

        Args:
            fmt: Format to get handler for

        Returns:
            Handler or None if not found
        """
        return self._find_handler_for_format(fmt)

    def list_handlers(self) -> list[tuple[str, list[InputFormat]]]:
        """List all registered handlers and their supported formats.

        Returns:
            List of (handler_name, supported_formats) tuples
        """
        return [
            (handler.__class__.__name__, handler.supported_formats)
            for handler in self._handlers
        ]

    def supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions.

        Returns:
            List of extensions (e.g., [".svg", ".html", ".css"])
        """
        return list(self.EXTENSION_MAP.keys())


# Module-level singleton for convenience
_default_registry: HandlerRegistry | None = None


def get_registry() -> HandlerRegistry:
    """Get the default handler registry (singleton).

    Returns:
        Default HandlerRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = HandlerRegistry()
    return _default_registry


def match_handler(source: Any, format_hint: InputFormat | None = None) -> HandlerMatch:
    """Find appropriate handler for source using default registry.

    Convenience function that uses the singleton registry.

    Args:
        source: Input source
        format_hint: Optional format hint

    Returns:
        HandlerMatch result
    """
    return get_registry().match(source, format_hint)
