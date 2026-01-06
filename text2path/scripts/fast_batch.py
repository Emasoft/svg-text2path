#!/usr/bin/env python3
"""
Fast cross-platform batch compare of text*.svg reference samples.

Targets: <1 minute, <5 GB by using scale=1, resolution=nominal
and a single sbb-compare batch.
Skips text4.svg by default (known fail).
Prints CSV lines and writes JSON summary.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def find_repo_root() -> Path:
    # scripts/fast_batch.py is in repo/text2path/scripts -> parents[2] is repo root
    return Path(__file__).resolve().parents[2]


def run(cmd, timeout=None, stdout=None):
    subprocess.run(cmd, check=True, timeout=timeout, stdout=stdout)


def main():
    parser = argparse.ArgumentParser(description="Fast batch text*.svg compare")
    parser.add_argument("--out-dir", default="tmp/fast_run", help="Output directory")
    parser.add_argument("--threshold", type=int, default=20)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--resolution", default="nominal")
    parser.add_argument(
        "--skip", nargs="*", default=["text4.svg"], help="Files to skip"
    )
    parser.add_argument(
        "--timeout", type=int, default=20, help="Per-command timeout seconds"
    )
    args = parser.parse_args()

    root = find_repo_root()
    samples = root / "samples/reference_objects"
    out_dir = root / args.out_dir
    conv_dir = out_dir / "converted"
    out_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    pairs = []
    for svg in sorted(samples.glob("text*.svg")):
        if svg.name in args.skip:
            continue
        out_svg = conv_dir / f"{svg.stem}_conv.svg"
        run(
            [
                sys.executable,
                str(root / "text2path/main.py"),
                str(svg),
                str(out_svg),
                "--no-html",
            ],
            timeout=args.timeout,
        )
        pairs.append({"a": str(svg), "b": str(out_svg)})

    pairs_path = out_dir / "pairs.json"
    pairs_path.write_text(json.dumps(pairs))

    summary_path = out_dir / "summary.json"
    # Use npx to run sbb-compare from npm svg-bbox package
    cmd = [
        "npx",
        "sbb-compare",
        "--batch",
        str(pairs_path),
        "--threshold",
        str(args.threshold),
        "--scale",
        str(args.scale),
        "--resolution",
        args.resolution,
        "--json",
    ]
    with summary_path.open("w") as f:
        run(cmd, timeout=args.timeout * max(1, len(pairs)), stdout=f)

    summary = json.loads(summary_path.read_text())
    failures = 0
    for r in summary.get("results", []):
        diff = float(r.get("diffPercent") or r.get("diff") or 0)
        status = "pass" if diff < 3 else "FAIL"
        print(f"{Path(r['a']).name},{diff:.2f},{status}")
        if status == "FAIL":
            failures += 1
    print(f"Summary: {summary_path}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
