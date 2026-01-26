"""Unit tests for svg_text2path.formats.plaintext module.

Coverage: 8 tests covering PlaintextHandler.
- can_handle detection for .txt files and data URIs
- parse decoding for base64, URL-encoded, and raw SVG
- serialize encoding back to base64
- supported_formats property

Tests use real parsing with defusedxml, no mocking of core logic.
"""

from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import quote

from svg_text2path.formats import InputFormat
from svg_text2path.formats.plaintext import PlaintextHandler

# Realistic test SVG content
SAMPLE_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Hello World</text>
  <rect x="5" y="5" width="190" height="90" fill="none" stroke="black"/>
</svg>"""

# Minimal SVG for simpler assertions
MINIMAL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><rect/></svg>'
)


class TestPlaintextHandler:
    """Test PlaintextHandler: detect and parse plaintext/data URI SVG content."""

    def test_can_handle_txt_with_base64_svg(self, tmp_path: Path) -> None:
        """PlaintextHandler returns True for .txt file containing base64-encoded SVG."""
        handler = PlaintextHandler()

        # Create .txt file with base64 SVG data URI
        b64_content = base64.b64encode(MINIMAL_SVG.encode("utf-8")).decode("ascii")
        data_uri = f"data:image/svg+xml;base64,{b64_content}"

        txt_file = tmp_path / "icon.txt"
        txt_file.write_text(data_uri, encoding="utf-8")

        # Test with Path object
        assert handler.can_handle(txt_file) is True

        # Test with string path
        assert handler.can_handle(str(txt_file)) is True

        # Non-.txt files should not be handled by extension check
        svg_file = tmp_path / "icon.svg"
        svg_file.write_text(MINIMAL_SVG, encoding="utf-8")
        assert handler.can_handle(svg_file) is False

    def test_can_handle_data_uri_string(self) -> None:
        """PlaintextHandler returns True for data:image/svg+xml string."""
        handler = PlaintextHandler()

        # Base64 data URI string
        b64_content = base64.b64encode(MINIMAL_SVG.encode("utf-8")).decode("ascii")
        data_uri_b64 = f"data:image/svg+xml;base64,{b64_content}"
        assert handler.can_handle(data_uri_b64) is True

        # URL-encoded data URI string
        url_encoded = quote(MINIMAL_SVG, safe="")
        data_uri_url = f"data:image/svg+xml,{url_encoded}"
        assert handler.can_handle(data_uri_url) is True

        # Case insensitive matching
        data_uri_upper = f"DATA:IMAGE/SVG+XML;BASE64,{b64_content}"
        assert handler.can_handle(data_uri_upper) is True

        # Non-SVG data URIs should not be handled
        assert handler.can_handle("data:image/png;base64,iVBORw0KGgo=") is False

        # Plain SVG strings should not be handled
        assert handler.can_handle(MINIMAL_SVG) is False

    def test_parse_decodes_base64_svg(self, tmp_path: Path) -> None:
        """PlaintextHandler.parse extracts SVG from base64 data URI."""
        handler = PlaintextHandler()

        # Create base64 data URI
        b64_content = base64.b64encode(SAMPLE_SVG.encode("utf-8")).decode("ascii")
        data_uri = f"data:image/svg+xml;base64,{b64_content}"

        # Parse the data URI string directly
        tree = handler.parse(data_uri)

        root = tree.getroot()
        assert root is not None
        assert root.tag.endswith("svg") or root.tag == "svg"
        assert root.get("width") == "200"
        assert root.get("height") == "100"
        assert root.get("viewBox") == "0 0 200 100"

        # Verify original format tracking
        assert handler._original_format == "base64"

    def test_parse_decodes_url_encoded_svg(self) -> None:
        """PlaintextHandler.parse extracts SVG from URL-encoded data URI."""
        handler = PlaintextHandler()

        # Create URL-encoded data URI
        url_encoded = quote(SAMPLE_SVG, safe="")
        data_uri = f"data:image/svg+xml,{url_encoded}"

        tree = handler.parse(data_uri)

        root = tree.getroot()
        assert root is not None
        assert root.tag.endswith("svg") or root.tag == "svg"
        assert root.get("width") == "200"
        assert root.get("viewBox") == "0 0 200 100"

        # Verify original format tracking
        assert handler._original_format == "urlencoded"

    def test_parse_handles_raw_svg_string(self, tmp_path: Path) -> None:
        """PlaintextHandler.parse correctly parses plain SVG content from .txt file."""
        handler = PlaintextHandler()

        # Create .txt file with raw SVG content (no data URI encoding)
        txt_file = tmp_path / "raw_svg.txt"
        txt_file.write_text(SAMPLE_SVG, encoding="utf-8")

        tree = handler.parse(txt_file)

        root = tree.getroot()
        assert root is not None
        assert root.tag.endswith("svg") or root.tag == "svg"
        assert root.get("width") == "200"
        assert root.get("height") == "100"

        # For raw SVG, original format should be None (not a data URI)
        assert handler._original_format is None

    def test_parse_returns_element_tree(self) -> None:
        """PlaintextHandler.parse returns valid ElementTree object."""
        from xml.etree.ElementTree import ElementTree

        handler = PlaintextHandler()

        # Create base64 data URI
        b64_content = base64.b64encode(MINIMAL_SVG.encode("utf-8")).decode("ascii")
        data_uri = f"data:image/svg+xml;base64,{b64_content}"

        result = handler.parse(data_uri)

        # Verify return type is ElementTree
        assert isinstance(result, ElementTree)

        # Verify tree has proper structure
        root = result.getroot()
        assert root is not None
        # Should be able to find child elements
        rect_elem = root.find(".//{http://www.w3.org/2000/svg}rect")
        if rect_elem is None:
            rect_elem = root.find(".//rect")
        assert rect_elem is not None

    def test_serialize_encodes_to_base64(self, tmp_path: Path) -> None:
        """PlaintextHandler.serialize outputs base64 encoded when input was base64."""
        handler = PlaintextHandler()

        # Parse base64 data URI to set _original_format
        b64_content = base64.b64encode(MINIMAL_SVG.encode("utf-8")).decode("ascii")
        data_uri = f"data:image/svg+xml;base64,{b64_content}"

        tree = handler.parse(data_uri)
        assert handler._original_format == "base64"

        # Serialize to file
        output_file = tmp_path / "output.txt"
        result_path = handler.serialize(tree, output_file)

        assert result_path == output_file
        assert output_file.exists()

        # Read and verify output is base64 data URI
        content = output_file.read_text()
        assert content.startswith("data:image/svg+xml;base64,")

        # Verify content can be decoded back to valid SVG
        b64_part = content.split(",", 1)[1]
        decoded_svg = base64.b64decode(b64_part).decode("utf-8")
        assert "<svg" in decoded_svg
        assert 'width="50"' in decoded_svg

    def test_supported_formats_includes_plaintext(self) -> None:
        """PlaintextHandler.supported_formats contains PLAINTEXT and DATA_URI."""
        handler = PlaintextHandler()

        formats = handler.supported_formats

        assert isinstance(formats, list)
        assert len(formats) == 2
        assert InputFormat.PLAINTEXT in formats
        assert InputFormat.DATA_URI in formats
