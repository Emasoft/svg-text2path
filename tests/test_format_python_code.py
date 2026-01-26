"""Unit tests for PythonCodeHandler.

Tests the Python source code handler that extracts and converts SVG content
embedded in Python string literals (single, double, triple-quoted).

Coverage: 8 tests covering can_handle, parse, get_all_svgs, serialize, supported_formats
"""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import ElementTree

from svg_text2path.formats.base import InputFormat
from svg_text2path.formats.python_code import PythonCodeHandler

# Sample Python code with triple-quoted SVG
PYTHON_WITH_TRIPLE_QUOTED_SVG = '''
"""Module with embedded SVG icon."""

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="10" fill="blue"/>
  <text x="12" y="16" text-anchor="middle" fill="white">A</text>
</svg>"""

def get_icon():
    return ICON_SVG
'''

# Sample Python code with single-quoted SVG (single line)
PYTHON_WITH_SINGLE_QUOTED_SVG = """
INLINE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="red"/></svg>'

def render():
    return INLINE_SVG
"""

# Sample Python code with multiple SVGs
PYTHON_WITH_MULTIPLE_SVGS = '''
"""Icons module."""

ICON_A = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">
  <circle cx="12" cy="12" r="10" fill="green"/>
</svg>"""

ICON_B = """<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">
  <rect x="4" y="4" width="24" height="24" fill="orange"/>
</svg>"""

ICON_C = """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48">
  <polygon points="24,4 44,44 4,44" fill="purple"/>
</svg>"""
'''

# Sample Python code without any SVG
PYTHON_WITHOUT_SVG = '''
"""Regular Python module without SVG."""

def add(a, b):
    return a + b

DATA = {"key": "value", "items": [1, 2, 3]}
'''


class TestPythonCodeHandlerCanHandle:
    """Tests for PythonCodeHandler.can_handle method."""

    def test_can_handle_py_file_with_svg(self, tmp_path: Path) -> None:
        """Verifies can_handle returns True for .py file containing SVG content."""
        py_file = tmp_path / "icons.py"
        py_file.write_text(PYTHON_WITH_TRIPLE_QUOTED_SVG, encoding="utf-8")

        handler = PythonCodeHandler()
        result = handler.can_handle(py_file)

        assert result is True

    def test_can_handle_py_file_without_svg(self, tmp_path: Path) -> None:
        """Verifies can_handle returns False for .py file without SVG content."""
        py_file = tmp_path / "utils.py"
        py_file.write_text(PYTHON_WITHOUT_SVG, encoding="utf-8")

        handler = PythonCodeHandler()
        result = handler.can_handle(py_file)

        assert result is False


class TestPythonCodeHandlerParse:
    """Tests for PythonCodeHandler.parse method."""

    def test_parse_extracts_svg_from_triple_quoted(self, tmp_path: Path) -> None:
        """Verifies parse extracts SVG from triple-quoted string literals."""
        py_file = tmp_path / "icons.py"
        py_file.write_text(PYTHON_WITH_TRIPLE_QUOTED_SVG, encoding="utf-8")

        handler = PythonCodeHandler()
        tree = handler.parse(py_file)

        root = tree.getroot()
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
        assert root.get("width") == "24"
        assert root.get("height") == "24"

    def test_parse_extracts_svg_from_single_quoted(self, tmp_path: Path) -> None:
        """Verifies parse extracts SVG from single-quoted string literals."""
        py_file = tmp_path / "inline.py"
        py_file.write_text(PYTHON_WITH_SINGLE_QUOTED_SVG, encoding="utf-8")

        handler = PythonCodeHandler()
        tree = handler.parse(py_file)

        root = tree.getroot()
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
        assert root.get("width") == "16"
        assert root.get("height") == "16"

    def test_parse_returns_element_tree(self, tmp_path: Path) -> None:
        """Verifies parse returns a valid ElementTree instance."""
        py_file = tmp_path / "icons.py"
        py_file.write_text(PYTHON_WITH_TRIPLE_QUOTED_SVG, encoding="utf-8")

        handler = PythonCodeHandler()
        result = handler.parse(py_file)

        assert isinstance(result, ElementTree)
        assert result.getroot() is not None


class TestPythonCodeHandlerGetAllSvgs:
    """Tests for PythonCodeHandler.get_all_svgs method."""

    def test_get_all_svgs_returns_all(self, tmp_path: Path) -> None:
        """Verifies get_all_svgs returns all SVGs found in the Python file."""
        py_file = tmp_path / "multi_icons.py"
        py_file.write_text(PYTHON_WITH_MULTIPLE_SVGS, encoding="utf-8")

        handler = PythonCodeHandler()
        handler.parse(py_file)  # Must parse first
        all_svgs = handler.get_all_svgs()

        assert len(all_svgs) == 3
        assert all(isinstance(tree, ElementTree) for tree in all_svgs)

        # Verify each SVG has correct dimensions
        widths = [tree.getroot().get("width") for tree in all_svgs]
        assert "24" in widths
        assert "32" in widths
        assert "48" in widths


class TestPythonCodeHandlerSerialize:
    """Tests for PythonCodeHandler.serialize method."""

    def test_serialize_updates_svg_in_source(self, tmp_path: Path) -> None:
        """Verifies serialize updates SVG while preserving Python code structure."""
        py_file = tmp_path / "icons.py"
        py_file.write_text(PYTHON_WITH_TRIPLE_QUOTED_SVG, encoding="utf-8")

        handler = PythonCodeHandler()
        tree = handler.parse(py_file)

        # Modify the SVG (change viewBox)
        root = tree.getroot()
        root.set("viewBox", "0 0 100 100")

        # Serialize to new file
        output_file = tmp_path / "icons_converted.py"
        result_path = handler.serialize(tree, output_file)

        assert result_path == output_file
        assert output_file.exists()

        # Verify Python structure preserved and SVG updated
        content = output_file.read_text(encoding="utf-8")
        assert "def get_icon():" in content  # Python code preserved
        assert 'viewBox="0 0 100 100"' in content  # SVG updated


class TestPythonCodeHandlerSupportedFormats:
    """Tests for PythonCodeHandler.supported_formats property."""

    def test_supported_formats_includes_python_code(self) -> None:
        """Verifies supported_formats includes InputFormat.PYTHON_CODE."""
        handler = PythonCodeHandler()
        formats = handler.supported_formats

        assert InputFormat.PYTHON_CODE in formats
        assert len(formats) >= 1
