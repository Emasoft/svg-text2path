#!/usr/bin/env python3
"""
Generate an HTML font report for an SVG.

Columns alternate original SVG font properties (even) and
properties read from the resolved font file (odd).

Rules:
  - Compare family exact, style exact, stretch exact
    except widthClass 5 -> 'normal'.
  - Weight is shown but not compared.
  - If SVG variation empty, ignore font axes (show n.a.).
Each row shows emojis on each pair and a GPT5 verdict SAME/DIFFERENT.
Adds a final summary row with SAME/total.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import (
    Element,  # For type hints (defusedxml doesn't export Element)
)

import defusedxml.ElementTree as ET  # type: ignore[import-untyped]

import text2path.main as main_module

if TYPE_CHECKING:
    from types import ModuleType


def load_main() -> ModuleType:
    """Load the main module."""
    return main_module


def parse_style(style_str: str) -> dict[str, str]:
    """Parse CSS style string into key-value pairs."""
    if not style_str:
        return {}
    out: dict[str, str] = {}
    for part in style_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def extract_font_info(font_path: Path | None) -> dict[str, str]:
    """Extract font metadata from a font file."""
    from fontTools.ttLib import TTFont  # type: ignore[import-untyped]

    info: dict[str, str] = {
        "family": "n.a.",
        "subfamily": "n.a.",
        "weight": "n.a.",
        "stretch": "n.a.",
        "variation": "n.a.",
    }
    if not font_path or not font_path.exists():
        return info
    try:
        tt = TTFont(font_path, lazy=True, fontNumber=0)
        name = tt["name"]

        def _get(nid: int) -> str | None:
            for rec in name.names:
                if rec.nameID == nid:
                    try:
                        return str(rec.toUnicode())
                    except Exception:
                        return str(rec.string, errors="ignore")
            return None

        fam = _get(16) or _get(1)
        sub = _get(17) or _get(2)
        if fam:
            info["family"] = fam
        if sub:
            info["subfamily"] = sub
        if "OS/2" in tt:
            os2 = tt["OS/2"]
            if hasattr(os2, "usWeightClass"):
                info["weight"] = str(os2.usWeightClass)
            if hasattr(os2, "usWidthClass"):
                info["stretch"] = str(os2.usWidthClass)
        if "fvar" in tt:
            axes = [a.axisTag for a in tt["fvar"].axes]
            info["variation"] = ",".join(axes) if axes else "n.a."
    except Exception:
        pass
    return info


def normalize_stretch(val: str | None) -> str:
    """Normalize stretch value for comparison."""
    if val is None or val in ("n.a.", ""):
        return "n.a."
    try:
        if int(val) == 5:
            return "normal"
    except (ValueError, TypeError):
        pass
    return val


def generate(svg_path: Path, out_html: Path) -> Path:
    """Generate the HTML font report."""
    loaded_main = load_main()
    FontCache = loaded_main.FontCache
    fc = FontCache()

    keys = [
        "font-family",
        "font-weight",
        "font-style",
        "font-stretch",
        "font-variation-settings",
    ]
    inherit: dict[str, str] = {
        "font-family": "Arial",
        "font-weight": "400",
        "font-style": "normal",
        "font-stretch": "normal",
        "font-variation-settings": "",
    }
    rows: list[dict[str, Any]] = []
    auto = 0

    def walk(elem: Element, inherited: dict[str, str]) -> None:
        nonlocal auto
        attrs = dict(inherited)
        style_map = parse_style(elem.get("style", ""))
        for k in keys:
            if k in elem.attrib:
                attrs[k] = elem.get(k) or ""
            elif k in style_map:
                attrs[k] = style_map[k]
        tag = elem.tag.split("}")[-1]
        if tag == "text":
            tid = elem.get("id") or f"text_auto_{auto + 1}"
            if not elem.get("id"):
                auto += 1
            fam_raw = attrs["font-family"]
            fam = fam_raw.split(",")[0].strip().strip("'\"") if fam_raw else "n.a."
            weight = attrs["font-weight"]
            style = attrs["font-style"]
            stretch = attrs["font-stretch"]
            var = attrs.get("font-variation-settings", "")
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
            resolved_path: Path | None = None
            resolved_name = "n.a."
            try:
                res = fc.get_font(
                    fam,
                    weight=w_int,
                    style=style,
                    stretch=stretch,
                    inkscape_spec=None,
                )
                if res:
                    resolved_path = Path(res[0].reader.file.name)
                    resolved_name = resolved_path.name
            except Exception:
                pass
            rows.append(
                {
                    "id": tid,
                    "orig_family": fam or "n.a.",
                    "orig_weight": weight or "n.a.",
                    "orig_style": style or "n.a.",
                    "orig_stretch": stretch or "n.a.",
                    "orig_var": var or "n.a.",
                    "resolved_path": resolved_path,
                    "resolved_file": resolved_name,
                }
            )
        for ch in elem:
            walk(ch, attrs)

    tree = ET.parse(svg_path)
    root = tree.getroot()
    if root is None:
        msg = f"Could not parse SVG: {svg_path}"
        raise ValueError(msg)
    walk(root, inherit)

    html_rows: list[str] = []
    same_count = 0
    total = len(rows)
    for r in rows:
        resolved = r["resolved_path"]
        font_info = extract_font_info(resolved)
        orig_var_val: str = r["orig_var"]
        font_var = font_info["variation"] if orig_var_val.strip() else "n.a."

        def canonical_style(subfamily: str) -> str:
            if not subfamily or subfamily == "n.a.":
                return "n.a."
            s = subfamily.lower()
            if s in ("regular", "plain"):
                return "normal"
            if "italic" in s:
                return "italic"
            if "oblique" in s:
                return "oblique"
            return "normal"

        # per-field equality flags
        orig_family: str = r["orig_family"]
        orig_style: str = r["orig_style"]
        orig_stretch: str = r["orig_stretch"]

        eq_family = orig_family == font_info["family"]
        eq_style = orig_style == canonical_style(font_info["subfamily"])
        eq_stretch = normalize_stretch(orig_stretch) == normalize_stretch(
            font_info["stretch"]
        )
        eq_var = (orig_var_val == font_var) or (
            orig_var_val.strip() == "" and font_var == "n.a."
        )

        auto_same = eq_family and eq_style and eq_stretch and eq_var
        if auto_same:
            same_count += 1

        def mark(val: str, ok: bool) -> str:
            emoji = "\u2705" if ok else "\u2754"
            return f"{val} {emoji}"

        if auto_same:
            verdict = '<span style="color:green;font-weight:bold">SAME</span>'
        else:
            verdict = '<span style="color:red;font-weight:bold">DIFFERENT</span>'

        orig_fam = orig_family
        font_fam = mark(font_info["family"], eq_family)
        orig_wt: str = r["orig_weight"]
        font_wt = font_info["weight"]
        orig_st = orig_style
        font_st = mark(font_info["subfamily"], eq_style)
        orig_str = orig_stretch
        font_str = mark(normalize_stretch(font_info["stretch"]), eq_stretch)
        orig_v = orig_var_val
        font_v = mark(font_var, eq_var)
        res_file: str = r["resolved_file"]
        row_id: str = r["id"]

        html_rows.append(f"""
        <tr>
          <td class="id">{row_id}</td>
          <td class="even">{orig_fam}</td><td class="odd">{font_fam}</td>
          <td class="even">{orig_wt}</td><td class="odd">{font_wt}</td>
          <td class="even">{orig_st}</td><td class="odd">{font_st}</td>
          <td class="even">{orig_str}</td><td class="odd">{font_str}</td>
          <td class="even">{orig_v}</td><td class="odd">{font_v}</td>
          <td class="verdict">{verdict}</td>
          <td class="user">\u2014</td>
          <td class="file">{res_file}</td>
        </tr>""")

    summary_text = f"GPT5 verdict: {same_count}/{total}"
    summary = (
        f"<tr class='summary'><td class='id'>TOTAL</td>"
        f"<td colspan='10' class='even'>{summary_text}</td>"
        f"<td class='verdict'></td><td class='user'></td>"
        f"<td class='file'></td></tr>"
    )

    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; font-size: 14px; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 4px 6px; }}
th {{ background: #444; color: #fff; }}
td.even {{ background: #eef5ff; }}
td.odd  {{ background: #f8f1e5; }}
td.id   {{ background: #ffd27f; font-weight: bold; }}
td.file {{ background: #d9ffd9; font-weight: bold; }}
td.verdict {{ text-align:center; }}
td.user {{ background:#fff8cc; }}
</style>
</head><body>
<h2>Font Resolution Report</h2>
<table>
<tr>
  <th>id</th>
  <th>orig family</th><th>font family</th>
  <th>orig weight</th><th>font weight</th>
  <th>orig style</th><th>font style</th>
  <th>orig stretch</th><th>font stretch</th>
  <th>orig variation</th><th>font variation</th>
  <th>GPT5 verdict</th>
  <th>User verdict</th>
  <th>resolved file</th>
</tr>
{"".join(html_rows)}
{summary}
</table>
</body></html>"""

    out_html.write_text(html)
    return out_html


def main() -> None:
    """CLI entry point."""
    import argparse

    ap = argparse.ArgumentParser(
        prog="t2p_font_report_html",
        description=(
            "Generate an HTML font mapping report for an SVG "
            "(orig values vs resolved font file values)."
        ),
        epilog=(
            "Example: t2p_font_report_html "
            "samples/test_text_to_path_advanced.svg -o report.html"
        ),
    )
    ap.add_argument("svg", type=Path, help="Input SVG file")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("/tmp/font_report.html"),
        help="Output HTML file",
    )
    ap.add_argument(
        "--open",
        action="store_true",
        help="Open the HTML in Chrome after generation",
    )
    args = ap.parse_args()
    out = generate(args.svg, args.out)
    print(f"Wrote {out}")
    if args.open:
        with contextlib.suppress(Exception):
            subprocess.run(["open", "-a", "Google Chrome", str(out)], check=False)


if __name__ == "__main__":
    main()
