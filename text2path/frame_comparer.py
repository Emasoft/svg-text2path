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
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image


class SVGRenderer:
    """Render SVG files to PNG using Inkscape"""

    @staticmethod
    def render_svg_to_png(svg_path: Path, png_path: Path, dpi: int = 96) -> bool:
        """
        Render SVG to PNG using Inkscape

        Args:
            svg_path: Path to SVG file
            png_path: Path to output PNG file
            dpi: DPI for rendering (default: 96)

        Returns:
            True if rendering succeeded, False otherwise
        """
        try:
            # Use Inkscape to render SVG to PNG
            result = subprocess.run(
                [
                    "inkscape",
                    "--export-type=png",
                    f"--export-filename={png_path}",
                    f"--export-dpi={dpi}",
                    str(svg_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"⚠️  Inkscape rendering failed: {result.stderr}", file=sys.stderr)
                return False

            return png_path.exists()

        except FileNotFoundError:
            print("❌ Error: Inkscape not found. Please install Inkscape to render SVG files.", file=sys.stderr)
            print("   macOS: brew install inkscape", file=sys.stderr)
            print("   Linux: apt-get install inkscape", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            print(f"❌ Error: Rendering timeout for {svg_path}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"❌ Error rendering {svg_path}: {e}", file=sys.stderr)
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
        "--tolerance",
        "-t",
        type=float,
        default=0.04,
        help="Image-level tolerance as percentage (0.0-100.0, default: 0.04)",
    )
    parser.add_argument(
        "--pixel-tolerance",
        "-p",
        type=float,
        default=1 / 256,
        help="Pixel-level color tolerance (0.0-1.0, default: 1/256 ≈ 0.0039)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=96,
        help="DPI for SVG rendering (default: 96)",
    )
    parser.add_argument(
        "--keep-pngs",
        action="store_true",
        help="Keep rendered PNG files (default: delete after comparison)",
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
    parser.add_argument("--open-html", action="store_true", help="No-op (compatibility).")
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip HTML summary generation/opening",
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

    print(f"Comparing SVG files:")
    print(f"  Reference: {args.svg1}")
    print(f"  Comparison: {args.svg2}")
    print()

    # Render SVGs to PNGs
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        renderer = SVGRenderer()
        comparator = ImageComparator()

        def run_one(svg_ref: Path, svg_cmp: Path, label: str):
            png1 = tmpdir_path / f"{svg_ref.stem}_{label}_ref.png"
            png2 = tmpdir_path / f"{svg_cmp.stem}_{label}_cmp.png"

            print("Rendering SVGs to PNG...")
            print(f"  Rendering {svg_ref.name}...")
            if not renderer.render_svg_to_png(svg_ref, png1, dpi=args.dpi):
                return None

            print(f"  Rendering {svg_cmp.name}...")
            if not renderer.render_svg_to_png(svg_cmp, png2, dpi=args.dpi):
                return None

            print("✓ Rendering complete\n")

            if args.keep_pngs:
                saved_png1 = args.output_dir / f"{svg_ref.stem}_{label}_rendered.png"
                saved_png2 = args.output_dir / f"{svg_cmp.stem}_{label}_rendered.png"
                Image.open(png1).save(saved_png1)
                Image.open(png2).save(saved_png2)
                print(f"✓ Saved rendered PNGs:")
                print(f"  {saved_png1}")
                print(f"  {saved_png2}\n")

            print("Comparing images...")
            is_identical, diff_info = comparator.compare_images_pixel_perfect(
                png1, png2, tolerance=args.tolerance, pixel_tolerance=args.pixel_tolerance
            )

            print()
            print(f"[{label}] {format_comparison_result(diff_info)}")
            print()

            if diff_info.get("diff_pixels", 0) > 0:
                print("Generating diff visualizations...")
                diff_img_path = args.output_dir / f"diff_{svg_ref.stem}_vs_{svg_cmp.stem}_{label}.png"
                generate_diff_image(png1, png2, diff_img_path, pixel_tolerance=args.pixel_tolerance)
                grayscale_diff_path = args.output_dir / f"diff_map_{svg_ref.stem}_vs_{svg_cmp.stem}_{label}.png"
                generate_grayscale_diff_map(png1, png2, grayscale_diff_path)
                print()

            return {
                "label": label,
                "ref": svg_ref,
                "cmp": svg_cmp,
                "diff_info": diff_info,
            }

        results = []
        primary = run_one(args.svg1, args.svg2, "ours")
        if primary:
            results.append(primary)
        if args.inkscape_svg:
            ink = run_one(args.svg1, args.inkscape_svg, "inkscape")
            if ink:
                results.append(ink)

    # HTML summary
    if results and not args.no_html:
        args.history_dir.mkdir(parents=True, exist_ok=True)
        counter_file = args.history_dir / "counter.txt"
        try:
            current = int(counter_file.read_text().strip())
        except Exception:
            current = 0
        test_number = current + 1
        counter_file.write_text(str(test_number))

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = args.history_dir / f"{test_number:04d}_{timestamp}"
        session_dir.mkdir(parents=True, exist_ok=True)

        def file_uri(p: Path) -> str:
            return p.resolve().as_uri()

        rows_html = []
        divider = '<hr style="height:6px;background:#333;border:0;margin:20px 0;">'
        for idx, res in enumerate(results):
            diff_pct = res["diff_info"].get("diff_percentage", 0.0)
            path_chars = total_path_chars(res["cmp"])
            res_ref = svg_resolution(res["ref"])
            res_cmp = svg_resolution(res["cmp"])
            bar = (
                f'<div style="background:#000;padding:10px 14px;'
                f'font-weight:bold;font-size:24px; text-align:center;">'
                f'<span style="color:#c67f00;">Diff:</span> '
                f'<span style="color:#ffb200;">{diff_pct:.4f}%</span>'
                f' &nbsp; <span style="color:#0e6b6b;">Path chars:</span> '
                f'<span style="color:#16a3a3;">{path_chars}</span>'
                f'</div>'
            )
            link_ref = f'<a href="{file_uri(res["ref"])}" style="font-size:20px;">{res["ref"].name}</a>'
            link_cmp = f'<a href="{file_uri(res["cmp"])}" style="font-size:20px;">{res["cmp"].name}</a>'
            # Colors per field
            res_label_color = "#5a2c8c"
            res_value_color = "#fffacd"
            vb_label_color = "#206d8a"
            vb_value_color = "#2aa7d6"
            name_label_color = "#5c2c85"
            name_value_color = "#8b46c4"
            row = f"""
            {bar}
            <div class="row">
              <div class="card">
                <div class="label"><span style="color:{name_label_color};">ORIGINAL:</span> <span style="color:{name_value_color};">{link_ref}</span></div>
                <object data="{file_uri(res['ref'])}" type="image/svg+xml"></object>
                <div class="meta-line res"><span style="color:#ffd700;font-weight:bold;">RESOLUTION:</span> <span style="color:{res_value_color};">{res_ref.split(';')[0]}</span></div>
                <div class="meta-line vb"><span style="color:{vb_label_color};font-weight:bold;">VIEWBOX:</span> <span style="color:{vb_value_color};">{res_ref.split(';')[-1].strip() if ';' in res_ref else res_ref}</span></div>
              </div>
              <div class="card">
                <div class="label"><span style="color:{name_label_color};">{'OUR CONVERSION:' if res['label']=='ours' else 'INKSCAPE:'}</span> <span style="color:{name_value_color};">{link_cmp}</span></div>
                <object data="{file_uri(res['cmp'])}" type="image/svg+xml"></object>
                <div class="meta-line res"><span style="color:#ffd700;font-weight:bold;">RESOLUTION:</span> <span style="color:{res_value_color};">{res_cmp.split(';')[0]}</span></div>
                <div class="meta-line vb"><span style="color:{vb_label_color};font-weight:bold;">VIEWBOX:</span> <span style="color:{vb_value_color};">{res_cmp.split(';')[-1].strip() if ';' in res_cmp else res_cmp}</span></div>
              </div>
            </div>
            """
            rows_html.append(row)
            if idx == 0 and len(results) > 1:
                rows_html.append(divider)

        html_path = session_dir / "comparison.html"
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>text2path comparison #{test_number}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; font-size:32px; }}
    .header {{ font-size: 48px; font-weight: bold; margin-bottom: 6px; }}
    .sub {{ color: #555; margin-bottom: 20px; font-size:28px; }}
    .row {{ display: flex; gap: 20px; margin-bottom: 16px; align-items: flex-start; }}
    .card {{ flex: 1; border: 2px solid #ccc; padding: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); background:#d9ffd9; }}
    .label {{ font-weight: bold; margin-bottom: 8px; font-size:32px; color:#7a2ca0; text-transform: uppercase; }}
    .meta {{ margin-top: 8px; color: #2a4a9a; font-size: 28px; }}
    .meta-line {{ padding:6px 8px; margin-top:4px; font-size: 24px; }}
    .meta-line.res {{ background:#933b5e; }}
    .meta-line.vb {{ background:#e0f5ff; }}
    object {{ width: 100%; height: 600px; border: 2px solid #eee; }}
  </style>
</head>
<body>
  <div class="header">Test #{test_number}</div>
  <div class="sub">{timestamp}</div>
  {''.join(rows_html)}
</body>
</html>"""

        html_path.write_text(html)
        try:
            subprocess.run(["open", "-a", "Google Chrome", str(html_path)], check=False)
        except Exception:
            pass

    return 0 if primary and primary["diff_info"].get("diff_pixels", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
