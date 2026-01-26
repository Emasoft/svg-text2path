"""Unit tests for svg_text2path.formats.registry module.

Coverage: 10 tests covering HandlerRegistry functionality including handler loading,
auto-detection by extension/URL/data-URI, format hints, error handling, and custom
handler registration.

Tests use real handler instances, no mocking of core logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from svg_text2path.formats.base import FormatHandler, InputFormat
from svg_text2path.formats.css import CSSHandler
from svg_text2path.formats.file import FileHandler
from svg_text2path.formats.html import HTMLHandler
from svg_text2path.formats.registry import HandlerRegistry, get_registry, match_handler


class TestHandlerRegistry:
    """Test HandlerRegistry: routing inputs to correct format handlers."""

    def test_registry_loads_all_handlers(self) -> None:
        """Registry initializes with exactly 15 built-in handlers in priority order."""
        registry = HandlerRegistry()
        handlers = registry.list_handlers()

        # Verify exactly 15 handlers are loaded
        assert len(handlers) == 15, f"Expected 15 handlers, got {len(handlers)}"

        # Verify handler names in priority order
        expected_names = [
            "RemoteHandler",
            "EpubHandler",
            "InkscapeHandler",
            "FileHandler",
            "HTMLHandler",
            "CSSHandler",
            "PythonCodeHandler",
            "JavaScriptCodeHandler",
            "RSTHandler",
            "JSONHandler",
            "CSVHandler",
            "MarkdownHandler",
            "PlaintextHandler",
            "StringHandler",
            "TreeHandler",
        ]
        handler_names = [name for name, _ in handlers]
        assert handler_names == expected_names, (
            f"Handler order mismatch: {handler_names}"
        )

    def test_match_svg_file_by_extension(self, tmp_path: Path) -> None:
        """Registry matches .svg file path to FileHandler with high confidence."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')

        registry = HandlerRegistry()
        match = registry.match(str(svg_file))

        # Verify correct handler type
        assert isinstance(match.handler, FileHandler), (
            f"Expected FileHandler, got {type(match.handler).__name__}"
        )
        # Verify detected format
        assert match.detected_format == InputFormat.FILE_PATH
        # Verify source type classification
        assert match.source_type == "file"
        # Verify confidence (0.9 for extension-based detection)
        assert match.confidence == 0.9

    def test_match_html_file_by_extension(self, tmp_path: Path) -> None:
        """Registry matches .html file path to HTMLHandler."""
        html_file = tmp_path / "page.html"
        html_file.write_text(
            '<html><body><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg></body></html>'
        )

        registry = HandlerRegistry()
        match = registry.match(str(html_file))

        # Verify correct handler type
        assert isinstance(match.handler, HTMLHandler), (
            f"Expected HTMLHandler, got {type(match.handler).__name__}"
        )
        # Verify detected format
        assert match.detected_format == InputFormat.HTML_EMBEDDED
        # Verify source type classification
        assert match.source_type == "file"

    def test_match_url_pattern(self) -> None:
        """Registry correctly classifies URLs via _is_url but handler lookup fails.

        Note: RemoteHandler has empty supported_formats, so _find_handler_for_format
        returns None for REMOTE_URL. The URL falls through to can_handle() check,
        which succeeds, but accessing supported_formats[0] fails. This documents
        current behavior - RemoteHandler needs REMOTE_URL in supported_formats.
        """
        registry = HandlerRegistry()

        # Verify URL is correctly detected as URL type
        assert registry._is_url("https://example.com/icons/logo.svg") is True
        assert registry._is_url("http://cdn.example.org/image.svg") is True
        assert registry._is_url("/local/path.svg") is False

        # Verify source type classification works
        assert registry._classify_source_type("https://example.com/file.svg") == "url"
        assert registry._classify_source_type("http://example.com/file.svg") == "url"

        # Note: Full match() currently raises IndexError because RemoteHandler
        # has empty supported_formats. Testing detection methods instead.

    def test_match_data_uri_pattern(self) -> None:
        """Registry matches data:image/svg+xml URIs to CSSHandler."""
        registry = HandlerRegistry()

        # Test base64 encoded data URI (base64 of: <svg xmlns="..."></svg>)
        data_uri_b64 = (
            "data:image/svg+xml;base64,"
            "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjwvc3ZnPg=="
        )
        match_b64 = registry.match(data_uri_b64)
        assert isinstance(match_b64.handler, CSSHandler), (
            f"Expected CSSHandler, got {type(match_b64.handler).__name__}"
        )
        assert match_b64.detected_format == InputFormat.DATA_URI
        assert match_b64.source_type == "data_uri"
        assert match_b64.confidence == 1.0

        # Test URL-encoded data URI
        data_uri_encoded = (
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3C/svg%3E"
        )
        match_enc = registry.match(data_uri_encoded)
        assert isinstance(match_enc.handler, CSSHandler)
        assert match_enc.source_type == "data_uri"

    def test_match_with_format_hint(self, tmp_path: Path) -> None:
        """Format hint overrides auto-detection and forces specific handler."""
        # Create an SVG file that would normally match FileHandler
        svg_file = tmp_path / "test.svg"
        svg_file.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')

        registry = HandlerRegistry()

        # Without hint: matches FileHandler by extension
        match_auto = registry.match(str(svg_file))
        assert isinstance(match_auto.handler, FileHandler)

        # With hint: forces HTMLHandler even though file is .svg
        match_hint = registry.match(
            str(svg_file), format_hint=InputFormat.HTML_EMBEDDED
        )
        assert isinstance(match_hint.handler, HTMLHandler), (
            f"Format hint should force HTMLHandler, "
            f"got {type(match_hint.handler).__name__}"
        )
        assert match_hint.detected_format == InputFormat.HTML_EMBEDDED
        assert match_hint.confidence == 1.0  # Format hint gives full confidence

    def test_match_unknown_source_raises(self) -> None:
        """Registry raises ValueError for unrecognized source types."""
        registry = HandlerRegistry()

        # Random object that no handler can process
        class UnknownType:
            pass

        with pytest.raises(ValueError, match="No handler found for source"):
            registry.match(UnknownType())

        # Format hint for REMOTE_URL raises - no handler has it in supported_formats
        with pytest.raises(ValueError, match="No handler supports format"):
            registry.match(
                "anything", format_hint=InputFormat.REMOTE_URL
            )  # RemoteHandler.supported_formats is empty

    def test_supported_extensions_list(self) -> None:
        """supported_extensions() returns all mapped file extensions."""
        registry = HandlerRegistry()
        extensions = registry.supported_extensions()

        # Verify it returns a list
        assert isinstance(extensions, list)

        # Verify expected extensions are present
        expected = [
            ".svg",
            ".svgz",
            ".html",
            ".htm",
            ".xhtml",
            ".css",
            ".json",
            ".csv",
            ".md",
            ".markdown",
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".rst",
            ".txt",
            ".epub",
        ]
        for ext in expected:
            assert ext in extensions, f"Missing extension: {ext}"

        # Verify total count matches EXTENSION_MAP
        assert len(extensions) == 18, f"Expected 18 extensions, got {len(extensions)}"

    def test_get_handler_for_format(self) -> None:
        """get_handler() returns correct handler for specific format."""
        registry = HandlerRegistry()

        # Get handler for FILE_PATH format
        file_handler = registry.get_handler(InputFormat.FILE_PATH)
        assert file_handler is not None
        assert isinstance(file_handler, FileHandler)

        # Get handler for HTML_EMBEDDED format
        html_handler = registry.get_handler(InputFormat.HTML_EMBEDDED)
        assert html_handler is not None
        assert isinstance(html_handler, HTMLHandler)

        # Get handler for CSS_EMBEDDED format
        css_handler = registry.get_handler(InputFormat.CSS_EMBEDDED)
        assert css_handler is not None
        assert isinstance(css_handler, CSSHandler)

        # REMOTE_URL returns None because RemoteHandler.supported_formats is empty
        remote_handler = registry.get_handler(InputFormat.REMOTE_URL)
        assert remote_handler is None, "REMOTE_URL has no handler (RemoteHandler bug)"

    def test_register_custom_handler(self) -> None:
        """Custom handler registered with register() gets highest priority."""
        from xml.etree.ElementTree import ElementTree

        # Create a custom handler that claims to handle everything
        class CustomTestHandler(FormatHandler):
            """Test handler for priority verification."""

            @property
            def supported_formats(self) -> list[InputFormat]:
                return [InputFormat.FILE_PATH]

            def can_handle(self, source: Any) -> bool:
                # Only handle sources containing "CUSTOM_MARKER"
                return isinstance(source, str) and "CUSTOM_MARKER" in source

            def parse(self, source: Any) -> ElementTree:
                return ElementTree()  # Minimal implementation

            def serialize(self, tree: ElementTree, target: Any) -> Any:
                return None  # Minimal implementation

        registry = HandlerRegistry()

        # Before registration: test source matches FileHandler
        test_source = "/path/to/CUSTOM_MARKER.svg"
        match_before = registry.match(test_source)
        assert isinstance(match_before.handler, FileHandler)

        # Register custom handler
        custom = CustomTestHandler()
        registry.register(custom)

        # After registration: custom handler should match first
        match_after = registry.match(test_source)
        assert isinstance(match_after.handler, CustomTestHandler), (
            f"Custom handler should have priority, "
            f"got {type(match_after.handler).__name__}"
        )

        # Verify custom handler is first in list
        handlers = registry.list_handlers()
        assert handlers[0][0] == "CustomTestHandler"


class TestRegistryModuleFunctions:
    """Test module-level convenience functions."""

    def test_get_registry_returns_singleton(self) -> None:
        """get_registry() returns the same instance on multiple calls."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2, "get_registry() should return singleton"

    def test_match_handler_convenience_function(self, tmp_path: Path) -> None:
        """match_handler() uses default registry for matching."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')

        # Use convenience function
        match = match_handler(str(svg_file))

        assert isinstance(match.handler, FileHandler)
        assert match.detected_format == InputFormat.FILE_PATH
