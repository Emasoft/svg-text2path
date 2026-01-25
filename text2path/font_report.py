#!/usr/bin/env python3
"""
Font report generator for SVG texts.

Outputs a markdown table mapping text element id -> requested font
attributes -> resolved font file (using our fuzzy matcher).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import defusedxml.ElementTree as ET

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


def load_fontcache() -> Any:
    """Load and return a FontCache instance."""
    from text2path.main import FontCache

    return FontCache()  # type: ignore[no-untyped-call]


def parse_style(style_str: str | None) -> dict[str, str]:
    """Parse CSS style string into a dictionary."""
    if not style_str:
        return {}
    out: dict[str, str] = {}
    for part in style_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


FontRow = tuple[str, str | None, str | None, str | None, str | None, str, str]


def collect(
    svg_path: Path,
) -> list[FontRow]:
    """Collect font information from all text elements in an SVG file."""
    fc = load_fontcache()
    root = ET.parse(svg_path).getroot()
    keys = [
        "font-family",
        "font-weight",
        "font-style",
        "font-stretch",
        "font-variation-settings",
    ]
    inherit: dict[str, str | None] = {
        "font-family": "Arial",
        "font-weight": "400",
        "font-style": "normal",
        "font-stretch": "normal",
        "font-variation-settings": None,
    }
    rows: list[FontRow] = []
    auto = 0

    def walk(elem: Element, inherited: dict[str, str | None]) -> None:
        nonlocal auto
        attrs = dict(inherited)
        style_map = parse_style(elem.get("style", ""))
        for k in keys:
            if k in elem.attrib:
                attrs[k] = elem.get(k)
            elif k in style_map:
                attrs[k] = style_map[k]
        tag = elem.tag.split("}")[-1]
        if tag == "text":
            tid = elem.get("id")
            if not tid:
                auto += 1
                tid = f"text_auto_{auto}"
            fam = attrs["font-family"]
            fam = fam.split(",")[0].strip().strip("'\"") if fam else fam
            weight = attrs["font-weight"]
            style = attrs["font-style"]
            stretch = attrs["font-stretch"]
            var = attrs.get("font-variation-settings") or ""
            try:
                if weight == "bold":
                    w_int = 700
                elif weight == "normal":
                    w_int = 400
                else:
                    m = re.search(r"(\\d+)", weight or "")
                    w_int = int(m.group(1)) if m else 400
            except Exception:
                w_int = 400
            resolved = ""
            try:
                res = fc.get_font(
                    fam,
                    weight=w_int,
                    style=style,
                    stretch=stretch,
                    inkscape_spec=None,
                )
                if res:
                    resolved = Path(res[0].reader.file.name).name
            except Exception as e:
                resolved = f"err:{e}"
            rows.append((tid, fam, weight, style, stretch, var, resolved))
        for ch in elem:
            walk(ch, attrs)

    if root is not None:
        walk(root, inherit)
    return rows


def main() -> None:
    """Main entry point for the font report CLI."""
    import argparse

    from svg_text2path.cli.utils.banner import print_banner

    ap = argparse.ArgumentParser(
        prog="t2p_font_report",
        description=(
            "Generate a markdown table of text element font "
            "attributes and the resolved font file."
        ),
        epilog=(
            "Example: t2p_font_report "
            "samples/test_text_to_path_advanced.svg -o font_report.md"
        ),
    )
    ap.add_argument("svg", type=Path, help="Input SVG file")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("font_report.md"),
        help="Output markdown file (default: font_report.md)",
    )
    ap.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress banner and non-error output.",
    )
    args = ap.parse_args()

    # Print banner unless in quiet mode (force=True for CLI invocation)
    if not args.quiet:
        print_banner(force=True)
    rows = collect(args.svg)
    lines: list[str] = []
    header = (
        "| id | font-family | weight | style | stretch | variation | resolved file |"
    )
    lines.append(header)
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    args.out.write_text("\\n".join(lines))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
