#!/usr/bin/env python3
"""
Regression checker for text2path conversions.

Workflow:
1) Convert all text*.svg samples to paths (cached fonts).
2) Compare originals vs converted with sbb-comparer.cjs.
3) Append results to a registry JSON file with timestamp.
4) Detect regressions by comparing against the previous entry; if any diff worsens,
   print a warning.

Defaults mirror our recent comparison settings:
- threshold=20
- resolution=viewbox
- scale=4
- precision=3
- no visual correction
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import (  # type: ignore
    FontCache,
    apply_visual_correction,
    convert_svg_text_to_paths,
)

_SBB_RESOLUTION_MODES = {"nominal", "viewbox", "full", "scale", "stretch", "clip"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_cmd(cmd: list[str], timeout: int | None = None, stdout=None):
    subprocess.run(cmd, check=True, timeout=timeout, stdout=stdout)


def main():
    p = argparse.ArgumentParser(description="Run text2path regression check")
    p.add_argument(
        "--samples-dir",
        default="samples/reference_objects",
        help="Directory containing text*.svg samples (default: samples/reference_objects)",
    )
    p.add_argument(
        "--out-dir",
        default="tmp/regression_check",
        help="Base output directory for converted files and summaries",
    )
    p.add_argument("--precision", type=int, default=3)
    p.add_argument("--threshold", type=int, default=20)
    p.add_argument(
        "--scale",
        type=float,
        default=4.0,
        help="Render scale multiplier passed to sbb-comparer (default: 4).",
    )
    p.add_argument(
        "--resolution",
        default="viewbox",
        help="Resolution mode passed to sbb-comparer (default: viewbox).",
    )
    p.add_argument(
        "--apply-correction",
        action="store_true",
        help="Apply visual correction after conversion (default: off)",
    )
    p.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Filenames to skip (e.g., text4.svg).",
    )
    p.add_argument(
        "--include-paths",
        action="store_true",
        help="Also include already-paths samples like text2-paths.svg (default: off).",
    )
    p.add_argument(
        "--registry",
        default="tmp/regression_history.json",
        help="Path to regression history registry JSON file.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Comparer timeout in seconds (default: 300).",
    )
    args = p.parse_args()
    # Back-compat / convenience: accept --resolution like "4x" (meaning scale=4, resolution=viewbox)
    if isinstance(args.resolution, str) and args.resolution.lower().endswith("x"):
        try:
            parsed_scale = float(args.resolution[:-1])
            if parsed_scale > 0:
                args.scale = parsed_scale
                args.resolution = "viewbox"
        except Exception:
            pass
    if args.resolution not in _SBB_RESOLUTION_MODES:
        raise SystemExit(
            f"Invalid --resolution '{args.resolution}'. Expected one of: {', '.join(sorted(_SBB_RESOLUTION_MODES))}"
        )

    root = repo_root()
    samples_dir = (root / args.samples_dir).resolve()
    out_base = (root / args.out_dir).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_base / timestamp
    conv_dir = run_dir / "converted"
    run_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    svgs = [
        p
        for p in sorted(samples_dir.glob("text*.svg"))
        if p.name not in set(args.skip) and (args.include_paths or "-paths" not in p.name)
    ]
    if not svgs:
        print("No text*.svg files found; nothing to do.")
        return

    # Warm font cache
    fc = FontCache()
    count = fc.prewarm()
    print(f"Font cache ready ({count} fonts indexed)")

    pairs = []
    failures: list[tuple[str, str]] = []
    for svg in svgs:
        out_svg = conv_dir / f"{svg.stem}_conv.svg"
        try:
            convert_svg_text_to_paths(
                svg, out_svg, precision=args.precision, font_cache=fc
            )
            if args.apply_correction:
                apply_visual_correction(svg, out_svg)
            pairs.append((str(svg), str(out_svg)))
            print(f"✓ converted {svg.name}")
        except SystemExit as e:
            failures.append((svg.name, f"SystemExit {e.code}"))
            print(f"✗ convert failed {svg.name}: SystemExit {e.code}")
            continue
        except Exception as e:
            failures.append((svg.name, str(e)))
            print(f"✗ convert failed {svg.name}: {e}")

    pairs_path = run_dir / "pairs.txt"
    pairs_path.write_text("\n".join("\t".join(p) for p in pairs))

    summary_path = run_dir / "summary.json"
    comparer_cmd = [
        "node",
        str(root / "SVG-BBOX/sbb-comparer.cjs"),
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
    print("Running comparer...")
    with summary_path.open("w") as f:
        run_cmd(comparer_cmd, timeout=args.timeout, stdout=f)
    summary = json.loads(summary_path.read_text())

    # Build current result map
    result_map: dict[str, float] = {}
    for r in summary.get("results", []):
        diff = r.get("diffPercent") or r.get("diffPercentage") or r.get("diff")
        svg1 = r.get("a") or r.get("svg1") or ""
        name = Path(svg1).name
        if diff is not None:
            result_map[name] = float(diff)

    # Load registry
    registry_path = (root / args.registry).resolve()
    registry: list[dict] = []
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text())
        except Exception:
            registry = []

    # Only compare against the most recent entry with identical settings.
    prev_entry = None
    for entry in reversed(registry):
        if (
            entry.get("threshold") == args.threshold
            and entry.get("scale") == args.scale
            and entry.get("resolution") == args.resolution
            and entry.get("precision") == args.precision
            and bool(entry.get("apply_correction")) == bool(args.apply_correction)
        ):
            prev_entry = entry
            break
    regressions = []
    if prev_entry and "results" in prev_entry:
        prev_results = prev_entry["results"]
        for name, diff in result_map.items():
            if name in prev_results and diff > prev_results[name]:
                regressions.append((name, prev_results[name], diff))

    # Append current run to registry
    registry.append(
        {
            "timestamp": timestamp,
            "threshold": args.threshold,
            "scale": args.scale,
            "resolution": args.resolution,
            "precision": args.precision,
            "apply_correction": args.apply_correction,
            "results": result_map,
            "failures": failures,
        }
    )
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2))

    if regressions:
        print("WARNING: regression found. Please revert the latest changes to the code")
        for name, old, new in regressions:
            print(f"  {name}: {old:.2f}% -> {new:.2f}%")
    else:
        print("No regression detected.")


if __name__ == "__main__":
    main()
