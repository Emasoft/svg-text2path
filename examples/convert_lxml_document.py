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

from __future__ import annotations

import argparse
import sys
import time
from io import BytesIO
from pathlib import Path

# lxml for SVG document handling
from lxml import etree  # type: ignore[attr-defined]  # lxml stubs issue

# Import the text2path converter
from svg_text2path import (
    ConversionResult,
    FontCache,
    Text2PathConverter,
    verify_all_dependencies,
)

# SVG namespace constant
SVG_NS = "http://www.w3.org/2000/svg"


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
    # Count text elements before conversion
    root = doc.getroot()
    text_count = len(root.findall(f".//{{{SVG_NS}}}text"))

    # Create converter with custom settings (or reuse provided one)
    if converter is None:
        converter = Text2PathConverter(
            precision=precision,
            preserve_styles=preserve_styles,
        )

    # Serialize lxml document to string for conversion
    # Note: lxml requires encoding="utf-8" (not "unicode") when xml_declaration=True
    svg_bytes = etree.tostring(doc, encoding="utf-8", xml_declaration=True)
    svg_string = svg_bytes.decode("utf-8")

    # Convert using the string API
    converted_string = converter.convert_string(svg_string)

    # Parse the converted string back to lxml
    converted_doc = etree.parse(BytesIO(converted_string.encode("utf-8")))

    # Count path elements after conversion to determine success
    converted_root = converted_doc.getroot()
    path_count = len(converted_root.findall(f".//{{{SVG_NS}}}path"))
    remaining_text = len(converted_root.findall(f".//{{{SVG_NS}}}text"))

    # Create a result object with conversion stats
    result = ConversionResult(
        success=(remaining_text == 0),
        input_format="lxml_document",
        output=None,
        text_count=text_count,
        path_count=path_count,
    )

    return converted_doc, result


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
    converter = Text2PathConverter(precision=precision)

    # Serialize element to string (use utf-8 bytes then decode)
    svg_bytes = etree.tostring(svg_root, encoding="utf-8", xml_declaration=True)
    svg_string = svg_bytes.decode("utf-8")

    # Convert
    converted_string = converter.convert_string(svg_string)

    # Parse back to element
    converted_root = etree.fromstring(converted_string.encode("utf-8"))

    return converted_root


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
    NSMAP = {None: SVG_NS}

    # Calculate dimensions based on number of texts
    height = max(200, 50 + num_texts * 50)

    # Create SVG root
    svg = etree.Element(f"{{{SVG_NS}}}svg", nsmap=NSMAP)
    svg.set("width", "400")
    svg.set("height", str(height))
    svg.set("viewBox", f"0 0 400 {height}")

    # Add a background rectangle
    rect = etree.SubElement(svg, f"{{{SVG_NS}}}rect")
    rect.set("width", "100%")
    rect.set("height", "100%")
    rect.set("fill", "#f0f0f0")

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
        text_elem = etree.SubElement(svg, f"{{{SVG_NS}}}text")
        text_elem.set("x", "20")
        text_elem.set("y", str(50 + i * 50))
        text_elem.set("font-family", "Arial")
        text_elem.set("font-size", str(16 + (i % 3) * 4))  # Vary sizes
        text_elem.set("fill", f"#{(i * 30) % 256:02x}3366")

        if text_content:
            text_elem.text = text_content
        else:
            text_elem.text = sample_texts[i % len(sample_texts)]

    return etree.ElementTree(svg)


# =============================================================================
# Test Functions
# =============================================================================


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
        _converted_doc, result = convert_lxml_document(
            doc, converter=converter
        )
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

    # Show original text elements
    root = doc.getroot()
    text_elements = root.findall(f".//{{{SVG_NS}}}text")
    print(f"\nFound {len(text_elements)} text element(s) in source:")
    for i, text_elem in enumerate(text_elements, 1):
        text_content = text_elem.text or "(empty)"
        font = text_elem.get("font-family", "default")
        size = text_elem.get("font-size", "default")
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

    # Save output
    if output_path is None:
        output_path = Path("output_converted.svg")

    converted_doc.write(
        str(output_path),
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
            "all", "basic", "element", "precision",
            "cache", "empty", "error", "stress"
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
        "-q", "--quiet",
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


if __name__ == "__main__":
    sys.exit(main())
