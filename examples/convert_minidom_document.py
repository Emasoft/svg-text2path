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

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from xml.dom import minidom

# Import the text2path converter
from svg_text2path import (
    ConversionResult,
    FontCache,
    Text2PathConverter,
    verify_all_dependencies,
)

# SVG namespace constant
SVG_NS = "http://www.w3.org/2000/svg"


def convert_minidom_document(
    doc: minidom.Document,
    precision: int = 6,
    preserve_styles: bool = False,
    converter: Text2PathConverter | None = None,
) -> tuple[minidom.Document, ConversionResult]:
    """Convert all text elements in a minidom SVG document to paths.

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
    # Count text elements before conversion
    text_elements = doc.getElementsByTagName("text")
    text_count = text_elements.length

    # Create converter with custom settings (or reuse provided one)
    if converter is None:
        converter = Text2PathConverter(
            precision=precision,
            preserve_styles=preserve_styles,
        )

    # Serialize minidom document to string for conversion
    svg_string = doc.toxml()

    # Convert using the string API
    converted_string = converter.convert_string(svg_string)

    # Parse the converted string back to minidom
    converted_doc = minidom.parseString(converted_string)

    # Count path elements after conversion to determine success
    path_elements = converted_doc.getElementsByTagName("path")
    remaining_text = converted_doc.getElementsByTagName("text")

    # Create a result object with conversion stats
    result = ConversionResult(
        success=(remaining_text.length == 0),
        input_format="minidom_document",
        output=None,
        text_count=text_count,
        path_count=path_elements.length,
    )

    return converted_doc, result


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


def create_sample_svg(
    num_texts: int = 3,
    text_content: str | None = None,
) -> minidom.Document:
    """Create a sample SVG document with text elements for demonstration.

    Args:
        num_texts: Number of text elements to create.
        text_content: Optional custom text content for all elements.

    Returns:
        A minidom Document with the sample SVG.
    """
    # Create document
    doc = minidom.Document()

    # Calculate dimensions based on number of texts
    height = max(200, 50 + num_texts * 50)

    # Create SVG root with namespace
    svg = doc.createElementNS(SVG_NS, "svg")
    svg.setAttribute("xmlns", SVG_NS)
    svg.setAttribute("width", "400")
    svg.setAttribute("height", str(height))
    svg.setAttribute("viewBox", f"0 0 400 {height}")
    doc.appendChild(svg)

    # Add a background rectangle
    rect = doc.createElementNS(SVG_NS, "rect")
    rect.setAttribute("width", "100%")
    rect.setAttribute("height", "100%")
    rect.setAttribute("fill", "#f0f0f0")
    svg.appendChild(rect)

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

    # Add text elements
    for i in range(num_texts):
        text_elem = doc.createElementNS(SVG_NS, "text")
        text_elem.setAttribute("x", "20")
        text_elem.setAttribute("y", str(50 + i * 50))
        text_elem.setAttribute("font-family", "Arial")
        text_elem.setAttribute("font-size", str(16 + (i % 3) * 4))  # Vary sizes
        text_elem.setAttribute("fill", f"#{(i * 30) % 256:02x}3366")

        if text_content:
            text_node = doc.createTextNode(text_content)
        else:
            text_node = doc.createTextNode(sample_texts[i % len(sample_texts)])
        text_elem.appendChild(text_node)
        svg.appendChild(text_elem)

    return doc


# =============================================================================
# DOM Manipulation Examples
# =============================================================================


def inspect_svg_dom(doc: minidom.Document) -> dict[str, object]:
    """Inspect an SVG document using minidom's DOM API.

    Demonstrates common minidom operations for SVG inspection.

    Args:
        doc: A minidom Document containing SVG.

    Returns:
        Dictionary with SVG structure information.
    """
    svg = doc.documentElement
    if svg is None:
        return {
            "root_tag": None,
            "width": None,
            "height": None,
            "viewBox": None,
            "elements": {},
        }
    info: dict[str, object] = {
        "root_tag": svg.tagName,
        "width": svg.getAttribute("width"),
        "height": svg.getAttribute("height"),
        "viewBox": svg.getAttribute("viewBox"),
        "elements": {},
    }

    # Count elements by tag name
    elements_dict: dict[str, int] = {}
    for tag in ["text", "path", "rect", "circle", "ellipse", "line", "polygon", "g"]:
        elements = doc.getElementsByTagName(tag)
        if elements.length > 0:
            elements_dict[tag] = elements.length
    info["elements"] = elements_dict

    return info


def modify_svg_paths(doc: minidom.Document, fill_color: str = "#ff0000") -> None:
    """Modify all path elements in an SVG document.

    Demonstrates in-place DOM modification using minidom.

    Args:
        doc: A minidom Document to modify in-place.
        fill_color: New fill color for all paths.
    """
    paths = doc.getElementsByTagName("path")
    for i in range(paths.length):
        path = paths.item(i)
        if path:
            path.setAttribute("fill", fill_color)


def extract_text_content(doc: minidom.Document) -> list[str]:
    """Extract all text content from SVG text elements.

    Args:
        doc: A minidom Document containing SVG.

    Returns:
        List of text strings from all <text> elements.
    """
    texts = []
    text_elements = doc.getElementsByTagName("text")
    for i in range(text_elements.length):
        elem = text_elements.item(i)
        if elem and elem.firstChild:
            texts.append(elem.firstChild.nodeValue or "")
    return texts


def add_title_to_svg(doc: minidom.Document, title: str) -> None:
    """Add a <title> element to the SVG document.

    Args:
        doc: A minidom Document to modify.
        title: Title text to add.
    """
    svg = doc.documentElement
    if svg is None:
        return

    # Check if title already exists
    existing = doc.getElementsByTagName("title")
    if existing.length > 0:
        # Update existing title by replacing text content
        title_elem = existing.item(0)
        if title_elem:
            # Remove existing children and add new text node
            while title_elem.firstChild:
                title_elem.removeChild(title_elem.firstChild)
            new_text_node = doc.createTextNode(title)
            title_elem.appendChild(new_text_node)
        return

    # Create new title element
    title_elem = doc.createElementNS(SVG_NS, "title")
    text_node = doc.createTextNode(title)
    title_elem.appendChild(text_node)

    # Insert as first child of SVG
    first_child = svg.firstChild
    if first_child is not None:
        svg.insertBefore(title_elem, first_child)
    else:
        svg.appendChild(title_elem)


# =============================================================================
# Test Functions
# =============================================================================


def test_basic_conversion(verbose: bool = True) -> bool:
    """Test basic document conversion."""
    if verbose:
        print("\n--- Test: Basic Conversion ---")

    doc = create_sample_svg(num_texts=3)
    converted_doc, result = convert_minidom_document(doc, precision=4)

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
        converted_doc, result = convert_minidom_document(doc, converter=converter)
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

    converted_doc, result = convert_minidom_document(doc, converter=converter)
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
