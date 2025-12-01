#!/usr/bin/env python3
"""
Automate text51 iteration packaging with and without manual patches.

Creates a timestamped iteration directory under samples/TEXT51_INVESTIGATION:
ITERATION_XXXX_<timestamp>/
  SVG-PAIR-A/            # original + freshly converted
  SVG-PAIR-B/            # original (unchanged) + patched converted (stroke-width, stroke color)
  COMPARISONS/
    SVG-PAIR-A-DIFF/     # png renders, diff png, json, html
    SVG-PAIR-B-DIFF/     # png renders, diff png, json, html

Requires: node, SVG-BBOX tools, text2path installed (this repo).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
import tempfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
INVEST_DIR = ROOT / "samples" / "TEXT51_INVESTIGATION"
BASE_INPUT = INVEST_DIR / "text51.svg"
PRECISION = "6"
THRESHOLD = "20"  # pixel threshold (20/256) to smooth AA diffs


def _next_iteration_dir() -> Path:
    existing = sorted(
        p for p in INVEST_DIR.iterdir() if p.is_dir() and p.name.startswith("ITERATION_")
    )
    next_idx = 1
    if existing:
        last = existing[-1].name.split("_", 2)[1]
        try:
            next_idx = int(last) + 1
        except Exception:
            next_idx = len(existing) + 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return INVEST_DIR / f"ITERATION_{next_idx:04d}_{ts}"


def _run(cmd: list[str], cwd: Path | None = None, capture_json: Path | None = None) -> None:
    res = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=bool(capture_json),
        check=True,
    )
    if capture_json is not None:
        capture_json.write_text(res.stdout or "{}")


def _convert_to_paths(src: Path, dst: Path) -> None:
    cmd = [
        "python",
        "-m",
        "text2path.main",
        str(src),
        str(dst),
        "--precision",
        PRECISION,
    ]
    _run(cmd, cwd=ROOT)


def _patch_converted_stroke_and_fill(src: Path, dst: Path) -> None:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    tree = ET.parse(src)
    root = tree.getroot()
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag != "path":
            continue
        style_val = elem.attrib.get("style", "")
        fill_val = elem.attrib.get("fill")
        if style_val:
            # Drop stroke-width (and fill) from style while keeping other font metadata.
            parts = []
            for part in style_val.split(";"):
                if ":" not in part:
                    continue
                k, v = (piece.strip() for piece in part.split(":", 1))
                if k == "stroke-width":
                    continue
                if k == "fill":
                    fill_val = v
                    continue
                parts.append(f"{k}:{v}")
            new_style = ";".join(parts)
            if new_style:
                elem.set("style", new_style)
            elif "style" in elem.attrib:
                del elem.attrib["style"]
        elem.set("stroke-width", "0.23px")
        elem.set("stroke", "#000080")
        if fill_val:
            elem.set("fill", fill_val)
        else:
            elem.set("fill", "#000080")
    tree.write(dst, encoding="utf-8", xml_declaration=True)


def _render_png(svg: Path, png: Path) -> None:
    cmd = [
        "node",
        str(ROOT / "SVG-BBOX" / "sbb-svg2png.cjs"),
        str(svg),
        str(png),
    ]
    _run(cmd, cwd=ROOT)


def _compare(svg1: Path, svg2: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    diff_png = out_dir / "diff.png"
    json_out = out_dir / "result.json"
    html_name = f"{svg1.stem}_vs_{svg2.stem}_comparison.html"
    html_path_root = ROOT / html_name

    comparer = ROOT / "SVG-BBOX" / "sbb-comparer.cjs"

    # JSON run (no HTML)
    json_cmd = [
        "node",
        str(comparer),
        str(svg1),
        str(svg2),
        "--out-diff",
        str(diff_png),
        "--threshold",
        THRESHOLD,
        "--scale",
        "4",
        "--json",
    ]
    _run(json_cmd, cwd=ROOT, capture_json=json_out)

    # HTML run (auto-opens Chrome via comparer)
    html_cmd = [
        "node",
        str(comparer),
        str(svg1),
        str(svg2),
        "--out-diff",
        str(diff_png),
        "--threshold",
        THRESHOLD,
        "--scale",
        "4",
    ]
    # Stub out "open" to prevent browser pop-up while still generating HTML
    with tempfile.TemporaryDirectory() as tmpd:
        stub = Path(tmpd) / "open"
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
        env = dict(**{"PATH": f"{tmpd}:{Path().cwd()}/venv/bin:{Path().cwd()}/bin:{Path().cwd()}"}, **{})
        env.update(**{k: v for k, v in os.environ.items()})
        env["PATH"] = f"{tmpd}:{env.get('PATH','')}"
        subprocess.run(html_cmd, cwd=ROOT, env=env, check=True)

    # Move HTML report into the comparison folder if generated
    if html_path_root.exists():
        shutil.move(str(html_path_root), str(out_dir / html_name))


def main() -> None:
    if not BASE_INPUT.exists():
        raise SystemExit(f"Input SVG not found: {BASE_INPUT}")

    iter_dir = _next_iteration_dir()
    pair_a = iter_dir / "SVG-PAIR-A"
    pair_b = iter_dir / "SVG-PAIR-B"
    comp_dir = iter_dir / "COMPARISONS"
    pair_a_diff = comp_dir / "SVG-PAIR-A-DIFF"
    pair_b_diff = comp_dir / "SVG-PAIR-B-DIFF"

    pair_a.mkdir(parents=True, exist_ok=True)
    pair_b.mkdir(parents=True, exist_ok=True)
    comp_dir.mkdir(parents=True, exist_ok=True)

    # Pair A: original + fresh conversion
    orig_a = pair_a / "text51_original.svg"
    conv_a = pair_a / "text51_converted.svg"
    shutil.copyfile(BASE_INPUT, orig_a)
    _convert_to_paths(orig_a, conv_a)

    # Pair B: monkey-patched versions
    orig_b = pair_b / "text51_original_patched.svg"
    conv_b = pair_b / "text51_converted_patched.svg"
    shutil.copyfile(orig_a, orig_b)
    _patch_converted_stroke_and_fill(conv_a, conv_b)

    # Render PNGs for both pairs
    _render_png(orig_a, pair_a / "text51_original.png")
    _render_png(conv_a, pair_a / "text51_converted.png")
    _render_png(orig_b, pair_b / "text51_original_patched.png")
    _render_png(conv_b, pair_b / "text51_converted_patched.png")

    # Comparisons
    _compare(orig_a, conv_a, pair_a_diff)
    _compare(orig_b, conv_b, pair_b_diff)

    print(f"\n✓ Iteration artifacts written to: {iter_dir}")


if __name__ == "__main__":
    main()
