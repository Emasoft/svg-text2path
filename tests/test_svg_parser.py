"""Unit tests for svg_text2path.svg.parser module."""

from pathlib import Path
from xml.etree.ElementTree import Element

import defusedxml
import pytest

from svg_text2path.svg.parser import (
    NAMESPACES,
    SVG_NS,
    find_text_elements,
    get_tag_name,
    parse_svg,
    parse_svg_string,
)


class TestParseSvgString:
    """Tests for parse_svg_string() function."""

    def test_parse_valid_svg_returns_element(self, simple_svg_content: str) -> None:
        """Verify parse_svg_string returns an Element for valid SVG content."""
        result = parse_svg_string(simple_svg_content)
        assert isinstance(result, Element)
        assert get_tag_name(result) == "svg"

    def test_parse_preserves_text_element(self, simple_svg_content: str) -> None:
        """Verify parsed SVG has text element with correct attributes."""
        root = parse_svg_string(simple_svg_content)
        text_elements = find_text_elements(root)
        assert len(text_elements) == 1
        assert text_elements[0].get("x") == "10"
        assert text_elements[0].get("y") == "50"
        assert text_elements[0].text == "Test"


class TestParseSvgFile:
    """Tests for parse_svg() file parsing function."""

    def test_parse_existing_file_returns_tree(self, temp_svg: Path) -> None:
        """Verify parse_svg returns ElementTree for existing SVG file."""
        tree = parse_svg(temp_svg)
        root = tree.getroot()
        assert isinstance(root, Element)
        assert get_tag_name(root) == "svg"

    def test_parse_file_preserves_content(self, temp_svg: Path) -> None:
        """Verify parsed file contains expected text element content."""
        tree = parse_svg(temp_svg)
        root = tree.getroot()
        text_elements = find_text_elements(root)
        assert len(text_elements) == 1
        assert text_elements[0].text == "Hello World"

    def test_parse_nonexistent_file_raises_error(self, tmp_path: Path) -> None:
        """Verify parse_svg raises FileNotFoundError for missing file."""
        missing_file = tmp_path / "nonexistent.svg"
        with pytest.raises(FileNotFoundError):
            parse_svg(missing_file)


class TestXxeSecurity:
    """Tests for XXE (XML External Entity) attack prevention via defusedxml."""

    def test_xxe_external_entity_blocked(self, tmp_path: Path) -> None:
        """Verify external entity declarations are blocked by defusedxml."""
        # Create a file that would be read if XXE were allowed
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("SECRET_DATA")

        # XXE attack payload attempting to read external file
        xxe_svg = f"""<?xml version="1.0"?>
<!DOCTYPE svg [
  <!ENTITY xxe SYSTEM "file://{secret_file}">
]>
<svg xmlns="http://www.w3.org/2000/svg">
  <text>&xxe;</text>
</svg>"""

        # defusedxml should raise an exception for DTD with external entities
        with pytest.raises(defusedxml.DefusedXmlException):
            parse_svg_string(xxe_svg)

    def test_billion_laughs_attack_blocked(self) -> None:
        """Verify billion laughs (entity expansion) attack is blocked."""
        # Simplified billion laughs attack
        billion_laughs_svg = """<?xml version="1.0"?>
<!DOCTYPE svg [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<svg xmlns="http://www.w3.org/2000/svg">
  <text>&lol2;</text>
</svg>"""

        with pytest.raises(defusedxml.DefusedXmlException):
            parse_svg_string(billion_laughs_svg)


class TestMalformedXml:
    """Tests for error handling with malformed XML content."""

    def test_unclosed_tag_raises_parse_error(self, malformed_svg_content: str) -> None:
        """Verify malformed SVG with unclosed tags raises ParseError."""
        from xml.etree.ElementTree import ParseError

        with pytest.raises(ParseError):
            parse_svg_string(malformed_svg_content)

    def test_mismatched_tags_raises_error(self) -> None:
        """Verify mismatched opening/closing tags raise ParseError."""
        from xml.etree.ElementTree import ParseError

        invalid_xml = "<svg><text>Hello</rect></svg>"
        with pytest.raises(ParseError):
            parse_svg_string(invalid_xml)

    def test_empty_string_raises_error(self) -> None:
        """Verify empty string raises ParseError."""
        from xml.etree.ElementTree import ParseError

        with pytest.raises(ParseError):
            parse_svg_string("")


class TestNamespaceHandling:
    """Tests for SVG namespace handling."""

    def test_svg_namespace_constant_defined(self) -> None:
        """Verify SVG_NS constant has correct W3C namespace URI."""
        assert SVG_NS == "http://www.w3.org/2000/svg"

    def test_namespaces_dict_contains_svg(self) -> None:
        """Verify NAMESPACES dict includes svg, xlink, inkscape, sodipodi."""
        assert "svg" in NAMESPACES
        assert "xlink" in NAMESPACES
        assert "inkscape" in NAMESPACES
        assert "sodipodi" in NAMESPACES

    def test_find_text_handles_namespaced_elements(self) -> None:
        """Verify find_text_elements works with namespace-prefixed SVG."""
        namespaced_svg = """<svg xmlns="http://www.w3.org/2000/svg">
          <text x="0" y="10">Namespaced</text>
        </svg>"""
        root = parse_svg_string(namespaced_svg)
        text_elements = find_text_elements(root)
        assert len(text_elements) == 1

    def test_get_tag_name_strips_namespace(self) -> None:
        """Verify get_tag_name removes namespace prefix from tag."""
        namespaced_svg = """<svg xmlns="http://www.w3.org/2000/svg">
          <text>Test</text>
        </svg>"""
        root = parse_svg_string(namespaced_svg)
        text_elements = find_text_elements(root)
        assert get_tag_name(text_elements[0]) == "text"
