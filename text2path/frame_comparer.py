#!/usr/bin/env python3
"""
Frame Comparer (t2p_compare)
----------------------------
Render two SVGs with Inkscape, diff their PNGs pixel-perfectly, and (optionally) compare against an Inkscape text-to-path reference.

Usage:
  t2p_compare ref.svg ours.svg [--inkscape-svg ref_paths.svg] [--output-dir DIR] [--tolerance 0.2] [--pixel-tolerance 0.01]

Examples:
  t2p_compare samples/test_text_to_path_advanced.svg /tmp/out.svg
  t2p_compare samples/test_text_to_path_advanced.svg /tmp/out.svg --inkscape-svg samples/test_text_to_path_advanced_inkscape_paths.svg
  t2p_compare a.svg b.svg -o ./diffs --tolerance 0.1 --pixel-tolerance 0.005 --keep-pngs
"""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def pixel_tol_to_threshold(pixel_tol: float) -> int:
    """Map a 0-1 pixel tolerance to sbb-comparer integer threshold (1-20)."""
    raw = int(round(pixel_tol * 256))
    return max(1, min(20, raw))


def run_sbb_comparer(
    svg1: Path, svg2: Path, output_dir: Path, pixel_tol: float, no_html: bool
) -> dict | None:
    """Run sbb-comparer.cjs and return parsed JSON result."""
    sbb_comparer_script = Path(__file__).parent.parent / "SVG-BBOX" / "sbb-comparer.cjs"
    if not sbb_comparer_script.exists():
        print(f"❌ sbb-comparer.cjs not found at {sbb_comparer_script}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    threshold = pixel_tol_to_threshold(pixel_tol)
    diff_png = output_dir / f"diff_{svg1.stem}_vs_{svg2.stem}.png"
    cmd = [
        "node",
        str(sbb_comparer_script),
        str(svg1),
        str(svg2),
        "--out-diff",
        str(diff_png),
        "--threshold",
        str(threshold),
        "--scale",
        "4",
        "--json",
    ]

    print(f"Running sbb-comparer: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=output_dir, capture_output=True, text=True)

    if result.stderr:
        print(result.stderr)

    payload = None
    if result.stdout:
        try:
            payload = json.loads(result.stdout.strip())
        except Exception:
            print(result.stdout)

    html_name = f"{svg1.stem}_vs_{svg2.stem}_comparison.html"
    html_path = output_dir / html_name
    if html_path.exists():
        print(f"✓ HTML report: {html_path}")

    if result.returncode != 0:
        print(f"✗ sbb-comparer exited with {result.returncode}")
        return payload

    if payload:
        diff_pct = payload.get("diffPercentage") or payload.get("difference") or payload.get("diff_percentage")
        if diff_pct is not None:
            print(f"✓ Diff: {float(diff_pct):.4f}% (threshold={threshold})")

    print(f"✓ Diff image: {diff_png}")
    return payload


class SVGRenderer:
    """Render SVG files to PNG using headless Chrome (puppeteer)."""

    @staticmethod
    def _parse_svg_dimensions(svg_path: Path) -> tuple[int, int] | None:
        try:
            root = ET.parse(svg_path).getroot()
            def _num(val: str) -> float | None:
                if val is None:
                    return None
                m = None
                try:
                    m = float(''.join([c for c in val if (c.isdigit() or c in '.+-')]))
                except Exception:
                    return None
                return m
            w_attr = root.get('width')
            h_attr = root.get('height')
            vb = root.get('viewBox')
            if w_attr and h_attr:
                w = _num(w_attr)
                h = _num(h_attr)
                if w and h:
                    return int(round(w)), int(round(h))
            if vb:
                parts = vb.replace(',', ' ').split()
                if len(parts) == 4:
                    try:
                        return int(float(parts[2])), int(float(parts[3]))
                    except Exception:
                        pass
        except Exception:
            return None
        return None

    @staticmethod
    def render_svg_to_png(svg_path: Path, png_path: Path, dpi: int = 96) -> bool:
        """Render SVG to PNG with Chrome via puppeteer script render_svg_chrome.js.

        Notes: dpi is ignored; Chrome renders at CSS pixel units matching SVG width/height.
        """
        dim = SVGRenderer._parse_svg_dimensions(svg_path)
        if not dim:
            print(f"❌ Error: cannot determine SVG dimensions for {svg_path}", file=sys.stderr)
            return False
        width, height = dim
        try:
            script = Path(__file__).parent / "render_svg_chrome.js"
            cmd = ["node", str(script), str(svg_path), str(png_path), str(width), str(height)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            if result.returncode != 0:
                print(f"⚠️  Chrome render failed: {result.stderr}", file=sys.stderr)
                return False
            return png_path.exists()
        except FileNotFoundError:
            print("❌ Error: node or Chrome (puppeteer) not found. Install Node.js and run `npm install puppeteer`.", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            print(f"❌ Error: Rendering timeout for {svg_path}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"❌ Error rendering {svg_path} with Chrome: {e}", file=sys.stderr)
            return False


class ImageComparator:
    """
    Pixel-perfect image comparison for SVG validation

    Based on tests/utils/image_comparison.py
    """

    @staticmethod
    def compare_images_pixel_perfect(
        img1_path: Path,
        img2_path: Path,
        tolerance: float = 0.04,  # Image-level tolerance (percentage of pixels)
        pixel_tolerance: float = 1 / 256,  # Pixel-level tolerance (color difference)
    ) -> tuple[bool, dict[str, Any]]:
        """
        Compare two PNG images pixel-by-pixel

        Args:
            img1_path: Path to first image (reference)
            img2_path: Path to second image (comparison)
            tolerance: Acceptable difference as percentage (0.0 to 100.0)
            pixel_tolerance: Acceptable color difference per pixel (0.0 to 1.0)

        Returns:
            (is_identical, diff_info)
        """
        try:
            img1 = Image.open(img1_path).convert("RGBA")
            img2 = Image.open(img2_path).convert("RGBA")
        except FileNotFoundError as e:
            return False, {"images_exist": False, "error": f"File not found: {str(e)}"}
        except Exception as e:
            return False, {"images_exist": False, "error": f"Error loading images: {str(e)}"}

        # Check dimensions match
        if img1.size != img2.size:
            return False, {
                "images_exist": True,
                "dimensions_match": False,
                "img1_size": img1.size,
                "img2_size": img2.size,
                "error": f"Dimension mismatch: {img1.size} vs {img2.size}",
            }

        # Convert to numpy arrays
        arr1 = np.array(img1)
        arr2 = np.array(img2)

        # Calculate absolute difference per channel
        abs_diff = np.abs(arr1.astype(float) - arr2.astype(float))

        # Convert pixel_tolerance to RGB scale
        threshold_rgb = pixel_tolerance * 255

        # Find differences
        diff_mask = np.any(abs_diff > threshold_rgb, axis=2)
        diff_pixels = int(np.sum(diff_mask))
        total_pixels = arr1.shape[0] * arr1.shape[1]

        # Calculate difference percentage
        diff_percentage = ((diff_pixels / total_pixels) * 100) if total_pixels > 0 else 0.0

        # Find first difference location
        first_diff_location = None
        if diff_pixels > 0:
            diff_indices = np.argwhere(diff_mask)
            first_diff_location = tuple(diff_indices[0])  # (y, x)

        # Check if within tolerance
        is_identical = diff_percentage <= tolerance

        # Build diff info
        diff_info = {
            "images_exist": True,
            "dimensions_match": True,
            "diff_pixels": diff_pixels,
            "total_pixels": total_pixels,
            "diff_percentage": diff_percentage,
            "tolerance": tolerance,
            "pixel_tolerance": pixel_tolerance,
            "pixel_tolerance_rgb": threshold_rgb,
            "within_tolerance": is_identical,
            "first_diff_location": first_diff_location,
            "img1_size": img1.size,
            "img2_size": img2.size,
        }

        return is_identical, diff_info


def svg_resolution(svg_path: Path) -> str:
    """Return a readable resolution string from width/height/viewBox."""
    try:
        root = ET.parse(svg_path).getroot()
        w = root.get("width")
        h = root.get("height")
        vb = root.get("viewBox")
        parts = []
        if w and h:
            parts.append(f"width={w}, height={h}")
        if (not w or not h) and vb:
            nums = vb.replace(",", " ").split()
            if len(nums) == 4:
                parts.append(f"viewBox={vb} (w={nums[2]}, h={nums[3]})")
        elif vb:
            parts.append(f"viewBox={vb}")
        # If only one of w/h present, still report it
        if not parts:
            if w:
                parts.append(f"width={w}")
            if h:
                parts.append(f"height={h}")
        return "; ".join(parts) if parts else "unknown"
    except Exception:
        return "unknown"


def total_path_chars(svg_path: Path) -> int:
    """Sum length of all path 'd' attributes in an SVG (namespace aware)."""
    root = ET.parse(svg_path).getroot()
    total = 0
    for el in root.iter():
        tag = el.tag
        if '}' in tag:
            tag = tag.split('}')[1]
        if tag != "path":
            continue
        dval = el.get("d")
        if dval:
            total += len(dval)
    return total

def generate_diff_image(img1_path: Path, img2_path: Path, output_path: Path, pixel_tolerance: float = 1 / 256) -> None:
    """Generate visual diff image highlighting differences in red."""
    try:
        img1 = Image.open(img1_path).convert("RGBA")
        img2 = Image.open(img2_path).convert("RGBA")

        if img1.size != img2.size:
            raise ValueError(f"Image sizes don't match: {img1.size} vs {img2.size}")

        arr1 = np.array(img1)
        arr2 = np.array(img2)

        abs_diff = np.abs(arr1.astype(float) - arr2.astype(float))
        threshold_rgb = pixel_tolerance * 255
        diff_mask = np.any(abs_diff > threshold_rgb, axis=2)

        diff_img = arr1.copy()
        diff_img[diff_mask] = [255, 0, 0, 255]

        Image.fromarray(diff_img).save(output_path)
        print(f"✓ Saved diff image: {output_path}")

    except Exception as e:
        print(f"⚠️  Error generating diff image: {str(e)}", file=sys.stderr)

def generate_grayscale_diff_map(img1_path: Path, img2_path: Path, output_path: Path) -> None:
    """Generate grayscale diff map showing magnitude of differences."""
    try:
        img1 = Image.open(img1_path).convert("RGBA")
        img2 = Image.open(img2_path).convert("RGBA")

        if img1.size != img2.size:
            raise ValueError(f"Image sizes don't match: {img1.size} vs {img2.size}")

        arr1 = np.array(img1, dtype=np.float64)
        arr2 = np.array(img2, dtype=np.float64)

        diff = np.sqrt(np.sum((arr1 - arr2) ** 2, axis=2))
        diff_norm = np.clip((diff / diff.max()) * 255 if diff.max() > 0 else diff, 0, 255).astype(np.uint8)

        Image.fromarray(diff_norm).save(output_path)
        print(f"✓ Saved grayscale diff map: {output_path}")

    except Exception as e:
        print(f"⚠️  Error generating grayscale diff map: {str(e)}", file=sys.stderr)


def format_comparison_result(diff_info: dict[str, Any]) -> str:
    """Format comparison results for display"""
    if not diff_info.get("images_exist", False):
        return f"❌ {diff_info.get('error', 'Unknown error')}"

    if not diff_info.get("dimensions_match", False):
        return f"❌ {diff_info.get('error', 'Dimension mismatch')}"

    diff_pixels = diff_info["diff_pixels"]
    total_pixels = diff_info["total_pixels"]
    diff_percentage = diff_info["diff_percentage"]
    tolerance = diff_info["tolerance"]
    is_identical = diff_info["within_tolerance"]

    status = "✓" if is_identical else "✗"
    result = f"{status} Comparison: {diff_percentage:.4f}% different ({diff_pixels:,} / {total_pixels:,} pixels)\n"
    result += f"  Tolerance: {tolerance}%\n"
    result += f"  Pixel tolerance: {diff_info['pixel_tolerance']} ({diff_info['pixel_tolerance_rgb']:.1f} RGB units)\n"

    if diff_pixels > 0:
        first_diff = diff_info["first_diff_location"]
        result += f"  First difference at: (y={first_diff[0]}, x={first_diff[1]})\n"

    if is_identical:
        result += "  Status: PASS ✓"
    else:
        result += "  Status: FAIL ✗"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Compare two SVG files visually with pixel-perfect diff output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("svg1", type=Path, help="First SVG file (reference)")
    parser.add_argument("svg2", type=Path, help="Second SVG file (comparison)")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("/tmp/frame_comparer"),
        help="Directory to save diff images (default: /tmp/frame_comparer)",
    )
    parser.add_argument(
        "--pixel-tolerance",
        "-p",
        type=float,
        default=20 / 256,
        help="Pixel-level color tolerance (0.0-1.0, default: 20/256 ≈ 0.078)",
    )
    parser.add_argument(
        "--inkscape-svg",
        type=Path,
        help="Optional Inkscape text-to-path SVG for secondary comparison",
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=Path("history"),
        help="Directory to store HTML comparison history (default: ./history)",
    )
    parser.add_argument("--precision", type=int, default=None, help="Ignored (compatibility).")
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Generate HTML summary but do not auto-open it",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.svg1.exists():
        print(f"❌ Error: File not found: {args.svg1}", file=sys.stderr)
        return 1

    if not args.svg2.exists():
        print(f"❌ Error: File not found: {args.svg2}", file=sys.stderr)
        return 1
    if args.inkscape_svg and not args.inkscape_svg.exists():
        print(f"❌ Error: Inkscape SVG not found: {args.inkscape_svg}", file=sys.stderr)
        return 1

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Comparing SVG files:")
    print(f"  Reference: {args.svg1}")
    print(f"  Comparison: {args.svg2}")
    print()

    results = []
    primary = run_sbb_comparer(
        args.svg1,
        args.svg2,
        args.output_dir,
        pixel_tol=args.pixel_tolerance,
        no_html=args.no_html,
    )
    if primary:
        results.append(primary)

    if args.inkscape_svg:
        secondary_dir = args.output_dir / "inkscape_compare"
        run_sbb_comparer(
            args.svg1,
            args.inkscape_svg,
            secondary_dir,
            pixel_tol=args.pixel_tolerance,
            no_html=args.no_html,
        )

    if not results:
        return 1

    try:
        diff_pix = results[0].get("differentPixels") or results[0].get("diff_pixels")
        return 0 if diff_pix == 0 else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
