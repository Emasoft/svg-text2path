"""SVG parsing utilities with XXE-safe XML handling.

Uses defusedxml to prevent XML External Entity (XXE) attacks.
This module provides safe alternatives to xml.etree.ElementTree.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

if TYPE_CHECKING:
    pass  # Types imported above for runtime use with cast()


# SVG namespace
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"

NAMESPACES = {
    "svg": SVG_NS,
    "xlink": XLINK_NS,
    "inkscape": INKSCAPE_NS,
    "sodipodi": SODIPODI_NS,
}


def parse_svg(source: str | Path) -> ElementTree:
    """Parse an SVG file safely using defusedxml.

    Args:
        source: File path to SVG file

    Returns:
        Parsed ElementTree

    Raises:
        defusedxml.DefusedXmlException: If malicious content detected
        FileNotFoundError: If file doesn't exist
    """
    path = Path(source) if isinstance(source, str) else source
    return ET.parse(str(path))  # type: ignore[no-any-return]


def parse_svg_string(svg_content: str) -> Element:
    """Parse an SVG string safely using defusedxml.

    Args:
        svg_content: SVG content as string

    Returns:
        Root Element

    Raises:
        defusedxml.DefusedXmlException: If malicious content detected
    """
    return ET.fromstring(svg_content)  # type: ignore[no-any-return]


def find_text_elements(root: Element) -> list[Element]:
    """Find all text elements in SVG tree.

    Args:
        root: Root element to search

    Returns:
        List of text elements (text, tspan, textPath)
    """
    text_elements: list[Element] = []

    # Find with and without namespace
    for tag in ["text", f"{{{SVG_NS}}}text"]:
        text_elements.extend(root.iter(tag))

    return text_elements


def find_tspans(text_elem: Element) -> list[Element]:
    """Find all tspan children of a text element.

    Args:
        text_elem: Parent text element

    Returns:
        List of tspan elements
    """
    tspans: list[Element] = []
    for tag in ["tspan", f"{{{SVG_NS}}}tspan"]:
        tspans.extend(text_elem.iter(tag))
    return tspans


def find_textpaths(text_elem: Element) -> list[Element]:
    """Find all textPath children of a text element.

    Args:
        text_elem: Parent text element

    Returns:
        List of textPath elements
    """
    textpaths: list[Element] = []
    for tag in ["textPath", f"{{{SVG_NS}}}textPath"]:
        textpaths.extend(text_elem.iter(tag))
    return textpaths


def get_tag_name(elem: Element) -> str:
    """Get element tag name without namespace.

    Args:
        elem: Element to get tag from

    Returns:
        Tag name without namespace prefix
    """
    tag = elem.tag
    if "}" in tag:
        return tag.split("}")[1]
    return tag


def write_svg(tree: ElementTree, output_path: str | Path) -> None:
    """Write ElementTree to SVG file.

    Args:
        tree: ElementTree to write
        output_path: Output file path
    """
    # Register namespaces to avoid ns0: prefixes.
    # Empty prefix for SVG (default namespace) outputs <svg> not <svg:svg>
    _register_namespace("", SVG_NS)
    for prefix, uri in NAMESPACES.items():
        if prefix != "svg":  # Skip svg prefix - use default namespace instead
            _register_namespace(prefix, uri)

    path = Path(output_path) if isinstance(output_path, str) else output_path
    tree.write(str(path), encoding="unicode", xml_declaration=True)
