"""Unit tests for JavaScriptCodeHandler.

Tests SVG extraction from JavaScript/TypeScript code files including
template literals, JSX expressions, and multiple SVG handling.

Coverage: 8 test cases covering core functionality
- can_handle detection for .js, .ts, .tsx files
- parse extraction from template literals and JSX
- ElementTree return type validation
- Multiple SVG extraction via all_svgs property
- supported_formats property verification
"""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element

from svg_text2path.formats.base import InputFormat
from svg_text2path.formats.javascript_code import JavaScriptCodeHandler

# Sample SVG content for testing - using multiline for readability
SIMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
    '<rect x="10" y="10" width="80" height="80"/></svg>'
)
SIMPLE_SVG_2 = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50">'
    '<circle cx="25" cy="25" r="20"/></svg>'
)


class TestJavaScriptCodeHandlerCanHandle:
    """Tests for can_handle method detecting JS/TS files."""

    def test_can_handle_js_file_with_svg(self, tmp_path: Path) -> None:
        """Verify can_handle returns True for .js file containing SVG."""
        # Create a .js file with embedded SVG in template literal
        js_file = tmp_path / "component.js"
        js_content = f"""
const svgIcon = `{SIMPLE_SVG}`;
export default svgIcon;
"""
        js_file.write_text(js_content, encoding="utf-8")

        handler = JavaScriptCodeHandler()
        result = handler.can_handle(js_file)

        assert result is True, "Handler should recognize .js files"

    def test_can_handle_ts_file_with_svg(self, tmp_path: Path) -> None:
        """Verify can_handle returns True for .ts file containing SVG."""
        # Create a .ts file with embedded SVG
        ts_file = tmp_path / "icon.ts"
        ts_content = f"""
export const iconSvg: string = `{SIMPLE_SVG}`;
"""
        ts_file.write_text(ts_content, encoding="utf-8")

        handler = JavaScriptCodeHandler()
        result = handler.can_handle(ts_file)

        assert result is True, "Handler should recognize .ts files"

    def test_can_handle_tsx_file_with_svg(self, tmp_path: Path) -> None:
        """Verify can_handle returns True for .tsx file containing SVG."""
        # Create a .tsx file with JSX SVG component
        tsx_file = tmp_path / "IconComponent.tsx"
        tsx_content = f"""
import React from 'react';

export const Icon = () => (
  {SIMPLE_SVG}
);
"""
        tsx_file.write_text(tsx_content, encoding="utf-8")

        handler = JavaScriptCodeHandler()
        result = handler.can_handle(tsx_file)

        assert result is True, "Handler should recognize .tsx files"


class TestJavaScriptCodeHandlerParse:
    """Tests for parse method extracting SVG content."""

    def test_parse_extracts_svg_from_template_literal(self, tmp_path: Path) -> None:
        """Verify parse extracts SVG from JavaScript template literal (backticks)."""
        js_file = tmp_path / "template.js"
        js_content = f"""
const mySvg = `{SIMPLE_SVG}`;
console.log(mySvg);
"""
        js_file.write_text(js_content, encoding="utf-8")

        handler = JavaScriptCodeHandler()
        result = handler.parse(js_file)

        # Verify we got an Element (fromstring returns Element, not ElementTree)
        assert result is not None, "Parse should return a result"
        # The result from ET.fromstring is actually an Element
        assert isinstance(result, Element), (
            "Parse should return Element from fromstring"
        )
        assert result.tag.endswith("svg") or result.tag == "svg", (
            "Root element should be svg"
        )

    def test_parse_extracts_svg_from_jsx(self, tmp_path: Path) -> None:
        """Verify parse extracts SVG from JSX return statement."""
        tsx_file = tmp_path / "Component.tsx"
        tsx_content = f"""
import React from 'react';

function MyIcon() {{
  return (
    {SIMPLE_SVG}
  );
}}

export default MyIcon;
"""
        tsx_file.write_text(tsx_content, encoding="utf-8")

        handler = JavaScriptCodeHandler()
        result = handler.parse(tsx_file)

        assert result is not None, "Parse should extract SVG from JSX"
        # Check we extracted the SVG element
        assert isinstance(result, Element), "Parse should return Element"
        assert result.tag.endswith("svg") or result.tag == "svg", (
            "Should extract svg element"
        )

    def test_parse_returns_element_tree(self, tmp_path: Path) -> None:
        """Verify parse returns a valid Element with expected structure."""
        js_file = tmp_path / "valid.js"
        js_content = f"""
export const svg = `{SIMPLE_SVG}`;
"""
        js_file.write_text(js_content, encoding="utf-8")

        handler = JavaScriptCodeHandler()
        result = handler.parse(js_file)

        # Verify structure of parsed result
        assert result is not None, "Should return parsed element"
        assert result.get("width") == "100", "Should preserve width attribute"
        assert result.get("height") == "100", "Should preserve height attribute"
        # Check child element exists
        children = list(result)
        assert len(children) == 1, "Should have one child element (rect)"
        assert children[0].tag.endswith("rect") or children[0].tag == "rect", (
            "Child should be rect"
        )


class TestJavaScriptCodeHandlerMultipleSVGs:
    """Tests for handling multiple SVGs in a single file."""

    def test_get_all_svgs_returns_all(self, tmp_path: Path) -> None:
        """Verify all_svgs property returns all SVGs found in file."""
        js_file = tmp_path / "multiple.js"
        js_content = f"""
const icon1 = `{SIMPLE_SVG}`;
const icon2 = `{SIMPLE_SVG_2}`;
export {{ icon1, icon2 }};
"""
        js_file.write_text(js_content, encoding="utf-8")

        handler = JavaScriptCodeHandler()
        handler.parse(js_file)  # Must parse first to populate _all_svgs
        all_svgs = handler.all_svgs

        assert len(all_svgs) == 2, "Should find both SVGs in the file"
        # Verify both SVGs are present (order may vary)
        svg_contents = "".join(all_svgs)
        assert "rect" in svg_contents, "First SVG with rect should be found"
        assert "circle" in svg_contents, "Second SVG with circle should be found"


class TestJavaScriptCodeHandlerSupportedFormats:
    """Tests for supported_formats property."""

    def test_supported_formats_includes_javascript(self) -> None:
        """Verify JAVASCRIPT_CODE is in supported_formats list."""
        handler = JavaScriptCodeHandler()
        formats = handler.supported_formats

        assert InputFormat.JAVASCRIPT_CODE in formats, (
            "JAVASCRIPT_CODE should be in supported_formats"
        )
        assert len(formats) == 1, "Should only support JAVASCRIPT_CODE format"
