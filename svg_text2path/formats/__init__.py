"""Input format handlers for svg-text2path.

This subpackage provides handlers for various SVG input formats:
- File paths (.svg, .svgz)
- Unicode strings (SVG content)
- xml.etree/lxml/BeautifulSoup trees
- Embedded SVG in HTML
- Embedded SVG in CSS (data URIs)
- Escaped SVG in JSON
- Escaped SVG in CSV
- SVG in Markdown files
- Inkscape format (sodipodi namespaces)
- Remote resources (HTTP/HTTPS URLs)
"""

from svg_text2path.formats.base import (
    FormatDetectionResult,
    FormatHandler,
    InputFormat,
    detect_format,
)
from svg_text2path.formats.css import CSSHandler
from svg_text2path.formats.file import FileHandler
from svg_text2path.formats.html import HTMLHandler
from svg_text2path.formats.inkscape import InkscapeHandler
from svg_text2path.formats.json_csv import CSVHandler, JSONHandler
from svg_text2path.formats.markdown import MarkdownHandler
from svg_text2path.formats.remote import RemoteHandler
from svg_text2path.formats.string import StringHandler
from svg_text2path.formats.tree import TreeHandler

__all__ = [
    # Base classes and utilities
    "FormatHandler",
    "detect_format",
    "InputFormat",
    "FormatDetectionResult",
    # Format handlers
    "FileHandler",
    "StringHandler",
    "TreeHandler",
    "HTMLHandler",
    "CSSHandler",
    "JSONHandler",
    "CSVHandler",
    "MarkdownHandler",
    "InkscapeHandler",
    "RemoteHandler",
]
