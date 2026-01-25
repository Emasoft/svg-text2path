import argparse
import re
from pathlib import Path

import defusedxml.ElementTree as ET


def get_bbox(svg_path: Path) -> None:
    tree = ET.parse(svg_path)
    root = tree.getroot()
    if root is None:
        print("Could not parse SVG root element")
        return
    ns = {"svg": "http://www.w3.org/2000/svg"}

    path = root.find(".//svg:path", ns)
    if path is None:
        print("No path found")
        return

    d = path.get("d")
    if d is None:
        print("Path element has no 'd' attribute")
        return

    # Simple regex to extract all numbers
    coords = [float(x) for x in re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", d)]

    # Group into pairs (this is a rough approximation,
    # assuming all commands use x,y pairs)
    # It works for M, L, but Q uses control points too.
    # However, we just want the min/max of ALL coordinates to get a rough bbox.

    xs = coords[0::2]
    ys = coords[1::2]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    print("Path BBox:")
    print(f"  X: {min_x:.2f} to {max_x:.2f} (Width: {max_x - min_x:.2f})")
    print(f"  Y: {min_y:.2f} to {max_y:.2f} (Height: {max_y - min_y:.2f})")

    # First point
    print(f"Start Point: ({xs[0]:.2f}, {ys[0]:.2f})")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="t2p_analyze_path",
        description="Compute rough bounding box for first <path> in SVG.",
        epilog="Example: t2p_analyze_path samples/test_text_to_path_advanced.svg",
    )
    parser.add_argument("svg", type=Path, help="SVG file containing a <path>")
    args = parser.parse_args()
    get_bbox(args.svg)


if __name__ == "__main__":
    main()
