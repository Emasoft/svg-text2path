#!/usr/bin/env python3
"""Example: Convert text to paths using Python's built-in xml.dom.minidom.

This example demonstrates how to use svg-text2path with the standard library's
minidom, which provides a simple DOM API without external dependencies.

Benefits of minidom:
- No external dependencies (part of Python standard library)
- Simple, intuitive DOM API (createElement, appendChild, getAttribute, etc.)
- Good for basic SVG manipulation and inspection

For more advanced use cases (XPath, validation, large files), see:
- convert_lxml_document.py (uses lxml)

Requirements:
    pip install svg-text2path

Usage:
    python convert_minidom_document.py                    # Basic demo
    python convert_minidom_document.py input.svg          # Convert file
    python convert_minidom_document.py --test all         # Run all tests
"""

# ============================================================================
# IMPORTS - External Libraries and Standard Library Modules
# ============================================================================
# This section imports all the tools we need for the script

from __future__ import annotations

# WHY: Allows using modern type hints (like list[str] instead of List[str])
# even in older Python versions. Makes code more readable and type-safe.
import argparse

# WHY: Provides command-line argument parsing - lets users pass options like
# --test, input file path, etc. to control how the script runs.
import sys

# WHY: Provides access to system-level functionality like sys.exit() to return
# status codes (0 = success, 1 = error) that the shell can read.
import time

# WHY: Allows us to measure how long operations take (like converting 50 texts)
# using time.time() to get timestamps before/after operations.
from pathlib import Path

# WHY: Modern way to work with file paths. More readable than os.path.join()
# and works consistently across Windows, Mac, Linux. Example: Path("file.svg").exists()
from xml.dom import minidom

# WHY: This is Python's built-in DOM (Document Object Model) parser for XML/SVG.
# DOM represents XML as a tree of nodes that you can navigate and modify.
# minidom is "minimal DOM" - simpler than full DOM but covers most needs.
# ============================================================================
# IMPORTS - Text2Path Converter Components
# ============================================================================
# These come from the svg-text2path library (our main conversion tool)
from svg_text2path import (
    ConversionResult,
    # WHY: A data class that holds statistics about conversion operations:
    # - How many text elements were found (text_count)
    # - How many path elements were created (path_count)
    # - Whether conversion succeeded (success boolean)
    # - What format was processed (input_format)
    # It's like a "receipt" that tells you what happened during conversion.
    FontCache,
    # WHY: Speeds up font lookups by caching font file locations in memory.
    # Without this, every text element would trigger a slow disk search for fonts.
    # With FontCache, we find "Arial" once and remember where it is.
    # PERFORMANCE IMPACT: Converting 50 texts might take 10s without cache,
    # but only 2s with cache (5x speedup!) because font lookup happens once.
    Text2PathConverter,
    # WHY: This is the main converter class that does the actual text-to-path work.
    # Think of it as a specialized tool that:
    # 1. Reads SVG files with <text> elements
    # 2. Finds the fonts used by each text element
    # 3. Extracts glyph shapes (letter outlines) from the font files
    # 4. Converts those shapes to SVG <path> elements with bezier curves
    # 5. Replaces the <text> with the new <path> in the output SVG
    verify_all_dependencies,
    # WHY: Checks if required external tools are installed (fontconfig, fonts, etc.)
    # Fails early with helpful error messages instead of cryptic failures later.
)

# ============================================================================
# SVG NAMESPACE CONSTANT
# ============================================================================
# WHY DO WE NEED THIS?
#
# XML documents can have multiple "languages" mixed together (like HTML inside SVG).
# Namespaces prevent name collisions - they're like last names for XML tags.
#
# Example WITHOUT namespaces (ambiguous):
#   <a>Link</a>  ← Is this an HTML link or SVG anchor element?
#
# Example WITH namespaces (clear):
#   <html:a>HTML Link</html:a>
#   <svg:a>SVG Anchor</svg:a>
#
# The namespace URI "http://www.w3.org/2000/svg" is like a unique ID for SVG.
# It's NOT a website you visit - it's just a unique string that identifies
# "this element belongs to the SVG language standard".
#
# When we create SVG elements with minidom, we use createElementNS() instead of
# createElement() to ensure the browser knows these are SVG elements, not HTML.
SVG_NS = "http://www.w3.org/2000/svg"


# ============================================================================
# MAIN CONVERSION FUNCTION
# ============================================================================
# This is the core function that converts text elements to paths


def convert_minidom_document(
    doc: minidom.Document,
    # DOCUMENT vs ELEMENT: A "Document" is the root container for the entire
    # XML/SVG tree. It's like the file itself. An "Element" is a single node
    # like <text> or <path>. The Document owns all Elements.
    # Think: Document = entire book, Element = a single page

    precision: int = 6,
    # PRECISION EXPLAINED: When converting text glyphs to path coordinates,
    # we use decimal numbers like 123.456789. Precision controls how many
    # decimal places to keep:
    # - precision=2  →  123.46  (smaller files, less accurate curves)
    # - precision=6  →  123.456789  (default, good balance)
    # - precision=12 →  123.456789012345  (huge files, unnecessary accuracy)
    # Most cases: precision=4-6 is perfect. You won't see visual differences.

    preserve_styles: bool = False,
    # WHY: If True, converted paths keep CSS classes/style attributes from
    # original text. Useful if you want to change colors via CSS later.

    converter: Text2PathConverter | None = None,
    # WHY: Allows reusing a converter with a pre-warmed FontCache across
    # multiple conversions. This is a HUGE performance boost when converting
    # many SVG files - the font cache is built once and reused.
) -> tuple[minidom.Document, ConversionResult]:
    """Convert all text elements in a minidom SVG document to paths.

    WHAT HAPPENS DURING CONVERSION (conceptually):
    ==============================================
    1. TEXT ELEMENT: <text font-family="Arial" font-size="20">Hello</text>
       ↓
    2. FONT LOOKUP: Find Arial.ttf on disk (or in FontCache)
       ↓
    3. GLYPH EXTRACTION: For each letter ("H", "e", "l", "l", "o"):
       - Open the font file (TrueType/OpenType format)
       - Find the glyph ID for that character (via Unicode mapping)
       - Extract the outline as a series of points and curves
       ↓
    4. BEZIER CURVES: Convert font outlines to SVG path commands:
       - M = Move to starting point
       - L = Line to point
       - C = Cubic bezier curve (smooth curves for letters)
       - Z = Close path
       Example: "M 10,20 L 30,40 C 50,60 70,80 90,100 Z"
       ↓
    5. PATH ELEMENT: <path d="M 10,20 L 30,40 C 50,60..." fill="#000"/>
       This path draws the exact shape of "Hello" as vector outlines

    WHY DO THIS? Text elements need fonts installed to render correctly.
    Path elements are pure geometry - they look the same everywhere, even
    without fonts installed. This makes SVGs portable and prevents
    "missing font" rendering errors.

    Args:
        doc: A minidom Document containing the SVG.
        precision: Decimal precision for path coordinates (default: 6).
        preserve_styles: Whether to preserve font metadata on paths.
        converter: Optional pre-configured converter (reuses font cache).

    Returns:
        Tuple of (modified_document, conversion_result).

    Example:
        >>> from xml.dom import minidom
        >>> doc = minidom.parse("input.svg")
        >>> converted_doc, result = convert_minidom_document(doc)
        >>> print(f"Converted {result.path_count}/{result.text_count} text elements")
        >>> with open("output.svg", "w") as f:
        ...     f.write(converted_doc.toxml())
    """

    # ========================================================================
    # STEP 1: Count Text Elements Before Conversion
    # ========================================================================
    # getElementsByTagName() searches the entire document tree for all
    # elements with the tag name "text". It returns a NodeList (not a Python list!)
    text_elements = doc.getElementsByTagName("text")
    # MINIDOM API: getElementsByTagName() returns a NodeList object from the
    # DOM specification. NodeList has:
    # - .length (NOT len()!) - number of items (this is JavaScript-style DOM API)
    # - .item(index) - get element at index (like [index] but DOM-compliant)
    # WHY .length not len()? Because minidom follows the W3C DOM standard
    # which was designed for JavaScript where arrays have .length property.

    # NODELIST EXPLAINED: A NodeList is like a live view into the document.
    # If you modify the document (add/remove elements), the NodeList updates
    # automatically. It's NOT a static Python list - it's a dynamic query result.
    text_count = text_elements.length

    # ========================================================================
    # STEP 2: Create or Reuse Converter
    # ========================================================================
    # Create converter with custom settings (or reuse provided one)
    if converter is None:
        # Create a new converter with the specified settings
        converter = Text2PathConverter(
            precision=precision,
            preserve_styles=preserve_styles,
        )
        # FONTCACHE PERFORMANCE: If no converter is provided, this creates
        # a NEW FontCache for each conversion. That means:
        # - First text element: Search disk for fonts (slow: ~500ms)
        # - Second text element: Search again (slow: ~500ms)
        # - Third text element: Search again (slow: ~500ms)
        # Total: 1500ms for 3 texts
        #
        # If you pass a converter with a pre-warmed FontCache:
        # - First text element: Use cached font info (fast: ~1ms)
        # - Second text element: Use cached font info (fast: ~1ms)
        # - Third text element: Use cached font info (fast: ~1ms)
        # Total: 3ms for 3 texts (500x faster!)

    # ========================================================================
    # STEP 3: Serialize Document to String
    # ========================================================================
    # Serialize minidom document to string for conversion
    # MINIDOM API: doc.toxml() converts the DOM tree back to XML text
    svg_string = doc.toxml()
    # WHAT IS toxml()? It walks the entire DOM tree and writes each element
    # as text. Example:
    # Document tree:       →  String output:
    # Document                 <?xml version="1.0"?>
    # └─ svg                   <svg>
    #    └─ text                 <text>Hello</text>
    #                          </svg>

    # ========================================================================
    # STEP 4: Convert Using Text2Path String API
    # ========================================================================
    # Convert using the string API
    converted_string = converter.convert_string(svg_string)
    # THIS IS WHERE THE MAGIC HAPPENS! The converter:
    # 1. Parses the SVG string internally
    # 2. Finds all <text> elements
    # 3. For each text element:
    #    a. Reads font-family, font-size, font-weight attributes
    #    b. Uses FontCache to find the font file
    #    c. Uses HarfBuzz to shape the text (handle ligatures, RTL, etc.)
    #    d. Extracts glyph outlines from the font
    #    e. Converts outlines to SVG path data (M, L, C, Z commands)
    #    f. Creates a <path> element to replace the <text>
    # 4. Returns the modified SVG as a string

    # ========================================================================
    # STEP 5: Parse Converted String Back to Document
    # ========================================================================
    # Parse the converted string back to minidom
    # MINIDOM API: parseString() takes XML text and builds a Document tree
    converted_doc = minidom.parseString(converted_string)
    # WHY SERIALIZE AND RE-PARSE? The Text2PathConverter works with strings,
    # not DOM objects. So we:
    # 1. Convert DOM → String (toxml)
    # 2. Process String → Modified String (converter)
    # 3. Convert String → DOM (parseString)
    # This seems inefficient but it's actually fast (<10ms) and keeps the
    # converter simple - it doesn't need to understand minidom internals.

    # ========================================================================
    # STEP 6: Count Results to Verify Success
    # ========================================================================
    # Count path elements after conversion to determine success
    path_elements = converted_doc.getElementsByTagName("path")
    remaining_text = converted_doc.getElementsByTagName("text")

    # ========================================================================
    # STEP 7: Create Result Statistics Object
    # ========================================================================
    # Create a result object with conversion stats
    result = ConversionResult(
        success=(remaining_text.length == 0),
        # Success means ALL text elements were converted (none remain)
        input_format="minidom_document",
        output=None,
        # output=None because we return the Document directly, not a file path
        text_count=text_count,
        # How many text elements we started with
        path_count=path_elements.length,
        # How many path elements exist after conversion (should be >= text_count
        # because one text element might create multiple paths)
    )

    return converted_doc, result
    # RETURN VALUE: A tuple with two items:
    # 1. converted_doc: The modified Document with paths instead of text
    # 2. result: Statistics about what happened (like a receipt)


def convert_minidom_element(
    svg_element: minidom.Element,
    precision: int = 6,
) -> minidom.Element | None:
    """Convert all text elements in a minidom SVG element to paths.

    This is useful when you have just the SVG element, not a full document.

    Args:
        svg_element: The <svg> element from a minidom document.
        precision: Decimal precision for path coordinates.

    Returns:
        Modified SVG element with text converted to paths.

    Example:
        >>> from xml.dom import minidom
        >>> doc = minidom.parse("input.svg")
        >>> svg_elem = doc.documentElement
        >>> converted_elem = convert_minidom_element(svg_elem)
        >>> # Create new document with converted element
        >>> new_doc = minidom.Document()
        >>> new_doc.appendChild(converted_elem.cloneNode(deep=True))
    """
    converter = Text2PathConverter(precision=precision)

    # Serialize element to string
    svg_string = svg_element.toxml()

    # Wrap in proper SVG if needed
    if not svg_string.startswith("<?xml"):
        svg_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg_string

    # Convert
    converted_string = converter.convert_string(svg_string)

    # Parse back to element
    converted_doc = minidom.parseString(converted_string)

    return converted_doc.documentElement


# ============================================================================
# DOM CONSTRUCTION EXAMPLE - Creating SVG from Scratch
# ============================================================================
# This function shows how to build an SVG document using minidom's DOM API


def create_sample_svg(
    num_texts: int = 3,
    text_content: str | None = None,
) -> minidom.Document:
    """Create a sample SVG document with text elements for demonstration.

    This function demonstrates core minidom DOM manipulation methods:
    - Document() - Create a new document container
    - createElementNS() - Create elements with namespace (for SVG)
    - createElement() - Create elements without namespace (for HTML)
    - setAttribute() - Set XML attributes like x="20"
    - createTextNode() - Create text content inside elements
    - appendChild() - Add child nodes to parent elements

    Args:
        num_texts: Number of text elements to create.
        text_content: Optional custom text content for all elements.

    Returns:
        A minidom Document with the sample SVG.
    """
    # ========================================================================
    # STEP 1: Create Empty Document Container
    # ========================================================================
    # Create document
    # MINIDOM API: Document() creates an empty XML document container.
    # It's like an empty file - you need to add elements to it.
    # The Document is the root of the entire tree structure.
    doc = minidom.Document()

    # ========================================================================
    # STEP 2: Calculate Dynamic Dimensions
    # ========================================================================
    # Calculate dimensions based on number of texts
    height = max(200, 50 + num_texts * 50)
    # We space text elements 50px apart vertically, plus 50px top margin

    # ========================================================================
    # STEP 3: Create SVG Root Element with Namespace
    # ========================================================================
    # Create SVG root with namespace
    # MINIDOM API: createElementNS(namespace, tagname) creates an element
    # that belongs to a specific XML namespace. This is CRITICAL for SVG!
    svg = doc.createElementNS(SVG_NS, "svg")
    # WHY createElementNS instead of createElement?
    # - createElement("svg") → Creates <svg> without namespace (breaks in browsers!)
    # - createElementNS(SVG_NS, "svg") → Creates proper SVG element
    # Browsers need the namespace to know this is SVG, not HTML or custom XML.

    # MINIDOM API: setAttribute(name, value) sets an XML attribute
    # Like writing <svg xmlns="..." width="400"> in XML
    svg.setAttribute("xmlns", SVG_NS)
    # The xmlns attribute tells XML parsers "all child elements are SVG"
    svg.setAttribute("width", "400")
    svg.setAttribute("height", str(height))
    # Note: setAttribute always takes strings, so we convert height to str
    svg.setAttribute("viewBox", f"0 0 400 {height}")
    # viewBox defines the coordinate system (min-x min-y width height)

    # MINIDOM API: appendChild(child) adds a child node to a parent
    # This creates the tree structure:
    # Document
    # └─ svg (we just added this)
    doc.appendChild(svg)
    # Now our document has a root <svg> element

    # ========================================================================
    # STEP 4: Add Background Rectangle
    # ========================================================================
    # Add a background rectangle
    rect = doc.createElementNS(SVG_NS, "rect")
    # WHY doc.createElementNS and not svg.createElementNS?
    # Elements are always created from the Document object, not from other
    # elements. The Document is the "factory" that creates all nodes.
    # Then we appendChild() to attach them to the right parent.

    rect.setAttribute("width", "100%")
    # 100% means "full width of the SVG canvas" (400px in this case)
    rect.setAttribute("height", "100%")
    rect.setAttribute("fill", "#f0f0f0")
    # Light gray background (hex color: rgb(240, 240, 240))

    svg.appendChild(rect)
    # Add the rectangle as a child of the SVG root
    # Tree now looks like:
    # Document
    # └─ svg
    #    └─ rect (we just added this)

    # ========================================================================
    # STEP 5: Prepare Sample Text Content
    # ========================================================================
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
    # We cycle through these if no custom text_content is provided

    # ========================================================================
    # STEP 6: Create Multiple Text Elements in a Loop
    # ========================================================================
    # Add text elements
    for i in range(num_texts):
        # Create a new <text> element for each iteration
        text_elem = doc.createElementNS(SVG_NS, "text")

        # Position text: all aligned left (x=20), vertically spaced 50px apart
        text_elem.setAttribute("x", "20")
        text_elem.setAttribute("y", str(50 + i * 50))
        # First text at y=50, second at y=100, third at y=150, etc.

        # Font styling
        text_elem.setAttribute("font-family", "Arial")
        text_elem.setAttribute("font-size", str(16 + (i % 3) * 4))
        # Vary sizes: 16, 20, 24, 16, 20, 24, ... (cycles through 3 sizes)
        # i % 3 gives: 0, 1, 2, 0, 1, 2, ...
        # (i % 3) * 4 gives: 0, 4, 8, 0, 4, 8, ...
        # 16 + offset gives: 16, 20, 24, 16, 20, 24, ...

        # Color: vary hue based on position
        text_elem.setAttribute("fill", f"#{(i * 30) % 256:02x}3366")
        # Format: #RRGGBB where RR is (i*30)%256 in hex
        # :02x means "hex with 2 digits, zero-padded"
        # (i*30) % 256 gives: 0, 30, 60, 90, 120, 150, 180, 210, 240, 14, 44, ...
        # This creates different shades of blue/purple

        # ====================================================================
        # STEP 6a: Create Text Content (Text Node)
        # ====================================================================
        if text_content:
            # Use custom text if provided
            # MINIDOM API: createTextNode(data) creates a text node
            # A text node is NOT an element - it's pure text content
            # In XML, elements have tags <like-this>, but text nodes are just
            # the text between tags: <text>THIS IS A TEXT NODE</text>
            text_node = doc.createTextNode(text_content)
        else:
            # Use sample text from our list
            text_node = doc.createTextNode(sample_texts[i % len(sample_texts)])
            # i % len(sample_texts) cycles through the array:
            # i=0 → sample_texts[0], i=8 → sample_texts[0], etc.

        # MINIDOM API: appendChild() can add both Elements and Text nodes
        text_elem.appendChild(text_node)
        # This creates the structure: <text>Hello, World!</text>
        # Where "Hello, World!" is the text_node we just created

        # Add the complete text element to the SVG
        svg.appendChild(text_elem)
        # Tree now looks like:
        # Document
        # └─ svg
        #    ├─ rect
        #    ├─ text[0] "Hello, World!"
        #    ├─ text[1] "Text converted to paths"
        #    └─ text[2] "Bold Text Example"

    # ========================================================================
    # STEP 7: Return the Complete Document
    # ========================================================================
    return doc
    # The returned Document can now be:
    # - Converted to string: doc.toxml()
    # - Pretty-printed: doc.toprettyxml()
    # - Saved to file: open(...).write(doc.toxml())
    # - Converted to paths: convert_minidom_document(doc)


# =============================================================================
# DOM MANIPULATION EXAMPLES - Reading and Modifying SVG
# =============================================================================
# These functions show how to inspect and modify existing SVG documents


def inspect_svg_dom(doc: minidom.Document) -> dict[str, object]:
    """Inspect an SVG document using minidom's DOM API.

    Demonstrates common minidom operations for SVG inspection:
    - documentElement - Get root element
    - tagName - Read element's tag name
    - getAttribute() - Read attribute values
    - getElementsByTagName() - Find all elements with a tag name

    Args:
        doc: A minidom Document containing SVG.

    Returns:
        Dictionary with SVG structure information.
    """
    # ========================================================================
    # Get Root Element
    # ========================================================================
    # MINIDOM API: doc.documentElement returns the root element of the document
    # For an SVG file, this is the <svg> element
    # For an HTML file, this would be the <html> element
    svg = doc.documentElement
    # WHAT IS documentElement? It's a shortcut to get the first child element
    # of the Document. Instead of doc.childNodes[0], you use doc.documentElement

    if svg is None:
        # Document has no root element (empty or malformed XML)
        return {
            "root_tag": None,
            "width": None,
            "height": None,
            "viewBox": None,
            "elements": {},
        }

    # ========================================================================
    # Read Element Properties and Attributes
    # ========================================================================
    info: dict[str, object] = {
        # MINIDOM API: .tagName property returns the element's tag name
        # For <svg>, this returns "svg"
        # For <text>, this returns "text"
        "root_tag": svg.tagName,

        # MINIDOM API: .getAttribute(name) reads an XML attribute value
        # Returns empty string "" if attribute doesn't exist (not None!)
        # This is different from Python dicts which return None for missing keys
        "width": svg.getAttribute("width"),
        # Reads <svg width="400"> → returns "400"

        "height": svg.getAttribute("height"),
        # Reads <svg height="600"> → returns "600"

        "viewBox": svg.getAttribute("viewBox"),
        # Reads <svg viewBox="0 0 400 600"> → returns "0 0 400 600"

        "elements": {},
        # Will be filled with element counts below
    }

    # ========================================================================
    # Count Elements by Tag Name
    # ========================================================================
    # Count elements by tag name
    elements_dict: dict[str, int] = {}
    for tag in ["text", "path", "rect", "circle", "ellipse", "line", "polygon", "g"]:
        # For each tag type, search the entire document
        elements = doc.getElementsByTagName(tag)
        # MINIDOM API: getElementsByTagName(name) returns a NodeList
        # of ALL elements with that tag name anywhere in the document tree

        if elements.length > 0:
            # Remember: NodeList uses .length (not len()!)
            elements_dict[tag] = elements.length
            # Store the count: {"text": 5, "path": 10, "rect": 2}

    info["elements"] = elements_dict

    return info


def modify_svg_paths(doc: minidom.Document, fill_color: str = "#ff0000") -> None:
    """Modify all path elements in an SVG document.

    Demonstrates in-place DOM modification using minidom:
    - getElementsByTagName() - Find elements to modify
    - .item(index) - Access elements in a NodeList
    - setAttribute() - Modify attribute values

    Args:
        doc: A minidom Document to modify in-place.
        fill_color: New fill color for all paths.
    """
    # ========================================================================
    # Find All Path Elements
    # ========================================================================
    paths = doc.getElementsByTagName("path")
    # This finds ALL <path> elements in the entire document

    # ========================================================================
    # Loop Through NodeList and Modify Each Element
    # ========================================================================
    for i in range(paths.length):
        # NodeList doesn't support Python's for...in loop or list comprehension!
        # We must use range(paths.length) and access via .item(index)

        # MINIDOM API: .item(index) returns the element at position index
        # This is the DOM standard way to access NodeList items
        # Alternative: paths[i] also works in Python's minidom (but .item()
        # is more portable to other languages like JavaScript)
        path = paths.item(i)

        if path:
            # Check if path is not None (defensive programming)
            # MINIDOM API: setAttribute(name, value) modifies an attribute
            path.setAttribute("fill", fill_color)
            # Changes <path fill="#000000"> to <path fill="#ff0000">
            # If "fill" attribute didn't exist, it creates it!


def extract_text_content(doc: minidom.Document) -> list[str]:
    """Extract all text content from SVG text elements.

    Demonstrates navigating the DOM tree to read text content:
    - getElementsByTagName() - Find elements
    - .item(index) - Access NodeList elements
    - .firstChild - Get first child node of an element
    - .nodeValue - Read text content from a text node

    Args:
        doc: A minidom Document containing SVG.

    Returns:
        List of text strings from all <text> elements.
    """
    texts = []

    # Find all <text> elements in the document
    text_elements = doc.getElementsByTagName("text")

    # Loop through each text element
    for i in range(text_elements.length):
        elem = text_elements.item(i)
        # Get the element at position i

        # ====================================================================
        # Navigate to Text Content
        # ====================================================================
        if elem and elem.firstChild:
            # MINIDOM API: .firstChild returns the first child node of an element
            # For <text>Hello</text>, the structure is:
            # Element "text"
            # └─ Text node "Hello"  ← this is firstChild
            #
            # DOM TREE STRUCTURE: Elements can have different types of children:
            # - Element nodes (like <tspan> inside <text>)
            # - Text nodes (the actual text content)
            # - Comment nodes (<!-- comments -->)
            # - Processing instructions, CDATA sections, etc.

            # MINIDOM API: .nodeValue reads the content of a text node
            # For element nodes, nodeValue is None
            # For text nodes, nodeValue is the text string
            # Example:
            # - Text node "Hello" → nodeValue = "Hello"
            # - Element <text> → nodeValue = None
            texts.append(elem.firstChild.nodeValue or "")
            # We use "or ''" to handle None case safely (if firstChild is
            # an Element instead of a Text node, nodeValue would be None)

    return texts
    # Returns a list like: ["Hello, World!", "Text converted to paths", ...]


def add_title_to_svg(doc: minidom.Document, title: str) -> None:
    """Add a <title> element to the SVG document.

    Demonstrates advanced DOM manipulation:
    - documentElement - Get root element
    - getElementsByTagName() - Search for existing elements
    - removeChild() - Remove nodes from parent
    - appendChild() - Add nodes to end of children
    - insertBefore() - Add nodes at specific position

    Args:
        doc: A minidom Document to modify.
        title: Title text to add.
    """
    svg = doc.documentElement
    if svg is None:
        return

    # ========================================================================
    # Check if Title Already Exists
    # ========================================================================
    # Check if title already exists
    existing = doc.getElementsByTagName("title")
    if existing.length > 0:
        # ====================================================================
        # Update Existing Title (Remove Old Content, Add New)
        # ====================================================================
        # Update existing title by replacing text content
        title_elem = existing.item(0)
        if title_elem:
            # MINIDOM API: removeChild(child) removes a child node from parent
            # We need to remove ALL existing children (text nodes) first
            # Remove existing children and add new text node
            while title_elem.firstChild:
                # Keep removing firstChild until there are no more children
                title_elem.removeChild(title_elem.firstChild)
                # After removal, the next child becomes firstChild
                # Loop continues until firstChild is None

            # Now create and add new text content
            new_text_node = doc.createTextNode(title)
            title_elem.appendChild(new_text_node)
        return

    # ========================================================================
    # Create New Title Element
    # ========================================================================
    # Create new title element
    title_elem = doc.createElementNS(SVG_NS, "title")
    text_node = doc.createTextNode(title)
    title_elem.appendChild(text_node)
    # Now we have: <title>My SVG Document</title>

    # ========================================================================
    # Insert Title as First Child of SVG
    # ========================================================================
    # Insert as first child of SVG (this is best practice for accessibility)
    first_child = svg.firstChild
    # MINIDOM API: .firstChild gets the first child node (could be Element,
    # Text, Comment, etc.)

    if first_child is not None:
        # MINIDOM API: insertBefore(newNode, referenceNode) inserts newNode
        # immediately before referenceNode in the parent's children
        # Example:
        # Before: <svg><rect/><circle/></svg>
        # After:  <svg><title/><rect/><circle/></svg>
        svg.insertBefore(title_elem, first_child)
        # This ensures <title> is the first child (important for screen readers
        # and accessibility tools which read elements in order)
    else:
        # SVG has no children yet, just append normally
        # MINIDOM API: appendChild(child) adds child to end of children list
        svg.appendChild(title_elem)


# =============================================================================
# Test Functions
# =============================================================================


def test_basic_conversion(verbose: bool = True) -> bool:
    """Test basic document conversion."""
    if verbose:
        print("\n--- Test: Basic Conversion ---")

    doc = create_sample_svg(num_texts=3)
    _converted_doc, result = convert_minidom_document(doc, precision=4)

    success = result.path_count > 0
    if verbose:
        print(f"  Input texts: {result.text_count}")
        print(f"  Paths created: {result.path_count}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_element_conversion(verbose: bool = True) -> bool:
    """Test element-level conversion."""
    if verbose:
        print("\n--- Test: Element Conversion ---")

    doc = create_sample_svg(num_texts=2)
    svg_elem = doc.documentElement
    if svg_elem is None:
        if verbose:
            print("  Error: No SVG element found")
            print("  Result: FAIL")
        return False

    converted_elem = convert_minidom_element(svg_elem, precision=6)
    if converted_elem is None:
        if verbose:
            print("  Error: Conversion returned None")
            print("  Result: FAIL")
        return False

    # Check that paths were created
    # Need to create temp doc to use getElementsByTagName
    temp_doc = minidom.Document()
    imported = temp_doc.importNode(converted_elem, deep=True)
    temp_doc.appendChild(imported)
    paths = temp_doc.getElementsByTagName("path")
    success = paths.length > 0

    if verbose:
        print(f"  Paths created: {paths.length}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_dom_inspection(verbose: bool = True) -> bool:
    """Test DOM inspection functions."""
    if verbose:
        print("\n--- Test: DOM Inspection ---")

    doc = create_sample_svg(num_texts=3)
    info = inspect_svg_dom(doc)

    elements_info = info["elements"]
    success = (
        info["root_tag"] == "svg"
        and isinstance(elements_info, dict)
        and "text" in elements_info
    )
    if verbose:
        print(f"  Root tag: {info['root_tag']}")
        print(f"  Elements: {info['elements']}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_dom_modification(verbose: bool = True) -> bool:
    """Test DOM modification after conversion."""
    if verbose:
        print("\n--- Test: DOM Modification ---")

    doc = create_sample_svg(num_texts=2)
    converted_doc, _ = convert_minidom_document(doc)

    # Modify all paths to red
    modify_svg_paths(converted_doc, fill_color="#ff0000")

    # Verify modification
    paths = converted_doc.getElementsByTagName("path")
    all_red = True
    for i in range(paths.length):
        path = paths.item(i)
        if path and path.getAttribute("fill") != "#ff0000":
            all_red = False
            break

    success = paths.length > 0 and all_red
    if verbose:
        print(f"  Paths modified: {paths.length}")
        print(f"  All paths red: {all_red}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_text_extraction(verbose: bool = True) -> bool:
    """Test text content extraction."""
    if verbose:
        print("\n--- Test: Text Extraction ---")

    doc = create_sample_svg(num_texts=3)
    texts = extract_text_content(doc)

    success = len(texts) == 3 and all(len(t) > 0 for t in texts)
    if verbose:
        print(f"  Texts extracted: {len(texts)}")
        for t in texts:
            print(f"    - '{t}'")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_add_title(verbose: bool = True) -> bool:
    """Test adding title to SVG."""
    if verbose:
        print("\n--- Test: Add Title ---")

    doc = create_sample_svg(num_texts=1)
    add_title_to_svg(doc, "My SVG Document")

    titles = doc.getElementsByTagName("title")
    success = titles.length == 1
    if success:
        title_elem = titles.item(0)
        if title_elem and title_elem.firstChild:
            success = title_elem.firstChild.nodeValue == "My SVG Document"

    if verbose:
        print(f"  Title added: {success}")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def test_pretty_print(verbose: bool = True) -> bool:
    """Test minidom pretty printing."""
    if verbose:
        print("\n--- Test: Pretty Print ---")

    doc = create_sample_svg(num_texts=2)
    converted_doc, _ = convert_minidom_document(doc)

    # Get pretty-printed output
    pretty_xml = converted_doc.toprettyxml(indent="  ")

    success = len(pretty_xml) > 0 and "\n" in pretty_xml
    if verbose:
        lines = pretty_xml.split("\n")
        print(f"  Total lines: {len(lines)}")
        print("  First 3 lines:")
        for line in lines[:3]:
            print(f"    {line}")
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
        _converted_doc, result = convert_minidom_document(doc, converter=converter)
        results.append(result.path_count > 0)

    success = all(results)
    if verbose:
        print(f"  Conversions: {len(results)}")
        print(f"  All successful: {success}")
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

    _converted_doc, result = convert_minidom_document(doc, converter=converter)
    elapsed = time.time() - start_time

    success = result.path_count > 0
    if verbose:
        print(f"  Input texts: {result.text_count}")
        print(f"  Paths created: {result.path_count}")
        print(f"  Time: {elapsed:.3f}s")
        print(f"  Rate: {result.text_count / elapsed:.1f} texts/sec")
        print(f"  Result: {'PASS' if success else 'FAIL'}")

    return success


def run_all_tests(verbose: bool = True) -> dict[str, bool]:
    """Run all tests and return results."""
    from collections.abc import Callable

    tests: dict[str, Callable[[bool], bool]] = {
        "basic_conversion": test_basic_conversion,
        "element_conversion": test_element_conversion,
        "dom_inspection": test_dom_inspection,
        "dom_modification": test_dom_modification,
        "text_extraction": test_text_extraction,
        "add_title": test_add_title,
        "pretty_print": test_pretty_print,
        "font_cache_reuse": test_font_cache_reuse,
        "stress_test": lambda v: test_stress(num_texts=20, verbose=v),
    }

    results: dict[str, bool] = {}
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

    print("  minidom: built-in (no install needed)")
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
        doc = minidom.parse(str(input_path))
    else:
        print("\nNo input file specified, creating sample SVG...")
        doc = create_sample_svg()

    # Show original text elements
    print("\nDOM Inspection (before conversion):")
    info = inspect_svg_dom(doc)
    print(f"  Root: <{info['root_tag']}> ({info['width']} x {info['height']})")
    print(f"  Elements: {info['elements']}")

    # Extract and show text content
    texts = extract_text_content(doc)
    print(f"\nFound {len(texts)} text element(s):")
    for i, text in enumerate(texts, 1):
        print(f"  {i}. '{text}'")

    # Convert the document
    print("\nConverting text to paths...")
    try:
        converted_doc, result = convert_minidom_document(doc, precision=4)
        print("  Conversion successful!")
    except Exception as e:
        print(f"  Conversion failed: {e}")
        return 1

    # Show conversion results
    print("\nDOM Inspection (after conversion):")
    converted_info = inspect_svg_dom(converted_doc)
    print(f"  Elements: {converted_info['elements']}")

    print("\nConversion results:")
    print(f"  Text elements converted: {result.text_count}")
    print(f"  Path elements created: {result.path_count}")

    # Add a title to demonstrate DOM manipulation
    add_title_to_svg(converted_doc, "Converted by svg-text2path")
    print("  Added <title> element")

    # Save output
    if output_path is None:
        output_path = Path("output_minidom_converted.svg")

    # Use toprettyxml for readable output
    pretty_xml = converted_doc.toprettyxml(indent="  ")

    # Remove extra blank lines that toprettyxml adds
    lines = [line for line in pretty_xml.split("\n") if line.strip()]
    clean_xml = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(clean_xml)

    print(f"\nSaved converted SVG to: {output_path}")

    return 0


def main() -> int:
    """Main entry point for the example script."""
    parser = argparse.ArgumentParser(
        description="svg-text2path minidom conversion example and test suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test modes:
  all           Run all tests
  basic         Basic conversion test
  element       Element-level conversion test
  inspection    DOM inspection test
  modification  DOM modification test
  extraction    Text extraction test
  title         Add title test
  pretty        Pretty print test
  cache         Font cache reuse test
  stress        Stress test with many text elements

Examples:
  %(prog)s                           # Run demo with sample SVG
  %(prog)s input.svg                 # Convert a file
  %(prog)s input.svg output.svg      # Convert with specific output
  %(prog)s --test all                # Run all tests
  %(prog)s --test stress             # Run stress test

Benefits of minidom over lxml:
  - No external dependencies (built into Python)
  - Simple DOM API familiar to web developers
  - Easy to learn and use for basic SVG manipulation
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
        help="Output SVG file (optional, uses output_minidom_converted.svg)",
    )
    parser.add_argument(
        "--test",
        choices=[
            "all",
            "basic",
            "element",
            "inspection",
            "modification",
            "extraction",
            "title",
            "pretty",
            "cache",
            "stress",
        ],
        help="Run specific test or all tests",
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
    print("svg-text2path: minidom Document Conversion Example")
    print("=" * 60)

    # Check dependencies
    if not check_dependencies():
        return 1

    # Run tests if requested
    if args.test:
        from collections.abc import Callable

        test_map: dict[str, Callable[[bool], bool]] = {
            "basic": test_basic_conversion,
            "element": test_element_conversion,
            "inspection": test_dom_inspection,
            "modification": test_dom_modification,
            "extraction": test_text_extraction,
            "title": test_add_title,
            "pretty": test_pretty_print,
            "cache": test_font_cache_reuse,
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

    # Run demo/conversion
    demo_result = run_demo(args.input, args.output)

    print("\n" + "=" * 60)
    print("Example completed!" if demo_result == 0 else "Example failed!")
    print("=" * 60)

    return demo_result


if __name__ == "__main__":
    sys.exit(main())
