#!/usr/bin/env python3
"""
Fast batch compare with font cache reuse.
- Loads FontCache once; converts all text*.svg (skips text4.svg by default).
- Uses sbb-comparer --batch for one Chromium session.
- First run may take ~2-3 min; subsequent runs are much faster (<1 min) thanks to warm font cache.
"""

import argparse
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# Import converter components
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import convert_svg_text_to_paths, apply_visual_correction  # type: ignore
from main import FontCache  # type: ignore


def convert_worker(payload: tuple[str, str, int, bool, bool]) -> tuple[str, str]:
    """Convert a single SVG to paths (optionally apply correction)."""
    svg_path, out_dir, precision, no_correction, verbose = payload
    svg = Path(svg_path)
    out_svg = Path(out_dir) / f"{svg.stem}_conv.svg"
    font_cache = FontCache()
    if verbose:
        convert_svg_text_to_paths(svg, out_svg, precision=precision, font_cache=font_cache)
        if not no_correction:
            apply_visual_correction(svg, out_svg)
    else:
        with open(os.devnull, "w") as devnull, redirect_stdout(devnull), redirect_stderr(devnull):
            convert_svg_text_to_paths(svg, out_svg, precision=precision, font_cache=font_cache)
            if not no_correction:
                apply_visual_correction(svg, out_svg)
    return (str(svg), str(out_svg))


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run(cmd, timeout=None, stdout=None):
    subprocess.run(cmd, check=True, stdout=stdout, timeout=timeout)


def main():
    p = argparse.ArgumentParser(description="Fast batch with cached fonts")
    p.add_argument("--out-dir", default="tmp/fast_cached", help="Output directory")
    p.add_argument("--threshold", type=int, default=20)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--resolution", default="nominal")
    p.add_argument("--skip", nargs="*", default=["text4.svg"], help="Files to skip")
    p.add_argument("--precision", type=int, default=3, help="Path precision for converter")
    p.add_argument(
        "--verbose", action="store_true", help="Show converter output (default: quiet)"
    )
    p.add_argument(
        "--no-correction",
        action="store_true",
        help="Skip bbox-based visual correction to speed up batch runs.",
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of parallel conversion workers (default: 1). Use >1 with care (spawns additional font scans).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Recompute conversions even if cached output is newer than input.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-command timeout in seconds (applies to comparer). Default: 60.",
    )
    args = p.parse_args()

    root = repo_root()
    samples = root / "samples/reference_objects"
    out_dir = root / args.out_dir
    conv_dir = out_dir / "converted"
    out_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    svgs = [svg for svg in sorted(samples.glob("text*.svg")) if svg.name not in args.skip]

    # Always prewarm the font cache; if the on-disk cache was deleted, this rebuilds it once.
    fc = FontCache()
    count = fc.prewarm()
    note = " (partial scan)" if fc.cache_is_partial() else ""
    print(f"Font cache ready ({count} fonts indexed){note}")

    pairs: list[tuple[str, str]] = []
    if args.jobs and args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            job_payloads = [
                (str(svg), str(conv_dir), args.precision, args.no_correction, args.verbose)
                for svg in svgs
            ]
            future_map = {
                ex.submit(convert_worker, payload): payload[0] for payload in job_payloads
            }
            for fut in as_completed(future_map):
                res = fut.result()
                pairs.append(res)
                print(f"✓ converted {Path(res[0]).name}")
    else:
        font_cache = FontCache()
        for svg in svgs:
            out_svg = conv_dir / f"{svg.stem}_conv.svg"
            if not args.force and out_svg.exists() and out_svg.stat().st_mtime >= svg.stat().st_mtime:
                pairs.append((str(svg), str(out_svg)))
                print(f"⏩ cached {svg.name}")
                continue
            if args.verbose:
                convert_svg_text_to_paths(
                    svg, out_svg, precision=args.precision, font_cache=font_cache
                )
                if not args.no_correction:
                    apply_visual_correction(svg, out_svg)
            else:
                with open(os.devnull, "w") as devnull, redirect_stdout(devnull), redirect_stderr(devnull):
                    convert_svg_text_to_paths(
                        svg, out_svg, precision=args.precision, font_cache=font_cache
                    )
                    if not args.no_correction:
                        apply_visual_correction(svg, out_svg)
            pairs.append((str(svg), str(out_svg)))
            print(f"✓ converted {svg.name}")

    pairs_path = out_dir / "pairs.txt"
    pairs_path.write_text("\n".join("\t".join(p) for p in pairs))

    summary_path = out_dir / "summary.json"
    cmd = [
        "node", str(root / "SVG-BBOX/sbb-comparer.cjs"),
        "--batch", str(pairs_path),
        "--threshold", str(args.threshold),
        "--scale", str(args.scale),
        "--resolution", args.resolution,
        "--json",
    ]
    with summary_path.open("w") as f:
        run(cmd, stdout=f, timeout=args.timeout)

    summary = json.loads(summary_path.read_text())
    failures = 0
    for r in summary.get("results", []):
        if r.get("error"):
            print(f"{Path(r.get('svg1','')).name},error,FAIL ({r.get('error')})")
            failures += 1
            continue
        diff = float(
            r.get("diffPercent")
            or r.get("diffPercentage")
            or r.get("diff")
            or 0
        )
        svg1 = r.get("a") or r.get("svg1") or ""
        status = "pass" if diff < 3 else "FAIL"
        print(f"{Path(svg1).name},{diff:.2f},{status}")
        if status == "FAIL":
            failures += 1
    print(f"Summary: {summary_path}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
