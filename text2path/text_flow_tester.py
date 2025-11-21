#!/usr/bin/env python3
"""
Text Flow Tester
----------------
Extract a single <text> element from an SVG (by id) into a minimal SVG,
run our text2path converter, render both with Inkscape, and report pixel diff.

Usage:
  python src/text_flow_tester.py --svg samples/test_text_to_path_advanced.svg --id text44 --work /tmp/flowtest
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from text2path.frame_comparer import SVGRenderer, ImageComparator


def extract_text(svg_path: Path, text_id: str, out_dir: Path) -> tuple[Path, Path]:
    """
    Extract a single <text> element (by id) along with defs/viewBox/width/height into a new SVG.
    Returns (original_svg, converted_svg_placeholder_path).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    import xml.etree.ElementTree as ET

    tree = ET.parse(svg_path)
    root = tree.getroot()

    ns = {"svg": "http://www.w3.org/2000/svg"}
    text_el = root.find(f".//svg:text[@id='{text_id}']", ns)
    if text_el is None:
        raise SystemExit(f"text id '{text_id}' not found")

    new_root = ET.Element(root.tag, root.attrib)
    # copy defs (gradients, paths) that text may reference
    for child in root:
        tag = child.tag.split('}')[-1]
        if tag == "defs":
            new_root.append(child)
    # copy referenced paths for textPath
    def collect_paths(el, dst_root):
        for ch in el:
            tag = ch.tag.split('}')[-1]
            if tag == "path" and ch.get("id"):
                dst_root.append(ch)
            collect_paths(ch, dst_root)
    collect_paths(root, new_root)

    new_root.append(text_el)
    new_tree = ET.ElementTree(new_root)
    extracted = out_dir / f"{text_id}_single.svg"
    new_tree.write(extracted, encoding="utf-8", xml_declaration=True)
    converted = out_dir / f"{text_id}_single_converted.svg"
    return extracted, converted


def run_converter(single_svg: Path, converted_svg: Path, precision: int = 6):
    cmds = ["t2p_convert", str(single_svg), str(converted_svg), "--precision", str(precision)]
    subprocess.run(cmds, check=True)


def compare(ref_svg: Path, cmp_svg: Path, workdir: Path, dpi: int = 96):
    renderer = SVGRenderer()
    comparator = ImageComparator()
    png_ref = workdir / f"{ref_svg.stem}.png"
    png_cmp = workdir / f"{cmp_svg.stem}.png"
    if not renderer.render_svg_to_png(ref_svg, png_ref, dpi=dpi):
        raise SystemExit("render ref failed")
    if not renderer.render_svg_to_png(cmp_svg, png_cmp, dpi=dpi):
        raise SystemExit("render cmp failed")
    ok, info = comparator.compare_images_pixel_perfect(
        png_ref, png_cmp, tolerance=0.0, pixel_tolerance=0.0
    )
    return ok, info


def main():
    ap = argparse.ArgumentParser(
        prog="t2p_text_flow_test",
        description="Extract a text element by id, convert with t2p_convert, render both, and diff PNGs.",
        epilog="Example: t2p_text_flow_test --svg samples/test_text_to_path_advanced.svg --id text44 --work /tmp/flow",
    )
    ap.add_argument("--svg", required=True, type=Path, help="Source SVG file")
    ap.add_argument("--id", required=True, help="text element id to extract and test")
    ap.add_argument("--work", type=Path, default=None, help="Work directory (default: mktemp)")
    ap.add_argument("--precision", type=int, default=6, help="Precision for t2p_convert")
    ap.add_argument("--annotate-only", action="store_true", help="Only extract element; skip convert/compare")
    args = ap.parse_args()

    workdir = args.work or Path(tempfile.mkdtemp(prefix="flowtest_"))
    workdir.mkdir(parents=True, exist_ok=True)

    single, converted = extract_text(args.svg, args.id, workdir)
    if args.annotate_only:
        print(f"Extracted {single}")
        return
    run_converter(single, converted, precision=args.precision)
    ok, info = compare(single, converted, workdir)

    diff_pct = info.get("diff_percentage", 0.0)
    print(f"Diff for {args.id}: {diff_pct:.4f}% (pixels {info.get('diff_pixels')})")
    print(f"PNGs: {workdir}")

if __name__ == "__main__":
    main()
