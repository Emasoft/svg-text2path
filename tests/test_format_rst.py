"""Unit tests for RSTHandler in svg_text2path.formats.rst.

Tests SVG extraction from reStructuredText files containing embedded SVG
via raw:: html, raw:: svg, and code-block directives.

Coverage: 8 tests covering can_handle, parse, serialize, and supported_formats.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import ElementTree

from svg_text2path.formats.base import InputFormat
from svg_text2path.formats.rst import RSTHandler

# Sample RST content with SVG in raw:: html directive
RST_WITH_RAW_HTML_SVG = """\
Title
=====

Some introductory text.

.. raw:: html

   <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
     <circle cx="50" cy="50" r="40" fill="red"/>
   </svg>

More text after the SVG.
"""

# Sample RST content with SVG in raw:: svg directive
RST_WITH_RAW_SVG = """\
Graphics Example
================

Below is an SVG graphic:

.. raw:: svg

   <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
     <rect x="10" y="10" width="80" height="80" fill="blue"/>
   </svg>

End of document.
"""

# Sample RST content with SVG in code-block directive
RST_WITH_CODE_BLOCK_SVG = """\
Code Sample
===========

Here is the SVG code:

.. code-block:: xml

   <svg xmlns="http://www.w3.org/2000/svg" width="50" height="50">
     <path d="M0 0 L50 50" stroke="green" stroke-width="2"/>
   </svg>

That's the code.
"""

# RST content without any SVG
RST_WITHOUT_SVG = """\
Plain Document
==============

This document has no SVG content.

.. raw:: html

   <div class="container">
     <p>Just HTML, no SVG here.</p>
   </div>

The end.
"""


class TestRSTHandlerCanHandle:
    """Tests for RSTHandler.can_handle() method."""

    def test_can_handle_rst_file_with_svg(self, tmp_path: Path) -> None:
        """Verify can_handle returns True for .rst file containing SVG."""
        rst_file = tmp_path / "test_doc.rst"
        rst_file.write_text(RST_WITH_RAW_HTML_SVG, encoding="utf-8")

        handler = RSTHandler()
        result = handler.can_handle(rst_file)

        assert result is True, "Handler should recognize .rst file with SVG"

    def test_can_handle_rst_without_svg(self, tmp_path: Path) -> None:
        """Verify can_handle returns False for .rst file without SVG."""
        rst_file = tmp_path / "no_svg.rst"
        rst_file.write_text(RST_WITHOUT_SVG, encoding="utf-8")

        handler = RSTHandler()
        result = handler.can_handle(rst_file)

        assert result is False, "Handler should reject .rst file without SVG"


class TestRSTHandlerParse:
    """Tests for RSTHandler.parse() method."""

    def test_parse_extracts_svg_from_raw_html(self, tmp_path: Path) -> None:
        """Verify parse extracts SVG from .. raw:: html directive."""
        rst_file = tmp_path / "raw_html.rst"
        rst_file.write_text(RST_WITH_RAW_HTML_SVG, encoding="utf-8")

        handler = RSTHandler()
        tree = handler.parse(rst_file)

        # Check that SVG was extracted
        root = tree.getroot()
        assert root is not None, "Parsed tree should have root element"
        assert root.tag.endswith("svg") or root.tag == "svg", (
            "Root should be svg element"
        )

        # Verify the circle element exists
        circle = root.find(".//{http://www.w3.org/2000/svg}circle")
        if circle is None:
            circle = root.find(".//circle")
        assert circle is not None, "SVG should contain circle element"
        assert circle.get("fill") == "red", "Circle fill should be red"

    def test_parse_extracts_svg_from_raw_svg(self, tmp_path: Path) -> None:
        """Verify parse extracts SVG from .. raw:: svg directive."""
        rst_file = tmp_path / "raw_svg.rst"
        rst_file.write_text(RST_WITH_RAW_SVG, encoding="utf-8")

        handler = RSTHandler()
        tree = handler.parse(rst_file)

        root = tree.getroot()
        assert root is not None, "Parsed tree should have root element"

        # Verify the rect element exists
        rect = root.find(".//{http://www.w3.org/2000/svg}rect")
        if rect is None:
            rect = root.find(".//rect")
        assert rect is not None, "SVG should contain rect element"
        assert rect.get("fill") == "blue", "Rect fill should be blue"

    def test_parse_extracts_svg_from_code_block(self, tmp_path: Path) -> None:
        """Verify parse extracts SVG from .. code-block:: xml directive."""
        rst_file = tmp_path / "code_block.rst"
        rst_file.write_text(RST_WITH_CODE_BLOCK_SVG, encoding="utf-8")

        handler = RSTHandler()
        tree = handler.parse(rst_file)

        root = tree.getroot()
        assert root is not None, "Parsed tree should have root element"

        # Verify the path element exists
        path_elem = root.find(".//{http://www.w3.org/2000/svg}path")
        if path_elem is None:
            path_elem = root.find(".//path")
        assert path_elem is not None, "SVG should contain path element"
        assert path_elem.get("stroke") == "green", "Path stroke should be green"

    def test_parse_returns_element_tree(self, tmp_path: Path) -> None:
        """Verify parse returns a valid ElementTree object."""
        rst_file = tmp_path / "element_tree.rst"
        rst_file.write_text(RST_WITH_RAW_HTML_SVG, encoding="utf-8")

        handler = RSTHandler()
        result = handler.parse(rst_file)

        assert isinstance(result, ElementTree), "parse() should return ElementTree"
        assert result.getroot() is not None, "ElementTree should have root"


class TestRSTHandlerSerialize:
    """Tests for RSTHandler.serialize() method."""

    def test_serialize_preserves_rst_structure(self, tmp_path: Path) -> None:
        """Verify serialize round-trip preserves RST document structure."""
        # Create input RST file
        input_file = tmp_path / "input.rst"
        input_file.write_text(RST_WITH_RAW_HTML_SVG, encoding="utf-8")

        # Parse the RST
        handler = RSTHandler()
        tree = handler.parse(input_file)

        # Serialize to output file
        output_file = tmp_path / "output.rst"
        result_path = handler.serialize(tree, output_file)

        # Verify output file was created
        assert result_path == output_file, "Serialize should return target path"
        assert output_file.exists(), "Output file should exist"

        # Read output and verify RST structure preserved
        output_content = output_file.read_text(encoding="utf-8")

        # Check RST markers are preserved
        assert "Title" in output_content, "Title should be preserved"
        assert "=====" in output_content, "Title underline should be preserved"
        assert ".. raw:: html" in output_content, "Raw directive should be preserved"
        assert "More text after the SVG." in output_content, (
            "Trailing text should be preserved"
        )

        # SVG should still be parseable
        handler2 = RSTHandler()
        tree2 = handler2.parse(output_file)
        root2 = tree2.getroot()
        assert root2 is not None, "Serialized RST should still contain valid SVG"


class TestRSTHandlerSupportedFormats:
    """Tests for RSTHandler.supported_formats property."""

    def test_supported_formats_includes_rst(self) -> None:
        """Verify supported_formats includes InputFormat.RST."""
        handler = RSTHandler()
        formats = handler.supported_formats

        assert InputFormat.RST in formats, "RST should be in supported_formats"
        assert len(formats) == 1, "RSTHandler should only support RST format"
