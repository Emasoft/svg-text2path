#!/usr/bin/env python3
"""Example: Convert text to paths in an already-loaded lxml SVG document.

This example demonstrates how to use svg-text2path programmatically
when you have an SVG already loaded as an lxml.etree document.

Requirements:
    pip install svg-text2path lxml

Usage:
    python convert_lxml_document.py                    # Basic demo
    python convert_lxml_document.py input.svg          # Convert file
    python convert_lxml_document.py --test all         # Run all tests
    python convert_lxml_document.py --test stress      # Stress test
    python convert_lxml_document.py --benchmark        # Performance test
"""

# ============================================================================
# IMPORTS - Loading the tools we need
# ============================================================================
# This section imports all the Python libraries and modules needed for this
# example. Each import brings specific functionality into our program.

from __future__ import annotations

# This special import enables modern type hints (like using 'list[str]' instead
# of 'List[str]' from typing module). It makes type hints cleaner and is
# recommended for all new Python code.
import argparse

# The 'argparse' module helps us handle command-line arguments. It automatically
# generates help messages and validates user input when running the script with
# flags like --test or --benchmark.
import sys

# The 'sys' module provides access to system-specific parameters and functions.
# We use sys.exit() to return error codes when the program finishes (0 = success,
# non-zero = error), which is important for scripts that might be called by
# other programs or build systems.
import time

# The 'time' module provides time-related functions. We use it to measure how
# long operations take (performance benchmarking) and to calculate conversion
# speeds (texts per second).
from io import BytesIO

# BytesIO creates an in-memory file-like object for bytes data. Think of it as
# a "fake file" that exists only in RAM instead of on disk.
# WHY USE IT? When converting SVG documents, we need to serialize (convert to
# string) and deserialize (parse back from string). Instead of writing to a
# real file on disk (slow, requires permissions, creates clutter), we use
# BytesIO to temporarily hold the XML data in memory during conversion.
# It's much faster and cleaner than creating temporary files.
from pathlib import Path

# Path is a modern, object-oriented way to work with file system paths. It's
# easier and safer than using raw strings for file paths because it handles
# differences between Windows (C:\path\file.txt) and Unix (/path/file.txt)
# automatically.
# ============================================================================
# LXML - The XML/SVG Parsing Library
# ============================================================================
# WHY LXML? lxml is the best Python library for working with XML/SVG files.
# It's much better than Python's built-in xml.dom.minidom for several reasons:
#
# 1. SPEED: lxml is built on libxml2 (written in C), making it 5-10x faster
#    than minidom for parsing and manipulating large XML files.
#
# 2. XPATH SUPPORT: lxml supports XPath, a powerful query language for finding
#    elements in XML. XPath is like "SQL for XML" - it lets you find elements
#    with queries like "//text" (all <text> elements anywhere) or
#    ".//{namespace}text" (all <text> elements in a specific namespace).
#    minidom does NOT support XPath at all.
#
# 3. VALIDATION: lxml can validate XML against schemas (DTD, XML Schema, RelaxNG),
#    ensuring your documents follow the correct structure. minidom cannot.
#
# 4. MEMORY EFFICIENCY: lxml uses less memory for large documents and provides
#    incremental parsing for huge files. minidom loads everything into memory.
#
# 5. FEATURES: lxml supports XSLT transformations, advanced namespace handling,
#    and has better error reporting. It's the industry standard for XML in Python.
#
from lxml import etree  # type: ignore[attr-defined]  # lxml stubs issue

# The 'etree' module from lxml is the ElementTree API - it treats XML as a tree
# of elements (parent-child relationships). The comment "type: ignore" tells
# type checkers to skip this line because lxml's type stubs have some issues.
# ============================================================================
# LXML KEY CONCEPTS: ElementTree vs Element
# ============================================================================
# lxml has two main types for representing XML/SVG documents:
#
# 1. etree.ElementTree - represents the ENTIRE XML DOCUMENT
#    - This is the "wrapper" that holds the whole document including XML
#      declaration (<?xml version="1.0"?>), processing instructions, and
#      the root element with all its children.
#    - Created with: etree.parse("file.xml") or etree.ElementTree(root_element)
#    - Has methods like: .getroot(), .write(), .docinfo
#    - Think of it as the "file" containing your XML tree
#
# 2. etree.Element - represents ONE ELEMENT (a single XML tag) in the tree
#    - This is a single node like <svg>, <text>, or <path>
#    - Has attributes (like width="100"), text content, and child elements
#    - Created with: etree.Element("svg") or doc.getroot() or tree.find("//text")
#    - Has methods like: .get(), .set(), .find(), .findall(), .text, .tail
#    - Think of it as a single "node" or "branch" in the tree
#
# RELATIONSHIP: An ElementTree contains Elements. The root Element is the
# top-level tag (like <svg>), and it contains child Elements (like <rect>,
# <text>, <path>), which may contain their own children, forming a tree.
#
# Example:
#   doc = etree.parse("file.svg")        # ElementTree (whole document)
#   root = doc.getroot()                 # Element (<svg> tag)
#   text_elem = root.find(".//text")     # Element (<text> tag)
#   path_elem = etree.Element("path")    # Element (new <path> tag)
# ============================================================================
# SVG-TEXT2PATH IMPORTS - The conversion functionality
# ============================================================================
from svg_text2path import (
    ConversionResult,
    # ConversionResult is a data structure (like a report card) that holds
    # information about what happened during conversion:
    # - success: Did the conversion complete without errors?
    # - text_count: How many <text> elements were in the original SVG?
    # - path_count: How many <path> elements were created?
    # - input_format: Where did the input come from? (file, string, document)
    # This lets us check if conversion worked and generate reports.
    FontCache,
    # FontCache is a performance optimization for font lookups. Finding fonts
    # on your system is SLOW - it requires searching many directories and
    # reading font files to extract metadata (font family, weight, style).
    # WHY REUSE IT? If converting multiple SVG files or many text elements:
    # - WITHOUT cache: Every conversion searches for fonts again (slow)
    # - WITH cache: Fonts are found once, then stored in memory for reuse (fast)
    # Think of it as a "phone book" for fonts that you create once and reuse
    # many times, instead of looking up the same numbers repeatedly.
    Text2PathConverter,
    # Text2PathConverter is the main class that does the actual conversion work.
    # It takes SVG text elements and converts them to path outlines.
    # WHAT HAPPENS DURING CONVERSION? (Conceptual explanation)
    # 1. TEXT → GLYPHS: Text like "Hello" is broken into individual characters
    # 2. GLYPHS → OUTLINES: Each character's shape is loaded from the font file
    #    as vector outlines (not pixels - these are mathematical curves)
    # 3. OUTLINES → BEZIER CURVES: The outlines are mathematical shapes called
    #    Bezier curves (curves defined by control points). SVG paths use cubic
    #    Bezier curves with commands like M (move), L (line), C (curve).
    # 4. BEZIER → SVG PATH: The curves are serialized into the "d" attribute of
    #    <path> elements using SVG path syntax like "M10,20 L30,40 C50,60..."
    #
    # Example: "Hi" → [H_glyph, i_glyph] → [H_outline, i_outline] →
    #          [H_beziers, i_beziers] → <path d="M0,0 L...C...Z M10,0 L..."/>
    #
    # WHY DO THIS? Once text is converted to paths:
    # - It looks EXACTLY the same on any device (no font substitution)
    # - It works even if the font is not installed
    # - It can be scaled, transformed, and styled like any SVG shape
    # - But it can no longer be edited as text or searched
    verify_all_dependencies,
    # This function checks if all required software is installed and available:
    # - Python libraries (fonttools, lxml, etc.)
    # - External programs (fontconfig for font matching)
    # It returns a report telling you what's missing, so you can install it
    # before trying to convert SVG files. Think of it as a "pre-flight checklist"
    # before running the converter.
)

# ============================================================================
# SVG NAMESPACE - Understanding XML namespaces
# ============================================================================
SVG_NS = "http://www.w3.org/2000/svg"
# This is the official SVG namespace URI (Uniform Resource Identifier). It's
# not a real website you visit - it's a unique string that identifies SVG elements.
#
# WHY NAMESPACES? XML can mix elements from different standards in one document.
# For example, SVG might contain MathML (math equations) or custom elements.
# Namespaces prevent naming conflicts by giving each element type a unique prefix.
#
# NAMESPACE SYNTAX IN LXML: {namespace}tagname
# - To find SVG elements, we write: f"{{{SVG_NS}}}text"
# - This expands to: "{http://www.w3.org/2000/svg}text"
# - The curly braces {} are part of the syntax, so we escape them in f-strings
#   with double braces: {{{ and }}}
#
# Example: root.findall(f".//{{{SVG_NS}}}text")
# This finds all <text> elements that belong to the SVG namespace, even if the
# XML also has <text> elements from other namespaces (like custom extensions).
#
# XPATH WITH NAMESPACES: When using XPath queries like ".//text" in lxml:
# - ".//text" means: starting from current element (.), search all descendants
#   (//), and find elements named "text"
# - "./" means current element, "//" means any descendant at any depth
# - f".//{{{SVG_NS}}}text" means: find all SVG <text> elements anywhere below


# ============================================================================
# MAIN CONVERSION FUNCTION - Document-level conversion
# ============================================================================
def convert_lxml_document(
    doc: etree._ElementTree,
    precision: int = 6,
    preserve_styles: bool = False,
    converter: Text2PathConverter | None = None,
) -> tuple[etree._ElementTree, ConversionResult]:
    """Convert all text elements in an lxml SVG document to paths.

    Args:
        doc: An lxml ElementTree containing the SVG document.
        precision: Decimal precision for path coordinates (default: 6).
        preserve_styles: Whether to preserve font metadata on paths.
        converter: Optional pre-configured converter (reuses font cache).

    Returns:
        Tuple of (modified_document, conversion_result).

    Example:
        >>> from lxml import etree
        >>> doc = etree.parse("input.svg")
        >>> converted_doc, result = convert_lxml_document(doc)
        >>> print(f"Converted {result.path_count}/{result.text_count} text elements")
        >>> converted_doc.write("output.svg", encoding="utf-8")
    """
    # ========================================================================
    # STEP 1: Count text elements before conversion
    # ========================================================================
    # We need to know how many <text> elements exist so we can report
    # conversion statistics later (how many were converted successfully).

    root = doc.getroot()
    # LXML METHOD: .getroot()
    # Returns the root Element of the document. For SVG files, this is the
    # <svg> element at the top level. Everything else (shapes, text, etc.)
    # is nested inside this root element.
    # Remember: doc is an ElementTree (the whole document), root is an Element
    # (the top-level <svg> tag).

    text_count = len(root.findall(f".//{{{SVG_NS}}}text"))
    # LXML METHOD: .findall(xpath)
    # Returns a LIST of all Elements matching the XPath query. Here we search
    # for all <text> elements anywhere in the SVG using the XPath pattern:
    # ".//{namespace}text" which means:
    # - "./" = start from the current element (root)
    # - "//" = search all descendants at any depth (children, grandchildren, etc.)
    # - "{namespace}text" = match only <text> elements in the SVG namespace
    # We count them with len() to get the total number of text elements.

    # ========================================================================
    # STEP 2: Create or reuse the converter
    # ========================================================================
    # The converter does the actual text-to-path conversion. Creating a new
    # converter is fine for single conversions, but if you're converting many
    # SVG files, reusing a converter (with its FontCache) is MUCH faster.

    if converter is None:
        converter = Text2PathConverter(
            precision=precision,
            # PRECISION: Controls how many decimal places to use in path coordinates.
            # SVG paths contain numbers like "M 10.123456 20.654321 L ...".
            # Higher precision = more accurate curves but larger file size.
            # - precision=2: "M 10.12 20.65" (small files, slight rounding errors)
            # - precision=4: "M 10.1235 20.6543" (good balance, default)
            # - precision=6: "M 10.123456 20.654321" (very accurate, larger files)
            # - precision=8: "M 10.12345678 20.65432100" (overkill for most uses)
            # Most SVG applications use 4-6 decimal places.
            preserve_styles=preserve_styles,
        )

    # ========================================================================
    # STEP 3: Serialize the lxml document to a string
    # ========================================================================
    # The Text2PathConverter expects an SVG string (text), not an lxml object.
    # So we need to convert (serialize) the lxml ElementTree into a string
    # representation of the XML.

    svg_bytes = etree.tostring(doc, encoding="utf-8", xml_declaration=True)
    # LXML METHOD: etree.tostring(tree_or_element, encoding, xml_declaration)
    # Converts an ElementTree or Element into bytes (byte string).
    # - encoding="utf-8": Use UTF-8 encoding for the output (supports all Unicode)
    # - xml_declaration=True: Include <?xml version="1.0" encoding="utf-8"?> at top
    # NOTE: With xml_declaration=True, lxml REQUIRES encoding="utf-8", NOT "unicode"
    # Returns: bytes (like b'<?xml version="1.0"?><svg>...</svg>')

    svg_string = svg_bytes.decode("utf-8")
    # Convert the bytes to a regular Python string (str type) by decoding UTF-8.
    # Now svg_string is a normal string: '<?xml version="1.0"?><svg>...</svg>'

    # ========================================================================
    # STEP 4: Convert text elements to paths
    # ========================================================================
    converted_string = converter.convert_string(svg_string)
    # This is where the magic happens! The converter:
    # 1. Parses the SVG string to find all <text> elements
    # 2. For each text element, loads the specified font
    # 3. Converts each character to its glyph outline (vector curves)
    # 4. Replaces the <text> element with <path> elements
    # 5. Returns a new SVG string with all text converted to paths

    # ========================================================================
    # STEP 5: Parse the converted string back to lxml
    # ========================================================================
    # Now we have a string with the converted SVG, but we want to return an
    # lxml ElementTree object so the caller can manipulate it further.

    converted_doc = etree.parse(BytesIO(converted_string.encode("utf-8")))
    # LXML METHOD: etree.parse(file_or_filelike_object)
    # Parses XML from a file or file-like object and returns an ElementTree.
    # Here's what's happening:
    # 1. converted_string.encode("utf-8") - Convert string to bytes
    # 2. BytesIO(...) - Wrap bytes in an in-memory file-like object
    #    WHY? etree.parse() expects a file, not a string. BytesIO creates a
    #    fake file that exists only in RAM, avoiding disk I/O (much faster).
    # 3. etree.parse() - Parse the "file" and return an ElementTree
    #
    # ALTERNATIVE: We could use etree.fromstring() instead:
    #   root = etree.fromstring(converted_string.encode("utf-8"))
    #   converted_doc = etree.ElementTree(root)
    # But etree.parse(BytesIO(...)) is more idiomatic and handles XML
    # declarations better.

    # ========================================================================
    # STEP 6: Count elements after conversion to verify success
    # ========================================================================
    # We want to know: Did the conversion work? How many paths were created?
    # Are there any text elements remaining (indicating partial failure)?

    converted_root = converted_doc.getroot()
    # Get the root <svg> element from the converted document

    path_count = len(converted_root.findall(f".//{{{SVG_NS}}}path"))
    # Count all <path> elements in the converted SVG using the same XPath
    # pattern we used for <text> elements earlier. This tells us how many
    # path elements were created during conversion.

    remaining_text = len(converted_root.findall(f".//{{{SVG_NS}}}text"))
    # Check if any <text> elements remain unconverted. Ideally this should
    # be 0 (all text converted). If it's > 0, some text elements couldn't
    # be converted (maybe missing fonts or unsupported features).

    # ========================================================================
    # STEP 7: Create a result object with conversion statistics
    # ========================================================================
    result = ConversionResult(
        success=(remaining_text == 0),
        # Success means NO text elements remain (all were converted to paths)
        input_format="lxml_document",
        # Record where the input came from for debugging/logging
        output=None,
        # We return the document directly, not a file path, so output is None
        text_count=text_count,
        # How many text elements were in the original SVG
        path_count=path_count,
        # How many path elements exist after conversion
        # Note: This includes both newly created paths AND any paths that
        # already existed in the original SVG, so path_count might be higher
        # than text_count if the original SVG had shapes.
    )

    return converted_doc, result


# ============================================================================
# ELEMENT-LEVEL CONVERSION - Working with Elements instead of Documents
# ============================================================================
def convert_lxml_element(
    svg_root: etree._Element,
    precision: int = 6,
) -> etree._Element:
    """Convert all text elements in an lxml SVG root element to paths.

    This is useful when you have just the root element, not a full document.

    Args:
        svg_root: The root <svg> element from an lxml tree.
        precision: Decimal precision for path coordinates.

    Returns:
        Modified SVG root element with text converted to paths.

    Example:
        >>> from lxml import etree
        >>> root = etree.parse("input.svg").getroot()
        >>> converted_root = convert_lxml_element(root)
        >>> etree.ElementTree(converted_root).write("output.svg", encoding="utf-8")
    """
    # This function is similar to convert_lxml_document(), but works with a
    # single Element (the <svg> root) instead of a full ElementTree document.
    # WHY? Sometimes you're manipulating SVG elements in memory and don't have
    # a full document structure - just the elements themselves.

    converter = Text2PathConverter(precision=precision)

    # Serialize element to string (use utf-8 bytes then decode)
    svg_bytes = etree.tostring(svg_root, encoding="utf-8", xml_declaration=True)
    # LXML METHOD: etree.tostring() works on both ElementTree AND Element objects.
    # When given an Element, it serializes just that element and its children.

    svg_string = svg_bytes.decode("utf-8")

    # Convert text to paths
    converted_string = converter.convert_string(svg_string)

    # Parse back to element (not document)
    converted_root = etree.fromstring(converted_string.encode("utf-8"))
    # LXML METHOD: etree.fromstring(bytes)
    # Parses XML from a byte string and returns the ROOT ELEMENT only (not an
    # ElementTree document). This is different from etree.parse() which returns
    # an ElementTree.
    #
    # KEY DIFFERENCE:
    # - etree.parse() → returns ElementTree (full document)
    # - etree.fromstring() → returns Element (just root element)
    #
    # Use etree.fromstring() when you want to work with elements directly
    # without the document wrapper.

    return converted_root


# ============================================================================
# SAMPLE SVG CREATION - Building SVG documents from scratch with lxml
# ============================================================================
def create_sample_svg(
    num_texts: int = 3,
    text_content: str | None = None,
) -> etree._ElementTree:
    """Create a sample SVG document with text elements for demonstration.

    Args:
        num_texts: Number of text elements to create.
        text_content: Optional custom text content for all elements.

    Returns:
        An lxml ElementTree with the sample SVG.
    """
    # This function demonstrates how to BUILD an SVG document from scratch
    # using lxml, rather than parsing an existing file. It shows all the key
    # lxml methods for creating and manipulating elements.

    # ========================================================================
    # NAMESPACE MAP - Defining the default XML namespace
    # ========================================================================
    NSMAP = {None: SVG_NS}
    # This dictionary maps namespace prefixes to namespace URIs.
    # {None: "http://..."} means: make this the DEFAULT namespace (no prefix).
    # So elements will be <svg>, <rect>, <text> instead of <svg:svg>, <svg:rect>.
    # The nsmap is passed to the root element to define namespaces for the document.

    # Calculate dimensions based on number of texts
    height = max(200, 50 + num_texts * 50)
    # Make the SVG tall enough to fit all text elements with 50px spacing

    # ========================================================================
    # CREATE ROOT ELEMENT
    # ========================================================================
    svg = etree.Element(f"{{{SVG_NS}}}svg", nsmap=NSMAP)
    # LXML METHOD: etree.Element(tag_name, nsmap=...)
    # Creates a NEW Element (XML tag) with the specified name.
    # - f"{{{SVG_NS}}}svg" creates an <svg> element in the SVG namespace
    # - nsmap=NSMAP sets the namespace map for this element (and its children)
    # The element is created in memory but not yet part of any tree.

    svg.set("width", "400")
    # LXML METHOD: element.set(attribute_name, value)
    # Sets an XML attribute on the element. This is like writing:
    # <svg width="400">
    # Both the attribute name and value must be strings.

    svg.set("height", str(height))
    # Convert height to string because .set() requires string values

    svg.set("viewBox", f"0 0 400 {height}")
    # The viewBox attribute defines the coordinate system for the SVG

    # ========================================================================
    # ADD CHILD ELEMENTS
    # ========================================================================
    rect = etree.SubElement(svg, f"{{{SVG_NS}}}rect")
    # LXML METHOD: etree.SubElement(parent, tag_name)
    # Creates a NEW Element AND adds it as a child of the parent in one step.
    # This is equivalent to:
    #   rect = etree.Element(f"{{{SVG_NS}}}rect")
    #   svg.append(rect)
    # SubElement is more convenient for building trees.

    rect.set("width", "100%")
    rect.set("height", "100%")
    rect.set("fill", "#f0f0f0")
    # Set attributes on the rectangle element:
    # <rect width="100%" height="100%" fill="#f0f0f0"/>

    # Sample texts with varying content
    sample_texts = [
        "Hello, World!",
        "Text converted to paths",
        "Bold Text Example",
        "Testing 123...",
        "Unicode: cafe",
        "Numbers: 0123456789",
        "Symbols: @#$%^&*()",
        "Mixed: Hello123!",
    ]

    # ========================================================================
    # CREATE MULTIPLE TEXT ELEMENTS
    # ========================================================================
    for i in range(num_texts):
        text_elem = etree.SubElement(svg, f"{{{SVG_NS}}}text")
        # Create a <text> element as a child of <svg>

        text_elem.set("x", "20")
        # Set horizontal position (20 pixels from left edge)

        text_elem.set("y", str(50 + i * 50))
        # Set vertical position (50px + 50px per text, stacking them vertically)

        text_elem.set("font-family", "Arial")
        # Specify which font to use for rendering this text

        text_elem.set("font-size", str(16 + (i % 3) * 4))  # Vary sizes
        # Vary font size: 16, 20, 24, 16, 20, 24, ... (cycles through 3 sizes)

        text_elem.set("fill", f"#{(i * 30) % 256:02x}3366")
        # Set text color using hexadecimal RGB format (#RRGGBB)
        # The red channel varies based on i, creating different colors

        # ====================================================================
        # SET TEXT CONTENT
        # ====================================================================
        if text_content:
            text_elem.text = text_content
        else:
            text_elem.text = sample_texts[i % len(sample_texts)]
        # LXML ATTRIBUTE: element.text
        # Sets the TEXT CONTENT of an element (the text between opening and
        # closing tags). In XML:
        #   <text>This is the .text content</text>
        #
        # KEY CONCEPT: .text vs .tail
        # - element.text = content INSIDE the element
        # - element.tail = content AFTER the closing tag
        # Example:
        #   <parent><child>text</child>tail</parent>
        #              child.text="text"
        #              child.tail="tail"
        # Most of the time you only use .text, but .tail is important when
        # parsing mixed-content XML (text and elements interleaved).

    # ========================================================================
    # WRAP ELEMENT IN ELEMENTTREE
    # ========================================================================
    return etree.ElementTree(svg)
    # LXML CONSTRUCTOR: etree.ElementTree(root_element)
    # Wraps an Element (the <svg> root) in an ElementTree document structure.
    # This is needed to use methods like .write() for saving to files.
    # Remember: Element = single node, ElementTree = whole document


# =============================================================================
# TEST FUNCTIONS - Validating the conversion functionality
# =============================================================================
# The following functions test various aspects of the text-to-path conversion.
# They demonstrate best practices for testing XML/SVG manipulation code and
# show how to verify conversion results programmatically.


def test_basic_conversion(verbose: bool = True) -> bool:
    """Test basic document conversion."""
    if verbose:
        print("\n--- Test: Basic Conversion ---")

    doc = create_sample_svg(num_texts=3)
    _converted_doc, result = convert_lxml_document(doc, precision=4)

    success = result.path_count > 0
    if verbose:
        print(f"  Input texts: {result.text_count}")
        print(f"  Paths created: {result.path_count}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_element_conversion(verbose: bool = True) -> bool:
    """Test element-level conversion (root element only)."""
    if verbose:
        print("\n--- Test: Element Conversion ---")

    doc = create_sample_svg(num_texts=2)
    root = doc.getroot()

    converted_root = convert_lxml_element(root, precision=6)

    # Check that paths were created
    paths = converted_root.findall(f".//{{{SVG_NS}}}path")
    success = len(paths) > 0

    if verbose:
        print(f"  Paths created: {len(paths)}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_precision_levels(verbose: bool = True) -> bool:
    """Test different precision levels."""
    if verbose:
        print("\n--- Test: Precision Levels ---")

    doc = create_sample_svg(num_texts=1)
    results = {}

    for precision in [2, 4, 6, 8]:
        converted_doc, _result = convert_lxml_document(doc, precision=precision)
        converted_root = converted_doc.getroot()
        paths = converted_root.findall(f".//{{{SVG_NS}}}path")

        if paths:
            # Get path data length as proxy for precision impact
            path_d = paths[0].get("d", "")
            results[precision] = len(path_d)

    success = len(results) > 0
    if verbose:
        for prec, length in results.items():
            print(f"  Precision {prec}: path data length = {length}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_font_cache_reuse(verbose: bool = True) -> bool:
    """Test font cache reuse across multiple conversions."""
    if verbose:
        print("\n--- Test: Font Cache Reuse ---")

    # Create a shared font cache
    font_cache = FontCache()

    # Create converter with shared cache
    converter = Text2PathConverter(font_cache=font_cache, precision=4)

    # Convert multiple documents
    results = []
    for i in range(3):
        doc = create_sample_svg(num_texts=2, text_content=f"Test {i + 1}")
        _converted_doc, result = convert_lxml_document(doc, converter=converter)
        results.append(result.path_count > 0)

    success = all(results)
    if verbose:
        print(f"  Conversions: {len(results)}")
        print(f"  All successful: {success}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_empty_svg(verbose: bool = True) -> bool:
    """Test handling of SVG with no text elements."""
    if verbose:
        print("\n--- Test: Empty SVG (no text) ---")

    # Create SVG with no text
    NSMAP = {None: SVG_NS}
    svg = etree.Element(f"{{{SVG_NS}}}svg", nsmap=NSMAP)
    svg.set("width", "100")
    svg.set("height", "100")

    rect = etree.SubElement(svg, f"{{{SVG_NS}}}rect")
    rect.set("width", "100%")
    rect.set("height", "100%")
    rect.set("fill", "#ccc")

    doc = etree.ElementTree(svg)

    try:
        _converted_doc, result = convert_lxml_document(doc)
        success = result.text_count == 0
    except Exception as e:
        if verbose:
            print(f"  Exception: {e}")
        success = False

    if verbose:
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_error_handling(verbose: bool = True) -> bool:
    """Test error handling for invalid input."""
    if verbose:
        print("\n--- Test: Error Handling ---")

    tests_passed = 0
    tests_total = 2

    # Test 1: Invalid XML
    try:
        converter = Text2PathConverter()
        converter.convert_string("<invalid>xml<here>")
        if verbose:
            print("  Invalid XML: Should have raised exception")
    except Exception:
        tests_passed += 1
        if verbose:
            print("  Invalid XML: Correctly raised exception")

    # Test 2: Non-existent font (should not crash, just warn)
    try:
        NSMAP = {None: SVG_NS}
        svg = etree.Element(f"{{{SVG_NS}}}svg", nsmap=NSMAP)
        svg.set("width", "100")
        svg.set("height", "100")

        text = etree.SubElement(svg, f"{{{SVG_NS}}}text")
        text.set("x", "10")
        text.set("y", "50")
        text.set("font-family", "NonExistentFont12345")
        text.set("font-size", "16")
        text.text = "Test"

        doc = etree.ElementTree(svg)
        _converted_doc, _result = convert_lxml_document(doc)
        tests_passed += 1
        if verbose:
            print("  Non-existent font: Handled gracefully")
    except Exception as e:
        if verbose:
            print(f"  Non-existent font: Exception {e}")

    success = tests_passed == tests_total
    if verbose:
        print(f"  Tests passed: {tests_passed}/{tests_total}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_stress(num_texts: int = 50, verbose: bool = True) -> bool:
    """Stress test with many text elements."""
    if verbose:
        print(f"\n--- Test: Stress Test ({num_texts} texts) ---")

    start_time = time.time()
    doc = create_sample_svg(num_texts=num_texts)

    # Use shared font cache for efficiency
    font_cache = FontCache()
    converter = Text2PathConverter(font_cache=font_cache, precision=4)

    _converted_doc, result = convert_lxml_document(doc, converter=converter)
    elapsed = time.time() - start_time

    success = result.path_count > 0
    if verbose:
        print(f"  Input texts: {result.text_count}")
        print(f"  Paths created: {result.path_count}")
        print(f"  Time: {elapsed:.3f}s")
        print(f"  Rate: {result.text_count / elapsed:.1f} texts/sec")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def run_benchmark(iterations: int = 10, verbose: bool = True) -> dict:
    """Run benchmark with timing statistics."""
    if verbose:
        print(f"\n--- Benchmark ({iterations} iterations) ---")

    times = []
    font_cache = FontCache()
    converter = Text2PathConverter(font_cache=font_cache, precision=4)

    for i in range(iterations):
        doc = create_sample_svg(num_texts=5)
        start = time.time()
        convert_lxml_document(doc, converter=converter)
        elapsed = time.time() - start
        times.append(elapsed)

        if verbose and (i + 1) % max(1, iterations // 5) == 0:
            print(f"  Iteration {i + 1}/{iterations}: {elapsed:.4f}s")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    results = {
        "iterations": iterations,
        "avg_time": avg_time,
        "min_time": min_time,
        "max_time": max_time,
        "total_time": sum(times),
    }

    if verbose:
        print(f"\n  Average: {avg_time:.4f}s")
        print(f"  Min: {min_time:.4f}s")
        print(f"  Max: {max_time:.4f}s")
        print(f"  Total: {sum(times):.2f}s")

    return results


def run_all_tests(verbose: bool = True) -> dict:
    """Run all tests and return results."""
    tests = {
        "basic_conversion": test_basic_conversion,
        "element_conversion": test_element_conversion,
        "precision_levels": test_precision_levels,
        "font_cache_reuse": test_font_cache_reuse,
        "empty_svg": test_empty_svg,
        "error_handling": test_error_handling,
        "stress_test": lambda v: test_stress(num_texts=20, verbose=v),
    }

    results = {}
    for name, test_func in tests.items():
        try:
            results[name] = test_func(verbose)
        except Exception as e:
            if verbose:
                print(f"  Exception in {name}: {e}")
            results[name] = False

    return results


# =============================================================================
# Main Entry Point
# =============================================================================


def check_dependencies() -> bool:
    """Check and report dependencies."""
    print("Checking dependencies...")
    report = verify_all_dependencies(check_npm=False)

    if not report.all_required_ok:
        print("Missing required dependencies:")
        for dep in report.missing_required:
            print(f"  - {dep.name}: {dep.install_hint}")
        return False

    # Check for lxml specifically
    try:
        print(f"  lxml version: {etree.LXML_VERSION}")
    except Exception:
        print("  ERROR: lxml not installed. Run: pip install lxml")
        return False

    print("  All dependencies OK!")
    return True


def run_demo(input_path: Path | None, output_path: Path | None) -> int:
    """Run the basic demo/conversion."""
    # Load or create SVG
    if input_path:
        if not input_path.exists():
            print(f"Error: Input file not found: {input_path}")
            return 1
        print(f"\nLoading SVG from: {input_path}")
        doc = etree.parse(str(input_path))
    else:
        print("\nNo input file specified, creating sample SVG...")
        doc = create_sample_svg()

    # ========================================================================
    # INSPECT ORIGINAL TEXT ELEMENTS
    # ========================================================================
    # Before converting, let's see what text elements exist in the source SVG
    root = doc.getroot()
    text_elements = root.findall(f".//{{{SVG_NS}}}text")
    print(f"\nFound {len(text_elements)} text element(s) in source:")
    for i, text_elem in enumerate(text_elements, 1):
        text_content = text_elem.text or "(empty)"
        # Get the text content of the element (or "(empty)" if None)

        font = text_elem.get("font-family", "default")
        # LXML METHOD: element.get(attribute_name, default_value)
        # Reads an XML attribute value from the element. Returns the attribute
        # value as a string, or the default value if the attribute doesn't exist.
        # This is safer than accessing attributes directly because it won't raise
        # an error for missing attributes.
        #
        # Example:
        #   <text font-family="Arial" font-size="16">Hello</text>
        #   text_elem.get("font-family") → "Arial"
        #   text_elem.get("color", "black") → "black" (attribute missing, use default)

        size = text_elem.get("font-size", "default")
        # Read the font-size attribute, defaulting to "default" if not present

        print(f"  {i}. '{text_content}' (font: {font}, size: {size})")

    # Convert the document
    print("\nConverting text to paths...")
    try:
        converted_doc, _result = convert_lxml_document(doc, precision=4)
        print("  Conversion successful!")
    except Exception as e:
        print(f"  Conversion failed: {e}")
        return 1

    # Verify conversion
    converted_root = converted_doc.getroot()
    remaining_text = converted_root.findall(f".//{{{SVG_NS}}}text")
    path_elements = converted_root.findall(f".//{{{SVG_NS}}}path")

    print("\nConversion results:")
    print(f"  Text elements remaining: {len(remaining_text)}")
    print(f"  Path elements created: {len(path_elements)}")

    # ========================================================================
    # SAVE THE CONVERTED DOCUMENT TO A FILE
    # ========================================================================
    if output_path is None:
        output_path = Path("output_converted.svg")

    converted_doc.write(
        str(output_path),
        # LXML METHOD: elementtree.write(filename, encoding, xml_declaration,
        #                                pretty_print)
        # Writes the ElementTree to a file on disk. This only works on
        # ElementTree objects, not on Element objects (if you have an Element,
        # wrap it first: etree.ElementTree(element).write(...))
        #
        # Parameters:
        # - filename: Path to the output file (as string)
        # - encoding: Character encoding (usually "utf-8" for Unicode support)
        # - xml_declaration: Whether to include <?xml version="1.0"?> at top
        # - pretty_print: Whether to add indentation and newlines for
        #   readability (True = human-readable, False = compact/minified)
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )
    print(f"\nSaved converted SVG to: {output_path}")

    return 0


def main() -> int:
    """Main entry point for the example script."""
    parser = argparse.ArgumentParser(
        description="svg-text2path lxml conversion example and test suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test modes:
  all        Run all tests
  basic      Basic conversion test
  element    Element-level conversion test
  precision  Test different precision levels
  cache      Test font cache reuse
  empty      Test empty SVG handling
  error      Test error handling
  stress     Stress test with many text elements

Examples:
  %(prog)s                           # Run demo with sample SVG
  %(prog)s input.svg                 # Convert a file
  %(prog)s input.svg output.svg      # Convert with specific output
  %(prog)s --test all                # Run all tests
  %(prog)s --test stress             # Run stress test
  %(prog)s --benchmark               # Run performance benchmark
  %(prog)s --benchmark --iterations 50  # Custom benchmark iterations
        """,
    )

    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Input SVG file (optional, uses sample if not provided)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="Output SVG file (optional, uses output_converted.svg)",
    )
    parser.add_argument(
        "--test",
        choices=[
            "all",
            "basic",
            "element",
            "precision",
            "cache",
            "empty",
            "error",
            "stress",
        ],
        help="Run specific test or all tests",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run performance benchmark",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of benchmark iterations (default: 10)",
    )
    parser.add_argument(
        "--stress-count",
        type=int,
        default=50,
        help="Number of text elements for stress test (default: 50)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Reduce output verbosity",
    )

    args = parser.parse_args()
    verbose = not args.quiet

    print("=" * 60)
    print("svg-text2path: lxml Document Conversion Example")
    print("=" * 60)

    # Check dependencies
    if not check_dependencies():
        return 1

    # Run tests if requested
    if args.test:
        test_map = {
            "basic": test_basic_conversion,
            "element": test_element_conversion,
            "precision": test_precision_levels,
            "cache": test_font_cache_reuse,
            "empty": test_empty_svg,
            "error": test_error_handling,
            "stress": lambda v: test_stress(args.stress_count, v),
        }

        if args.test == "all":
            results = run_all_tests(verbose)
            passed = sum(results.values())
            total = len(results)
            print(f"\n{'=' * 60}")
            print(f"Test Summary: {passed}/{total} passed")
            for name, result in results.items():
                status = "PASS" if result else "FAIL"
                print(f"  [{status}] {name}")
            print("=" * 60)
            return 0 if passed == total else 1
        else:
            test_func = test_map.get(args.test)
            if test_func:
                result = test_func(verbose)
                return 0 if result else 1
            else:
                print(f"Unknown test: {args.test}")
                return 1

    # Run benchmark if requested
    if args.benchmark:
        run_benchmark(args.iterations, verbose)
        print("\n" + "=" * 60)
        print("Benchmark completed!")
        print("=" * 60)
        return 0

    # Run demo/conversion
    result = run_demo(args.input, args.output)

    print("\n" + "=" * 60)
    print("Example completed!" if result == 0 else "Example failed!")
    print("=" * 60)

    return result


# =============================================================================
# LXML METHODS QUICK REFERENCE - Summary of all methods used in this example
# =============================================================================
#
# PARSING (Reading XML/SVG):
# ---------------------------
# etree.parse(file_or_filelike) → ElementTree
#     Parse XML from a file or file-like object (like BytesIO), returns full document
#
# etree.fromstring(bytes) → Element
#     Parse XML from a byte string, returns just the root element (no document wrapper)
#
# SERIALIZING (Writing XML/SVG):
# -------------------------------
# etree.tostring(element_or_tree, encoding="utf-8", xml_declaration=True) → bytes
#     Convert an Element or ElementTree to a byte string (XML text as bytes)
#
# elementtree.write(filename, encoding="utf-8", xml_declaration=True, pretty_print=True)
#     Write an ElementTree to a file on disk (only works on ElementTree, not Element)
#
# CREATING ELEMENTS:
# ------------------
# etree.Element(tag_name, nsmap={...}) → Element
#     Create a new element (XML tag) with optional namespace map
#
# etree.SubElement(parent, tag_name) → Element
#     Create a new element AND add it as a child of parent in one step
#
# etree.ElementTree(root_element) → ElementTree
#     Wrap an Element in an ElementTree document structure (needed for .write())
#
# NAVIGATING THE TREE:
# --------------------
# elementtree.getroot() → Element
#     Get the root element from an ElementTree document
#
# element.findall(xpath_pattern) → list[Element]
#     Find ALL elements matching an XPath query, returns a list
#     Example: root.findall(f".//{{{SVG_NS}}}text") finds all <text> elements
#
# element.find(xpath_pattern) → Element | None
#     Find the FIRST element matching an XPath query, or None if not found
#     Example: root.find(".//text") finds the first <text> element
#
# ATTRIBUTES (Reading and Writing):
# ----------------------------------
# element.get(attribute_name, default_value=None) → str | None
#     Read an attribute value (returns default if attribute doesn't exist)
#     Example: text_elem.get("font-family", "Arial") returns "Arial" if no font-family
#
# element.set(attribute_name, value)
#     Set an attribute value (both name and value must be strings)
#     Example: svg.set("width", "400") creates <svg width="400">
#
# TEXT CONTENT:
# -------------
# element.text → str | None
#     The text content INSIDE an element: <elem>text</elem>
#     Can be read or assigned: element.text = "Hello"
#
# element.tail → str | None
#     The text content AFTER an element's closing tag:
#     <parent><child>text</child>tail</parent>
#     Usually only needed for mixed-content XML (text and tags interleaved)
#
# XPATH PATTERNS USED:
# --------------------
# ".//text" - Find all <text> descendants (. = current node, // = any depth)
# "./text" - Find direct <text> children (. = current node, / = immediate children)
# "//text" - Find all <text> elements in entire document (no . means from root)
# f".//{{{namespace}}}text" - Find all <text> elements in specific XML namespace
#
# NAMESPACE SYNTAX:
# -----------------
# {http://www.w3.org/2000/svg}text means <text> in the SVG namespace
# In Python f-strings, we escape braces: f"{{{SVG_NS}}}text"
#
# WHY LXML OVER MINIDOM?
# ----------------------
# 1. SPEED: 5-10x faster (built on libxml2 in C)
# 2. XPATH: Full XPath support (minidom has none)
# 3. VALIDATION: Can validate against schemas
# 4. MEMORY: More efficient for large documents
# 5. FEATURES: XSLT, better namespaces, better errors
#
# ELEMENTTREE vs ELEMENT:
# -----------------------
# ElementTree = ENTIRE DOCUMENT (wrapper with XML declaration, root element)
# Element = SINGLE NODE (one tag with attributes, text, and children)
# ElementTree.getroot() → Element
# etree.ElementTree(element) → ElementTree
#
# =============================================================================


if __name__ == "__main__":
    sys.exit(main())
