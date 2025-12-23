#!/usr/bin/env python3
"""
Text-to-Path Converter V4

Key features:
- Unicode BiDi support for RTL text (Arabic, Hebrew)
- HarfBuzz text shaping for proper ligatures and contextual forms
- Visual run processing like the Rust version
- Transform attribute handling to avoid rendering differences
"""

import xml.etree.ElementTree as ET
from pathlib import Path
import sys
import re
import math
import os
import json
import subprocess
import uuid
from dataclasses import dataclass
import tempfile
import shutil
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Logging setup --------------------------------------------------------
LOG = logging.getLogger("t2p")
DEBUG_ENABLED = False


def setup_logging(debug: bool = False, log_dir: Path | str | None = None):
    """Configure centralized logging with rotation and optional debug verbosity."""
    global DEBUG_ENABLED
    DEBUG_ENABLED = debug
    level = logging.DEBUG if debug else logging.INFO
    LOG.setLevel(level)

    # Clear old handlers to allow reconfiguration
    for h in list(LOG.handlers):
        LOG.removeHandler(h)

    fmt = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(fmt, datefmt))
    LOG.addHandler(ch)

    # File handler with rotation
    log_root = Path(log_dir) if log_dir else Path("logs")
    log_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    log_file = log_root / f"text2path_{stamp}.log"
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(fmt, datefmt))
    LOG.addHandler(fh)

    LOG.debug("Logging initialized. Debug=%s log_file=%s", debug, log_file)


def dbg(msg: str, *args):
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug(msg, *args)


# Initialize default logging once on import (INFO level, console+rotating file)
if not LOG.handlers:
    setup_logging(debug=False)

try:
    from svg.path import parse_path
except ImportError:
    print("Error: svg.path is required. Install with:")
    print("  pip install svg.path")
    sys.exit(1)


def _set_font_family(elem: ET.Element, family: str, weight: int | None = None):
    """Update font-family/inkscape spec (and optionally font-weight/variations) on an element."""
    style = elem.get("style", "")
    # Replace font-family
    style = re.sub(r"font-family:[^;]+", f"font-family:'{family}'", style)
    style = re.sub(
        r"-inkscape-font-specification:[^;]+",
        f"-inkscape-font-specification:'{family}'",
        style,
    )
    if weight:
        style = re.sub(r"font-weight:[^;]+", f"font-weight:{weight}", style)
        # inject/replace wght variation
        if "font-variation-settings" in style:
            style = re.sub(
                r"font-variation-settings:[^;]+",
                f"font-variation-settings:'wght' {weight}",
                style,
            )
        else:
            style += f";font-variation-settings:'wght' {weight}"
        elem.set("font-weight", str(weight))
    elem.set("style", style)
    elem.set("font-family", family)
    elem.set("-inkscape-font-specification", family)


def parse_svg_transform(transform_str):
    """Parse SVG transform attribute and return scale values."""
    if not transform_str:
        return (1.0, 1.0)

    # Parse scale(sx, sy) or scale(s)
    scale_match = re.search(
        r"scale\s*\(\s*([-+]?\d*\.?\d+)\s*(?:,\s*([-+]?\d*\.?\d+))?\s*\)", transform_str
    )
    if scale_match:
        sx = float(scale_match.group(1))
        sy = float(scale_match.group(2)) if scale_match.group(2) else sx
        return (sx, sy)

    # Parse matrix(a, b, c, d, e, f) - extract scale from a and d
    matrix_match = re.search(
        r"matrix\s*\(\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,",
        transform_str,
    )
    if matrix_match:
        a = float(matrix_match.group(1))  # x-scale
        d = float(matrix_match.group(4))  # y-scale
        return (a, d)

    return (1.0, 1.0)


def parse_transform_matrix(
    transform_str: str,
) -> tuple[float, float, float, float, float, float] | None:
    """Parse SVG transform list into a single affine matrix (a,b,c,d,e,f).

    Supports matrix(), translate(), scale(). Returns None if unsupported
    transforms (rotate/skew) are present.
    """
    if not transform_str:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def mat_mul(m1, m2):
        a1, b1, c1, d1, e1, f1 = m1
        a2, b2, c2, d2, e2, f2 = m2
        return (
            a1 * a2 + c1 * b2,
            b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2,
            b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1,
            b1 * e2 + d1 * f2 + f1,
        )

    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    # Simple parser left-to-right
    for part in re.finditer(r"(matrix|translate|scale)\s*\(([^)]*)\)", transform_str):
        kind = part.group(1)
        nums = [
            float(x)
            for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", part.group(2))
        ]
        if kind == "matrix" and len(nums) == 6:
            m = mat_mul(m, tuple(nums))
        elif kind == "translate" and len(nums) >= 1:
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            m = mat_mul(m, (1.0, 0.0, 0.0, 1.0, tx, ty))
        elif kind == "scale" and len(nums) >= 1:
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            m = mat_mul(m, (sx, 0.0, 0.0, sy, 0.0, 0.0))
        else:
            return None

    # If unsupported transforms appear (rotate/skew), bail out
    if re.search(r"rotate|skew", transform_str):
        return None

    return m


def apply_transform_to_path(path_d, scale_x, scale_y):
    """Apply scale transform to all coordinates in path data."""
    if scale_x == 1.0 and scale_y == 1.0:
        return path_d

    def scale_numbers(match):
        num = float(match.group(0))
        # Determine if this is an x or y coordinate based on position in string
        # This is approximate but works for our use case
        return f"{num:.2f}"

    # Split path into commands and coordinates
    result = []
    parts = re.split(r"([MLHVCSQTAZ])", path_d, flags=re.IGNORECASE)

    for i, part in enumerate(parts):
        if not part or part.isspace():
            continue

        if part.upper() in "MLHVCSQTAZ":
            result.append(part)
        else:
            # This is a coordinate string
            coords = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", part)]
            scaled = []
            for j, val in enumerate(coords):
                if j % 2 == 0:  # x coordinate
                    scaled.append(val * scale_x)
                else:  # y coordinate
                    scaled.append(val * scale_y)
            result.append(" ".join(f"{v:.2f}" for v in scaled))

    return " ".join(result)


def _mat_mul(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _mat_apply_pt(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _mat_scale_lengths(m):
    """Return average scale from matrix for length attributes."""
    a, b, c, d, e, f = m
    sx = (a * a + b * b) ** 0.5
    sy = (c * c + d * d) ** 0.5
    return (sx + sy) / 2.0 if (sx or sy) else 1.0


try:
    from fontTools.ttLib import TTFont, TTCollection
    from fontTools.pens.recordingPen import RecordingPen, DecomposingRecordingPen
    from fontTools.pens.svgPathPen import SVGPathPen
except ImportError:
    print("Error: fontTools is required. Install with:")
    print("  uv pip install fonttools")
    sys.exit(1)

try:
    from bidi.algorithm import get_display, get_embedding_levels
    import uharfbuzz as hb
except ImportError:
    print("Error: python-bidi and uharfbuzz are required. Install with:")
    print("  uv pip install python-bidi uharfbuzz")
    sys.exit(1)


@dataclass
class MissingFontError(Exception):
    family: str
    weight: int
    style: str
    stretch: str
    message: str


class FontCache:
    """Cache loaded fonts using fontconfig for proper font matching."""

    def __init__(self):
        self._fonts: dict[
            str, tuple[TTFont, bytes, int]
        ] = {}  # Cache: font_spec -> (TTFont, bytes, face_index)
        self._coverage_cache: dict[Path, set[int]] = {}

    def _parse_inkscape_spec(self, inkscape_spec: str) -> tuple[str, str | None]:
        """Parse Inkscape font specification like 'Futura, Medium' or '.New York, Italic'."""
        s = inkscape_spec.strip().strip("'\"")
        if "," in s:
            family, rest = s.split(",", 1)
            return family.strip(), rest.strip() or None
        else:
            return s, None

    def _weight_to_style(self, weight: int) -> str | None:
        """Map CSS font-weight to font style name.

        This is needed because some fonts (like Futura) use style names
        instead of numeric weights in fontconfig.
        """
        weight_map = {
            100: "Thin",
            200: "ExtraLight",
            300: "Light",
            400: "Regular",
            500: "Medium",
            600: "SemiBold",
            700: "Bold",
            800: "ExtraBold",
            900: "Black",
        }
        return weight_map.get(weight)

    _fc_cache: list[tuple[Path, list[str], list[str], str, int]] | None = None
    _cache_file: Path | None = None
    _cache_version: int = 3
    _prebaked: dict[str, list[dict]] | None = None
    _cache_partial: bool = False

    def _font_dirs(self) -> list[Path]:
        """Return platform-specific font directories."""
        dirs: list[Path] = []
        home = Path.home()
        if sys.platform == "darwin":
            dirs += [
                Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"),
                home / "Library" / "Fonts",
            ]
        elif sys.platform.startswith("linux"):
            dirs += [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                home / ".fonts",
                home / ".local" / "share" / "fonts",
            ]
        elif sys.platform.startswith("win"):
            windir = os.environ.get("WINDIR", r"C:\\Windows")
            dirs.append(Path(windir) / "Fonts")
        return [d for d in dirs if d.exists()]

    def _cache_path(self) -> Path:
        """Location for persistent font cache."""
        if self._cache_file:
            return self._cache_file
        env = os.environ.get("T2P_FONT_CACHE")
        if env:
            self._cache_file = Path(env)
        else:
            base = Path.home() / ".cache" / "text2path"
            base.mkdir(parents=True, exist_ok=True)
            self._cache_file = base / "font_cache.json"
        return self._cache_file

    def _load_persistent_cache(self) -> tuple[
        list[tuple[Path, list[str], list[str], str, int]], dict[str, list[dict]], bool
    ] | None:
        """Load cached font metadata if present and fresh."""
        cache_path = self._cache_path()
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text())
            if data.get("version") != self._cache_version:
                return None
            dirs_state = {
                d: int(Path(d).stat().st_mtime) if Path(d).exists() else 0
                for d in data.get("dirs", [])
            }
            for d in dirs_state:
                if not Path(d).exists() or int(Path(d).stat().st_mtime) != dirs_state[d]:
                    return None
            entries: list[tuple[Path, list[str], list[str], str, int]] = []
            for rec in data.get("fonts", []):
                p = Path(rec["path"])
                if not p.exists():
                    continue
                if int(p.stat().st_mtime) != rec.get("mtime"):
                    continue
                entries.append(
                    (
                        p,
                        [f.lower() for f in rec.get("families", [])],
                        [s.lower() for s in rec.get("styles", [])],
                        rec.get("ps", "").lower(),
                        int(rec.get("weight", 400)),
                    )
                )
            prebaked = data.get("prebaked", {})
            partial = bool(data.get("partial", False))
            if entries:
                return (entries, prebaked, partial)
        except Exception:
            return None
        return None

    def _spinner(self, message: str, stop_event: threading.Event):
        """Simple console spinner."""
        symbols = "|/-\\"
        idx = 0
        while not stop_event.is_set():
            sys.stdout.write(f"\r{message} {symbols[idx % len(symbols)]}")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.12)
        sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")
        sys.stdout.flush()

    def _read_font_meta(self, path: Path, need_flags: bool) -> tuple[Path, list[str], list[str], str, int, dict] | None:
        try:
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc", ".otc", ".woff2"}:
                return None
            tt = TTFont(path, lazy=True, fontNumber=0 if path.suffix.lower() != ".ttc" else None)
            names = tt["name"]
            fams = []
            for nid in (16, 1):
                nm = names.getName(nid, 3, 1) or names.getName(nid, 1, 0)
                if nm:
                    fams.append(nm.toUnicode().strip().lower())
            subfam = names.getName(2, 3, 1) or names.getName(2, 1, 0)
            styles = []
            if subfam:
                styles.append(subfam.toUnicode().strip().lower())
            ps = names.getName(6, 3, 1) or names.getName(6, 1, 0)
            psname = ps.toUnicode().strip().lower() if ps else ""
            weight = 400
            try:
                if "OS/2" in tt:
                    weight = int(tt["OS/2"].usWeightClass)
            except Exception:
                pass
            flags = {}
            if need_flags:
                # Light coverage flags (avoid loading later): basic Latin, Latin-1, CJK, RTL
                flags = {"latin": False, "latin1": False, "cjk": False, "rtl": False}
                try:
                    cmap = tt.getBestCmap() or {}
                    codes = set(cmap.keys())
                    flags["latin"] = any(0x0041 <= c <= 0x007A for c in codes)
                    flags["latin1"] = any(0x00A0 <= c <= 0x00FF for c in codes)
                    flags["rtl"] = any(0x0600 <= c <= 0x08FF for c in codes) or any(0x0590 <= c <= 0x05FF for c in codes)
                    flags["cjk"] = any(0x4E00 <= c <= 0x9FFF for c in codes) or any(0x3040 <= c <= 0x30FF for c in codes)
                except Exception:
                    pass
            return (path, fams, styles, psname, weight, flags)
        except Exception:
            return None

    def _build_cache_entries(self) -> tuple[list[tuple[Path, list[str], list[str], str, int]], dict[str, list[dict]], bool]:
        dirs = self._font_dirs()
        font_files: set[Path] = set()
        for d in dirs:
            if not d.exists():
                continue
            for ext in ("*.ttf", "*.otf", "*.ttc", "*.otc", "*.woff2"):
                font_files.update(d.rglob(ext))

        # Deduplicate by resolved path
        font_list = sorted({p.resolve() for p in font_files if p.exists()})

        entries: list[tuple[Path, list[str], list[str], str, int]] = []
        prebaked: dict[str, list[dict]] = {}
        prebake_fams = {
            "arial",
            "helvetica",
            "noto sans",
            "noto serif",
            "noto sans cjk",
            "noto serif cjk",
            "times new roman",
            "times",
            "georgia",
            "courier",
            "courier new",
            "dejavu sans",
            "dejavu serif",
            "dejavu sans mono",
            "apple color emoji",
            "symbol",
        }
        start = time.time()
        budget_seconds = 300  # hard cap ~5 minutes
        partial = False
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(self._read_font_meta, p, False): p for p in font_list}
            for fut in as_completed(futures):
                meta = fut.result()
                if meta:
                    path, fams, styles, ps, weight, _flags = meta
                    entries.append((path, fams, styles, ps, weight))
                    fam_set = set(fams) | ({ps} if ps else set())
                    if fam_set & prebake_fams:
                        prebake_key = list(fam_set & prebake_fams)[0]
                        # For prebake candidates, compute flags lazily now (may need to reopen)
                        flags = {}
                        try:
                            flags_meta = self._read_font_meta(path, True)
                            if flags_meta:
                                flags = flags_meta[-1]
                        except Exception:
                            pass
                        prebaked.setdefault(prebake_key, []).append(
                            {"path": str(path), "styles": styles, "ps": ps, "weight": weight, "flags": flags}
                        )
                if time.time() - start > budget_seconds:
                    partial = True
                    break
        return entries, prebaked, partial

    def _save_cache(
        self,
        entries: list[tuple[Path, list[str], list[str], str, int]],
        prebaked: dict[str, list[dict]],
        partial: bool,
    ) -> None:
        cache_path = self._cache_path()
        dirs = [str(d) for d in self._font_dirs()]
        payload = {
            "version": self._cache_version,
            "created_at": datetime.now().isoformat(),
            "dirs": dirs,
            "fonts": [
                {
                    "path": str(p),
                    "mtime": int(p.stat().st_mtime),
                    "families": fams,
                    "styles": styles,
                    "ps": ps,
                    "weight": weight,
                }
                for (p, fams, styles, ps, weight) in entries
            ],
            "prebaked": prebaked,
            "partial": partial,
        }
        try:
            cache_path.write_text(json.dumps(payload))
        except Exception as e:
            print(f"⚠️  Could not write font cache: {e}")

    def _load_fc_cache(self):
        """Load persistent font cache (cross-platform). Falls back to scanning once."""
        if self._fc_cache is not None:
            return

        cached = self._load_persistent_cache()
        if cached is not None:
            self._fc_cache, self._prebaked, self._cache_partial = cached
            return

        # Build cache with spinner notice (first run)
        msg = "The first time text2paths must build the font cache, and it can take up to 5 minutes. Please wait..."
        stop_evt = threading.Event()
        spinner_thread = threading.Thread(target=self._spinner, args=(msg, stop_evt))
        spinner_thread.daemon = True
        spinner_thread.start()
        start = time.time()
        try:
            entries, prebaked, partial = self._build_cache_entries()
            self._fc_cache = entries
            self._prebaked = prebaked
            self._cache_partial = partial
            self._save_cache(entries, prebaked, partial)
        finally:
            stop_evt.set()
            spinner_thread.join(timeout=0.5)
            elapsed = time.time() - start
            print(f"Font cache ready in {elapsed:.1f}s ({len(self._fc_cache or [])} fonts indexed).")

    def prewarm(self) -> int:
        """Ensure the font metadata cache is loaded, returning number of indexed fonts."""
        self._load_fc_cache()
        return len(self._fc_cache or [])

    def prebaked_candidates(self, family: str) -> list[dict]:
        """Return prebaked fallback records for a family name (case-insensitive)."""
        self._load_fc_cache()
        if not self._prebaked:
            return []
        key = family.strip().lower()
        return self._prebaked.get(key, [])

    def cache_is_partial(self) -> bool:
        self._load_fc_cache()
        return bool(self._cache_partial)

    def fonts_with_coverage(self, codepoints: set[int], limit: int | None = 15) -> list[str]:
        """Return font family names for installed fonts that cover at least one of the given codepoints (capped)."""
        self._load_fc_cache()
        found: list[str] = []
        seen_fams: set[str] = set()
        for path, fams, styles, ps, _weight in self._fc_cache:
            if limit and len(found) >= limit:
                break
            try:
                if path in self._coverage_cache:
                    cover = self._coverage_cache[path]
                else:
                    # Load first face to inspect cmap (lazy to reduce memory)
                    if path.suffix.lower() == ".ttc":
                        from fontTools.ttLib import TTCollection

                        coll = TTCollection(path, lazy=True)
                        tt = coll.fonts[0]
                    else:
                        tt = TTFont(path, lazy=True)
                    cmap = tt.getBestCmap() or {}
                    cover = set(cmap.keys())
                    self._coverage_cache[path] = cover
                if not (codepoints & cover):
                    continue
                fam = (fams[0] if fams else "") or ps or path.stem
                fam_norm = fam.strip()
                if not fam_norm or fam_norm in seen_fams:
                    continue
                seen_fams.add(fam_norm)
                found.append(fam_norm)
            except Exception:
                continue
        return found

    def _split_words(self, name: str) -> set[str]:
        """Split a font name into lowercase word tokens (camelCase, underscores, spaces)."""
        import re

        tokens = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
        tokens = tokens.replace("_", " ")
        parts = [p.strip().lower() for p in tokens.split() if p.strip()]
        return set(parts)

    def _style_weight_class(self, styles: list[str]) -> int:
        """Rough weight class from style tokens."""
        s = " ".join(styles)
        if any(tok in s for tok in ["black", "heavy", "ultra", "extra bold"]):
            return 800
        if "bold" in s:
            return 700
        if any(tok in s for tok in ["semi", "demi"]):
            return 600
        if any(tok in s for tok in ["light", "thin", "hair"]):
            return 300
        return 400

    def _style_slant(self, styles: list[str]) -> str:
        s = " ".join(styles)
        if "italic" in s or "oblique" in s:
            return "italic"
        return "normal"

    def _normalize_style_name(self, name: str) -> str:
        n = name.lower().strip()
        # Inkscape canonicalization
        n = n.replace("semi-light", "light")
        n = n.replace("book", "normal")
        n = n.replace("ultra-heavy", "heavy")
        # Treat Medium/Regular/Plain as Normal
        n = n.replace("medium", "normal")
        if n in ("regular", "plain", "roman"):
            n = "normal"
        return n

    def _style_token_set(self, style_str: str) -> set[str]:
        tokens = re.sub(r"([a-z])([A-Z])", r"\1 \2", style_str)
        tokens = tokens.replace("-", " ").replace("_", " ")
        parts = [self._normalize_style_name(p) for p in tokens.split() if p.strip()]
        # Drop neutral tokens that shouldn't block a match
        filtered = []
        for p in parts:
            if p in ("normal", "plain", "regular", "400", "500", "roman"):
                continue
            filtered.append(p)
        return set(filtered)

    def _style_match_score(
        self, style_str: str, target_weight: int, target_style: str, target_stretch: str
    ) -> float:
        """Score how well a face style matches the requested weight/style/stretch.

        Lower scores are better. This helps prefer Regular over Bold when the
        desired style tokens are empty (e.g., weight=400, style=normal).
        """
        weight_class = self._style_weight_class([style_str])
        weight_score = abs(target_weight - weight_class)

        slant = self._style_slant([style_str])
        slant_score = 0
        if target_style in ("italic", "oblique"):
            if slant not in ("italic", "oblique"):
                slant_score = 200
        else:
            if slant != "normal":
                slant_score = 200

        stretch_score = 0
        if target_stretch and target_stretch.lower() not in ("normal", ""):
            stretch_norm = target_stretch.lower().replace("-", "")
            tokens = self._style_token_set(style_str)
            if stretch_norm not in tokens:
                stretch_score = 50

        # Slight bias toward truly regular faces when nothing else is specified
        if (
            target_weight == 400
            and target_style == "normal"
            and style_str.strip().lower() in ("", "normal", "regular", "plain", "roman")
        ):
            weight_score -= 10

        return weight_score + slant_score + stretch_score

    def _build_style_label(
        self, weight: int, style: str, stretch: str = "normal"
    ) -> str:
        base = []
        # weight
        if weight >= 800:
            base.append("heavy")
        elif weight >= 700:
            base.append("bold")
        elif weight >= 600:
            base.append("semibold")
        elif weight >= 500:
            base.append("medium")
        elif weight <= 300:
            base.append("light")
        else:
            base.append("normal")
        # slant
        st = style.lower()
        if st in ("italic", "oblique"):
            base.append("italic")
        elif st not in ("normal", ""):
            base.append(st)
        # stretch
        if stretch and stretch.lower() not in ("normal", ""):
            base.append(stretch.lower())
        return " ".join(base)

    def _match_exact(
        self,
        font_family: str,
        weight: int,
        style: str,
        stretch: str,
        ps_hint: str | None,
    ) -> tuple[Path, int] | None:
        """Strict match: family must exist; weight/style must match token sets; no substitution.

        This version inspects TTC collections to pick the face whose style tokens
        best match the requested weight/style/stretch (prevents grabbing Regular
        when Condensed or other faces exist)."""
        self._load_fc_cache()
        fam_norm = font_family.strip().lower()
        ps_norm = ps_hint.strip().lower() if ps_hint else None
        desired_style_tokens = self._style_token_set(
            self._build_style_label(weight, style, stretch)
        )

        best_candidate: tuple[Path, str] | None = None
        best_score: float | None = None

        def pick_face(path: Path, preferred_style: str | None) -> tuple[Path, int] | None:
            try:
                if path.suffix.lower() == ".ttc":
                    from fontTools.ttLib import TTCollection

                    coll = TTCollection(path)
                    best_idx = 0
                    best_face_score: float | None = None
                    for idx, face in enumerate(coll.fonts):
                        name_table = face["name"]
                        subfam = name_table.getName(2, 3, 1) or name_table.getName(
                            2, 1, 0
                        )
                        psname = name_table.getName(6, 3, 1) or name_table.getName(
                            6, 1, 0
                        )
                        label = (subfam.toUnicode() if subfam else "") or ""
                        ps_label = (psname.toUnicode() if psname else "") or ""
                        tokens = self._style_token_set(label) | self._style_token_set(
                            ps_label
                        )
                        if desired_style_tokens and not desired_style_tokens.issubset(
                            tokens
                        ):
                            continue
                        score = self._style_match_score(
                            label or ps_label or preferred_style or "",
                            weight,
                            style,
                            stretch,
                        )
                        if best_face_score is None or score < best_face_score:
                            best_face_score = score
                            best_idx = idx
                    if best_face_score is not None:
                        return (path, best_idx)
                return (path, 0)
            except Exception:
                return (path, 0)

        for path, fams, styles, ps, weight_val in self._fc_cache:
            fam_hit = (
                any(
                    fam_norm == f or fam_norm.lstrip(".") == f.lstrip(".") for f in fams
                )
                or fam_norm == ps
                or fam_norm.lstrip(".") == ps.lstrip(".")
            )
            ps_hit = ps_norm and ps_norm == ps
            if not fam_hit and not ps_hit:
                continue
            for st in styles or ["normal"]:
                st_tokens = self._style_token_set(st)
                if desired_style_tokens and not desired_style_tokens.issubset(
                    st_tokens
                ):
                    continue
                score = self._style_match_score(st, weight, style, stretch)
                try:
                    score += abs((weight_val or 0) - weight) / 1000.0
                except Exception:
                    pass
                if best_score is None or score < best_score:
                    best_score = score
                    best_candidate = (path, st)

        if best_candidate:
            picked = pick_face(best_candidate[0], best_candidate[1])
            if picked:
                return picked
        return None

    def _match_font_with_fc(
        self,
        font_family: str,
        weight: int = 400,
        style: str = "normal",
        stretch: str = "normal",
    ) -> tuple[Path, int] | None:
        """Use fontconfig to match fonts like a browser, but select the correct face inside
        TTC collections based on weight/style/stretch tokens (e.g., choose Condensed face
        instead of Regular when requested)."""
        import subprocess

        def stretch_token(stretch: str) -> str | None:
            s = stretch.lower()
            mapping = {
                "ultra-condensed": "ultracondensed",
                "extra-condensed": "extracondensed",
                "condensed": "condensed",
                "semi-condensed": "semicondensed",
                "normal": None,
                "semi-expanded": "semiexpanded",
                "expanded": "expanded",
                "extra-expanded": "extraexpanded",
                "ultra-expanded": "ultraexpanded",
            }
            return mapping.get(s)

        desired_tokens = self._style_token_set(
            self._build_style_label(weight, style, stretch)
        )

        # Build candidate patterns from specific to generic to prefer Regular when available
        style_name = self._weight_to_style(weight)
        patterns: list[str] = []
        if weight == 400 and style == "normal":
            patterns.append(f"{font_family}:style=Regular:weight=400")
        if weight == 400 and style == "italic":
            patterns.append(f"{font_family}:style=Italic:weight=400:slant=italic")
        if style_name and weight != 400:
            patterns.append(f"{font_family}:style={style_name}")
        if weight != 400:
            patterns.append(f"{font_family}:weight={weight}")

        base = f"{font_family}"
        if style == "italic":
            base += ":slant=italic"
        elif style == "oblique":
            base += ":slant=oblique"
        st_tok = stretch_token(stretch)
        if st_tok:
            base += f":width={st_tok}"
        if stretch != "normal":
            base += f":width={stretch}"
        patterns.append(base)

        # Special-case Arial regular to avoid Bold fallback on some systems
        if font_family.lower() == "arial" and weight == 400 and style == "normal":
            patterns.insert(0, "Arial:style=Regular")

        def pick_face(path: Path, preferred_style: str | None = None) -> tuple[Path, int]:
            try:
                if path.suffix.lower() == ".ttc":
                    from fontTools.ttLib import TTCollection

                    coll = TTCollection(path)
                    best_idx = 0
                    best_face_score: float | None = None
                    for idx, face in enumerate(coll.fonts):
                        name_table = face["name"]
                        subfam = name_table.getName(2, 3, 1) or name_table.getName(
                            2, 1, 0
                        )
                        psname = name_table.getName(6, 3, 1) or name_table.getName(
                            6, 1, 0
                        )
                        label = (subfam.toUnicode() if subfam else "") or ""
                        ps_label = (psname.toUnicode() if psname else "") or ""
                        tokens = self._style_token_set(label) | self._style_token_set(
                            ps_label
                        )
                        if desired_tokens and not desired_tokens.issubset(tokens):
                            continue
                        score = self._style_match_score(
                            label or ps_label or preferred_style or "",
                            weight,
                            style,
                            stretch,
                        )
                        if best_face_score is None or score < best_face_score:
                            best_face_score = score
                            best_idx = idx
                    if best_face_score is not None:
                        return (path, best_idx)
                return (path, 0)
            except Exception:
                return (path, 0)

        for pattern in patterns:
            # Retry mechanism for busy font subsystem
            max_retries = 3
            result = None
            for attempt in range(max_retries):
                try:
                    result = subprocess.run(
                        ["fc-match", "--format=%{file}\n%{index}", pattern],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    if attempt < max_retries - 1:
                        import time

                        time.sleep(0.5)
                        continue
                except Exception:
                    pass

            if result and result.returncode == 0:
                try:
                    lines = result.stdout.strip().split("\n")
                    if len(lines) >= 2:
                        font_file = Path(lines[0])
                        font_index = int(lines[1]) if lines[1].isdigit() else 0
                        if font_file.exists():
                            if font_file.suffix.lower() == ".ttc":
                                return pick_face(
                                    font_file,
                                    self._build_style_label(weight, style, stretch),
                                )
                            return (font_file, font_index)
                except Exception:
                    continue

        return None

    def get_font(
        self,
        font_family: str,
        weight: int = 400,
        style: str = "normal",
        stretch: str = "normal",
        inkscape_spec: str | None = None,
        strict_family: bool = True,
    ):
        """Load font strictly; if exact face not found, return None (caller must abort unless strict_family=False).

        Args:
            font_family: Font family name
            weight: CSS font-weight (100-900)
            style: CSS font-style
            stretch: CSS font-stretch
            inkscape_spec: Optional Inkscape font specification hint (e.g., 'Futura Medium')

        Returns:
            (TTFont, font_blob_bytes, face_index) or None
        """
        # Normalize generic Pango family names to CSS generics (but do NOT substitute specific faces)
        generic_map = {
            "sans": "sans-serif",
            "sans-serif": "sans-serif",
            "serif": "serif",
            "monospace": "monospace",
            "mono": "monospace",
        }
        font_family = generic_map.get(font_family.strip().lower(), font_family.strip())

        cache_key = f"{font_family}:{weight}:{style}:{stretch}:{inkscape_spec}".lower()

        if cache_key not in self._fonts:
            match_result = None
            ink_ps = None
            if inkscape_spec:
                ink_family, ink_style = self._parse_inkscape_spec(inkscape_spec)
                font_family = ink_family or font_family
                if ink_style:
                    style = ink_style
            # strict exact match from fc cache by family/style/postscript
            match_result = self._match_exact(
                font_family, weight, style, stretch, ink_ps
            )

            if match_result is None:
                # Fallback to fontconfig best match (non-strict) to honor installed fonts
                match_result = self._match_font_with_fc(
                    font_family, weight, style, stretch
                )
            if match_result is None and font_family in ("sans-serif", "sans"):
                match_result = self._match_font_with_fc("sans", weight, style, stretch)
            if match_result is None:
                return None

            font_path, font_index = match_result

            try:
                # Load font (lazy to keep memory low)
                if font_index > 0 or str(font_path).endswith(".ttc"):
                    ttfont = TTFont(font_path, fontNumber=font_index, lazy=True)
                else:
                    ttfont = TTFont(font_path, lazy=True)

                with open(font_path, "rb") as f:
                    font_blob = f.read()

                # Verify family match strictly against name table
                def _name(tt, ids):
                    for nid in ids:
                        for rec in tt["name"].names:
                            if rec.nameID == nid:
                                try:
                                    return str(rec.toUnicode()).strip().lower()
                                except Exception:
                                    return (
                                        str(rec.string, errors="ignore").strip().lower()
                                    )
                    return None

                fam_candidate = (
                    _name(ttfont, [16, 1]) or _name(ttfont, [1]) or ""
                ).lower()
                sub_candidate = (_name(ttfont, [17, 2]) or "").lower()

                def _norm(s: str) -> str:
                    import re

                    return re.sub(r"[^a-z0-9]+", "", s.lower().lstrip("."))

                if strict_family and font_family.lower() not in ("sans-serif", "sans"):
                    if _norm(fam_candidate) != _norm(font_family):
                        # Allow subset match
                        if _norm(font_family) not in _norm(fam_candidate):
                            print(
                                f"⚠️  Loaded font '{font_path.name}' but family mismatch ({fam_candidate}) for requested '{font_family}'. Using it anyway."
                            )
                            # return None  <-- RELAXED: Do not abort, use the best match we found

                self._fonts[cache_key] = (ttfont, font_blob, font_index)
                print(
                    f"✓ Loaded: {font_family} w={weight} s={style} st={stretch} → {font_path.name}:{font_index}"
                )

            except Exception as e:
                print(f"✗ Failed to load {font_path}:{font_index}: {e}")
                return None

        return self._fonts.get(cache_key)


def recording_pen_to_svg_path(recording, precision: int = 28) -> str:
    """Convert RecordingPen recording to SVG path commands.

    Precision is configurable; default 28 for maximum fidelity (matching previous behavior).
    """
    fmt = f"{{:.{precision}f}}"
    commands = []

    for op, args in recording:
        if op == "moveTo":
            x, y = args[0]
            commands.append(f"M {fmt.format(x)} {fmt.format(y)}")
        elif op == "lineTo":
            x, y = args[0]
            commands.append(f"L {fmt.format(x)} {fmt.format(y)}")
        elif op == "qCurveTo":
            # TrueType quadratic Bezier curve(s)
            # qCurveTo can have multiple points: (cp1, cp2, ..., cpN, end)
            # If more than 2 points, there are implied on-curve points halfway between control points
            if len(args) == 2:
                # Simple case: one control point + end point
                x1, y1 = args[0]
                x, y = args[1]
                commands.append(
                    f"Q {fmt.format(x1)} {fmt.format(y1)} {fmt.format(x)} {fmt.format(y)}"
                )
            else:
                # Multiple control points - need to add implied on-curve points
                # Last point is the end point, others are control points
                for i in range(len(args) - 1):
                    x1, y1 = args[i]
                    if i == len(args) - 2:
                        # Last control point - use actual end point
                        x, y = args[i + 1]
                    else:
                        # Implied on-curve point halfway to next control point
                        x2, y2 = args[i + 1]
                        x, y = (x1 + x2) / 2, (y1 + y2) / 2
                    commands.append(
                        f"Q {fmt.format(x1)} {fmt.format(y1)} {fmt.format(x)} {fmt.format(y)}"
                    )
        elif op == "curveTo":
            # Cubic Bezier curve
            if len(args) >= 3:
                x1, y1 = args[0]
                x2, y2 = args[1]
                x, y = args[2]
                commands.append(
                    f"C {fmt.format(x1)} {fmt.format(y1)} {fmt.format(x2)} {fmt.format(y2)} {fmt.format(x)} {fmt.format(y)}"
                )
        elif op == "closePath":
            commands.append("Z")

    return " ".join(commands)


def _parse_num_list(val: str) -> list[float]:
    """Parse a list of numbers from an SVG attribute (space/comma separated)."""
    nums: list[float] = []
    for part in re.split(r"[ ,]+", val.strip()):
        if part == "":
            continue
        try:
            nums.append(float(part))
        except Exception:
            continue
    return nums


def text_to_path_rust_style(
    text_elem: ET.Element,
    font_cache: FontCache,
    path_obj: Path | None = None,
    path_start_offset: float = 0.0,
    precision: int = 5,
    dx_list: list[float] | None = None,
    dy_list: list[float] | None = None,
    trim_trailing_spacing: bool = True,
    input_svg_path: Path | None = None,
) -> tuple[ET.Element, float] | None:
    import sys

    """
    Convert text element to path element.

    Follows the Rust text2path implementation exactly:
    1. Unicode BiDi analysis to get visual runs
    2. HarfBuzz shaping for each run
    3. Glyph positioning from shaper

    Args:
        text_elem: The text element to convert
        font_cache: Font cache
        path_obj: Optional svg.path.Path object for textPath support
        path_offset: Starting offset along the path (in user units)

    Note: Transform attributes are NOT applied during conversion.
    They are copied from the text element to the path element.
    """

    # 1. Extract text content (including from tspan children)
    text_content = text_elem.text or ""
    if "兛" in text_content or text_elem.get("id") == "text4":
        dbg(f"DEBUG text4: entered text_to_path_rust_style with text='{text_content}'")

    # If no direct text, check for tspan elements
    if not text_content:
        # Get text from all tspan children
        tspan_texts = []
        for child in text_elem:
            tag = child.tag
            if "}" in tag:
                tag = tag.split("}")[1]
            if tag == "tspan" and child.text:
                tspan_texts.append(child.text)

        if tspan_texts:
            text_content = "".join(tspan_texts)  # Join tspans directly without space

    if not text_content:
        print("  ✗ No text content after extracting tspans")
        return None

    # Symbol font PUA remap
    def _sym_map_char(ch: str) -> str:
        cp = ord(ch)
        return chr(0xF000 + cp) if 0x20 <= cp <= 0xFF else ch

    # 2. Extract attributes
    def get_attr(elem, key, default=None):
        # Check style string first
        style = elem.get("style", "")
        match = re.search(f"{key}:([^;]+)", style)
        if match:
            return match.group(1).strip()
        # Check direct attribute
        return elem.get(key, default)

    x_attr = text_elem.get("x")
    y_attr = text_elem.get("y")
    dx_attr = text_elem.get("dx")
    dy_attr = text_elem.get("dy")

    # If x/y are missing, they default to 0 in SVG, but for tspans they should flow.
    # However, since we are processing this as an isolated element (for now),
    # we rely on the caller to handle flow or explicit coordinates.
    x = float(x_attr) if x_attr else 0.0
    y = float(y_attr) if y_attr else 0.0
    if (
        "No javascript" in text_content
        or text_elem.get("id") in ["text53", "text4", "text54", "text39", "text45"]
        or "兛" in text_content
    ):
        dbg(f"DEBUG ATTR: attrib={text_elem.attrib} x_attr='{x_attr}' x={x}")

    # Parse per-glyph dx/dy lists (do NOT pre-apply; handled per-glyph)
    if dx_list is None and dx_attr:
        dx_list = _parse_num_list(dx_attr)
    if dy_list is None and dy_attr:
        dy_list = _parse_num_list(dy_attr)

    # Get text alignment
    # Per SVG 2 spec (https://www.w3.org/TR/SVG2/text.html#TextAnchoringProperties):
    # - text-anchor is the ONLY alignment property for SVG text elements
    # - text-align is CSS-only and NOT part of SVG spec for text elements
    # - Valid values: start (default), middle, end
    #
    # However, many SVG authoring tools (including Inkscape) incorrectly use
    # text-align:center instead of text-anchor="middle". Since we're converting
    # to paths anyway, we handle both cases to apply correct alignment regardless
    # of whether the source SVG uses correct or incorrect syntax.
    # Respect style text-anchor; style should override attribute if both present.
    text_anchor = get_attr(text_elem, "text-anchor", None)

    # Check for text-align in style (common mistake in SVG authoring tools)
    # Map CSS text-align to SVG text-anchor values
    style = text_elem.get("style", "")
    text_align_match = re.search(r"text-align:\s*(center|left|right)", style)
    if (
        text_align_match and (not text_anchor or text_anchor == "start")
    ):  # Only use if text-anchor not explicitly set
        text_align_map = {"center": "middle", "left": "start", "right": "end"}
        text_anchor = text_align_map.get(text_align_match.group(1), "start")
    if not text_anchor:
        text_anchor = "start"

    # Do not bake transforms. We want to preserve them on the output element.
    transform_attr = text_elem.get("transform")
    baked_matrix = None

    # Parse font-family
    raw_font = get_attr(text_elem, "font-family", "Arial")
    font_family = raw_font.split(",")[0].strip().strip("'\"")
    symbol_families = {"webdings", "wingdings", "wingdings 2", "wingdings 3", "symbol"}

    # Remap text content for symbol fonts to PUA so glyphs are reachable
    if font_family.lower() in symbol_families:
        text_content = "".join(_sym_map_char(ch) for ch in text_content)
    symbol_paths_mac = {
        "webdings": "/System/Library/Fonts/Supplemental/Webdings.ttf",
        "wingdings": "/System/Library/Fonts/Supplemental/Wingdings.ttf",
        "wingdings 2": "/System/Library/Fonts/Supplemental/Wingdings 2.ttf",
        "wingdings 3": "/System/Library/Fonts/Supplemental/Wingdings 3.ttf",
        "symbol": "/System/Library/Fonts/Supplemental/Symbol.ttf",
    }

    # Parse font-size
    raw_size = get_attr(text_elem, "font-size", "16")
    # Handle units (px is default, pt needs conversion)
    if "pt" in raw_size:
        font_size = float(re.search(r"([\d.]+)", raw_size).group(1)) * 1.3333
    else:
        font_size = float(re.search(r"([\d.]+)", raw_size).group(1))

    # Spacing
    # IMPORTANT (✱ gain ~50% diff reduction when spacing present):
    # In earlier runs we failed to parse letter/word-spacing like "10" and treated them as 0,
    # causing anchor widths to collapse and large left shifts (e.g., diff 14%→7%). Keep this robust parser.
    raw_letter_spacing = get_attr(text_elem, "letter-spacing", None)
    letter_spacing = 0.0
    if raw_letter_spacing and raw_letter_spacing != "normal":
        m_num = re.search(r"([-+]?[\d.]+)", raw_letter_spacing)
        if m_num:
            try:
                letter_spacing = float(m_num.group(1))
            except Exception:
                letter_spacing = 0.0

    raw_word_spacing = get_attr(text_elem, "word-spacing", None)
    word_spacing = 0.0
    if raw_word_spacing and raw_word_spacing != "normal":
        m_num = re.search(r"([-+]?[\d.]+)", raw_word_spacing)
        if m_num:
            try:
                word_spacing = float(m_num.group(1))
            except Exception:
                word_spacing = 0.0

    # Parse font-variation settings (optional)
    fv_settings_str = get_attr(text_elem, "font-variation-settings", None)
    variation_wght = None
    variation_settings: list[tuple[str, float]] = []
    if fv_settings_str:
        for tag, val in re.findall(
            r"'([A-Za-z0-9]{4})'\s*([\d\.]+)", fv_settings_str
        ):
            try:
                num_val = float(val)
                variation_settings.append((tag, num_val))
                if tag.lower() == "wght":
                    variation_wght = num_val
            except Exception:
                pass

    # SVG/CSS default: font-optical-sizing is 'auto'. If the font supports the
    # OpenType variable axis 'opsz' and no explicit opsz is set, browsers
    # typically auto-set opsz to the computed font-size.
    font_optical_sizing = (
        (get_attr(text_elem, "font-optical-sizing", "auto") or "auto")
        .strip()
        .lower()
    )

    # Parse font-weight (use wght variation if present)
    raw_weight = get_attr(text_elem, "font-weight", "400")
    if raw_weight == "normal":
        font_weight = 400
    elif raw_weight == "bold":
        font_weight = 700
    else:
        font_weight = (
            int(re.search(r"(\\d+)", raw_weight).group(1))
            if re.search(r"(\\d+)", raw_weight)
            else 400
        )
    if variation_wght:
        try:
            font_weight = int(max(100, min(900, variation_wght)))
        except Exception:
            pass

    # Parse font-style
    font_style = get_attr(text_elem, "font-style", "normal")

    # Parse font-stretch
    font_stretch = get_attr(text_elem, "font-stretch", "normal")

    # Extract inkscape-font-specification hint if present
    # This helps with font matching, especially for TTC files where weight matching can fail
    inkscape_spec_raw = get_attr(text_elem, "-inkscape-font-specification", None)
    inkscape_spec = None
    if inkscape_spec_raw:
        # Keep the full string for token analysis (e.g., "Futura, Medium Italic")
        spec_clean = inkscape_spec_raw.strip("'\"")
        spec_lower = spec_clean.lower()
        tokens = set(
            t.strip().lower() for t in re.split(r"[\s,]+", spec_clean) if t.strip()
        )

        # Use tokens to refine weight/style when CSS parsing fell back to defaults
        def has_token(sub: str) -> bool:
            return sub in tokens or sub in spec_lower

        if font_weight in (400, 500):
            wght_match = re.search(r"wght\s*=\s*(\d+)", spec_lower)
            if wght_match:
                try:
                    font_weight = int(
                        max(100, min(900, float(wght_match.group(1))))
                    )
                except Exception:
                    pass

        if font_weight in (400, 500):  # adjust only if we didn't get a strong signal
            # Break down common multi-word weight names (extra/ultra/semi/demi + light/bold/etc.)
            if has_token("black") or has_token("heavy"):
                font_weight = 900
            elif has_token("extrabold") or has_token("ultrabold") or (
                (has_token("extra") or has_token("ultra")) and has_token("bold")
            ):
                font_weight = 800
            elif has_token("semibold") or has_token("demibold") or (
                (has_token("semi") or has_token("demi")) and has_token("bold")
            ):
                font_weight = 600
            elif has_token("medium"):
                font_weight = 500
            elif has_token("extralight") or has_token("ultralight") or (
                (has_token("extra") or has_token("ultra")) and has_token("light")
            ):
                font_weight = 200
            elif has_token("light"):
                font_weight = 300
            elif has_token("bold"):
                font_weight = 700
            elif has_token("thin"):
                font_weight = 100

        if font_style == "normal":
            if "italic" in tokens:
                font_style = "italic"
            elif "oblique" in tokens:
                font_style = "oblique"

        # Cleaned family-only hint for font matching
        inkscape_spec = spec_clean.split(",")[0].strip()

    # Note: We do NOT handle text-anchor/text-align here!
    # The x, y coordinates in the SVG are already positioned correctly by the SVG renderer.
    # Applying text-anchor adjustments would incorrectly shift the glyphs.
    # We just use raw x, y coordinates and copy the transform attribute.
    # The transform attribute (if any) will be copied to the path element later.
    # The transform attribute (if any) will be copied to the path element later.
    if "No javascript" in text_content or text_elem.get("id") in ["text8", "text54"]:
        dbg(
            f"DEBUG FONT ARGS for {text_elem.get('id')}: family='{font_family}' weight={font_weight} style='{font_style}' stretch='{font_stretch}' inkscape_spec='{inkscape_spec}'"
        )
    dbg(
        f"DEBUG RUN: '{text_content[:40]}' font={font_family} size={font_size} w={font_weight} style={font_style} stretch={font_stretch} inkscape_spec={inkscape_spec}"
    )

    # 3. Load font using CSS properties (fontconfig matches like browsers do)
    norm_fam = font_family.strip().lower()
    symbol_aliases = {"webdings", "wingdings", "marlett"}
    newyork_aliases = {".new york", "new york"}
    phosphate_aliases = {"phosphate"}

    font_data = None

    if norm_fam in ("sans", "sans-serif"):
        if norm_fam == "sans":
            serif_candidates = ["Times", "Times New Roman", "Times Roman", "Noto Serif"]
            for fam in serif_candidates:
                cand = font_cache.get_font(
                    fam,
                    weight=font_weight,
                    style=font_style,
                    stretch=font_stretch,
                    inkscape_spec=None,
                    strict_family=False,
                )
                if cand:
                    font_data = cand
                    break
        else:
            sfns_path = Path(
                "/System/Library/Fonts/SFNSItalic.ttf"
                if font_style in ("italic", "oblique")
                else "/System/Library/Fonts/SFNS.ttf"
            )
            if sfns_path.exists():
                try:
                    tt = TTFont(sfns_path, lazy=True)
                    with open(sfns_path, "rb") as f:
                        blob = f.read()
                    font_data = (tt, blob, 0)
                except Exception:
                    font_data = None
            if not font_data:
                sans_candidates = [".SF NS Text", "Helvetica", "Arial", "Noto Sans"]
                for fam in sans_candidates:
                    cand = font_cache.get_font(
                        fam,
                        weight=font_weight,
                        style=font_style,
                        stretch=font_stretch,
                        inkscape_spec=None,
                        strict_family=False,
                    )
                    if cand:
                        font_data = cand
                        break
    if norm_fam in symbol_aliases:
        # Prefer platform symbol fonts; score by coverage of ASCII + dingbats
        symbol_candidates = [
            "Segoe UI Symbol",
            "Apple Symbols",
            "Symbola",
            "Arial Unicode MS",
            "Noto Sans Symbols",
            "Noto Sans Symbols2",
        ]
        best_sym = None
        best_score = -1
        needed = set(ord(ch) for ch in text_content)
        dingbat_range = lambda cp: 0x2600 <= cp <= 0x27FF
        for fam in symbol_candidates:
            cand = font_cache.get_font(
                fam,
                weight=font_weight,
                style="normal",
                stretch=font_stretch,
                inkscape_spec=None,
                strict_family=False,
            )
            if not cand:
                continue
            tt = cand[0]
            cmap_c = tt.getBestCmap() or {}
            cover = sum(1 for cp in needed if cp in cmap_c and cmap_c[cp] != 0)
            cover_ding = sum(1 for cp in needed if dingbat_range(cp) and cp in cmap_c and cmap_c[cp] != 0)
            score = cover + cover_ding * 2
            if score > best_score:
                best_score = score
                best_sym = cand
        font_data = best_sym
    elif norm_fam in newyork_aliases:
        for fam in ("New York", "Times New Roman"):
            font_data = font_cache.get_font(
                fam,
                weight=font_weight,
                style=font_style,
                stretch=font_stretch,
                inkscape_spec=None,
                strict_family=False,
            )
            if font_data:
                break
    elif norm_fam in phosphate_aliases:
        for fam in ("Phosphate", "Impact", "Arial Black"):
            font_data = font_cache.get_font(
                fam,
                weight=font_weight,
                style=font_style,
                stretch=font_stretch,
                inkscape_spec=None,
                strict_family=False,
            )
            if font_data:
                break

    # If still none and it's a symbol family, try direct system path to avoid fc substitution
    if not font_data and norm_fam in symbol_families:
        symbol_paths_mac = {
            "webdings": "/System/Library/Fonts/Supplemental/Webdings.ttf",
            "wingdings": "/System/Library/Fonts/Supplemental/Wingdings.ttf",
            "wingdings 2": "/System/Library/Fonts/Supplemental/Wingdings 2.ttf",
            "wingdings 3": "/System/Library/Fonts/Supplemental/Wingdings 3.ttf",
            "symbol": "/System/Library/Fonts/Supplemental/Symbol.ttf",
        }
        p = Path(symbol_paths_mac.get(norm_fam, ""))
        if p.exists():
            try:
                tt = TTFont(p, lazy=False)
                with open(p, "rb") as f:
                    blob = f.read()
                font_data = (tt, blob, 0)
            except Exception:
                font_data = None

    if not font_data or norm_fam in symbol_families:
        # Force symbol primary to actual symbol font if available
        if norm_fam in symbol_families:
            symbol_paths_mac = {
                "webdings": "/System/Library/Fonts/Supplemental/Webdings.ttf",
                "wingdings": "/System/Library/Fonts/Supplemental/Wingdings.ttf",
                "wingdings 2": "/System/Library/Fonts/Supplemental/Wingdings 2.ttf",
                "wingdings 3": "/System/Library/Fonts/Supplemental/Wingdings 3.ttf",
                "symbol": "/System/Library/Fonts/Supplemental/Symbol.ttf",
            }
            p = Path(symbol_paths_mac.get(norm_fam, ""))
            if p.exists():
                try:
                    tt = TTFont(p, lazy=False)
                    with open(p, "rb") as f:
                        blob = f.read()
                    font_data = (tt, blob, 0)
                except Exception:
                    font_data = None

    if not font_data:
        font_data = font_cache.get_font(
            font_family,
            weight=font_weight,
            style=font_style,
            stretch=font_stretch,
            inkscape_spec=inkscape_spec,
        )
    if not font_data:
        raise MissingFontError(
            font_family,
            font_weight,
            font_style,
            font_stretch,
            f"Font '{font_family}' w={font_weight} s={font_style} st={font_stretch} not found",
        )

    ttfont, font_blob, font_index = font_data

    # Auto-apply opsz for variable fonts when optical sizing is enabled and opsz is not explicitly set.
    # Keep this limited to shaping (HarfBuzz variations); do not force outline instancing here to avoid
    # regressions on variable-font samples with explicit font-variation-settings.
    if font_optical_sizing != "none":
        try:
            if "fvar" in ttfont and not any(
                tag.lower() == "opsz" for tag, _v in variation_settings
            ):
                for axis in ttfont["fvar"].axes:
                    if axis.axisTag == "opsz":
                        opsz_val = float(font_size)
                        opsz_val = max(
                            float(axis.minValue),
                            min(float(axis.maxValue), opsz_val),
                        )
                        variation_settings.append(("opsz", opsz_val))
                        break
        except Exception:
            pass

    # Log the actual font file being used
    if (
        hasattr(ttfont, "reader")
        and hasattr(ttfont.reader, "file")
        and hasattr(ttfont.reader.file, "name")
    ):
        print(f"    → Using font file: {ttfont.reader.file.name}")
    # Ensure all characters have glyphs in this font
    cmap = ttfont.getBestCmap() or {}
    # Prefer Microsoft Symbol cmap (3,0) for symbol fonts even if getBestCmap is non-empty
    if font_family.lower() in symbol_families and "cmap" in ttfont:
        cm = ttfont["cmap"].getcmap(3, 0)
        if cm and cm.cmap:
            cmap = cm.cmap
    if not cmap and "cmap" in ttfont:
        cm = ttfont["cmap"].getcmap(3, 0)
        if cm:
            cmap = cm.cmap

    if not cmap:
        cmap = {}
    if font_family.lower() in symbol_families:
        dbg(
            f"DEBUG symbol cmap: len={len(cmap)} sample_keys={list(cmap.keys())[:5] if cmap else []} has_F04E={0xF04E in cmap}"
        )
    try:
        glyph_set_primary = ttfont.getGlyphSet()
    except Exception:
        glyph_set_primary = None

    symbol_families = {"webdings", "wingdings", "wingdings 2", "wingdings 3", "symbol"}

    def _sym_map(cp: int) -> int:
        return 0xF000 + cp if 0x20 <= cp <= 0xFF else cp

    def _has_glyph(tt, glyph_set, codepoint):
        mapped_cp = _sym_map(codepoint) if font_family.lower() in symbol_families else codepoint
        if mapped_cp not in cmap or cmap.get(mapped_cp, 0) == 0:
            return False
        try:
            gid = cmap.get(mapped_cp)
            name = gid if isinstance(gid, str) else tt.getGlyphName(gid)
            if not glyph_set or name not in glyph_set:
                # For symbol fonts, trust cmap presence
                return font_family.lower() in symbol_families
            # For symbol fonts, trust cmap regardless of outline content
            if font_family.lower() in symbol_families:
                return True
            pen = DecomposingRecordingPen(glyph_set)
            glyph_set[name].draw(pen)
            if pen.value:
                return True
            # Treat whitespace as present even if outline is empty
            if chr(codepoint).isspace():
                return True
            return False
        except Exception:
            return False

    missing_chars = [
        ch for ch in text_content if not _has_glyph(ttfont, glyph_set_primary, ord(ch))
    ]
    dbg(f"DEBUG missing_chars initial: {missing_chars}")
    # For symbol fonts, ignore missing glyphs that are only spaces/PUA
    if font_family.lower() in symbol_families:
        missing_chars = [
            ch for ch in missing_chars if not ch.isspace()
        ]
    if font_family.lower() in symbol_families and missing_chars:
        missing_chars = []
    if font_family.lower() in symbol_families and missing_chars:
        # For symbol fonts, if cmap has mapped entries, consider them present even if outlines empty
        still_missing = []
        for ch in missing_chars:
            mapped = _sym_map(ord(ch))
            if mapped in cmap and cmap.get(mapped, 0) != 0:
                continue
            still_missing.append(ch)
        missing_chars = still_missing
    fallback_ttfont = None
    fallback_cmap = None
    fallback_glyph_set = None
    fallback_scale = None
    fallback_hb_font = None
    
    # Load standard fallback (sans-serif)
    fallback_data = font_cache.get_font("sans-serif", weight=400, style="normal")
    if fallback_data:
        fallback_ttfont, _, _ = fallback_data
        print(f"    → Loaded fallback font: {fallback_ttfont.reader.file.name}")
        fallback_cmap = fallback_ttfont.getBestCmap() or {}
        fallback_glyph_set = fallback_ttfont.getGlyphSet()
        fallback_scale = (
            (font_size / fallback_ttfont["head"].unitsPerEm) if fallback_ttfont else 1.0
        )
    
        # Create HarfBuzz font for fallback
        fallback_blob = hb.Blob(fallback_data[1])
        fallback_face = hb.Face(fallback_blob)
        fallback_hb_font = hb.Font(fallback_face)
        fallback_hb_font.scale = (int(font_size * 64), int(font_size * 64))
        if variation_settings:
            try:
                fallback_hb_font.set_variations(dict(variation_settings))
            except Exception:
                pass
    
    # Load dedicated CJK font for fallback
    cjk_ttfont = None
    cjk_hb_font = None
    cjk_scale = None
    cjk_glyph_set = None
    cjk_cmap = None
    symbol_ttfont = None
    symbol_blob = None
    symbol_index = None
    symbol_hb_font = None
    symbol_scale = None
    symbol_glyph_set = None
    symbol_cmap = None
    
    # Identify CJK chars in text to check coverage
    cjk_chars_in_text = [
        ord(ch)
        for ch in text_content
        if 0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF
    ]
    
    if cjk_chars_in_text:
        # Determine if serif is preferred based on font family name
        primary_lower = font_family.lower()
        is_serif = (
            "serif" in primary_lower
            or "song" in primary_lower
            or "mincho" in primary_lower
            or "times" in primary_lower
        )
    
        cjk_candidates = [
            "PingFang SC",
            "Heiti SC",
            "Source Han Sans SC VF",
            "Source Han Sans SC",
            "STHeiti",
            "Apple SD Gothic Neo",
            "Hiragino Sans GB",
            "Songti SC",
        ]
        if is_serif:
            # Prioritize Serif CJK fonts
            cjk_candidates = [
                "PingFang SC",
                "Heiti SC",
                "Source Han Serif SC VF",
                "Source Han Serif SC",
                "Songti SC",
                "Noto Serif CJK SC",
                "STHeiti",
                "Apple SD Gothic Neo",
                "Hiragino Sans GB",
            ]
        env_cjk = os.environ.get("T2P_CJK_FALLBACKS")
        if env_cjk:
            cjk_candidates = [
                fam.strip() for fam in env_cjk.split(",") if fam.strip()
            ] or cjk_candidates
        target_bbox_cjk = (
            measure_bbox_with_font(input_svg_path, text_elem.get("id", ""), None)
            if input_svg_path
            else None
        )
        weight_candidates = expand_weights(font_weight)
        chrome_detect_best = detect_chrome_font(
            text_content,
            font_size,
            font_weight,
            cjk_candidates,
            font_family,
            Path(__file__).parent.parent,
        )
        scored_cjk: list[tuple[float, str, tuple | None, dict, Any]] = []
    
        for cjk_fam in cjk_candidates:
            for wgt in weight_candidates:
                cjk_data = font_cache.get_font(
                    cjk_fam,
                    weight=wgt,
                    style=font_style,
                    stretch=font_stretch,
                    strict_family=False,
                )
                if cjk_data:
                    temp_ttfont = cjk_data[0]
                    temp_cmap = temp_ttfont.getBestCmap() or {}
                    # Check if this font covers at least one of the CJK chars we need
                    if any(cp in temp_cmap for cp in cjk_chars_in_text):
                        dims = (
                            measure_bbox_with_font(
                                input_svg_path, text_elem.get("id", ""), cjk_fam, weight=wgt
                            )
                            if input_svg_path
                            else None
                        )
                        score = float("inf")
                        if target_bbox_cjk and dims:
                            tw, th = target_bbox_cjk
                            cw, ch = dims
                            score = abs(cw - tw) + abs(ch - th)
                            if wgt:
                                score += 0.01 * abs(wgt - font_weight)
                        else:
                            score = -sum(1 for cp in cjk_chars_in_text if cp in temp_cmap)
                        scored_cjk.append((score, cjk_fam, dims, temp_cmap, cjk_data))
                    else:
                        print(f"    → Skipped CJK font {cjk_fam} (no coverage for text)")
    
        if scored_cjk:
            scored_cjk.sort(key=lambda x: x[0])
            # If Chrome detector found a match, bias toward it only when scores tie.
            if chrome_detect_best and any(f == chrome_detect_best for _, f, _, _, _ in scored_cjk):
                best_score = scored_cjk[0][0]
                chrome_entry = next((e for e in scored_cjk if e[1] == chrome_detect_best), None)
                if chrome_entry and abs(chrome_entry[0] - best_score) < 1e-6:
                    entry = chrome_entry
                else:
                    entry = scored_cjk[0]
            else:
                entry = scored_cjk[0]
            _, _, _, temp_cmap, cjk_data = entry
            cjk_fam = entry[1]
            cjk_ttfont = cjk_data[0]
            print(
                f"    → Loaded CJK fallback font: {cjk_fam} (covers {sum(1 for cp in cjk_chars_in_text if cp in temp_cmap)}/{len(cjk_chars_in_text)} chars)"
            )
            cjk_cmap = temp_cmap
            cjk_glyph_set = cjk_ttfont.getGlyphSet()
            cjk_scale = (
                (font_size / cjk_ttfont["head"].unitsPerEm) if cjk_ttfont else 1.0
            )
    
            # Create HarfBuzz font for CJK
            cjk_blob = hb.Blob(cjk_data[1])
            cjk_face = hb.Face(cjk_blob)
            cjk_hb_font = hb.Font(cjk_face)
            cjk_upem = cjk_ttfont["head"].unitsPerEm
            cjk_hb_font.scale = (cjk_upem, cjk_upem)
            if variation_settings:
                try:
                    cjk_hb_font.set_variations(dict(variation_settings))
                except Exception:
                    pass
    
    # If we have a dedicated CJK fallback with coverage, don't force general fallback to handle those glyphs
    if cjk_cmap:
        missing_chars = [
            ch
            for ch in missing_chars
            if not (
                0x3400 <= ord(ch) <= 0x9FFF and cjk_cmap.get(ord(ch), 0) not in (None, 0)
            )
        ]
    
    # Check for CJK script mismatch to force fallback
    # (If we have CJK chars but loaded a non-CJK font like .SF Arabic Rounded, force fallback)
    cjk_indicators = [
        "cjk",
        "mincho",
        "gothic",
        "song",
        "kai",
        "ming",
        "hei",
        "fang",
        "noto sans sc",
        "noto sans tc",
        "noto sans jp",
        "noto sans kr",
        "pingfang",
        "hiragino",
    ]
    primary_name = font_family.lower()
    is_cjk_font = any(ind in primary_name for ind in cjk_indicators)
    
    symbol_families = {"webdings", "wingdings", "wingdings 2", "wingdings 3", "symbol"}

    # Identify CJK chars in text
    cjk_chars = [
        ch
        for ch in text_content
        if 0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF
    ]
    
    if cjk_chars and not is_cjk_font:
        # Only force fallback for CJK chars actually missing in the primary font
        missing_cjk = [
            ch for ch in cjk_chars if ord(ch) not in cmap or cmap.get(ord(ch), 0) == 0
        ]
        if cjk_cmap:
            missing_cjk = [
                ch for ch in missing_cjk if cjk_cmap.get(ord(ch), 0) == 0
            ]
        if missing_cjk:
            print(
                f"    ℹ️  Detected CJK chars missing in non-CJK font '{font_family}'. Forcing fallback lookup."
            )
            missing_chars.extend(missing_cjk)
            missing_chars = list(set(missing_chars))
    fallback_cmap = None

    def _font_has_outlines(ttfont) -> bool:
        try:
            return any(tbl in ttfont for tbl in ("glyf", "CFF ", "CFF2", "SVG "))
        except Exception:
            return False

    def _os_symbol_candidates() -> list[Path]:
        """Return platform-specific symbol outline font paths in priority order."""
        candidates: list[Path] = []
        # macOS
        mac_paths = [
            "/System/Library/Fonts/Apple Symbols.ttf",
            "/System/Library/Fonts/Supplemental/Symbol.ttf",
        ]
        for p in mac_paths:
            path = Path(p)
            if path.exists():
                candidates.append(path)

        # Windows
        win_paths = [
            r"C:\\Windows\\Fonts\\seguisym.ttf",  # Segoe UI Symbol
            r"C:\\Windows\\Fonts\\arialuni.ttf",  # Arial Unicode MS
            r"C:\\Windows\\Fonts\\symbol.ttf",
        ]
        for p in win_paths:
            path = Path(p)
            if path.exists():
                candidates.append(path)

        # Linux common
        linux_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
        ]
        for p in linux_paths:
            path = Path(p)
            if path.exists():
                candidates.append(path)

        return candidates
    
    if missing_chars:
        if text_elem.get("id") == "text8":
            print(f"DEBUG missing_chars for {text_elem.get('id')}: {missing_chars}")
        # Script-based fallback selection (single fallback per run)
        fb_weight = int(max(100, min(900, font_weight)))
    
        src_path = input_svg_path
        target_bbox = (
            measure_bbox_with_font(src_path, text_elem.get("id", ""), None)
            if src_path
            else None
        )
        # fontconfig candidates
        lang_attr = text_elem.get("{http://www.w3.org/XML/1998/namespace}lang") or None
        fc_cands = fetch_fontconfig_candidates(font_family, lang_attr)
        charset_cands = fetch_charset_candidates({ord(ch) for ch in missing_chars})
        # weights to explore
        weight_candidates = expand_weights(font_weight)
    
        def pick_fallback(chars: list[str]) -> list[str]:
            # Prioritize specific scripts
            for ch in chars:
                code = ord(ch)
                if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
                    # Prefer Arial for Arabic as it often matches browser rendering better than Geeza Pro on some systems
                    return [
                        "Arial",
                        "Geeza Pro",
                        "Noto Sans Arabic",
                        ":lang=ar",
                        "Arial Unicode MS",
                        "Times New Roman",
                        "Last Resort",
                    ]
                if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
                    return [
                        ":lang=zh-cn",
                        "PingFang SC",
                        "Heiti SC",
                        "Hiragino Sans GB",
                        "Source Han Sans SC VF",
                        "Source Han Sans SC",
                        "Noto Sans CJK SC",
                        "Noto Sans SC",
                        "Arial Unicode MS",
                        "Last Resort",
                    ]
    
            # Secondary pass for symbols
            for ch in chars:
                code = ord(ch)
                if 0x2600 <= code <= 0x27FF or 0x1F300 <= code <= 0x1FAFF:
                    return [
                        "Helvetica",
                        "Arial",
                        "Segoe UI Symbol",
                        "Times New Roman",
                        "Symbola",
                        "Apple Symbols",
                        "Arial Unicode MS",
                        "Last Resort",
                    ]
    
            return ["Apple Symbols", "Arial Unicode MS", "Last Resort"]
    
        def _load_family_candidate(
            family: str, avoid_tokens: list[str] | None = None
        ):
            """Load a candidate font by family name, optionally skipping file paths with tokens."""
            font_cache._load_fc_cache()
            fam_norm = family.strip().lower()
            best = None
            best_score = None
            for path, fams, _styles, ps, weight_val in font_cache._fc_cache or []:
                fam_hit = any(
                    fam_norm == f or fam_norm.lstrip(".") == f.lstrip(".") for f in fams
                )
                ps_norm = (ps or "").lower()
                if not fam_hit and fam_norm != ps_norm and fam_norm.lstrip(".") != ps_norm.lstrip("."):
                    continue
                if avoid_tokens and any(tok in path.name.lower() for tok in avoid_tokens):
                    continue
                try:
                    score = abs((weight_val or 0) - font_weight)
                except Exception:
                    score = 0
                if best_score is None or score < best_score:
                    best_score = score
                    best = (path, 0)
            if best:
                path, idx = best
                try:
                    if path.suffix.lower() == ".ttc":
                        tt = TTFont(path, fontNumber=idx, lazy=True)
                    else:
                        tt = TTFont(path, lazy=True)
                    with open(path, "rb") as f:
                        blob = f.read()
                    return (tt, blob, idx)
                except Exception:
                    return None
            return None

        fb_names = pick_fallback(missing_chars)
        missing_set = set(missing_chars)
        if any(
            (0x2600 <= ord(ch) <= 0x27FF) or (0x1F300 <= ord(ch) <= 0x1FAFF)
            for ch in missing_chars
        ):
            symbol_candidates = [
                "Apple Color Emoji",
                "Apple Symbols",
                "Noto Color Emoji",
                "Noto Emoji",
                "Symbola",
                "Segoe UI Symbol",
                "Arial Unicode MS",
                "Last Resort",
            ]
            for fam in symbol_candidates:
                if fam not in fb_names:
                    fb_names.append(fam)
        # merge fontconfig candidates
        for fam in fc_cands:
            if fam not in fb_names:
                fb_names.append(fam)
            for fam in charset_cands:
                if fam not in fb_names:
                    fb_names.append(fam)
        # ensure fb_names are plain strings
        fb_names = [f[0] if isinstance(f, tuple) else f for f in fb_names]
        # Heuristic: when using SF Arabic, prefer SF Compact Rounded as fallback for ASCII/punctuation
        if "sf arabic" in font_family.lower():
            preferred_sf_fb = [
                "SF Compact Rounded",
                "SFCompactRounded",
                "SF Compact",
                ".SF Compact Rounded",
            ]
            for fam in reversed(preferred_sf_fb):
                if fam not in fb_names:
                    fb_names.insert(0, fam)
            # If all missing chars are ASCII, force the preferred SF fallback to be the primary candidate
            if all(ord(ch) < 256 for ch in missing_chars):
                for fam in preferred_sf_fb:
                    cand = font_cache.get_font(
                        fam,
                        weight=font_weight,
                        style=font_style,
                        stretch="normal",
                        inkscape_spec=None,
                        strict_family=False,
                    )
                    if cand:
                        best_fb = (fam, font_weight)
                        break
        # If original family is a symbol font, strongly prefer symbol fallbacks first
        if font_family.lower() in symbol_families:
            symbol_priority = [
                "Webdings",
                "Wingdings",
                "Wingdings 2",
                "Wingdings 3",
                "Apple Symbols",
                "Symbola",
                "Segoe UI Symbol",
                "Noto Sans Symbols2",
                "Noto Sans Symbols",
                "Arial Unicode MS",
            ]
            fb_names = [f for f in symbol_priority if f not in fb_names] + fb_names
        # Paths cannot be built from color-emoji bitmap fonts; drop any emoji families
        fb_names = [f for f in fb_names if "emoji" not in f.lower()]
        preferred_fb = None
        preferred_candidate = None
        primary_is_mono = False
        try:
            primary_is_mono = bool(ttfont["post"].isFixedPitch)
        except Exception:
            primary_is_mono = False
        arabic_missing = any(
            0x0600 <= ord(ch) <= 0x06FF or 0x0750 <= ord(ch) <= 0x077F
            for ch in missing_set
        )
        is_generic_sans = font_family.strip().lower() in ("sans", "sans-serif")
        if arabic_missing and primary_is_mono:
            mono_weight = 700 if font_weight >= 500 else 400
            mono_styles = [font_style]
            if font_style != "normal":
                mono_styles.append("normal")
            mono_priority = ["Courier New", "Courier", "Menlo", "Monaco"]
            for fam in mono_priority:
                cand = None
                for style in mono_styles:
                    cand = font_cache.get_font(
                        fam,
                        weight=mono_weight,
                        style=style,
                        stretch="normal",
                        inkscape_spec=None,
                        strict_family=False,
                    )
                    if cand:
                        break
                if not cand:
                    continue
                cmap_test = cand[0].getBestCmap() or {}
                if all(
                    ord(ch) in cmap_test and cmap_test.get(ord(ch), 0) != 0
                    for ch in missing_set
                ):
                    preferred_fb = (fam, mono_weight)
                    preferred_candidate = cand
                    break
        if arabic_missing and is_generic_sans:
            arabic_priority = [
                "Geeza Pro",
                "Arial",
                "Noto Sans Arabic",
                "Noto Naskh Arabic",
                "Arial Unicode MS",
                "Times New Roman",
            ]
            for fam in arabic_priority:
                cand = None
                avoid_tokens = ["condensed"] if fam.lower() == "noto sans arabic" else None
                if avoid_tokens:
                    cand = _load_family_candidate(fam, avoid_tokens=avoid_tokens)
                if not cand:
                    cand = font_cache.get_font(
                        fam,
                        weight=font_weight,
                        style=font_style,
                        stretch="normal",
                        inkscape_spec=None,
                        strict_family=False,
                    )
                if not cand:
                    continue
                cmap_test = cand[0].getBestCmap() or {}
                if all(
                    ord(ch) in cmap_test and cmap_test.get(ord(ch), 0) != 0
                    for ch in missing_set
                ):
                    preferred_fb = (fam, font_weight)
                    preferred_candidate = cand
                    break

        # Chrome detection: if we get a hash match, trust it as the primary fallback
        if preferred_fb:
            chrome_best_fb = None
        else:
            chrome_text = "".join(
                ch if ch in missing_set else " " for ch in text_content
            ).strip()
            if not chrome_text:
                chrome_text = "".join(missing_chars)
            chrome_best_fb = detect_chrome_font(
                chrome_text, font_size, font_weight, fb_names, font_family, Path(__file__).parent.parent
            )
        # bbox + weight grid chooser (only if Chrome didn't give us a decisive answer)
        best_fb = None
        if preferred_fb:
            best_fb = preferred_fb
        elif chrome_best_fb:
            best_fb = (chrome_best_fb, font_weight)
        else:
            best_fb = (
                choose_fallback_by_bbox(
                    src_path,
                    text_elem.get("id", ""),
                    fb_names,
                    target_bbox,
                    weights=weight_candidates,
                    base_weight=font_weight,
                )
                if src_path
                else (fb_names[0], None) if fb_names else None
            )
        best_family, best_weight = best_fb if best_fb else (None, None)
        fb_weight = int(
            max(100, min(900, best_weight if best_weight is not None else font_weight))
        )
        # re-order with winner first, then Chrome tie, then others
        ordered = []
        if best_family:
            ordered.append(best_family)
        if chrome_best_fb and chrome_best_fb not in ordered:
            ordered.append(chrome_best_fb)
        for fam in fb_names:
            if fam not in ordered:
                ordered.append(fam)
        fb_names = [f[0] if isinstance(f, tuple) else f for f in ordered]
        if best_family:
            fb_names = [best_family] + [c for c in fb_names if c != best_family]
        if (
            "No javascript" in text_content
            or text_elem.get("id") in ["text54", "text4"]
            or "☞" in text_content
        ):
            dbg(f"DEBUG FALLBACK: missing={missing_chars[:10]}... fb_names={fb_names}")
    
        fallback_font = None
        fallback_cmap = None
        best_cover = -1
        skip_coverage = False
        if preferred_candidate:
            fallback_font = preferred_candidate
            fallback_cmap = preferred_candidate[0].getBestCmap() or {}
            best_cover = len(missing_set)
            skip_coverage = True
            missing_set = set()
        # If Chrome told us the exact fallback, try it first and lock it in if it covers anything
        if chrome_best_fb:
            candidate = font_cache.get_font(
                chrome_best_fb,
                weight=fb_weight,
                style=font_style,
                stretch="normal",
                inkscape_spec=None,
                strict_family=False,
            )
            if candidate:
                tt_test, blob_test, idx_test = candidate
                if not _font_has_outlines(tt_test):
                    # Color-only fonts (e.g., Apple Color Emoji) lack outlines; fall back to next strategy
                    candidate = None
                else:
                    cmap_test = tt_test.getBestCmap() or {}
                    cov = sum(
                        1 for ch in missing_set if ord(ch) in cmap_test and cmap_test.get(ord(ch), 0) != 0
                    )
                    # Trust Chrome: even if cov==0 (unlikely for outline fonts), use it first
                    fallback_font = candidate
                    fallback_cmap = cmap_test
                    best_cover = cov if cov > 0 else len(missing_set)
                    skip_coverage = True
                    # if cov==0 we still assume Chrome rendered it; clear missing_set to avoid abort
                    missing_set = (
                        {ch for ch in missing_set if ord(ch) not in cmap_test}
                        if cov > 0
                        else set()
                    )
    
        def _sym_map(cp: int) -> int:
            return 0xF000 + cp if 0x20 <= cp <= 0xFF else cp

        def coverage(candidate_tt, cmap):
            return sum(
                1
                for ch in missing_set
                if _sym_map(ord(ch)) in cmap
                and cmap.get(_sym_map(ord(ch)), 0) != 0
            )
    
        # If no Chrome coverage, try bbox sampling on the missing chars to pick the closest visual match
        if not skip_coverage and missing_set:
            symbol_candidates = [
                "Helvetica",
                "Arial",
                "Segoe UI Symbol",
                "Times New Roman",
                "Symbola",
                "Apple Symbols",
                "Arial Unicode MS",
                "Noto Sans",
                "Noto Serif",
                "Last Resort",
            ]
            env_symbols = os.environ.get("T2P_SYMBOL_FALLBACKS")
            if env_symbols:
                for fam in env_symbols.split(","):
                    fam = fam.strip()
                    if fam and fam not in symbol_candidates:
                        symbol_candidates.append(fam)
            bbox_candidates = []
            for fam in fb_names + symbol_candidates:
                if fam not in bbox_candidates:
                    bbox_candidates.append(fam)
            # add dynamic candidates that actually cover the missing glyphs
            dyn = font_cache.fonts_with_coverage(
                {ord(ch) for ch in missing_set}, limit=8
            )
            for fam in dyn:
                if fam not in bbox_candidates:
                    bbox_candidates.append(fam)
            # keep bbox probing small to avoid loading many fonts
            if len(bbox_candidates) > 12:
                bbox_candidates = bbox_candidates[:12]
            bbox_best = score_candidates_by_bbox(
                src_path,
                list(missing_set),
                font_family,
                font_size,
                fb_weight,
                font_style,
                font_stretch,
                bbox_candidates,
                sample_size=min(5, len(missing_set)),
            ) if src_path else None
            if bbox_best:
                cand = font_cache.get_font(
                    bbox_best,
                    weight=fb_weight,
                    style=font_style,
                    stretch="normal",
                    inkscape_spec=None,
                    strict_family=False,
                )
                if cand:
                    tt_test, blob_test, idx_test = cand
                    cmap_test = tt_test.getBestCmap() or {}
                    cov = coverage(tt_test, cmap_test)
                    if cov > 0:
                        fallback_font = cand
                        fallback_cmap = cmap_test
                        best_cover = cov
                        skip_coverage = True
    
        if not skip_coverage:
            for fb in fb_names:
                candidate = None
                if fb.startswith(":lang="):
                    match = font_cache._match_font_with_fc(
                        fb, weight=fb_weight, style=font_style, stretch="normal"
                    )
                    if match:
                        try:
                            fp, findex = match
                            tt = (
                                TTFont(fp, fontNumber=findex)
                                if fp.suffix.lower() == ".ttc" or findex > 0
                                else TTFont(fp)
                            )
                            with open(fp, "rb") as f:
                                fb_blob = f.read()
                            candidate = (tt, fb_blob, findex)
                        except Exception:
                            candidate = None
                else:
                    candidate = font_cache.get_font(
                        fb,
                        weight=fb_weight,
                        style=font_style,
                        stretch="normal",
                        inkscape_spec=None,
                        strict_family=False,
                    )
    
                if candidate:
                    tt_test, blob_test, idx_test = candidate
                    if not _font_has_outlines(tt_test):
                        continue
                    cmap_test = tt_test.getBestCmap() or {}
                    cov = coverage(tt_test, cmap_test)
                    if cov == 0:
                        continue
                    if cov > best_cover:
                        best_cover = cov
                        fallback_font = candidate
                        fallback_cmap = cmap_test
                    if cov == len(missing_set):
                        # stop scanning once full coverage is achieved to avoid loading more fonts
                        break
                # If we've already achieved full coverage, exit outer loop too
                if best_cover == len(missing_set):
                    break
    
        # Dedicated symbol fallback for dingbats (keep separate from general fallback).
        if any(0x2600 <= ord(ch) <= 0x27FF for ch in missing_chars):
            symbol_missing = [
                ch for ch in missing_chars if 0x2600 <= ord(ch) <= 0x27FF
            ]
            candidate = None
            best_symbol = None
            best_cov = -1
            symbol_candidates = [
                "Noto Sans Symbols2",
                "Times New Roman",
                "Apple Symbols",
                "Symbola",
                "Segoe UI Symbol",
                "Arial Unicode MS",
                "Noto Sans Symbols",
            ]
            # 1) Platform-specific paths
            for p in _os_symbol_candidates():
                try:
                    tt = TTFont(p, lazy=False)
                    if not _font_has_outlines(tt):
                        continue
                    cmap_test = tt.getBestCmap() or {}
                    cov = sum(
                        1
                        for ch in symbol_missing
                        if ord(ch) in cmap_test and cmap_test.get(ord(ch), 0) != 0
                    )
                    if cov > best_cov:
                        with open(p, "rb") as f:
                            blob = f.read()
                        best_symbol = (tt, blob, 0)
                        best_cov = cov
                    if cov == len(symbol_missing):
                        break
                except Exception:
                    continue
            # 2) fontconfig/name fallbacks
            if best_symbol is None:
                for fam in symbol_candidates:
                    c = font_cache.get_font(
                        fam,
                        weight=400,
                        style="normal",
                        stretch="normal",
                        inkscape_spec=None,
                        strict_family=False,
                    )
                    if not c or not _font_has_outlines(c[0]):
                        continue
                    cmap_test = c[0].getBestCmap() or {}
                    cov = sum(
                        1
                        for ch in symbol_missing
                        if ord(ch) in cmap_test and cmap_test.get(ord(ch), 0) != 0
                    )
                    if cov > best_cov:
                        best_symbol = c
                        best_cov = cov
                    if cov == len(symbol_missing):
                        break
            candidate = best_symbol
            if candidate and _font_has_outlines(candidate[0]):
                symbol_ttfont, symbol_blob, symbol_index = candidate
                symbol_cmap = symbol_ttfont.getBestCmap() or {}
                symbol_glyph_set = symbol_ttfont.getGlyphSet()
                symbol_scale = (
                    (font_size / symbol_ttfont["head"].unitsPerEm)
                    if symbol_ttfont
                    else 1.0
                )
                # Remove symbol chars now covered so missing checks don't fail.
                missing_chars = [
                    ch
                    for ch in missing_chars
                    if not (
                        0x2600 <= ord(ch) <= 0x27FF
                        and ord(ch) in symbol_cmap
                        and symbol_cmap.get(ord(ch), 0) != 0
                    )
                ]
                missing_set = set(missing_chars)
    
        if fallback_font:
            fallback_ttfont, fallback_blob, fallback_index = fallback_font
            print(f"    → Loaded fallback font: {fallback_ttfont.reader.file.name}")
            fallback_units_per_em = fallback_ttfont["head"].unitsPerEm
            fallback_scale = font_size / fallback_units_per_em
            fallback_glyph_set = fallback_ttfont.getGlyphSet()
            # Remove chars now covered by the chosen fallback to avoid later promotion
            if fallback_cmap:
                missing_chars = [
                    ch
                    for ch in missing_chars
                    if ord(ch) not in fallback_cmap
                    or fallback_cmap.get(ord(ch), 0) == 0
                ]
                missing_set = set(missing_chars)
        else:
            fallback_ttfont = None
        # For symbol fonts, if cmap contains the PUA-mapped chars, treat as covered even
        # if glyph outline probing failed (many symbol fonts have empty glyphs for some entries).
        if font_family.lower() in symbol_families and missing_chars:
            still_missing = []
            for ch in missing_chars:
                cp = ord(ch)
                mapped = cp if cp >= 0xF000 else 0xF000 + cp
                if mapped in cmap and cmap.get(mapped, 0) != 0:
                    continue
                still_missing.append(ch)
            missing_chars = still_missing

        if missing_chars and (not fallback_font or best_cover <= 0):
            uniq = "".join(sorted(set(missing_chars)))
            raise MissingFontError(
                font_family,
                font_weight,
                font_style,
                font_stretch,
                f"Glyphs missing for chars '{uniq}' in font '{font_family}' and fallback",
            )
    
    # If primary is a symbol font, force primary to an outline-capable symbol font (PUA mapped)
    if font_family.lower() in symbol_families:
        symbol_priority = [
            "Webdings",
            "Wingdings",
            "Wingdings 2",
            "Wingdings 3",
            "Apple Symbols",
            "Symbola",
            "Segoe UI Symbol",
            "Noto Sans Symbols2",
            "Noto Sans Symbols",
            "Arial Unicode MS",
        ]
        for fam in symbol_priority:
            cand = font_cache.get_font(
                fam,
                weight=font_weight,
                style=font_style,
                stretch="normal",
                inkscape_spec=None,
                strict_family=False,
            )
            if cand:
                ttfont, font_blob, font_index = cand
                if _font_has_outlines(ttfont):
                    cmap = ttfont.getBestCmap() or {}
                    glyph_set = ttfont.getGlyphSet()
                    hb_font = hb.Font(hb.Face(hb.Blob(font_blob), font_index))
                    hb_font.scale = (ttfont["head"].unitsPerEm, ttfont["head"].unitsPerEm)
                    font_family = fam  # adopt outline symbol font as primary
                    break

    # If all chars are missing in the primary and a fallback covers everything, promote it to primary
    if missing_chars and len(missing_chars) == len(text_content):
        print(f"DEBUG promote fallback id={text_elem.get('id')} missing={missing_chars}")
        if cjk_ttfont and cjk_cmap and all(ord(ch) in cjk_cmap for ch in text_content):
            print("    → Switching primary to CJK fallback for full coverage")
            ttfont = cjk_ttfont
            cmap = cjk_cmap
            glyph_set = cjk_glyph_set
            hb_font = cjk_hb_font
            missing_chars = []
        elif fallback_ttfont and fallback_cmap and all(
            ord(ch) in fallback_cmap for ch in text_content
        ):
            print("    → Switching primary to general fallback for full coverage")
            ttfont = fallback_ttfont
            cmap = fallback_cmap
            glyph_set = fallback_glyph_set
            hb_font = fallback_hb_font
            missing_chars = []
    
    # 4. Get font metrics
    units_per_em = ttfont["head"].unitsPerEm
    scale = font_size / units_per_em
    if text_elem.get("id") == "text4" or "兛" in text_content:
        dbg(f"DEBUG text4: metrics upem={units_per_em} scale={scale}")
    # Note: transform_sx and transform_sy will be applied when generating path coordinates
    # but NOT to the font_size itself (transform is on the element, not the font)
    
    # Font coordinates have Y going up, SVG has Y going down
    # We need to flip Y, so we'll negate in the transform
    
    # 5. Unicode BiDi analysis and script detection
    # Split text into runs by BOTH direction (LTR/RTL) AND script (Latin/Arab/etc)
    
    # Get explicit direction from SVG attributes
    svg_direction = get_attr(text_elem, "direction", "ltr").lower()
    base_dir = "RTL" if svg_direction == "rtl" else "LTR"
    
    try:
        import unicodedata
    
        runs = []
        if not text_content:
            runs = [(0, 0, base_dir, "Latn")]
        else:
            # Get direction and script for each character
            char_props = []  # List of (direction, script)
    
            for char in text_content:
                # Determine direction
                bidi_class = unicodedata.bidirectional(char)
                if bidi_class in ("R", "AL", "RLE", "RLO"):
                    direction = "RTL"
                elif bidi_class in ("L", "LRE", "LRO"):
                    direction = "LTR"
                else:
                    direction = None  # Neutral
    
                # Determine script (simplified - just Latin vs Arabic for now)
                if bidi_class in ("R", "AL"):
                    script = "Arab"
                elif "\u0600" <= char <= "\u06ff":  # Arabic Unicode range
                    script = "Arab"
                elif 0x4E00 <= ord(char) <= 0x9FFF or 0x3400 <= ord(char) <= 0x4DBF:
                    script = "Hani"  # CJK
                elif char.isalpha():
                    script = "Latn"
                else:
                    script = None  # Neutral (numbers, punctuation, spaces)
    
                char_props.append((direction, script))
    
            # Resolve neutrals - inherit from previous non-neutral or base direction
            current_dir = base_dir
            current_script = "Latn"
    
            for i, (d, s) in enumerate(char_props):
                if d is not None:
                    current_dir = d
                if s is not None:
                    current_script = s
    
                # Fill in neutrals
                if char_props[i][0] is None:
                    char_props[i] = (current_dir, char_props[i][1])
                if char_props[i][1] is None:
                    char_props[i] = (char_props[i][0], current_script)
    
            # Extract runs - split when EITHER direction OR script changes
            run_start = 0
            current_dir, current_script = char_props[0]
    
            for i in range(1, len(char_props)):
                char_dir, char_script = char_props[i]
                if char_dir != current_dir or char_script != current_script:
                    # Direction or script changed, finish current run
                    runs.append((run_start, i, current_dir, current_script))
                    run_start = i
                    current_dir = char_dir
                    current_script = char_script
    
            # Add the final run
            runs.append((run_start, len(text_content), current_dir, current_script))
    
    except Exception as e:
        print(f"  ⚠️  BiDi/script analysis failed: {e}")
        runs = [(0, len(text_content), base_dir, "Latn")]
    
    # 6. Create HarfBuzz font
    if text_elem.get("id") == "text4" or "兛" in text_content:
        dbg("DEBUG text4: entering HB setup")
    try:
        # Ensure fallback_font is defined for later HB setup
        fallback_font = None if "fallback_font" not in locals() else fallback_font
        fallback_hb_font = None
        hb_blob = hb.Blob(font_blob)
        hb_face = hb.Face(
            hb_blob, font_index
        )  # CRITICAL: Must specify face index for TTC files
        hb_font = hb.Font(hb_face)
        hb_font.scale = (units_per_em, units_per_em)
    
        # Apply font variations (e.g. wght, opsz)
        if variation_settings:
            try:
                hb_font.set_variations(dict(variation_settings))
                # print(f"    ✓ Applied variations: {variation_settings}")
            except Exception as e:
                print(f"  ⚠️  Failed to apply font variations {variation_settings}: {e}")
    
        # Fallback HB font (if needed later)
        if fallback_font:
            fb_tt, fb_blob, fb_idx = fallback_font
            try:
                fb_face = hb.Face(hb.Blob(fb_blob), fb_idx)
                fb_font = hb.Font(fb_face)
                fb_units = fb_tt["head"].unitsPerEm
                fb_font.scale = (fb_units, fb_units)
                fallback_hb_font = fb_font
            except Exception:
                fallback_hb_font = None

        # Symbol HB font (dingbat fallback)
        if symbol_ttfont and symbol_blob is not None:
            try:
                sym_face = hb.Face(hb.Blob(symbol_blob), symbol_index or 0)
                sym_font = hb.Font(sym_face)
                sym_units = symbol_ttfont["head"].unitsPerEm
                sym_font.scale = (sym_units, sym_units)
                symbol_hb_font = sym_font
            except Exception:
                symbol_hb_font = None
    
        if text_content and len(text_content) == 1 and text_content in "☰":
            dbg(
                f"DEBUG icon '{text_content}': font_index={font_index}, ttfont_face={ttfont}, hb_face_index={hb_face.index}"
            )
        if "兛" in text_content or text_elem.get("id") == "text4":
            dbg("DEBUG text4: HarfBuzz font created successfully")
    except Exception as e:
        print(f"  ✗ Failed to create HarfBuzz font: {e}")
        return None
    if text_elem.get("id") == "text4" or "兛" in text_content:
        dbg("DEBUG text4: after HB setup, before runs")
    
    def _hb_features(n_bytes: int):
        feats = {}
        for tag, val in feature_settings:
            try:
                feats[tag] = val
            except Exception:
                continue
        return feats
    
    # Collect font-feature-settings (before shaping)
    feature_settings: list[tuple[str, int]] = []
    feat_raw = get_attr(text_elem, "font-feature-settings", None)
    if feat_raw:
        try:
            # format: 'kern' 0, "liga" 1, etc.
            for tag, val in re.findall(
                r"[\"']?([A-Za-z0-9]{4})[\"']?\\s+(-?\\d+)", feat_raw
            ):
                feature_settings.append((tag, int(val)))
        except Exception:
            feature_settings = []
    
    # 7. Chunk layout and anchor computation (per Inkscape plain-SVG behavior)
    # Split runs into chunks by font coverage and accumulate widths before anchoring.
    # This also gives us per-chunk metrics for underline placement.
    chunk_list = []  # list of dicts: {start,end,font_key,width,positions,infos,ttfont,glyph_set,scale,cmap}
    
    import bisect
    
    # Precompute glyph set for primary
    glyph_set_primary = ttfont.getGlyphSet()
    # Build global byte offsets for dx/dy mapping
    byte_offsets_global = [0]
    acc_global = 0
    for ch in text_content:
        acc_global += len(ch.encode("utf-8"))
        byte_offsets_global.append(acc_global)
    
    for run_start, run_end, direction, script in runs:
        run_text = text_content[run_start:run_end]
    
        if text_elem.get("id") == "text4" or "兛" in text_content:
            dbg(f"DEBUG text4: run '{run_text}' dir={direction} script={script}")
    
        # Segment run by font coverage (primary vs fallback)
        segments = []
        current_font = None
        seg_start = 0
        for idx, ch in enumerate(run_text):
            cp = ord(ch)
            # Special handling for CJK: prefer fallback if primary is likely not CJK
            # (heuristic: if script is Hani but font name doesn't suggest CJK)
            prefer_fallback = False
            if script == "Hani":
                # List of common CJK font substrings
                cjk_indicators = [
                    "cjk",
                    "mincho",
                    "gothic",
                    "song",
                    "kai",
                    "ming",
                    "hei",
                    "fang",
                    "noto sans sc",
                    "noto sans tc",
                    "noto sans jp",
                    "noto sans kr",
                    "pingfang",
                    "hiragino",
                ]
                primary_name = font_family.lower()
                if not any(ind in primary_name for ind in cjk_indicators):
                    prefer_fallback = True
    
            # Check symbol font PUA first
            is_symbol = (font_family or "").lower() in (
                "webdings",
                "wingdings",
                "wingdings 2",
                "wingdings 3",
                "symbol",
            )
            # Webdings/Wingdings map ASCII 0x20-0xFF to the PUA block at +0xF000.
            # text_content is sometimes pre-mapped to PUA already, so only add the
            # offset when we see a non-PUA codepoint to avoid double-shifting and
            # false "missing glyph" errors (e.g., Webdings text52).
            pua_cp = cp if cp >= 0xF000 else 0xF000 + cp
            if is_symbol:
                dbg(
                    f"DEBUG symbol seg: cp=0x{cp:04X} pua_cp=0x{pua_cp:04X} in_cmap={pua_cp in cmap if cmap else False} val={cmap.get(pua_cp) if cmap else None} primary={getattr(ttfont.reader.file, 'name', '')}"
                )
                # Trust symbol fonts: they often lack Unicode cmap; we already picked a symbol font.
                font_key = "primary"
                if current_font is None:
                    current_font = font_key
                    seg_start = idx
                    continue
                if font_key != current_font:
                    segments.append((current_font, seg_start, idx))
                    current_font = font_key
                    seg_start = idx
                continue
    
            if 0x4E00 <= cp <= 0x9FFF:
                print(
                    f"DEBUG CJK: cp={cp} in_cjk={cp in cjk_cmap if cjk_cmap else 'None'} in_fallback={cp in fallback_cmap if fallback_cmap else 'None'} in_primary={cp in cmap}"
                )
    
            if is_symbol and pua_cp in cmap and cmap.get(pua_cp, 0) != 0:
                font_key = "primary"
            elif (
                cjk_cmap
                and (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF)
                and cp in cjk_cmap
                and cjk_cmap.get(cp, 0) != 0
            ):
                # Prioritize CJK font for CJK characters
                font_key = "cjk"
            elif (
                0x2600 <= cp <= 0x27FF
                and symbol_cmap
                and cp in symbol_cmap
                and symbol_cmap.get(cp, 0) != 0
            ):
                font_key = "symbol"
            elif (
                prefer_fallback
                and fallback_cmap
                and cp in fallback_cmap
                and fallback_cmap.get(cp, 0) != 0
            ):
                font_key = "fallback"
            elif cp in cmap and cmap.get(cp, 0) != 0:
                font_key = "primary"
            elif (
                fallback_cmap and cp in fallback_cmap and fallback_cmap.get(cp, 0) != 0
            ):
                if 0x0600 <= cp <= 0x06FF and fallback_ttfont:
                    dbg(
                        f"DEBUG ARABIC: cp={cp} found in fallback {fallback_ttfont.reader.file.name}"
                    )
                font_key = "fallback"
            elif cjk_cmap and cp in cjk_cmap and cjk_cmap.get(cp, 0) != 0:
                # Try CJK for non-CJK chars if missing elsewhere
                font_key = "cjk"
            else:
                raise MissingFontError(
                    font_family,
                    font_weight,
                    font_style,
                    font_stretch,
                    f"Glyph {repr(ch)} missing in primary and fallback fonts",
                )
            if current_font is None:
                current_font = font_key
                seg_start = idx
            elif font_key != current_font:
                segments.append((current_font, seg_start, idx))
                current_font = font_key
                seg_start = idx
        if current_font is not None:
            segments.append((current_font, seg_start, len(run_text)))
    
        # Shape each segment and store
        for font_key, s, e in segments:
            seg_text = run_text[s:e]
            local_byte_offsets = [0]
            acc_local = 0
            for ch in seg_text:
                acc_local += len(ch.encode("utf-8"))
                local_byte_offsets.append(acc_local)
            # Debug print
            dbg(
                f"DEBUG layout_line: font_family='{font_family}' font_key='{font_key}' text='{seg_text}'"
            )
            if font_key == "primary":
                seg_ttfont = ttfont
                seg_scale = scale
                seg_hb_font = hb_font
                seg_glyph_set = glyph_set_primary
                seg_cmap = cmap
                if "text4" in str(text_elem.get("id")) or "兛" in text_content:
                    dbg(
                        f"DEBUG text4: Using PRIMARY font. Scale={scale}, UnitsPerEm={units_per_em}"
                    )
            elif font_key == "cjk":
                seg_ttfont = cjk_ttfont
                seg_scale = cjk_scale
                seg_hb_font = cjk_hb_font
                seg_glyph_set = cjk_glyph_set
                seg_cmap = cjk_cmap
                if "text4" in str(text_elem.get("id")) or "兛" in text_content:
                    dbg(f"DEBUG text4: Using CJK font. Scale={cjk_scale}")
                    if cjk_ttfont:
                        dbg(f"DEBUG text4: CJK Font Name: {cjk_ttfont.reader.file.name}")
                        dbg(f"DEBUG text4: CJK UnitsPerEm: {cjk_ttfont['head'].unitsPerEm}")
            elif font_key == "symbol":
                seg_ttfont = symbol_ttfont
                seg_scale = symbol_scale
                seg_hb_font = symbol_hb_font
                seg_glyph_set = symbol_glyph_set
                seg_cmap = symbol_cmap
                if "text4" in str(text_elem.get("id")) or "兛" in text_content:
                    dbg(f"DEBUG text4: Using SYMBOL font. Scale={symbol_scale}")
                    if symbol_ttfont and hasattr(symbol_ttfont, "reader"):
                        dbg(f"DEBUG text4: Symbol Font Name: {symbol_ttfont.reader.file.name}")
            else:  # fallback
                seg_ttfont = fallback_ttfont
                seg_scale = fallback_scale
                seg_hb_font = fallback_hb_font
                seg_glyph_set = fallback_glyph_set
                seg_cmap = fallback_cmap
                if "text4" in str(text_elem.get("id")) or "兛" in text_content:
                    dbg(f"DEBUG text4: Using FALLBACK font. Scale={fallback_scale}")
                    if fallback_ttfont:
                        dbg(f"DEBUG text4: Fallback Font Name: {fallback_ttfont.reader.file.name}")
                        dbg(f"DEBUG text4: Fallback UnitsPerEm: {fallback_ttfont['head'].unitsPerEm}")
    
            buf = hb.Buffer()
    
            # Handle Symbol font PUA remapping
            if font_key == "primary" and font_family.lower() in (
                "webdings",
                "wingdings",
                "wingdings 2",
                "wingdings 3",
                "symbol",
            ):
                remapped_text = ""
                for c in seg_text:
                    cp = ord(c)
                    if 0x20 <= cp <= 0xFF:
                        remapped_text += chr(0xF000 + cp)
                    else:
                        remapped_text += c
                buf.add_str(remapped_text)
            else:
                if text_elem.get("id") == "text52":
                    print(
                        f"    DEBUG text52: font_key={font_key} family='{font_family}' seg_text='{seg_text}'"
                    )
                # Remap to PUA for symbol fonts if needed (fallback path)
                # We detect symbol fonts by name. This is a heuristic.
                # We only remap if the characters are in ASCII range (0-127)
                font_family_lower = font_family.lower() if font_family else ""
                if font_family_lower in (
                    "webdings",
                    "wingdings",
                    "wingdings 2",
                    "wingdings 3",
                    "symbol",
                ):
                    new_seg_text = []
                    for ch in seg_text:
                        cp = ord(ch)
                        if 0x20 <= cp <= 0x7E:  # ASCII printable
                            new_seg_text.append(chr(0xF000 + cp))
                        else:
                            new_seg_text.append(ch)
                    seg_text = "".join(new_seg_text)
    
                buf.add_str(seg_text)
    
            buf.direction = "rtl" if direction == "RTL" else "ltr"
            buf.guess_segment_properties()
            hb.shape(
                seg_hb_font, buf, features=_hb_features(len(seg_text.encode("utf-8")))
            )
            seg_infos = buf.glyph_infos
            seg_positions = buf.glyph_positions
    
            if "javascript" in text_content.lower() or text_elem.get("id") in [
                "text53",
                "text54",
            ]:
                dbg(f"\nDEBUG SHAPING elem_id={text_elem.get('id')}:")
                dbg(f"  Text segment: '{seg_text}'")
                dbg(f"  Font family: {font_family} (key={font_key})")
                if hasattr(seg_ttfont, "reader") and hasattr(seg_ttfont.reader, "file"):
                    dbg(f"  Font file: {seg_ttfont.reader.file.name}")
                dbg(f"  Scale: {seg_scale}")
                dbg(f"  Glyphs:")
                for i, (info, pos) in enumerate(zip(seg_infos, seg_positions)):
                    dbg(
                        f"    [{i}] char_idx={info.cluster} codepoint={info.codepoint} x_adv={pos.x_advance} x_off={pos.x_offset} y_off={pos.y_offset}"
                    )
    
            width = sum(p.x_advance for p in seg_positions) * (seg_scale or 1.0)
    
            chunk_list.append(
                {
                    "run_start": run_start,
                    "start": run_start + s,
                    "end": run_start + e,
                    "font_key": font_key,
                    "width": width,
                    "infos": seg_infos,
                    "positions": seg_positions,
                    "ttfont": seg_ttfont,
                    "glyph_set": seg_glyph_set,
                    "scale": seg_scale,
                    "cmap": seg_cmap,
                    "direction": direction,
                    "buf": buf,
                    "local_offset": s,
                    "run_text": run_text,
                    "local_byte_offsets": local_byte_offsets,
                }
            )
    
    # 8. Shape text with HarfBuzz and render glyphs (chunk-based, anchor once)
    import bisect
    
    all_paths = []
    advance_x = 0.0  # legacy total advance across lines
    line_decors: list[tuple[float, float, float]] = []  # (start_x, end_x, baseline_y)
    
    path_len = path_obj.length() if path_obj is not None else None
    
    # Group chunks by baseline (y) to anchor per line (handles multiple tspans sharing a line)
    lines: list[list[dict]] = []
    current_line = []
    last_y = y
    for chunk in chunk_list:
        # Assume same y for now; text in this converter uses explicit y per text/tspan
        # If y changes (different tspans), start new line
        if (
            current_line
            and chunk.get("line_y") is not None
            and chunk["line_y"] != last_y
        ):
            lines.append(current_line)
            current_line = []
        current_line.append(chunk)
        chunk["line_y"] = y  # preserve baseline
        last_y = y
    if current_line:
        lines.append(current_line)
    
    def _measure_line_width(line_chunks: list[dict]) -> float:
        """Compute visual line width like Inkscape: sum advances & dx/spacing; trim trailing spacing."""
        width = 0.0
        last_letter = 0.0
        last_word = 0.0
        for chunk in line_chunks:
            seg_scale = chunk["scale"] or 1.0
            seg_infos = chunk["infos"]
            seg_positions = chunk["positions"]
            run_text = chunk["run_text"]
            local_offset = chunk["local_offset"]
            seg_len = chunk["end"] - chunk["start"]
            seg_text = run_text[local_offset : local_offset + seg_len]
    
            local_byte_offsets = [0]
            acc_local = 0
            for ch in seg_text:
                acc_local += len(ch.encode("utf-8"))
                local_byte_offsets.append(acc_local)
    
            cursor = 0.0
            for info, pos in zip(seg_infos, seg_positions):
                cluster = info.cluster
                char_idx_local = max(
                    0, bisect.bisect_right(local_byte_offsets, cluster) - 1
                )
                char_idx = chunk["start"] + char_idx_local
                current_dx = (
                    dx_list[char_idx] if dx_list and char_idx < len(dx_list) else 0.0
                )
                add_spacing = letter_spacing
                is_space = text_content[char_idx : char_idx + 1] == " "
                if is_space:
                    add_spacing += word_spacing
                    last_word = word_spacing
                else:
                    last_word = 0.0
                adv = (pos.x_advance * seg_scale) + current_dx + add_spacing
                if chunk.get("direction", "LTR") == "RTL":
                    cursor -= adv
                else:
                    cursor += adv
                last_letter = letter_spacing
            width += abs(cursor)
    
            if DEBUG_ENABLED and "No javascript" in run_text:
                dbg(
                    "DEBUG MEASURE: run_text='%s' glyph_count=%s cursor=%s width_so_far=%s",
                    run_text,
                    len(seg_infos),
                    cursor,
                    width,
                )
    
        width -= last_letter
        width -= last_word
        return width
    
    for line_chunks in lines:
        # Use base_dir (from SVG attribute) for alignment logic to match SVG spec/Chrome
        # This fixes the "Inkscape Arabic bug" where Inkscape ignores direction:ltr
        align_dir = base_dir
        line_dirs = {chunk.get("direction", "LTR") for chunk in line_chunks}
        mixed_dir = "RTL" in line_dirs and "LTR" in line_dirs

        line_width = _measure_line_width(line_chunks)
        if text_anchor == "middle":
            line_anchor_offset = -line_width / 2.0
        elif text_anchor == "end":
            line_anchor_offset = 0.0 if align_dir == "RTL" else -line_width
        else:
            line_anchor_offset = -line_width if align_dir == "RTL" else 0.0
    
        line_baseline = line_chunks[0].get("line_y", y) if line_chunks else y
    
        def _chunk_width(chunk: dict) -> float:
            seg_scale = chunk["scale"] or 1.0
            seg_infos = chunk["infos"]
            seg_positions = chunk["positions"]
            run_text = chunk["run_text"]
            local_offset = chunk["local_offset"]
            seg_len = chunk["end"] - chunk["start"]
            seg_text = run_text[local_offset : local_offset + seg_len]
            local_byte_offsets = [0]
            acc_local = 0
            for ch in seg_text:
                acc_local += len(ch.encode("utf-8"))
                local_byte_offsets.append(acc_local)
            cursor = 0.0
            for info, pos in zip(seg_infos, seg_positions):
                cluster = info.cluster
                char_idx_local = max(
                    0, bisect.bisect_right(local_byte_offsets, cluster) - 1
                )
                char_idx = chunk["start"] + char_idx_local
                current_dx = (
                    dx_list[char_idx] if dx_list and char_idx < len(dx_list) else 0.0
                )
                add_spacing = letter_spacing
                if text_content[char_idx : char_idx + 1] == " ":
                    add_spacing += word_spacing
                cursor += (pos.x_advance * seg_scale) + current_dx + add_spacing
            return abs(cursor - letter_spacing)
    
        # Unified cursor for mixed BiDi flow
        # We process chunks in logical order (as they appear in the list)
        # and advance a single cursor. This ensures "100% " (LTR) comes before "ARABIC" (RTL)
        # in the visual layout if that's how they are ordered in the runs.
    
        current_x = x + line_anchor_offset
    
        for chunk in line_chunks:
            seg_ttfont = chunk["ttfont"]
            seg_scale = chunk["scale"] or 1.0
            seg_infos = chunk["infos"]
            seg_positions = chunk["positions"]
            seg_glyph_set = chunk["glyph_set"]
            run_text = chunk["run_text"]
            local_offset = chunk["local_offset"]
            seg_len = chunk["end"] - chunk["start"]
            seg_text = run_text[local_offset : local_offset + seg_len]
    
            chunk_width = _chunk_width(chunk)
            chunk_dir = chunk.get("direction", "LTR")
    
            if "No javascript" in text_content:
                print(
                    f"DEBUG LAYOUT: font={font_family} x={x} line_width={line_width} anchor={text_anchor} offset={line_anchor_offset} dir={chunk_dir} chunk_width={chunk_width}"
                )
    
            # Determine start position for this chunk
            if chunk_dir == "RTL":
                # For RTL chunk, we occupy [current_x, current_x + chunk_width]
                # But glyphs are drawn from right to left, so we might need to adjust
                # how we calculate 'chunk_start' for the glyph loop.
                # In the loop below, 'chunk_start' is the origin for the first glyph.
                # If we iterate glyphs in logical order (which HarfBuzz does),
                # for RTL they should be placed starting from the right edge?
                # HarfBuzz positions are usually visual.
    
                # Let's assume standard LTR flow of chunks:
                chunk_start = current_x
    
                # But wait, if the chunk is RTL, the glyphs inside might need
                # to be offset differently.
                # If we use the same logic as before:
                # chunk_start = x + line_anchor_offset + (line_width - rtl_cursor - chunk_width)
                # That was for right-aligned pile.
    
                # For inline RTL:
                # The chunk starts at current_x.
                # We need to ensure the glyphs land in [current_x, current_x + chunk_width].
                # If we rely on the 'cursor' logic inside the loop:
                # It initializes 'cursor' to 0 (or chunk_width for RTL?).
                pass
            else:
                chunk_start = current_x
    
            # We'll handle the internal cursor logic inside the loop
            # But we need to pass the correct 'chunk_start' to the loop
            # For now, let's stick to the single cursor advancement
    
            # Update for next chunk
            # current_x += chunk_width # We do this AFTER the loop or implicitly
    
            # RE-DESIGN of the loop below:
            # We need to calculate absolute positions for glyphs.
    
            # Let's use a local cursor for the chunk
            chunk_cursor = 0.0
            # if chunk_dir == 'RTL':
            #     chunk_cursor = chunk_width # WRONG if chunk_origin is already shifted
    
            # For mixed-direction lines, HarfBuzz already outputs RTL glyphs in visual order.
            # For pure RTL lines, keep legacy right-edge placement.
            if chunk_dir == "RTL" and not mixed_dir:
                chunk_origin = current_x + chunk_width
            else:
                chunk_origin = current_x
            local_byte_offsets = chunk.get("local_byte_offsets")
            if not local_byte_offsets:
                local_byte_offsets = [0]
                acc_local = 0
                for ch in seg_text:
                    acc_local += len(ch.encode("utf-8"))
                    local_byte_offsets.append(acc_local)

            for info, pos in zip(seg_infos, seg_positions):
                # HarfBuzz returns codepoint indices (not byte indices) when using add_str with Python strings
                cluster = info.cluster
                char_idx_local = max(
                    0, bisect.bisect_right(local_byte_offsets, cluster) - 1
                )
                char_idx = chunk["start"] + char_idx_local
                current_dx = (
                    dx_list[char_idx] if dx_list and char_idx < len(dx_list) else 0.0
                )
                current_dy = (
                    dy_list[char_idx] if dy_list and char_idx < len(dy_list) else 0.0
                )
    
                # Calculate advance width for this glyph
                add_spacing = letter_spacing
                if text_content[char_idx : char_idx + 1] == " ":
                    add_spacing += word_spacing
                adv = (pos.x_advance * seg_scale) + add_spacing
    
                # Apply dx to cursor (accumulate shift)
                chunk_cursor += current_dx
    
                if chunk_dir == "RTL" and not mixed_dir:
                    chunk_cursor -= adv
                    glyph_origin = chunk_origin + chunk_cursor
                else:
                    glyph_origin = chunk_origin + chunk_cursor
                    chunk_cursor += adv
    
                glyph_id = info.codepoint
                try:
                    glyph_name = seg_ttfont.getGlyphName(glyph_id)
                except Exception:
                    glyph_name = None
    
                if DEBUG_ENABLED and any(
                    x in text_content for x in ["Λοπ", "No javascript", "lkœtrëå", "兛"]
                ):
                    has_path = False
                    if glyph_name and glyph_name in seg_glyph_set:
                        pen = DecomposingRecordingPen(seg_glyph_set)
                        seg_glyph_set[glyph_name].draw(pen)
                        dbg(f"    DEBUG PEN VALUE: {pen.value}")
                        if pen.value:
                            has_path = True
                    dbg(
                        f"    DEBUG_GLYPH: char='{text_content[char_idx] if char_idx < len(text_content) else '?'}' cp={ord(text_content[char_idx]) if char_idx < len(text_content) else -1} gid={glyph_id} name={glyph_name} has_path={has_path} cluster={cluster} char_idx={char_idx}"
                    )

                    if "兛" in text_content:
                        dbg(
                            f"    DEBUG COND CHECK: has_path={has_path} content='{text_content}' id='{text_elem.get('id')}'"
                        )
                    if has_path and (
                        "No javascript" in text_content
                        or "text4" in str(text_elem.get("id"))
                        or "兛" in text_content
                    ):
                        # Print path bounds or start
                        pen = DecomposingRecordingPen(seg_glyph_set)
                        seg_glyph_set[glyph_name].draw(pen)
                        # Simple check of first move
                        if pen.value:
                            dbg(
                                "    DEBUG_PATH: %s (Scale: %s, Offset: %s, %s)",
                                pen.value,
                                seg_scale,
                                current_dx,
                                0,
                            )

                    sys.stdout.flush()
    
                # If glyph_name is None or not in seg_glyph_set, it's truly missing.
                # If glyph_name is '.notdef' or glyph_id is 0, we check if it has a path.
                glyph_is_notdef_or_zero = glyph_name == ".notdef" or glyph_id == 0

                glyph = seg_glyph_set.get(glyph_name) if glyph_name else None

                # If glyph missing, try shaping/drawing with fallback font
                if glyph is None or glyph_is_notdef_or_zero:
                    drew_fallback = False
                    if (
                        fallback_hb_font
                        and fallback_glyph_set
                        and fallback_ttfont
                        and fallback_cmap
                        and _sym_map(ord(text_content[char_idx])) in fallback_cmap
                        and fallback_cmap.get(_sym_map(ord(text_content[char_idx])), 0) != 0
                    ):
                        try:
                            fb_buf = hb.Buffer()
                            ch_code = _sym_map(ord(text_content[char_idx])) if font_family.lower() in symbol_families else ord(text_content[char_idx])
                            fb_buf.add_str(chr(ch_code))
                            fb_buf.direction = "rtl" if direction == "RTL" else "ltr"
                            fb_buf.guess_segment_properties()
                            hb.shape(
                                fallback_hb_font,
                                fb_buf,
                                features=_hb_features(
                                    len(text_content[char_idx].encode("utf-8"))
                                ),
                            )
                            fb_info = fb_buf.glyph_infos[0]
                            fb_pos = fb_buf.glyph_positions[0]
                            fb_gid = fb_info.codepoint
                            fb_name = fallback_ttfont.getGlyphName(fb_gid)
                            fb_glyph = fallback_glyph_set.get(fb_name)
                            if fb_glyph:
                                fb_pen = DecomposingRecordingPen(fallback_glyph_set)
                                fb_glyph.draw(fb_pen)
                                recording = fb_pen.value
                                seg_scale = fallback_scale  # use fallback scale for this glyph
                                pos = fb_pos
                                glyph_name = fb_name
                                glyph_is_notdef_or_zero = False
                                drew_fallback = True
                        except Exception:
                            drew_fallback = False

                    if not drew_fallback:
                        adv_na = (pos.x_advance * seg_scale) + current_dx + letter_spacing
                        if text_content[char_idx : char_idx + 1] == " ":
                            adv_na += word_spacing
                        if chunk_dir == "RTL":
                            chunk_cursor -= adv_na
                        else:
                            chunk_cursor += adv_na
                        continue
    
                pen = DecomposingRecordingPen(seg_glyph_set if glyph_name in (seg_glyph_set or {}) else fallback_glyph_set)
                try:
                    glyph.draw(pen)
                except Exception as e:
                    print(f"    ⚠️  Glyph draw failed for {glyph_name}: {e}")
                    adv_na = (pos.x_advance * seg_scale) + current_dx + letter_spacing
                    if text_content[char_idx : char_idx + 1] == " ":
                        adv_na += word_spacing
                    if chunk_dir == "RTL":
                        cursor_chunk -= adv_na
                    else:
                        cursor_chunk += adv_na
                    continue
                recording = pen.value
    
                glyph_offset = 0.0
    
                if path_obj is not None and path_len and path_len > 0:
                    # Calculate offset along the path
                    # glyph_origin is the absolute X position in the text line
                    # We need the offset relative to the start of the line (x)
                    # This preserves line_anchor_offset in the position.
    
                    dist_along_path = path_start_offset + (glyph_origin - x)
    
                    # Apply dx
                    dist_along_path += current_dx
    
                    # Clamp distance to path length to avoid errors
                    dist_along_path = max(0.0, min(path_len, dist_along_path))
    
                    try:
                        base_point = path_obj.point(dist_along_path)
                        tangent_unit = path_obj.tangent(dist_along_path)
                    except Exception:
                        # Fallback if point/tangent fails even after clamping
                        base_point = complex(0, 0)
                        tangent_unit = complex(1, 0)
                    if tangent_unit == 0:
                        tangent_unit = complex(1, 0)
                    t_len = abs(tangent_unit)
                    tangent_unit = tangent_unit / t_len
                    normal_unit = complex(-tangent_unit.imag, tangent_unit.real)
                    offset_normal = (pos.y_offset * seg_scale) + current_dy
                    base_x = base_point.real + normal_unit.real * offset_normal
                    base_y = base_point.imag + normal_unit.imag * offset_normal
    
                    cos_t = tangent_unit.real
                    sin_t = tangent_unit.imag
    
                    transformed_recording = []
                    for op, args in recording:
                        if op in ["moveTo", "lineTo"]:
                            px, py = args[0]
                            lx = px * seg_scale
                            ly = -py * seg_scale
                            rx = lx * cos_t - ly * sin_t
                            ry = lx * sin_t + ly * cos_t
                            new_x = base_x + rx
                            new_y = base_y + ry
                            if baked_matrix:
                                a, b, c, d, e, f = baked_matrix
                                new_x, new_y = (
                                    a * new_x + c * new_y + e,
                                    b * new_x + d * new_y + f,
                                )
                            transformed_recording.append((op, [(new_x, new_y)]))
                        elif op == "qCurveTo":
                            new_args = []
                            for px, py in args:
                                lx = px * seg_scale
                                ly = -py * seg_scale
                                rx = lx * cos_t - ly * sin_t
                                ry = lx * sin_t + ly * cos_t
                                nx = base_x + rx
                                ny = base_y + ry
                                if baked_matrix:
                                    a, b, c, d, e, f = baked_matrix
                                    nx, ny = (a * nx + c * ny + e, b * nx + d * ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == "curveTo":
                            new_args = []
                            for px, py in args:
                                lx = px * seg_scale
                                ly = -py * seg_scale
                                rx = lx * cos_t - ly * sin_t
                                ry = lx * sin_t + ly * cos_t
                                nx = base_x + rx
                                ny = base_y + ry
                                if baked_matrix:
                                    a, b, c, d, e, f = baked_matrix
                                    nx, ny = (a * nx + c * ny + e, b * nx + d * ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == "closePath":
                            transformed_recording.append((op, args))
                else:
                    # Calculate glyph position based on chunk_origin and chunk_cursor
                    # Ensure glyph_origin is defined (it should be from above)
                    glyph_x = glyph_origin + (pos.x_offset * seg_scale) - glyph_offset
                    glyph_y = line_baseline + (pos.y_offset * seg_scale) + current_dy
    
                    transformed_recording = []
                    for op, args in recording:
                        if op in ["moveTo", "lineTo"]:
                            px, py = args[0]
                            new_x = px * seg_scale + glyph_x
                            new_y = -py * seg_scale + glyph_y
                            if baked_matrix:
                                a, b, c, d, e, f = baked_matrix
                                new_x, new_y = (
                                    a * new_x + c * new_y + e,
                                    b * new_x + d * new_y + f,
                                )
                            transformed_recording.append((op, [(new_x, new_y)]))
                        elif op == "qCurveTo":
                            new_args = []
                            # Handle implied on-curve points (None) in qCurveTo
                            # TrueType quadratic splines can have off-curve points with implied on-curve midpoints.
                            # However, RecordingPen usually delivers explicit points.
                            # If we get None, it's likely an implied point.
                            # We need to interpolate it from the previous and next points.
    
                            # Flatten the list of points, handling None
                            clean_points = []
                            for i, point in enumerate(args):
                                if point is not None:
                                    clean_points.append(point)
                                else:
                                    # Interpolate midpoint between prev and next
                                    # Note: This is a simplification. Real TT handling is more complex.
                                    # But for drawing, we just need a coordinate.
                                    if (
                                        i > 0
                                        and i < len(args) - 1
                                        and args[i - 1] is not None
                                        and args[i + 1] is not None
                                    ):
                                        p0 = args[i - 1]
                                        p1 = args[i + 1]
                                        mid_x = (p0[0] + p1[0]) / 2
                                        mid_y = (p0[1] + p1[1]) / 2
                                        clean_points.append((mid_x, mid_y))
                                    elif i > 0 and args[i - 1] is not None:
                                        # End of list None? Use prev point (degenerate)
                                        clean_points.append(args[i - 1])
                                    else:
                                        # Start of list None? Should not happen for qCurveTo
                                        clean_points.append((0, 0))  # Fallback
    
                            for px, py in clean_points:
                                nx = px * seg_scale + glyph_x
                                ny = -py * seg_scale + glyph_y
                                if baked_matrix:
                                    a, b, c, d, e, f = baked_matrix
                                    nx, ny = (a * nx + c * ny + e, b * nx + d * ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == "curveTo":
                            new_args = []
                            for px, py in args:
                                nx = px * seg_scale + glyph_x
                                ny = -py * seg_scale + glyph_y
                                if baked_matrix:
                                    a, b, c, d, e, f = baked_matrix
                                    nx, ny = (a * nx + c * ny + e, b * nx + d * ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == "closePath":
                            transformed_recording.append((op, args))
    
                path_data = recording_pen_to_svg_path(transformed_recording, precision)
                if path_data:
                    all_paths.append(path_data)

            current_x += chunk_width

        # Track per-line geometry for decorations
        if path_obj is None:
            start_x_line = x + line_anchor_offset
            end_x_line = start_x_line + line_width
            line_decors.append((start_x_line, end_x_line, line_baseline))
        advance_x = max(advance_x, line_width)
    
    # Generate text decorations (underline, line-through)
    decoration = get_attr(text_elem, "text-decoration", "none")
    # Also check style for text-decoration
    style_decoration = re.search(
        r"text-decoration:\s*([^;]+)", text_elem.get("style", "")
    )
    if style_decoration:
        decoration = style_decoration.group(1)
    
    if decoration and decoration != "none" and line_decors:
        # Get font metrics for decoration
        # Default values if metrics are missing
        underline_position = -0.1 * units_per_em
        underline_thickness = 0.05 * units_per_em
        strikeout_position = 0.3 * units_per_em
        strikeout_thickness = 0.05 * units_per_em
    
        # Use metrics from the dominant chunk font (first chunk) for decoration
        dom_tt = chunk_list[0]["ttfont"] if chunk_list else ttfont
        try:
            post = dom_tt["post"]
            if hasattr(post, "underlinePosition"):
                underline_position = post.underlinePosition
            if hasattr(post, "underlineThickness"):
                underline_thickness = post.underlineThickness
            if "OS/2" in dom_tt:
                os2 = dom_tt["OS/2"]
                if hasattr(os2, "yStrikeoutPosition"):
                    strikeout_position = os2.yStrikeoutPosition
                if hasattr(os2, "yStrikeoutSize"):
                    strikeout_thickness = os2.yStrikeoutSize
        except Exception:
            pass
    
        fmt = f"{{:.{precision}f}}"
    
        for start_x, end_x, baseline_y in line_decors:
            deco_paths = []
            if "underline" in decoration:
                y_pos = baseline_y - (underline_position * scale)
                thickness = underline_thickness * scale
                deco_paths.append(
                    [
                        (start_x, y_pos),
                        (end_x, y_pos),
                        (end_x, y_pos + thickness),
                        (start_x, y_pos + thickness),
                    ]
                )
    
            if "line-through" in decoration:
                y_pos = baseline_y - (strikeout_position * scale)
                thickness = strikeout_thickness * scale
                deco_paths.append(
                    [
                        (start_x, y_pos),
                        (end_x, y_pos),
                        (end_x, y_pos + thickness),
                        (start_x, y_pos + thickness),
                    ]
                )
    
            for rect in deco_paths:
                pts = []
                for px, py in rect:
                    if baked_matrix:
                        a, b, c, d, e, f = baked_matrix
                        px, py = (a * px + c * py + e, b * px + d * py + f)
                    pts.append((px, py))
                deco_path = f"M {fmt.format(pts[0][0])} {fmt.format(pts[0][1])} L {fmt.format(pts[1][0])} {fmt.format(pts[1][1])} L {fmt.format(pts[2][0])} {fmt.format(pts[2][1])} L {fmt.format(pts[3][0])} {fmt.format(pts[3][1])} Z"
                all_paths.append(deco_path)
    
    if not all_paths:
        print(
            f"  ✗ No path data generated for text '{text_content}' "
            f"(chunks={len(chunk_list)} infos={[len(ch['infos']) for ch in chunk_list] if chunk_list else []})"
        )
        return None
    
    # 8. Create path element with SVG namespace
    path_elem = ET.Element("{http://www.w3.org/2000/svg}path")
    
    # Copy presentation attributes from the source element
    # This ensures fill, stroke, etc. are preserved
    presentation_attrs = {
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-opacity",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-dasharray",
        "stroke-dashoffset",
        "opacity",
        "style",
        "class",
        "filter",
        "mask",
        "clip-path",
        "transform",
    }
    
    for k, v in text_elem.attrib.items():
        if k in presentation_attrs:
            path_elem.set(k, v)
    
    # Ensure style is copied if present (it might contain fill/stroke)
    if "style" in text_elem.attrib and "style" not in path_elem.attrib:
        path_elem.set("style", text_elem.attrib["style"])
    
    # Handle text-decoration (underline, line-through)
    decoration = get_attr(text_elem, "text-decoration", "none")
    if decoration != "none":
        # We need font metrics to position the decoration
        # Use the first run's font metrics as a baseline
        if runs and runs[0][0] < len(text_content):
            # Find the font used for the first run
            # This is a simplification; ideally we'd check each run's font
            # but usually decoration is consistent across the element
    
            # Re-resolve the font for metrics (we didn't store the TTFont object in a way easily accessible here,
            # but we can grab it from the cache using the same params)
            # Actually, we can just use the metrics from the first chunk of the first line if available
    
            # Let's look at the first chunk of the first line
            first_chunk = None
            if lines and lines[0]:
                first_chunk = lines[0][0]
    
            if first_chunk:
                ttfont = first_chunk["ttfont"]
                units_per_em = ttfont["head"].unitsPerEm
                scale = font_size / units_per_em  # This is the font scale
    
                # Get underline/strikeout metrics from 'post' or 'OS/2' table
                underline_position = -100  # Default
                underline_thickness = 50  # Default
                strikeout_position = 250  # Default
                strikeout_thickness = 50  # Default
    
                if "post" in ttfont:
                    underline_position = ttfont["post"].underlinePosition
                    underline_thickness = ttfont["post"].underlineThickness
    
                if "OS/2" in ttfont:
                    strikeout_position = ttfont["OS/2"].yStrikeoutPosition
                    strikeout_thickness = ttfont["OS/2"].yStrikeoutSize
    
                # Calculate decoration geometry
                # The decoration should span the entire width of the text
                # We calculated 'advance_x' as the total width (approx)
                # But for centered text, the start x is shifted.
    
                # We need the bounding box of the text to know where to draw the line
                # Since we have the path data, we could calculate the bbox, but that's expensive.
                # Instead, we use the layout information we computed.
    
                # For simplicity, we'll draw a rectangle for each line of text
    
                for line_chunks in lines:
                    if not line_chunks:
                        continue
    
                    # Calculate line width and start position (similar to how we placed glyphs)
                    line_width = _measure_line_width(line_chunks)
                    if "text4" in str(text_elem.get("id")):
                        dbg(f"DEBUG text4: Measured line_width={line_width}")
                        for chunk in line_chunks:  # Changed chunk_list to line_chunks
                            dbg(
                                f"DEBUG text4 chunk: width={chunk['width']}, text='{chunk['text']}'"
                            )
                    line_dir = line_chunks[0].get("direction", "LTR")
    
                    # Re-calculate line anchor offset
                    if text_anchor == "middle":
                        line_anchor_offset = -line_width / 2.0
                    elif text_anchor == "end":
                        line_anchor_offset = 0.0 if line_dir == "RTL" else -line_width
                    else:
                        line_anchor_offset = -line_width if line_dir == "RTL" else 0.0
    
                    # Line start X (relative to text insertion point 'x')
                    # Note: 'x' and 'y' are the text element's x,y
                    # But we are generating paths relative to (0,0) and letting the transform handle x,y?
                    # NO. In text_to_path_rust_style, we bake x,y into the path data?
                    # Let's check:
                    #   pos_x = x + line_anchor_offset + ltr_cursor + (pos.x_offset * seg_scale)
                    # Yes, we bake x,y.
    
                    # So the decoration line starts at: x + line_anchor_offset
                    # And has width: line_width
                    # Y position: y + (underline_position * scale)  (remember Y is flipped in SVG vs Font?)
                    # Wait, font coordinates: Y up. SVG: Y down.
                    # We flip Y when generating path commands: y_scale = -1 * scale
                    # So:
                    #   glyph_y = y - (pos.y_offset * seg_scale) - (pos.y_advance * seg_scale) ...
                    #   Actually, the pen flips it: transform=(scale, 0, 0, -scale, ...)
    
                    # Let's look at how we draw glyphs:
                    # t = (seg_scale, 0, 0, -seg_scale, pos_x, pos_y)
                    # So pos_y is the baseline in SVG coordinates.
    
                    # Underline Y (SVG coords) = baseline_y - (underline_position * scale)
                    # (Minus because underline_position is usually negative in font coords (below baseline),
                    #  and we want it below baseline in SVG (positive Y relative to baseline? No, SVG Y is down).
                    #  If font Y is up, underline_pos -100 is below.
                    #  In SVG Y down, below baseline is +100.
                    #  So we should SUBTRACT underline_position * scale (since -(-100) = +100).
    
                    # Use the line's baseline y
                    line_y = line_chunks[0].get("line_y", y)
    
                    deco_start_x = x + line_anchor_offset
                    deco_end_x = deco_start_x + line_width
    
                    fmt = f"{{:.{precision}f}}"
    
                    if "underline" in decoration:
                        u_y = line_y - (underline_position * scale)
                        u_h = underline_thickness * scale
                        # Draw rectangle
                        # Top-left: (start_x, u_y)
                        # Top-right: (end_x, u_y)
                        # Bottom-right: (end_x, u_y + u_h)
                        # Bottom-left: (start_x, u_y + u_h)
    
                        rect_d = f"M {fmt.format(deco_start_x)} {fmt.format(u_y)} L {fmt.format(deco_end_x)} {fmt.format(u_y)} L {fmt.format(deco_end_x)} {fmt.format(u_y + u_h)} L {fmt.format(deco_start_x)} {fmt.format(u_y + u_h)} Z"
                        all_paths.append(rect_d)
    
                    if "line-through" in decoration:
                        s_y = line_y - (strikeout_position * scale)
                        s_h = strikeout_thickness * scale
                        rect_d = f"M {fmt.format(deco_start_x)} {fmt.format(s_y)} L {fmt.format(deco_end_x)} {fmt.format(s_y)} L {fmt.format(deco_end_x)} {fmt.format(s_y + s_h)} L {fmt.format(deco_start_x)} {fmt.format(s_y + s_h)} Z"
                        all_paths.append(rect_d)
    
    path_elem.set("d", " ".join(all_paths))
    
    # 9. Copy ID
    if "id" in text_elem.attrib:
        path_elem.set("id", text_elem.get("id"))
    
    # 10. Bake transform when possible; otherwise preserve
    # 10. Preserve transform
    if transform_attr:
        path_elem.set("transform", transform_attr)
    
    # No stroke scaling needed since we preserved the transform
    stroke_scale = 1.0
    
    # 11. Preserve styling (full style plus common stroke/fill attributes)
    if "style" in text_elem.attrib:
        style_val = text_elem.get("style")
        # If stroke-width present in style and we baked transform, scale it
        if stroke_scale != 1.0 and style_val and "stroke-width" in style_val:
    
            def _scale_sw(match):
                try:
                    num = float(match.group(1))
                    return f"stroke-width:{num * stroke_scale}"
                except Exception:
                    return match.group(0)
    
            style_val = re.sub(r"stroke-width:([\\d\\.]+)", _scale_sw, style_val)
        path_elem.set("style", style_val)
    for attr_name in (
        "fill",
        "stroke",
        "stroke-width",
        "stroke-linejoin",
        "stroke-linecap",
        "stroke-miterlimit",
        "fill-opacity",
        "stroke-opacity",
        "opacity",
        "stroke-dasharray",
        "stroke-dashoffset",
    ):
        if attr_name in text_elem.attrib:
            val = text_elem.get(attr_name)
            if attr_name == "stroke-width" and stroke_scale != 1.0:
                try:
                    val = str(float(val) * stroke_scale)
                except Exception:
                    pass
            path_elem.set(attr_name, val)
    
    # 12. Preserve animations
    # Copy animate, animateTransform, set, animateMotion children
    for child in text_elem:
        tag = child.tag
        if "}" in tag:
            tag = tag.split("}")[1]
    
        if tag in ("animate", "animateTransform", "set", "animateMotion"):
            # Clone the animation element
            import copy
    
            anim_clone = copy.deepcopy(child)
            path_elem.append(anim_clone)
    
    # Return both the path element and the total advance width
    return path_elem, advance_x
    
    
def get_path_bbox(path_d):
    """Calculate the bounding box of a path string."""
    if not path_d:
        return None
    try:
        path = parse_path(path_d)
        min_x, min_y, max_x, max_y = (
            float("inf"),
            float("inf"),
            float("-inf"),
            float("-inf"),
        )

        # Check if path is empty
        if len(path) == 0:
            return None

        for segment in path:
            # Check start
            min_x = min(min_x, segment.start.real)
            min_y = min(min_y, segment.start.imag)
            max_x = max(max_x, segment.start.real)
            max_y = max(max_y, segment.start.imag)

            # Check end
            min_x = min(min_x, segment.end.real)
            min_y = min(min_y, segment.end.imag)
            max_x = max(max_x, segment.end.real)
            max_y = max(max_y, segment.end.imag)

            # Check controls
            if hasattr(segment, "control"):  # Quadratic
                min_x = min(min_x, segment.control.real)
                min_y = min(min_y, segment.control.imag)
                max_x = max(max_x, segment.control.real)
                max_y = max(max_y, segment.control.imag)
            elif hasattr(segment, "control1"):  # Cubic
                min_x = min(min_x, segment.control1.real)
                min_y = min(min_y, segment.control1.imag)
                max_x = max(max_x, segment.control1.real)
                max_y = max(max_y, segment.control1.imag)

                min_x = min(min_x, segment.control2.real)
                min_y = min(min_y, segment.control2.imag)
                max_x = max(max_x, segment.control2.real)
                max_y = max(max_y, segment.control2.imag)

        if min_x == float("inf"):
            return None
        return (min_x, min_y, max_x, max_y)
    except Exception:
        return None


def get_element_bbox(elem):
    """Recursively calculate bbox of an element (path or group)."""
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
    if tag == "path":
        return get_path_bbox(elem.get("d"))
    elif tag == "g":
        min_x, min_y, max_x, max_y = (
            float("inf"),
            float("inf"),
            float("-inf"),
            float("-inf"),
        )
        found = False
        for child in elem:
            bbox = get_element_bbox(child)
            if bbox:
                found = True
                min_x = min(min_x, bbox[0])
                min_y = min(min_y, bbox[1])
                max_x = max(max_x, bbox[2])
                max_y = max(max_y, bbox[3])
        if found:
            return (min_x, min_y, max_x, max_y)
    return None


def get_visual_bboxes(svg_path):
    import subprocess
    import json

    script_path = Path(__file__).parent / "get_bboxes_for_text2path.cjs"
    if not script_path.exists():
        print(f"Warning: {script_path} not found. Skipping visual bbox alignment.")
        return {}

    try:
        cwd = script_path.parent
        abs_svg_path = svg_path.resolve()
        result = subprocess.run(
            ["node", script_path.name, str(abs_svg_path)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Error getting visual bboxes: {e}")
        return {}


def convert_svg_text_to_paths(
    svg_path: Path,
    output_path: Path,
    precision: int = 28,
    font_cache: FontCache | None = None,
) -> None:
    """Convert all text elements in SVG to paths."""
    print(f"Converting text to paths (Rust-style) in: {svg_path}")

    # 1. Parse SVG
    ET.register_namespace(
        "", "http://www.w3.org/2000/svg"
    )  # Default namespace, no prefix

    tree = ET.parse(svg_path)
    root = tree.getroot()

    # Bake transforms up front to eliminate inherited transform-induced shifts.
    # This was critical to reduce anchor drift across the document.
    # flatten_transforms(root)

    # Reject Inkscape SVG (sodipodi namespace)
    if any("sodipodi" in (elem.tag or "") for elem in root.iter()):
        raise RuntimeError(
            "please export the file from inkscape using the plain svg option!"
        )

    # 2. Create or reuse font cache
    font_cache = font_cache or FontCache()

    # 2b. Collect path definitions for textPath
    path_map = {}  # id -> svg.path.Path

    def find_paths_recursive(element):
        for child in element:
            tag = child.tag
            if "}" in tag:
                tag = tag.split("}")[1]

            if tag == "path":
                path_id = child.get("id")
                d = child.get("d")
                if path_id and d:
                    try:
                        path_map[path_id] = parse_path(d)
                    except Exception as e:
                        print(f"Warning: Failed to parse path {path_id}: {e}")

            find_paths_recursive(child)

    find_paths_recursive(root)
    print(f"Found {len(path_map)} path definitions")

    # 3. Collect text elements
    text_elements = []

    # We need to collect (parent, child) tuples
    # ElementTree doesn't have getparent(), so we walk and store
    def collect_text(elem):
        for child in elem:
            tag = child.tag
            if "}" in tag:
                tag = tag.split("}")[1]
            if tag == "text":
                text_elements.append((elem, child))
            collect_text(child)

    collect_text(root)
    print(f"  Found {len(text_elements)} text elements")

    # 4. Convert each text element to path
    converted = 0
    failed = 0
    missing_fonts: list[MissingFontError] = []

    for parent, text_elem in text_elements:
        elem_id = text_elem.get("id", "unknown")
        print(f"Processing element: {elem_id}")

        # Skip if no text content and no children
        if not text_elem.text and not list(text_elem):
            print(
                f"  Skipping text element {elem_id} with no text content or children."
            )
            continue

        try:
            # Check for textPath
            text_path_elem = None
            for child in text_elem:
                tag = child.tag
                if "}" in tag:
                    tag = tag.split("}")[1]
                if tag == "textPath":
                    text_path_elem = child
                    break

            # Determine content source (textPath or direct/tspans)
            content_elem = text_path_elem if text_path_elem is not None else text_elem

            # Trim incidental whitespace around textPath to avoid rendering
            # indent/newline artifacts (especially when white-space:pre is set).
            if text_path_elem is not None:
                text_elem.text = ""  # ignore indentation before textPath
                if text_path_elem.text:
                    text_path_elem.text = text_path_elem.text.strip()

            # Check if text has tspan children
            tspans = []
            for child in content_elem:
                tag = child.tag
                if "}" in tag:
                    tag = tag.split("}")[1]
                if tag == "tspan":
                    tspans.append(child)

            # Get preview text for logging
            if tspans:
                preview_text = (tspans[0].text or "")[:50]
            else:
                preview_text = (content_elem.text or "")[:50]

            print(
                f"  Converting text '{preview_text}' (id={elem_id}, {len(tspans)} tspan(s))..."
            )

            # Setup textPath info if present
            path_obj = None
            path_start_offset = 0.0

            if text_path_elem is not None:
                # Get href
                href = text_path_elem.get("{http://www.w3.org/1999/xlink}href")
                if not href:
                    href = text_path_elem.get("href")

                if href and href.startswith("#"):
                    path_id = href[1:]
                    path_obj = path_map.get(path_id)

                    if path_obj:
                        # Calculate startOffset
                        start_offset_attr = text_path_elem.get("startOffset", "0")
                        path_len = path_obj.length()

                        if "%" in start_offset_attr:
                            pct = float(start_offset_attr.strip("%")) / 100.0
                            path_start_offset = path_len * pct
                        else:
                            path_start_offset = float(start_offset_attr)
                    else:
                        print(f"    ⚠️  Referenced path '{path_id}' not found")

            # Handle multi-tspan text elements (or single textPath with tspans)
            if tspans:
                # Create a group to hold multiple paths
                group_elem = ET.Element("{http://www.w3.org/2000/svg}g")
                group_elem.set("id", elem_id + "_group")

                # Copy transform from text to group if it exists
                if "transform" in text_elem.attrib:
                    group_elem.set("transform", text_elem.get("transform"))

                # Track cursor position for flow
                base_x = float(text_elem.get("x", "0"))
                base_y = float(text_elem.get("y", "0"))
                cursor_x = 0.0 if path_obj else base_x
                cursor_y = base_y
                current_path_offset = path_start_offset if path_obj else 0.0

                parent_style = text_elem.get("style", "")
                inline_size = (
                    None  # plain SVG: do not auto-wrap; rely on explicit x/y or tspans
                )

                def merge_style(p_style: str, c_style: str) -> str:
                    if p_style and c_style:
                        p_props = dict(
                            prop.split(":", 1)
                            for prop in p_style.split(";")
                            if ":" in prop
                        )
                        c_props = dict(
                            prop.split(":", 1)
                            for prop in c_style.split(";")
                            if ":" in prop
                        )
                        merged = {**p_props, **c_props}
                        return ";".join(f"{k}:{v}" for k, v in merged.items())
                    return c_style or p_style

                def strip_anchor(style_str: str) -> str:
                    if not style_str:
                        return style_str
                    props = []
                    for prop in style_str.split(";"):
                        if ":" not in prop:
                            continue
                        k, v = prop.split(":", 1)
                        k = k.strip()
                        if k in ("text-anchor", "text-align"):
                            continue
                        props.append(f"{k}:{v.strip()}")
                    return ";".join(props)

                tspan_converted = 0
                temp_id_counter = 0
                def _set_path_id(path_elem: ET.Element, preferred_id: str | None) -> None:
                    nonlocal temp_id_counter
                    if preferred_id:
                        path_elem.set("id", preferred_id)
                    else:
                        path_elem.set("id", f"{elem_id}_tspan{temp_id_counter}")
                    temp_id_counter += 1

                leaf_items = []

                # Resolve parent anchor once
                def _get_attr_local(elem, key, default=None):
                    style_val = elem.get("style", "")
                    m = re.search(f"{key}:([^;]+)", style_val)
                    if m:
                        return m.group(1).strip()
                    return elem.get(key, default)

                parent_anchor = _get_attr_local(text_elem, "text-anchor", None)
                if any("dx" in t.attrib for t in tspans):
                    parent_anchor = "start"
                if not parent_anchor:
                    # check style on text_elem
                    style_anchor_match = re.search(
                        r"text-anchor:\s*(start|middle|end)", text_elem.get("style", "")
                    )
                    if style_anchor_match:
                        parent_anchor = style_anchor_match.group(1)
                text_align_match_parent = re.search(
                    r"text-align:\s*(center|left|right)", text_elem.get("style", "")
                )
                if text_align_match_parent and not parent_anchor:
                    text_align_map = {
                        "center": "middle",
                        "left": "start",
                        "right": "end",
                    }
                    parent_anchor = text_align_map.get(text_align_match_parent.group(1))
                if not parent_anchor:
                    parent_anchor = "start"

                def _is_tspan(elem: ET.Element) -> bool:
                    tag = elem.tag
                    if "}" in tag:
                        tag = tag.split("}", 1)[1]
                    return tag == "tspan"

                def _style_matches_parent(span_style: str) -> bool:
                    if not span_style:
                        return True
                    def _style_dict(style_str: str) -> dict[str, str]:
                        out: dict[str, str] = {}
                        for prop in style_str.split(";"):
                            if ":" not in prop:
                                continue
                            k, v = prop.split(":", 1)
                            k = k.strip()
                            if k in ("text-anchor", "text-align"):
                                continue
                            out[k] = v.strip()
                        return out

                    merged = merge_style(parent_style, span_style)
                    return _style_dict(merged) == _style_dict(parent_style)

                has_dx_child = False
                can_flatten_dx = path_obj is None
                for line_span in tspans:
                    if not can_flatten_dx:
                        break
                    if line_span.get("style") and not _style_matches_parent(
                        line_span.get("style", "")
                    ):
                        can_flatten_dx = False
                        break
                    for child in list(line_span):
                        if not _is_tspan(child):
                            continue
                        if list(child):
                            can_flatten_dx = False
                            break
                        if child.get("x") or child.get("y"):
                            if (child.text or "").strip():
                                can_flatten_dx = False
                                break
                        if child.get("style") and not _style_matches_parent(
                            child.get("style", "")
                        ):
                            can_flatten_dx = False
                            break
                        if "dx" in child.attrib or "dy" in child.attrib:
                            has_dx_child = True
                    if not can_flatten_dx:
                        break

                if can_flatten_dx and has_dx_child:
                    def _append_text_with_offsets(
                        text: str | None,
                        dx_vals: list[float],
                        dy_vals: list[float],
                        text_parts: list[str],
                        dx_out: list[float],
                        dy_out: list[float],
                    ) -> None:
                        if not text:
                            return
                        text_parts.append(text)
                        for i, _ch in enumerate(text):
                            dx_out.append(dx_vals[i] if i < len(dx_vals) else 0.0)
                            dy_out.append(dy_vals[i] if i < len(dy_vals) else 0.0)

                    for line_idx, line_span in enumerate(tspans):
                        line_text_parts: list[str] = []
                        dx_list_line: list[float] = []
                        dy_list_line: list[float] = []
                        _append_text_with_offsets(
                            line_span.text, [], [], line_text_parts, dx_list_line, dy_list_line
                        )
                        for child in list(line_span):
                            if not _is_tspan(child):
                                continue
                            dx_vals = (
                                _parse_num_list(child.get("dx", ""))
                                if "dx" in child.attrib
                                else []
                            )
                            dy_vals = (
                                _parse_num_list(child.get("dy", ""))
                                if "dy" in child.attrib
                                else []
                            )
                            _append_text_with_offsets(
                                child.text, dx_vals, dy_vals, line_text_parts, dx_list_line, dy_list_line
                            )
                            _append_text_with_offsets(
                                child.tail, [], [], line_text_parts, dx_list_line, dy_list_line
                            )

                        line_text = "".join(line_text_parts)
                        if not line_text.strip():
                            continue
                        line_x = line_span.get("x") or base_x
                        line_y = line_span.get("y") or base_y

                        temp_text = ET.Element("{http://www.w3.org/2000/svg}text")
                        temp_text.set("x", str(line_x))
                        temp_text.set("y", str(line_y))
                        if parent_style:
                            temp_text.set("style", parent_style)
                        if parent_anchor:
                            temp_text.set("text-anchor", parent_anchor)
                        temp_text.text = line_text

                        result_line = text_to_path_rust_style(
                            temp_text,
                            font_cache,
                            None,
                            path_start_offset=0.0,
                            precision=precision,
                            dx_list=dx_list_line,
                            dy_list=dy_list_line,
                        )
                        if result_line is not None:
                            path_elem, _ = result_line
                            if "transform" in path_elem.attrib:
                                del path_elem.attrib["transform"]
                            path_elem.set("id", f"{elem_id}_tspan{temp_id_counter}")
                            temp_id_counter += 1
                            group_elem.append(path_elem)
                            tspan_converted += 1

                    if tspan_converted > 0:
                        idx = list(parent).index(text_elem)
                        parent.remove(text_elem)
                        parent.insert(idx, group_elem)
                        converted += 1
                        print(
                            f"    ✓ Converted successfully ({tspan_converted} leaf span(s))"
                        )
                        continue

                def span_anchor(span: ET.Element, fallback: str) -> str:
                    anchor = span.get("text-anchor", None)
                    if not anchor:
                        style_anchor_match = re.search(
                            r"text-anchor:\s*(start|middle|end)", span.get("style", "")
                        )
                        if style_anchor_match:
                            anchor = style_anchor_match.group(1)
                    text_align_match = re.search(
                        r"text-align:\s*(center|left|right)", span.get("style", "")
                    )
                    if text_align_match and not anchor:
                        text_align_map = {
                            "center": "middle",
                            "left": "start",
                            "right": "end",
                        }
                        anchor = text_align_map.get(text_align_match.group(1))
                    return anchor or fallback

                def process_span(
                    span: ET.Element,
                    cx: float,
                    cy: float,
                    p_offset: float,
                    inherited_style: str,
                ) -> tuple[float, float, float, int]:
                    nonlocal temp_id_counter, tspan_converted

                    # Resolve x/y
                    if "x" in span.attrib:
                        cx = float(span.get("x"))
                    if "y" in span.attrib:
                        cy = float(span.get("y"))

                    # Collect per-glyph shifts (do not pre-apply; text_to_path_rust_style handles them)
                    dx_list_span = (
                        _parse_num_list(span.get("dx", ""))
                        if "dx" in span.attrib
                        else None
                    )
                    dy_list_span = (
                        _parse_num_list(span.get("dy", ""))
                        if "dy" in span.attrib
                        else None
                    )

                    # Effective style
                    span_style = merge_style(inherited_style, span.get("style", ""))

                    # If this span has direct text, convert it
                    text_content = span.text or ""
                    has_child_tspan = any(
                        (c.tag.split("}", 1)[-1] == "tspan") for c in list(span)
                    )

                    # Check if we should force wrapping (ignore manual positions)
                    force_wrap = bool(text_elem.get("inline-size"))

                    if text_content.strip() and not has_child_tspan:
                        anchor_resolved = span_anchor(span, parent_anchor)
                        if (dx_list_span or dy_list_span) and not force_wrap:
                            # Directly convert spans with explicit per-glyph offsets to avoid
                            # anchoring explosions on RTL text with large dx values.
                            temp_text = ET.Element("{http://www.w3.org/2000/svg}text")
                            temp_text.set("x", str(cx))
                            temp_text.set("y", str(cy))
                            if span_style:
                                temp_text.set("style", strip_anchor(span_style))
                            temp_text.set("text-anchor", "start")
                            if "direction" in text_elem.attrib:
                                temp_text.set("direction", text_elem.get("direction"))
                            temp_text.text = text_content
                            result_span = text_to_path_rust_style(
                                temp_text,
                                font_cache,
                                path_obj,
                                path_start_offset=p_offset,
                                precision=precision,
                                dx_list=dx_list_span,
                                dy_list=dy_list_span,
                            )
                            if result_span is not None:
                                path_elem, width = result_span
                                if "transform" in path_elem.attrib:
                                    del path_elem.attrib["transform"]
                                path_elem.set("id", f"{elem_id}_tspan{temp_id_counter}")
                                temp_id_counter += 1
                                group_elem.append(path_elem)
                                tspan_converted += 1
                                cx += width
                            elif elem_id == "text4":
                                dbg("DEBUG text4: result_span None in process_span branch (dx/dy)")
                            # continue processing siblings without returning early
                        else:
                            leaf_items.append(
                                {
                                    "text": text_content,
                                    "x": cx,
                                    "y": cy,
                                    "explicit_xy": ("x" in span.attrib)
                                    or ("y" in span.attrib),
                                    "anchor": anchor_resolved,
                                    "style": span_style,
                                    "dx_list": None if force_wrap else dx_list_span,
                                    "dy_list": None if force_wrap else dy_list_span,
                                    "p_offset": p_offset,
                                }
                            )

                    # Recurse into children
                    for child in list(span):
                        cx, cy, p_offset, _ = process_span(
                            child, cx, cy, p_offset, span_style
                        )
                        # Handle tail text after child
                        if child.tail and child.tail.strip():
                            tail_text = child.tail
                            temp_text = ET.Element("{http://www.w3.org/2000/svg}text")
                            temp_text.set("x", str(cx))
                            temp_text.set("y", str(cy))
                            if span_style:
                                temp_text.set("style", span_style)
                            temp_text.text = tail_text
                            result_tail = text_to_path_rust_style(
                                temp_text,
                                font_cache,
                                path_obj,
                                path_start_offset=p_offset,
                                precision=precision,
                            )
                            if result_tail is not None:
                                path_elem, width = result_tail
                                if "transform" in path_elem.attrib:
                                    del path_elem.attrib["transform"]
                                path_elem.set("id", f"{elem_id}_tspan{temp_id_counter}")
                                temp_id_counter += 1
                                group_elem.append(path_elem)
                                tspan_converted += 1
                                cx += width
                                if path_obj:
                                    p_offset += width

                    return cx, cy, p_offset, tspan_converted

                # Walk each top-level tspan
                for i, tspan in enumerate(tspans):
                    t_preview = (tspan.text or "").strip().replace(
                        "\n", " "
                    ) or "(nested)"
                    print(f"      tspan {i}: '{t_preview[:40]}'")
                    cursor_x, cursor_y, current_path_offset, _ = process_span(
                        tspan, cursor_x, cursor_y, current_path_offset, parent_style
                    )

                has_explicit_xy = any(
                    "x" in t.attrib or "y" in t.attrib for t in tspans
                )

                # If inline-size specified, no textPath, and no explicit x/y on tspans, perform wrapping
                # If inline-size specified, no textPath, and no explicit x/y on tspans, perform wrapping
                if elem_id == "text44":
                    print(
                        f"DEBUG WRAP: inline_size={inline_size} path_obj={path_obj} has_explicit_xy={has_explicit_xy}"
                    )
                    for li in leaf_items:
                        print(
                            f"  LI: x={li['x']} y={li['y']} anchor={li.get('anchor')} text='{li['text']}'"
                        )

                if inline_size and not path_obj and leaf_items:
                    line_height = (
                        float(
                            re.search(
                                r"([\\d\\.]+)", text_elem.get("font-size", "16")
                            ).group(1)
                        )
                        * 1.2
                        if re.search(r"([\\d\\.]+)", text_elem.get("font-size", "16"))
                        else 16 * 1.2
                    )

                    lines = []
                    current_line = []
                    current_width = 0.0

                    def measure_leaf(li):
                        temp_text = ET.Element("{http://www.w3.org/2000/svg}text")
                        temp_text.set("x", str(0))
                        temp_text.set("y", str(0))
                        if li["style"]:
                            temp_text.set("style", strip_anchor(li["style"]))
                        temp_text.text = li["text"]
                        res = text_to_path_rust_style(
                            temp_text,
                            font_cache,
                            None,
                            path_start_offset=0.0,
                            precision=precision,
                            dx_list=li["dx_list"],
                            dy_list=li["dy_list"],
                            trim_trailing_spacing=True,
                        )
                        if res is None:
                            return 0.0, None
                        path_elem, width = res
                        return width, path_elem

                    measured_paths = []
                    for li in leaf_items:
                        w, p_elem = measure_leaf(li)
                        measured_paths.append((li, w, p_elem))
                        if current_width + w > inline_size and current_width > 0:
                            lines.append((current_line, current_width))
                            current_line = []
                            current_width = 0.0
                        current_line.append((li, w, p_elem))
                        current_width += w
                    if current_line:
                        lines.append((current_line, current_width))

                    # Place lines honoring text-anchor
                    # respect style-based anchor too
                    anchor_attr = _get_attr_local(text_elem, "text-anchor", None)
                    anchor = anchor_attr or "start"
                    base_x = float(text_elem.get("x", "0"))
                    base_y = float(text_elem.get("y", "0"))

                    line_index = 0
                    for line_items, lw in lines:
                        if anchor == "middle":
                            line_x = base_x - lw / 2
                        elif anchor == "end":
                            line_x = base_x - lw
                        else:
                            line_x = base_x
                        line_y = base_y + line_index * line_height
                        cursor = 0.0
                        for li, w, p_elem in line_items:
                            if p_elem is None:
                                continue
                            # translate path by line_x + cursor, line_y
                            # wrap p_elem in group with translate
                            g = ET.Element("{http://www.w3.org/2000/svg}g")
                            g.set("transform", f"translate({line_x + cursor},{line_y})")
                            g.append(p_elem)
                            g.set("id", f"{elem_id}_tspan{temp_id_counter}")
                            temp_id_counter += 1
                            group_elem.append(g)
                            cursor += w
                            tspan_converted += 1
                        line_index += 1
                else:
                    # No wrapping; convert collected leafs. If not a textPath, apply anchor once per line.
                    if path_obj:
                        cursor = 0.0
                        for li in leaf_items:
                            li_x = li["x"]
                            li_y = li["y"]
                            li_anchor = li.get("anchor") or parent_anchor
                            temp_text = ET.Element("{http://www.w3.org/2000/svg}text")
                            temp_text.set("x", str(li_x))
                            temp_text.set("y", str(li_y))
                            if "transform" in text_elem.attrib:
                                temp_text.set("transform", text_elem.get("transform"))
                            if li["style"]:
                                temp_text.set("style", strip_anchor(li["style"]))
                            if li_anchor:
                                temp_text.set("text-anchor", li_anchor)
                            if "direction" in text_elem.attrib:
                                temp_text.set("direction", text_elem.get("direction"))
                            temp_text.text = li["text"]
                            result_inner = text_to_path_rust_style(
                                temp_text,
                                font_cache,
                                path_obj,
                                path_start_offset=li["p_offset"],
                                precision=precision,
                                dx_list=li["dx_list"],
                                dy_list=li["dy_list"],
                            )
                            if result_inner is not None:
                                path_elem, width = result_inner
                                if "transform" in path_elem.attrib:
                                    del path_elem.attrib["transform"]
                                path_elem.set("id", f"{elem_id}_tspan{temp_id_counter}")
                                temp_id_counter += 1
                                group_elem.append(path_elem)
                                tspan_converted += 1
                                cursor += width
                            else:
                                if elem_id == "text4":
                                    dbg("DEBUG text4: result_inner None in line_single branch")
                                raise RuntimeError(
                                    f"Failed to convert span in element {elem_id}"
                                )
                    else:
                        # Group spans by their y coordinate (lines)
                        lines: list[list[dict]] = []
                        for li in leaf_items:
                            if not lines or abs(li["y"] - lines[-1][0]["y"]) > 1e-6:
                                lines.append([])
                            lines[-1].append(li)

                        for line_items in lines:
                            # Base x for the line comes from the first explicit x if present, else parent x
                            explicit_starts = [
                                li for li in line_items if li["explicit_xy"]
                            ]
                            line_base_x = (
                                explicit_starts[0]["x"] if explicit_starts else base_x
                            )
                            line_anchor = parent_anchor

                            # Measure widths with anchor=start to avoid double shifting
                            measured: list[tuple[dict, float]] = []  # (leaf, width)
                            for li in line_items:
                                temp_measure = ET.Element(
                                    "{http://www.w3.org/2000/svg}text"
                                )
                                temp_measure.set("x", "0")
                                temp_measure.set("y", "0")
                                if "transform" in text_elem.attrib:
                                    temp_measure.set(
                                        "transform", text_elem.get("transform")
                                    )
                                if li["style"]:
                                    temp_measure.set("style", li["style"])
                                temp_measure.set("text-anchor", "start")
                                if "direction" in text_elem.attrib:
                                    temp_measure.set(
                                        "direction", text_elem.get("direction")
                                    )
                                temp_measure.text = li["text"]
                                res = text_to_path_rust_style(
                                    temp_measure,
                                    font_cache,
                                    None,
                                    path_start_offset=0.0,
                                    precision=precision,
                                    dx_list=li["dx_list"],
                                    dy_list=li["dy_list"],
                                    input_svg_path=svg_path,
                                )
                                width = res[1] if res is not None else 0.0
                                measured.append((li, width))

                            # Widths already include dx/spacing from text_to_path_rust_style.
                            total_width = sum(w for _, w in measured)
                            # Keep parent anchor but avoid double shifts on children.
                            # This change removed a major left drift on some lines (~14%→7% diff overall).
                            parent_shift = 0.0
                            if line_anchor == "middle":
                                parent_shift = -total_width / 2.0
                            elif line_anchor == "end":
                                parent_shift = -total_width

                            cursor = 0.0
                            for li, width in measured:
                                temp_text = ET.Element(
                                    "{http://www.w3.org/2000/svg}text"
                                )
                                anchor_shift = 0.0
                                leaf_anchor = li.get("anchor") or line_anchor
                                if leaf_anchor != line_anchor:
                                    if leaf_anchor == "middle":
                                        anchor_shift = -width / 2.0
                                    elif leaf_anchor == "end":
                                        anchor_shift = -width

                                # If leaf anchor overrides parent, do not reapply parent_shift to avoid double anchoring.
                                effective_parent_shift = (
                                    0.0 if leaf_anchor != line_anchor else parent_shift
                                )

                                if elem_id in ["text39", "text53", "text54"]:
                                    print(
                                        f"DEBUG FINAL: id={elem_id} anchor={line_anchor} leaf_anchor={leaf_anchor} width={width} total_width={total_width} parent_shift={parent_shift} eff_shift={effective_parent_shift} base_x={line_base_x} x={line_base_x + effective_parent_shift + cursor + anchor_shift}"
                                    )

                                temp_text.set(
                                    "x",
                                    str(
                                        line_base_x
                                        + effective_parent_shift
                                        + cursor
                                        + anchor_shift
                                    ),
                                )
                                temp_text.set("y", str(li["y"]))
                                if "transform" in text_elem.attrib:
                                    temp_text.set(
                                        "transform", text_elem.get("transform")
                                    )
                                if li["style"]:
                                    temp_text.set("style", strip_anchor(li["style"]))
                                temp_text.set("text-anchor", "start")
                                if "direction" in text_elem.attrib:
                                    temp_text.set(
                                        "direction", text_elem.get("direction")
                                    )
                                temp_text.text = li["text"]
                                result_inner = text_to_path_rust_style(
                                    temp_text,
                                    font_cache,
                                    None,
                                    path_start_offset=li["p_offset"],
                                    precision=precision,
                                    dx_list=li["dx_list"],
                                    dy_list=li["dy_list"],
                                    input_svg_path=svg_path,
                                )
                                if result_inner is not None:
                                    path_elem, _ = result_inner
                                    if "transform" in path_elem.attrib:
                                        del path_elem.attrib["transform"]
                                    path_elem.set(
                                        "id", f"{elem_id}_tspan{temp_id_counter}"
                                    )
                                    temp_id_counter += 1
                                    group_elem.append(path_elem)
                                    tspan_converted += 1
                                else:
                                    if elem_id == "text4":
                                        dbg("DEBUG text4: result_inner None in measured branch")
                                    raise RuntimeError(
                                        f"Failed to convert span in element {elem_id}"
                                    )
                                cursor += width

                if tspan_converted > 0:
                    idx = list(parent).index(text_elem)
                    parent.remove(text_elem)
                    parent.insert(idx, group_elem)
                    converted += 1
                    print(
                        f"    ✓ Converted successfully ({tspan_converted} leaf span(s))"
                    )

                else:
                    failed += 1
                    raise RuntimeError(
                        f"Failed to convert tspans for element id={elem_id}"
                    )
            else:
                # Single text element (or textPath without tspans)

                # If textPath, we need to create a temp text element with the content from textPath
                if text_path_elem is not None:
                    temp_text = ET.Element("{http://www.w3.org/2000/svg}text")
                    # Copy attributes from text_elem
                    for k, v in text_elem.attrib.items():
                        temp_text.set(k, v)
                    # Set text content from textPath
                    temp_text.text = text_path_elem.text or ""

                    # Use temp_text for conversion
                    target_elem = temp_text
                else:
                    target_elem = text_elem

                result = text_to_path_rust_style(
                    target_elem,
                    font_cache,
                    path_obj,
                    path_start_offset,
                    precision,
                    input_svg_path=svg_path,
                )

                if result is not None:
                    path_elem, _ = result
                    # Replace text element with path
                    idx = list(parent).index(text_elem)
                    parent.remove(text_elem)
                    parent.insert(idx, path_elem)
                    converted += 1
                    print(f"    ✓ Converted successfully")

                else:
                    failed += 1
                    raise RuntimeError(f"Conversion failed for text id={elem_id}")

        except Exception as e:
            if isinstance(e, MissingFontError):
                missing_fonts.append(e)
                print(f"✗ Missing font for element {elem_id}: {e.message}")
                continue
            import traceback

            print(f"\n✗ FATAL ERROR converting text element '{elem_id}':")
            print(f"   Preview: '{preview_text}'")
            print(f"   Error: {e}")
            print(f"\nTraceback:")
            traceback.print_exc()
            sys.exit(1)

    if missing_fonts:
        print("\n✗ Missing fonts detected (conversion aborted):")
        print(" family | weight | style | stretch ")
        print("------------------------------------")
        seen = set()
        for mf in missing_fonts:
            key = (mf.family, mf.weight, mf.style, mf.stretch)
            if key in seen:
                continue
            seen.add(key)
            print(f" {mf.family} | {mf.weight} | {mf.style} | {mf.stretch}")
        sys.exit(1)

    # 5. Sanity check: ensure no <text> elements remain
    leftover = []

    def find_texts(el):
        for ch in el:
            tag = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
            if tag == "text":
                leftover.append(ch.get("id", ""))
            find_texts(ch)

    find_texts(root)
    if leftover:
        raise RuntimeError(f"Unconverted text elements remain: {leftover}")

    # 5. Save the result (preserve the original viewBox)
    print(f"Saving result to {output_path}...")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    print(f"\n✓ Conversion complete (Rust-style):")
    print(f"  Converted: {converted} text elements")
    print(f"  Failed: {failed} text elements")
    print(f"  Output: {output_path}")


def compare_svgs(input_path: Path, output_path: Path, open_html: bool = True) -> None:
    """Compare input and output SVGs using sbb-comparer.cjs"""
    sbb_comparer_script = Path(__file__).parent.parent / "SVG-BBOX" / "sbb-comparer.cjs"
    if not sbb_comparer_script.exists():
        print(f"  ⚠️  sbb-comparer.cjs not found at {sbb_comparer_script}")
        return

    try:
        out_dir = output_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        diff_output = (out_dir / f"{input_path.stem}_vs_{output_path.stem}_diff.png").resolve()
        html_output = (out_dir / f"{input_path.stem}_vs_{output_path.stem}_comparison.html").resolve()
        project_root = Path(__file__).parent.parent
        try:
            rel_input = input_path.resolve().relative_to(project_root)
            rel_output = output_path.resolve().relative_to(project_root)
            rel_diff = diff_output.relative_to(project_root)
        except Exception:
            rel_input = input_path.resolve()
            rel_output = output_path.resolve()
            rel_diff = diff_output
        cmd = [
            "node",
            str(sbb_comparer_script),
            str(rel_input),
            str(rel_output),
            "--out-diff",
            str(rel_diff),
            "--threshold",
            "20",  # higher tolerance to smooth out font AA differences
            "--scale",
            "4",
            "--json",
        ]

        cwd = project_root
        print(f"Running comparison: {' '.join(cmd)}")

        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

        diff_pct = None
        if result.stdout:
            try:
                payload = json.loads(result.stdout.strip())
                diff_pct = (
                    payload.get("diffPercentage")
                    or payload.get("diff_percentage")
                    or payload.get("difference")
                )
            except Exception:
                # Fall back to raw stdout if parsing fails
                print(result.stdout)

        if diff_pct is not None:
            print(f"  ✓ Comparison diff: {float(diff_pct):.4f}% (threshold=20)")
        elif result.stdout:
            print(result.stdout)

        if result.stderr:
            print(f"  ⚠️  Comparer stderr: {result.stderr}")

        if result.returncode == 0:
            print(f"  ✓ Diff image saved to {diff_output}")
            if html_output.exists():
                print(f"  ✓ HTML report: {html_output}")
        else:
            print(f"  ✗ Comparison failed with exit code {result.returncode}")

    except Exception as e:
        print(f"  ⚠️  Failed to run sbb-comparer: {e}")


def get_visual_bboxes(svg_path: Path, elem_ids: list = None) -> dict:
    """Get visual bboxes for elements in SVG using sbb-getbbox.cjs"""
    sbb_getbbox_script = Path(__file__).parent.parent / "SVG-BBOX" / "sbb-getbbox.cjs"
    if not sbb_getbbox_script.exists():
        print(f"  ⚠️  sbb-getbbox.cjs not found at {sbb_getbbox_script}")
        return {}

    try:
        json_output_path = svg_path.with_suffix(f".bbox_{uuid.uuid4()}.json")

        cmd = ["node", str(sbb_getbbox_script), str(svg_path)]

        if elem_ids:
            cmd.extend(elem_ids)

        cmd.extend(["--json", str(json_output_path), "--ignore-vbox"])

        cwd = sbb_getbbox_script.parent.parent
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)

        if json_output_path.exists():
            with open(json_output_path, "r") as f:
                bbox_data = json.load(f)

            visual_bboxes = {}
            abs_path = str(svg_path.resolve())

            for k, v in bbox_data.items():
                if abs_path in k or k in abs_path:
                    visual_bboxes = v
                    break

            json_output_path.unlink()
            return visual_bboxes
        else:
            return {}

    except Exception as e:
        print(f"  ⚠️  Failed to get visual bboxes: {e}")
        if "json_output_path" in locals() and json_output_path.exists():
            json_output_path.unlink()
        return {}


def measure_bbox_with_font(svg_path: Path, target_id: str, font_family: str | None, weight: int | None = None) -> tuple[float, float] | None:
    """Render bbox for a given element, optionally overriding its font family/weight."""
    if not target_id:
        return None
    tmp_path: Path | None = None
    try:
        # Write temp SVG alongside the source file so sbb-getbbox security checks allow it
        tmp_dir = svg_path.parent if svg_path else None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".svg", dir=tmp_dir) as tmp:
            tmp_path = Path(tmp.name)
        tree = ET.parse(svg_path)
        root = tree.getroot()
        if font_family or weight:
            for elem in root.iter():
                if elem.get("id") == target_id:
                    _set_font_family(elem, font_family or elem.get("font-family", ""), weight)
                    break
        tree.write(tmp_path, encoding="utf-8", xml_declaration=True)

        bboxes = get_visual_bboxes(tmp_path, [target_id])
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        if not bboxes:
            return None
        data = bboxes.get(target_id) or next(iter(bboxes.values()), None)
        if not data or "bbox" not in data:
            return None
        x, y, w, h = data["bbox"]
        return (w, h)
    except Exception:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        return None


def score_candidates_by_bbox(
    svg_path: Path,
    sample_chars: list[str],
    base_family: str,
    font_size: float,
    font_weight: int,
    font_style: str,
    font_stretch: str,
    candidates: list[str],
    sample_size: int = 5,
) -> str | None:
    """
    Pick the fallback whose bbox best matches a sampled subset of missing chars.
    Renders a minimal SVG with the sampled chars and compares bbox across candidates.
    """
    if not candidates or not sample_chars:
        return None
    samples = list(dict.fromkeys(sample_chars))[: max(1, min(sample_size, len(sample_chars)))]
    sample_text = "".join(samples)

    tmp_svg: Path | None = None
    try:
        tmp_dir = svg_path.parent if svg_path else None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".svg", dir=tmp_dir) as tmp:
            tmp_svg = Path(tmp.name)
            content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="4000" height="4000" viewBox="0 0 4000 4000">
  <text id="sample_text" x="50" y="{font_size*2:.2f}"
        style="font-family:'{base_family}';font-size:{font_size}px;font-weight:{font_weight};font-style:{font_style};font-stretch:{font_stretch};fill:#000;">
    {sample_text}
  </text>
</svg>
"""
            tmp.write(content.encode("utf-8"))

        target_bbox = measure_bbox_with_font(tmp_svg, "sample_text", None, weight=None)
        if not target_bbox:
            return None
        target_w, target_h = target_bbox
        best: tuple[float, str] | None = None
        for fam in candidates:
            dims = measure_bbox_with_font(tmp_svg, "sample_text", fam, weight=font_weight)
            if not dims:
                continue
            w, h = dims
            score = abs(w - target_w) + abs(h - target_h)
            if best is None or score < best[0]:
                best = (score, fam)
        return best[1] if best else None
    finally:
        if tmp_svg:
            try:
                tmp_svg.unlink(missing_ok=True)
            except Exception:
                pass


def choose_fallback_by_bbox(
    svg_path: Path,
    target_id: str,
    candidates: list[str],
    target_bbox: tuple[float, float] | None,
    weights: list[int] | None = None,
    base_weight: int | None = None,
) -> tuple[str, int | None] | None:
    """Pick the fallback whose bbox best matches the target bbox. Returns (family, weight)."""
    if not candidates:
        return None
    if target_bbox is None:
        target_bbox = measure_bbox_with_font(svg_path, target_id, None)
    if target_bbox is None:
        return (candidates[0], None)

    target_w, target_h = target_bbox
    best = None  # (score, family, weight)
    best_score = float("inf")
    weights = weights or [None]
    base_w = base_weight or (weights[0] if weights else None)
    for fam in candidates:
        for wgt in weights:
            dims = measure_bbox_with_font(svg_path, target_id, fam, weight=wgt)
            if not dims:
                continue
            w, h = dims
            score = abs(w - target_w) + abs(h - target_h)
            if base_w and wgt:
                score += 0.01 * abs(wgt - base_w)
            if score < best_score:
                best_score = score
                best = (score, fam, wgt)
    if best:
        return (best[1], best[2])
    return (candidates[0], None)


def detect_chrome_font(
    text: str,
    size: float,
    weight: int,
    candidates: list[str],
    baseline: str,
    project_root: Path,
) -> str | None:
    """Use scripts/detect_chrome_font.js to pick the font Chrome actually uses."""
    script = project_root / "scripts" / "detect_chrome_font.js"
    if not script.exists():
        return None
    try:
        cmd = [
            "node",
            str(script),
            "--text",
            text,
            "--size",
            str(size),
            "--weight",
            str(weight),
            "--baseline",
            baseline,
            "--candidates",
            ",".join(candidates),
        ]
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        matches = [c["family"] for c in data.get("candidates", []) if c.get("hashMatch")]
        if matches:
            return matches[0]
    except Exception:
        return None
    return None


def fetch_fontconfig_candidates(family: str, lang: str | None = None, limit: int = 8) -> list[str]:
    """Get candidate families from fontconfig (fc-match --sort)."""
    patterns = []
    if family:
        pat = f"family:{family}"
        if lang:
            pat += f":lang={lang}"
        patterns.append(pat)
    if lang:
        patterns.append(f":lang={lang}")
    if not patterns:
        patterns.append("sans-serif")

    seen = []
    for pat in patterns:
        cmd = ["fc-match", "-s", pat]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                continue
            for line in res.stdout.splitlines():
                m = re.search(r"family=\"([^\"]+)\"", line)
                if m:
                    fams = [f.strip() for f in m.group(1).split(",")]
                    for f in fams:
                        if f and f not in seen:
                            seen.append(f)
                            if len(seen) >= limit:
                                return seen
        except Exception:
            continue
    return seen[:limit]


def fetch_charset_candidates(codepoints: set[int], limit: int = 8) -> list[str]:
    """Use fc-match charset queries to quickly gather fonts that claim coverage for sample codepoints."""
    from shutil import which

    if not which("fc-match") or not codepoints:
        return []

    picked: list[str] = []
    seen: set[str] = set()
    samples = list(codepoints)[:3]  # only a few to stay fast
    for cp in samples:
        hex_cp = format(cp, "x")
        try:
            res = subprocess.run(
                ["fc-match", "-s", f":charset={hex_cp}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode != 0:
                continue
            for line in res.stdout.splitlines():
                m = re.search(r'family="([^"]+)"', line)
                if not m:
                    continue
                fams = [f.strip() for f in m.group(1).split(",")]
                for fam in fams:
                    if fam and fam not in seen:
                        picked.append(fam)
                        seen.add(fam)
                        if limit and len(picked) >= limit:
                            return picked
        except Exception:
            continue
    return picked[:limit] if limit else picked


def expand_weights(base: int) -> list[int]:
    """Return a tiny set of weights (requested + a couple of common fallbacks) to keep memory low."""
    b = int(base)
    weights = {max(100, min(900, b)), 400, 500}
    return sorted(weights)


def apply_visual_correction(input_path: Path, output_path: Path) -> None:
    """Apply visual correction by comparing bboxes of input and output."""
    print("Applying visual correction...")

    # Collect IDs from input SVG
    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        tree = ET.parse(input_path)
        root = tree.getroot()
        input_ids = []
        for elem in root.iter():
            # We care about text, tspan, textPath
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("text", "tspan", "textPath") and "id" in elem.attrib:
                input_ids.append(elem.attrib["id"])
    except Exception as e:
        print(f"  ⚠️  Failed to parse input SVG for IDs: {e}")
        return

    if not input_ids:
        print("  ⚠️  No text IDs found in input SVG.")
        return

    # 1. Get original bboxes
    orig_bboxes = get_visual_bboxes(input_path, input_ids)
    if not orig_bboxes:
        print("  ⚠️  No original bboxes found, skipping correction.")
        return

    # 2. Get converted bboxes
    conv_bboxes = get_visual_bboxes(output_path, input_ids)
    if not conv_bboxes:
        print("  ⚠️  No converted bboxes found, skipping correction.")
        return

    # 3. Load output SVG to modify
    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        tree = ET.parse(output_path)
        root = tree.getroot()

        # Map IDs to elements
        id_map = {}
        for elem in root.iter():
            if "id" in elem.attrib:
                id_map[elem.attrib["id"]] = elem

        corrected_count = 0

        for elem_id, orig_bbox in orig_bboxes.items():
            if elem_id == "WHOLE CONTENT":
                continue

            if elem_id in conv_bboxes and elem_id in id_map:
                conv_bbox = conv_bboxes[elem_id]

                # Calculate centers
                orig_cx = orig_bbox["x"] + orig_bbox["width"] / 2
                orig_cy = orig_bbox["y"] + orig_bbox["height"] / 2

                conv_cx = conv_bbox["x"] + conv_bbox["width"] / 2
                conv_cy = conv_bbox["y"] + conv_bbox["height"] / 2

                dx = orig_cx - conv_cx
                dy = orig_cy - conv_cy

                if abs(dx) > 0.1 or abs(dy) > 0.1:
                    # Apply translation
                    elem = id_map[elem_id]
                    current_transform = elem.get("transform", "")
                    new_transform = f"translate({dx:.2f}, {dy:.2f}) {current_transform}"
                    elem.set("transform", new_transform.strip())
                    corrected_count += 1
                    # print(f"    Corrected {elem_id}: dx={dx:.2f}, dy={dy:.2f}")

        if corrected_count > 0:
            print(f"  ✓ Applied visual correction to {corrected_count} elements.")
            tree.write(output_path, encoding="utf-8", xml_declaration=True)
        else:
            print("  No corrections needed.")

    except Exception as e:
        print(f"  ⚠️  Failed to apply visual correction: {e}")


def main():
    """CLI entry for t2p_convert."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="t2p_convert",
        description="Convert all SVG <text>/<tspan>/<textPath> to <path> outlines using HarfBuzz shaping.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  t2p_convert samples/test_text_to_path.svg\n"
        "  t2p_convert samples/test_text_to_path.svg /tmp/out.svg --precision 6\n",
    )
    parser.add_argument("input_svg", help="Input SVG file")
    parser.add_argument(
        "output_svg",
        nargs="?",
        help="Output SVG file (default: <input>_rust_paths.svg)",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=28,
        help="Decimal places for generated path coordinates (use 6 to roughly match Inkscape path size).",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Generate comparison HTML but do not auto-open Chrome/Chromium.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging (keeps existing debug instrumentation).",
    )
    parser.add_argument(
        "--log-dir",
        help="Directory for rotated log files (default: ./logs)",
        default=None,
    )
    args = parser.parse_args()

    setup_logging(debug=args.debug, log_dir=args.log_dir)

    input_path = Path(args.input_svg)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    output_path = (
        Path(args.output_svg)
        if args.output_svg
        else input_path.parent / f"{input_path.stem}_rust_paths{input_path.suffix}"
    )

    convert_svg_text_to_paths(input_path, output_path, precision=args.precision)

    # Apply visual correction to align paths with original layout
    apply_visual_correction(input_path, output_path)

    # Compare results
    compare_svgs(input_path, output_path, open_html=not args.no_html)


if __name__ == "__main__":
    main()
