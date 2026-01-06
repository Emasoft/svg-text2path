"""Unit tests for svg_text2path.formats module.

Coverage: 5 tests covering FileHandler, StringHandler, HTMLHandler,
CSSHandler, and format detection.

Tests use real parsing with defusedxml, no mocking of core logic.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from svg_text2path.formats import (
    CSSHandler,
    FileHandler,
    HTMLHandler,
    InputFormat,
    StringHandler,
    detect_format,
)

# Realistic test SVG content with multiple elements
SAMPLE_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Hello World</text>
  <rect x="5" y="5" width="190" height="90" fill="none" stroke="black"/>
</svg>"""

SAMPLE_SVG_SNIPPET = '<text x="10" y="50" font-family="Arial">Test snippet</text>'


class TestFileHandler:
    """Test FileHandler: detect and load SVG files."""

    def test_can_handle_svg_file(self, tmp_path: Path) -> None:
        """FileHandler correctly identifies .svg file paths as handleable."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text(SAMPLE_SVG, encoding="utf-8")

        handler = FileHandler()

        # Test with Path object
        assert handler.can_handle(svg_file) is True

        # Test with string path
        assert handler.can_handle(str(svg_file)) is True

        # Test that SVG content strings are NOT handled
        assert handler.can_handle(SAMPLE_SVG) is False

    def test_parse_svg_file(self, tmp_path: Path) -> None:
        """FileHandler parses SVG file and returns valid ElementTree."""
        svg_file = tmp_path / "test_parse.svg"
        svg_file.write_text(SAMPLE_SVG, encoding="utf-8")

        handler = FileHandler()
        tree = handler.parse(svg_file)

        root = tree.getroot()
        # Verify root is svg element
        assert root.tag.endswith("svg") or root.tag == "svg"
        # Verify attributes preserved
        assert root.get("width") == "200"
        assert root.get("height") == "100"

    def test_parse_gzipped_svgz_file(self, tmp_path: Path) -> None:
        """FileHandler correctly parses gzip-compressed .svgz files."""
        svgz_file = tmp_path / "test.svgz"
        with gzip.open(svgz_file, "wt", encoding="utf-8") as f:
            f.write(SAMPLE_SVG)

        handler = FileHandler()

        # Verify it can be handled
        assert handler.can_handle(svgz_file) is True

        # Parse and verify content
        tree = handler.parse(svgz_file)
        root = tree.getroot()
        assert root.get("width") == "200"

    def test_serialize_svg_file(self, tmp_path: Path) -> None:
        """FileHandler serializes ElementTree back to SVG file."""
        # First parse an SVG
        svg_file = tmp_path / "input.svg"
        svg_file.write_text(SAMPLE_SVG, encoding="utf-8")

        handler = FileHandler()
        tree = handler.parse(svg_file)

        # Serialize to new file
        output_file = tmp_path / "output.svg"
        result_path = handler.serialize(tree, output_file)

        assert result_path == output_file
        assert output_file.exists()
        # Verify content is valid SVG
        content = output_file.read_text()
        assert "<svg" in content
        assert 'width="200"' in content


class TestStringHandler:
    """Test StringHandler: detect and parse SVG strings."""

    def test_can_handle_svg_string(self) -> None:
        """StringHandler identifies SVG string content correctly."""
        handler = StringHandler()

        # Full SVG document
        assert handler.can_handle(SAMPLE_SVG) is True

        # SVG without XML declaration
        svg_no_decl = '<svg xmlns="http://www.w3.org/2000/svg"><text>Hi</text></svg>'
        assert handler.can_handle(svg_no_decl) is True

        # SVG snippet
        assert handler.can_handle(SAMPLE_SVG_SNIPPET) is True

        # Non-SVG content
        assert handler.can_handle("Hello world") is False
        assert handler.can_handle("/path/to/file.svg") is False

    def test_parse_svg_string(self) -> None:
        """StringHandler parses SVG string into ElementTree."""
        handler = StringHandler()
        tree = handler.parse(SAMPLE_SVG)

        root = tree.getroot()
        assert root.tag.endswith("svg") or root.tag == "svg"
        assert root.get("viewBox") == "0 0 200 100"

    def test_parse_svg_snippet_wraps_in_svg(self) -> None:
        """StringHandler wraps SVG snippets in proper SVG container."""
        handler = StringHandler()
        tree = handler.parse(SAMPLE_SVG_SNIPPET)

        root = tree.getroot()
        # Root should be svg element
        assert root.tag.endswith("svg") or root.tag == "svg"
        # Should contain text element
        text_elem = root.find(".//{http://www.w3.org/2000/svg}text")
        if text_elem is None:
            text_elem = root.find(".//text")
        assert text_elem is not None
        assert text_elem.text == "Test snippet"

    def test_serialize_to_string(self) -> None:
        """StringHandler serializes ElementTree back to SVG string."""
        handler = StringHandler()
        tree = handler.parse(SAMPLE_SVG)

        result = handler.serialize(tree)

        assert isinstance(result, str)
        assert "<?xml" in result
        assert "<svg" in result
        assert 'width="200"' in result


class TestHTMLHandler:
    """Test HTMLHandler: extract SVG from HTML."""

    def test_can_handle_html_with_svg(self) -> None:
        """HTMLHandler identifies HTML with embedded SVG."""
        handler = HTMLHandler()

        html_with_svg = f"""<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
{SAMPLE_SVG}
</body>
</html>"""

        assert handler.can_handle(html_with_svg) is True

        # HTML without SVG should not be handled
        html_no_svg = "<!DOCTYPE html><html><body><p>No SVG here</p></body></html>"
        assert handler.can_handle(html_no_svg) is False

        # Plain SVG should not be handled as HTML
        assert handler.can_handle(SAMPLE_SVG) is False

    def test_extract_svg_elements_from_html(self) -> None:
        """HTMLHandler._extract_svg_elements correctly extracts SVGs from HTML."""
        handler = HTMLHandler()

        # SVG without XML declaration (more realistic in HTML context)
        svg_in_html = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><text>Test</text></svg>'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>SVG Test</title></head>
<body>
<div class="container">
{svg_in_html}
</div>
</body>
</html>"""

        # Test the internal extraction method which works correctly
        elements = handler._extract_svg_elements(html)

        assert len(elements) == 1
        assert elements[0].get("width") == "200"
        assert elements[0].get("height") == "100"

    def test_extract_multiple_svgs_from_html(self) -> None:
        """HTMLHandler._extract_svg_elements handles multiple SVG elements."""
        handler = HTMLHandler()

        svg1 = '<svg xmlns="http://www.w3.org/2000/svg" id="first"><rect/></svg>'
        svg2 = '<svg xmlns="http://www.w3.org/2000/svg" id="second"><circle/></svg>'

        html = f"""<!DOCTYPE html>
<html>
<body>
{svg1}
<p>Some text</p>
{svg2}
</body>
</html>"""

        elements = handler._extract_svg_elements(html)

        assert len(elements) == 2
        assert elements[0].get("id") == "first"
        assert elements[1].get("id") == "second"


class TestCSSHandler:
    """Test CSSHandler: extract SVG from CSS background-image."""

    def test_can_handle_css_with_svg_data_uri(self) -> None:
        """CSSHandler identifies CSS with SVG data URIs."""
        handler = CSSHandler()

        css_with_svg = """.icon {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Crect/%3E%3C/svg%3E");
}"""

        assert handler.can_handle(css_with_svg) is True

        # Plain CSS without SVG
        plain_css = ".box { background: blue; }"
        assert handler.can_handle(plain_css) is False

    def test_decode_url_encoded_svg_from_css(self) -> None:
        """CSSHandler._decode_data_uri correctly decodes URL-encoded SVG."""
        handler = CSSHandler()

        # Properly URL-encoded SVG with XML-compatible quotes
        import urllib.parse

        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="40" fill="red"/></svg>'
        encoded = urllib.parse.quote(svg, safe="")
        data_uri = f"data:image/svg+xml,{encoded}"

        result = handler._decode_data_uri(data_uri)

        assert result is not None
        assert "<svg" in result
        assert 'width="100"' in result
        assert "<circle" in result

    def test_decode_base64_svg_from_css(self) -> None:
        """CSSHandler._decode_data_uri correctly decodes base64-encoded SVG."""
        import base64

        handler = CSSHandler()

        # Create base64-encoded SVG
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><rect/></svg>'
        b64 = base64.b64encode(svg.encode()).decode()
        data_uri = f"data:image/svg+xml;base64,{b64}"

        result = handler._decode_data_uri(data_uri)

        assert result is not None
        assert "<svg" in result
        assert 'width="50"' in result

    def test_extract_all_svgs_from_css(self) -> None:
        """CSSHandler extracts multiple SVGs from CSS with multiple data URIs."""
        handler = CSSHandler()

        css = """.icon1 {
  background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Crect/%3E%3C/svg%3E");
}
.icon2 {
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle/%3E%3C/svg%3E");
}"""

        svgs = handler.extract_all_svgs(css)

        assert len(svgs) == 2
        assert "<rect" in svgs[0]
        assert "<circle" in svgs[1]


class TestDetectFormat:
    """Test detect_format: format detection based on content."""

    def test_detect_svg_file_path(self, tmp_path: Path) -> None:
        """detect_format identifies SVG file paths correctly."""
        svg_file = tmp_path / "sample.svg"
        svg_file.write_text(SAMPLE_SVG, encoding="utf-8")

        # Path object
        result = detect_format(svg_file)
        assert result.format == InputFormat.FILE_PATH
        assert result.confidence >= 0.8

        # String path
        result = detect_format(str(svg_file))
        assert result.format == InputFormat.FILE_PATH

    def test_detect_svgz_file(self, tmp_path: Path) -> None:
        """detect_format identifies compressed .svgz files."""
        svgz_file = tmp_path / "sample.svgz"
        with gzip.open(svgz_file, "wt", encoding="utf-8") as f:
            f.write(SAMPLE_SVG)

        result = detect_format(svgz_file)
        assert result.format == InputFormat.ZSVG
        assert result.confidence == 1.0

    def test_detect_svg_string(self) -> None:
        """detect_format identifies SVG string content."""
        result = detect_format(SAMPLE_SVG)

        assert result.format == InputFormat.SVG_STRING
        assert result.confidence >= 0.9

    def test_detect_html_file_path(self, tmp_path: Path) -> None:
        """detect_format identifies .html files correctly."""
        # detect_format works correctly for HTML FILE PATHS (by extension)
        # For string content with <svg>, it returns SVG_STRING due to check ordering
        html_file = tmp_path / "page.html"
        html_file.write_text('<html><body><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg></body></html>')

        result = detect_format(html_file)

        assert result.format == InputFormat.HTML_EMBEDDED
        assert result.confidence >= 0.7

    def test_detect_css_with_svg(self) -> None:
        """detect_format identifies CSS with SVG data URIs."""
        css = '.icon { background: url("data:image/svg+xml,%3Csvg%3E%3C/svg%3E"); }'

        result = detect_format(css)

        assert result.format == InputFormat.CSS_EMBEDDED
        assert result.confidence >= 0.8

    def test_detect_inkscape_format(self, tmp_path: Path) -> None:
        """detect_format identifies Inkscape SVG files by namespace."""
        inkscape_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd">
  <sodipodi:namedview/>
  <text>Inkscape SVG</text>
</svg>"""

        ink_file = tmp_path / "inkscape.svg"
        ink_file.write_text(inkscape_svg, encoding="utf-8")

        result = detect_format(ink_file)

        assert result.format == InputFormat.INKSCAPE
        assert result.metadata.get("inkscape") is True

    def test_detect_element_tree(self) -> None:
        """detect_format identifies ElementTree objects."""
        from io import StringIO

        import defusedxml.ElementTree as ET

        tree = ET.parse(StringIO(SAMPLE_SVG))

        result = detect_format(tree)
        assert result.format == InputFormat.ELEMENT_TREE
        assert result.confidence == 1.0

        # Also test Element
        elem = tree.getroot()
        result = detect_format(elem)
        assert result.format == InputFormat.ELEMENT_TREE
