"""Visual comparison utilities for SVG validation.

This module provides:
- ImageComparator: Pixel-perfect image comparison using NumPy
- SVGRenderer: Render SVG files to PNG using headless Chrome (puppeteer)
- Utility functions for generating diff images and parsing SVG metadata
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as ET
import numpy as np
from PIL import Image


def pixel_tol_to_threshold(pixel_tol: float) -> int:
    """Map a 0-1 pixel tolerance to sbb-comparer integer threshold (1-20).

    Args:
        pixel_tol: Pixel tolerance value between 0.0 and 1.0

    Returns:
        Integer threshold value between 1 and 20 for svg-bbox comparison
    """
    raw = int(round(pixel_tol * 256))
    return max(1, min(20, raw))


class SVGRenderer:
    """Render SVG files to PNG using headless Chrome (puppeteer)."""

    @staticmethod
    def _parse_svg_dimensions(svg_path: Path) -> tuple[int, int] | None:
        """Parse width and height from SVG file.

        Args:
            svg_path: Path to SVG file

        Returns:
            Tuple of (width, height) in pixels, or None if unable to parse
        """
        try:
            root = ET.parse(str(svg_path)).getroot()
            if root is None:
                return None

            def _num(val: str | None) -> float | None:
                if val is None:
                    return None
                try:
                    digits = [c for c in val if (c.isdigit() or c in ".+-")]
                    return float("".join(digits))
                except Exception:
                    return None

            w_attr = root.get("width")
            h_attr = root.get("height")
            vb = root.get("viewBox")

            if w_attr and h_attr:
                w = _num(w_attr)
                h = _num(h_attr)
                if w and h:
                    return int(round(w)), int(round(h))

            if vb:
                parts = vb.replace(",", " ").split()
                if len(parts) == 4:
                    try:
                        return int(float(parts[2])), int(float(parts[3]))
                    except Exception:
                        pass
        except Exception:
            return None
        return None

    @staticmethod
    def render_svg_to_png(svg_path: Path, png_path: Path, _dpi: int = 96) -> bool:
        """Render SVG to PNG with Chrome via puppeteer script render_svg_chrome.js.

        Args:
            svg_path: Path to input SVG file
            png_path: Path for output PNG file
            dpi: DPI setting (ignored; Chrome renders at CSS pixel units)

        Returns:
            True if rendering succeeded, False otherwise

        Notes:
            dpi parameter is ignored; Chrome renders at CSS pixel units
            matching SVG width/height.
        """
        dim = SVGRenderer._parse_svg_dimensions(svg_path)
        if not dim:
            msg = f"Error: cannot determine SVG dimensions for {svg_path}"
            print(f"X {msg}", file=sys.stderr)
            return False

        width, height = dim
        try:
            script = Path(__file__).parent / "render_svg_chrome.js"
            cmd = [
                "node",
                str(script),
                str(svg_path),
                str(png_path),
                str(width),
                str(height),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            if result.returncode != 0:
                print(f"! Chrome render failed: {result.stderr}", file=sys.stderr)
                return False
            return png_path.exists()
        except FileNotFoundError:
            msg = (
                "Error: node or Chrome (puppeteer) not found. "
                "Install Node.js and run `npm install puppeteer`."
            )
            print(f"X {msg}", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            print(f"X Error: Rendering timeout for {svg_path}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"X Error rendering {svg_path} with Chrome: {e}", file=sys.stderr)
            return False


class ImageComparator:
    """Pixel-perfect image comparison for SVG validation.

    Uses NumPy for efficient pixel-by-pixel comparison with configurable
    tolerance thresholds at both the pixel level and image level.
    """

    @staticmethod
    def compare_images_pixel_perfect(
        img1_path: Path,
        img2_path: Path,
        tolerance: float = 0.04,
        pixel_tolerance: float = 1 / 256,
    ) -> tuple[bool, dict[str, Any]]:
        """Compare two PNG images pixel-by-pixel.

        Args:
            img1_path: Path to first image (reference)
            img2_path: Path to second image (comparison)
            tolerance: Acceptable difference as percentage of total pixels
                (0.0 to 100.0)
            pixel_tolerance: Acceptable color difference per pixel (0.0 to 1.0)

        Returns:
            Tuple of (is_within_tolerance, diff_info_dict) where diff_info contains:
                - images_exist: bool
                - dimensions_match: bool
                - diff_pixels: int
                - total_pixels: int
                - diff_percentage: float
                - tolerance: float
                - pixel_tolerance: float
                - pixel_tolerance_rgb: float
                - within_tolerance: bool
                - first_diff_location: tuple[int, int] | None
                - img1_size: tuple[int, int]
                - img2_size: tuple[int, int]
        """
        try:
            img1 = Image.open(img1_path).convert("RGBA")
            img2 = Image.open(img2_path).convert("RGBA")
        except FileNotFoundError as e:
            return False, {"images_exist": False, "error": f"File not found: {e!s}"}
        except Exception as e:
            err = f"Error loading images: {e!s}"
            return False, {"images_exist": False, "error": err}

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
        diff_percentage = (
            (diff_pixels / total_pixels) * 100 if total_pixels > 0 else 0.0
        )

        # Find first difference location
        first_diff_location = None
        if diff_pixels > 0:
            diff_indices = np.argwhere(diff_mask)
            first_diff_location = tuple(diff_indices[0])  # (y, x)

        # Check if within tolerance
        is_identical = diff_percentage <= tolerance

        # Build diff info
        diff_info: dict[str, Any] = {
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
    """Return a readable resolution string from width/height/viewBox.

    Args:
        svg_path: Path to SVG file

    Returns:
        Human-readable resolution string, or "unknown" if unable to parse
    """
    try:
        root = ET.parse(str(svg_path)).getroot()
        if root is None:
            return "unknown"

        w = root.get("width")
        h = root.get("height")
        vb = root.get("viewBox")
        parts: list[str] = []

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
    """Sum length of all path 'd' attributes in an SVG (namespace aware).

    Args:
        svg_path: Path to SVG file

    Returns:
        Total character count of all path d attributes
    """
    try:
        root = ET.parse(str(svg_path)).getroot()
    except Exception:
        return 0

    if root is None:
        return 0

    total = 0
    for el in root.iter():
        tag = el.tag
        if "}" in tag:
            tag = tag.split("}")[1]
        if tag != "path":
            continue
        dval = el.get("d")
        if dval:
            total += len(dval)
    return total


def generate_diff_image(
    img1_path: Path,
    img2_path: Path,
    output_path: Path,
    pixel_tolerance: float = 1 / 256,
) -> None:
    """Generate visual diff image highlighting differences in red.

    Args:
        img1_path: Path to first image (reference)
        img2_path: Path to second image (comparison)
        output_path: Path for output diff image
        pixel_tolerance: Acceptable color difference per pixel (0.0 to 1.0)

    Raises:
        ValueError: If image sizes don't match
    """
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
        print(f"Saved diff image: {output_path}")

    except Exception as e:
        print(f"Error generating diff image: {e!s}", file=sys.stderr)


def generate_grayscale_diff_map(
    img1_path: Path,
    img2_path: Path,
    output_path: Path,
) -> None:
    """Generate grayscale diff map showing magnitude of differences.

    Args:
        img1_path: Path to first image (reference)
        img2_path: Path to second image (comparison)
        output_path: Path for output grayscale diff map

    Raises:
        ValueError: If image sizes don't match
    """
    try:
        img1 = Image.open(img1_path).convert("RGBA")
        img2 = Image.open(img2_path).convert("RGBA")

        if img1.size != img2.size:
            raise ValueError(f"Image sizes don't match: {img1.size} vs {img2.size}")

        arr1 = np.array(img1, dtype=np.float64)
        arr2 = np.array(img2, dtype=np.float64)

        diff = np.sqrt(np.sum((arr1 - arr2) ** 2, axis=2))
        max_diff = diff.max()
        scaled = (diff / max_diff) * 255 if max_diff > 0 else diff
        diff_norm = np.clip(scaled, 0, 255).astype(np.uint8)

        Image.fromarray(diff_norm).save(output_path)
        print(f"Saved grayscale diff map: {output_path}")

    except Exception as e:
        print(f"Error generating grayscale diff map: {e!s}", file=sys.stderr)
