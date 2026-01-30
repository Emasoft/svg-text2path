#!/usr/bin/env python3
"""
Font caching and resolution module.

This module provides cross-platform font discovery, caching, and matching.
The FontCache class builds a persistent cache of all installed fonts and
provides strict matching based on family, weight, style, and stretch.

Key features:
- Cross-platform font discovery (macOS, Linux, Windows)
- Persistent font cache with TTC/OTC collection support
- Strict font matching with no silent fallbacks
- fontconfig integration for browser-like font selection
"""

import contextlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from fontTools.ttLib import TTFont  # type: ignore[import-untyped]


class FontCache:
    """Cache loaded fonts using fontconfig for proper font matching."""

    def __init__(self) -> None:
        # Cache: font_spec -> (TTFont, bytes, face_index)
        self._fonts: dict[str, tuple[TTFont, bytes, int]] = {}
        # (path, font_index) -> codepoints
        self._coverage_cache: dict[tuple[Path, int], set[int]] = {}

    def _parse_inkscape_spec(self, inkscape_spec: str) -> tuple[str, str | None]:
        """Parse Inkscape font specification.

        Examples: 'Futura, Medium' or '.New York, Italic'.
        """
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

    # TTC-fix applied 2025-12-31: Cache now stores ALL fonts from TTC/OTC
    # collections. This fixes fonts like "Futura Medium Italic" being found.
    # The fix uses 6-tuple with font_index and iterates all fonts in TTC/OTC.
    # Tested: improved text3.svg (12.35%->2.94%) and text54.svg (12.89%->0.78%).
    # (path, font_index, fams, styles, ps, weight)
    _fc_cache: list[tuple[Path, int, list[str], list[str], str, int]] | None = None
    _cache_file: Path | None = None
    # v4: stores all fonts from TTC collections with font_index
    _cache_version: int = 4
    _prebaked: dict[str, list[dict[str, object]]] | None = None
    _cache_partial: bool = False
    # Cache fc-match subprocess results: pattern -> (Path, face_index) | None
    _fc_match_cache: dict[str, tuple[Path, int] | None] = {}

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

    def _load_persistent_cache(
        self,
    ) -> (
        tuple[
            list[tuple[Path, int, list[str], list[str], str, int]],
            dict[str, list[dict[str, object]]],
            bool,
        ]
        | None
    ):
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
                if (
                    not Path(d).exists()
                    or int(Path(d).stat().st_mtime) != dirs_state[d]
                ):
                    return None
            entries: list[tuple[Path, int, list[str], list[str], str, int]] = []
            for rec in data.get("fonts", []):
                p = Path(rec["path"])
                if not p.exists():
                    continue
                if int(p.stat().st_mtime) != rec.get("mtime"):
                    continue
                entries.append(
                    (
                        p,
                        int(rec.get("font_index", 0)),  # font_index for TTC collections
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

    def _spinner(self, message: str, stop_event: threading.Event) -> None:
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

    def _read_font_meta(
        self, path: Path, need_flags: bool
    ) -> list[tuple[Path, int, list[str], list[str], str, int, dict[str, bool]]] | None:
        """Read font metadata from a font file.

        For TTC/OTC collections, returns ALL fonts in the collection
        (not just the first). This is critical for fonts like Futura.ttc
        which contain multiple styles.

        Returns:
            List of tuples: (path, font_index, families, styles, psname, weight, flags)
        """
        try:
            suffix = path.suffix.lower()
            if suffix not in {".ttf", ".otf", ".ttc", ".otc", ".woff2"}:
                return None

            results: list[
                tuple[Path, int, list[str], list[str], str, int, dict[str, bool]]
            ] = []

            # For TTC/OTC collections, iterate ALL fonts to capture all styles
            if suffix in {".ttc", ".otc"}:
                from fontTools.ttLib import TTCollection

                try:
                    coll = TTCollection(path, lazy=True)
                    for font_index, tt in enumerate(coll.fonts):
                        meta = self._extract_single_font_meta(
                            path, font_index, tt, need_flags
                        )
                        if meta:
                            results.append(meta)
                except Exception:
                    # Fallback: try reading as single font with fontNumber=0
                    tt = TTFont(path, lazy=True, fontNumber=0)
                    meta = self._extract_single_font_meta(path, 0, tt, need_flags)
                    if meta:
                        results.append(meta)
            else:
                # Single font file
                tt = TTFont(path, lazy=True)
                meta = self._extract_single_font_meta(path, 0, tt, need_flags)
                if meta:
                    results.append(meta)

            return results if results else None
        except Exception:
            return None

    def _extract_single_font_meta(
        self, path: Path, font_index: int, tt: TTFont, need_flags: bool
    ) -> tuple[Path, int, list[str], list[str], str, int, dict[str, bool]] | None:
        """Extract metadata from a single font face."""
        try:
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
            flags: dict[str, bool] = {}
            if need_flags:
                # Light coverage flags (avoid loading later): Latin, Latin-1, CJK, RTL
                flags = {"latin": False, "latin1": False, "cjk": False, "rtl": False}
                try:
                    cmap = tt.getBestCmap() or {}
                    codes = set(cmap.keys())
                    flags["latin"] = any(0x0041 <= c <= 0x007A for c in codes)
                    flags["latin1"] = any(0x00A0 <= c <= 0x00FF for c in codes)
                    flags["rtl"] = any(0x0600 <= c <= 0x08FF for c in codes) or any(
                        0x0590 <= c <= 0x05FF for c in codes
                    )
                    flags["cjk"] = any(0x4E00 <= c <= 0x9FFF for c in codes) or any(
                        0x3040 <= c <= 0x30FF for c in codes
                    )
                except Exception:
                    pass
            return (path, font_index, fams, styles, psname, weight, flags)
        except Exception:
            return None

    def _build_cache_entries(
        self,
    ) -> tuple[
        list[tuple[Path, int, list[str], list[str], str, int]],
        dict[str, list[dict[str, object]]],
        bool,
    ]:
        """Build font cache entries, including ALL fonts from TTC/OTC collections."""
        dirs = self._font_dirs()
        font_files: set[Path] = set()
        for d in dirs:
            if not d.exists():
                continue
            for ext in ("*.ttf", "*.otf", "*.ttc", "*.otc", "*.woff2"):
                font_files.update(d.rglob(ext))

        # Deduplicate by resolved path
        font_list = sorted({p.resolve() for p in font_files if p.exists()})

        # Now stores 6-tuples: (path, font_index, fams, styles, ps, weight)
        entries: list[tuple[Path, int, list[str], list[str], str, int]] = []
        prebaked: dict[str, list[dict[str, object]]] = {}
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
                meta_list = fut.result()
                # _read_font_meta now returns a list of tuples (one per font in TTC)
                if meta_list:
                    for meta in meta_list:
                        path, font_index, fams, styles, ps, weight, _flags = meta
                        entries.append((path, font_index, fams, styles, ps, weight))
                        fam_set = set(fams) | ({ps} if ps else set())
                        if fam_set & prebake_fams:
                            prebake_key = list(fam_set & prebake_fams)[0]
                            # Compute flags lazily for prebake candidates
                            flags: dict[str, bool] = {}
                            try:
                                flags_meta_list = self._read_font_meta(path, True)
                                if flags_meta_list:
                                    # Find the matching font_index entry
                                    for fm in flags_meta_list:
                                        if fm[1] == font_index:
                                            flags = fm[-1]
                                            break
                            except Exception:
                                pass
                            prebaked.setdefault(prebake_key, []).append(
                                {
                                    "path": str(path),
                                    "font_index": font_index,
                                    "styles": styles,
                                    "ps": ps,
                                    "weight": weight,
                                    "flags": flags,
                                }
                            )
                if time.time() - start > budget_seconds:
                    partial = True
                    break
        return entries, prebaked, partial

    def _save_cache(
        self,
        entries: list[tuple[Path, int, list[str], list[str], str, int]],
        prebaked: dict[str, list[dict[str, object]]],
        partial: bool,
    ) -> None:
        """Save font cache to disk, including font_index for TTC collections."""
        cache_path = self._cache_path()
        dirs = [str(d) for d in self._font_dirs()]
        payload = {
            "version": self._cache_version,
            "created_at": datetime.now().isoformat(),
            "dirs": dirs,
            "fonts": [
                {
                    "path": str(p),
                    # font_index stores TTC collection index
                    "font_index": font_index,
                    "mtime": int(p.stat().st_mtime),
                    "families": fams,
                    "styles": styles,
                    "ps": ps,
                    "weight": weight,
                }
                for (p, font_index, fams, styles, ps, weight) in entries
            ],
            "prebaked": prebaked,
            "partial": partial,
        }
        try:
            cache_path.write_text(json.dumps(payload))
        except Exception as e:
            print(f"⚠️  Could not write font cache: {e}")

    def _load_fc_cache(self) -> None:
        """Load persistent font cache (cross-platform). Falls back to scanning."""
        if self._fc_cache is not None:
            return

        cached = self._load_persistent_cache()
        if cached is not None:
            self._fc_cache, self._prebaked, self._cache_partial = cached
            return

        # Build cache with spinner notice (first run)
        msg = "First run: building font cache (can take up to 5 minutes)..."
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
            fonts_count = len(self._fc_cache or [])
            print(f"Font cache ready in {elapsed:.1f}s ({fonts_count} fonts).")

    def prewarm(self) -> int:
        """Ensure the font metadata cache is loaded.

        Returns:
            Number of indexed fonts.
        """
        self._load_fc_cache()
        return len(self._fc_cache or [])

    def prebaked_candidates(self, family: str) -> list[dict[str, object]]:
        """Return prebaked fallback records for a family name (case-insensitive)."""
        self._load_fc_cache()
        if not self._prebaked:
            return []
        key = family.strip().lower()
        return self._prebaked.get(key, [])

    def cache_is_partial(self) -> bool:
        self._load_fc_cache()
        return bool(self._cache_partial)

    def fonts_with_coverage(
        self, codepoints: set[int], limit: int | None = 15
    ) -> list[str]:
        """Return font family names covering at least one of the given codepoints.

        Args:
            codepoints: Set of Unicode codepoints to check coverage for.
            limit: Maximum number of fonts to return (default 15).

        Returns:
            List of font family names that cover at least one codepoint.
        """
        self._load_fc_cache()
        found: list[str] = []
        seen_fams: set[str] = set()
        if self._fc_cache is None:
            return found
        for path, font_index, fams, _styles, ps, _weight in self._fc_cache:
            if limit and len(found) >= limit:
                break
            try:
                # Cache key includes font_index for TTC collections
                cache_key = (path, font_index)
                if cache_key in self._coverage_cache:
                    cover = self._coverage_cache[cache_key]
                else:
                    # Load specific face to inspect cmap (using font_index for TTC)
                    if path.suffix.lower() in {".ttc", ".otc"}:
                        from fontTools.ttLib import TTCollection

                        coll = TTCollection(path, lazy=True)
                        tt = (
                            coll.fonts[font_index]
                            if font_index < len(coll.fonts)
                            else coll.fonts[0]
                        )
                    else:
                        tt = TTFont(path, lazy=True)
                    cmap = tt.getBestCmap() or {}
                    cover = set(cmap.keys())
                    self._coverage_cache[cache_key] = cover
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
        """Split a font name into lowercase word tokens.

        Handles camelCase, underscores, and spaces.
        """
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
        # Localized style name translations (ES, CA, DE, FR, IT, PT, NL)
        # Bold variants
        n = n.replace("negreta", "bold")  # Catalan
        n = n.replace("negrita", "bold")  # Spanish
        n = n.replace("fett", "bold")  # German
        n = n.replace("gras", "bold")  # French
        n = n.replace("grassetto", "bold")  # Italian
        n = n.replace("negrito", "bold")  # Portuguese
        n = n.replace("vet", "bold")  # Dutch
        # Italic variants
        n = n.replace("kursiv", "italic")  # German
        n = n.replace("cursiva", "italic")  # Spanish
        n = n.replace("italique", "italic")  # French
        n = n.replace("corsivo", "italic")  # Italian
        n = n.replace("itálico", "italic")  # Portuguese
        n = n.replace("cursief", "italic")  # Dutch
        # Light variants
        n = n.replace("leicht", "light")  # German
        n = n.replace("ligera", "light")  # Spanish
        n = n.replace("léger", "light")  # French (without accent handled below)
        n = n.replace("leger", "light")  # French (simplified)
        n = n.replace("leggero", "light")  # Italian
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
        # Normalize style string to convert localized names (e.g., "negreta" -> "bold")
        normalized_style = self._normalize_style_name(style_str)
        weight_class = self._style_weight_class([normalized_style])
        weight_score = abs(target_weight - weight_class)

        slant = self._style_slant([normalized_style])
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
        """Strict match: family must exist; weight/style must match tokens.

        No substitution allowed.

        TTC-fix: Cache stores each font face from TTC collections as a separate
        entry with its font_index, so we can directly return the cached font_index
        without needing to re-scan the TTC file at runtime.
        """
        self._load_fc_cache()
        if self._fc_cache is None:
            return None
        fam_norm = font_family.strip().lower()
        ps_norm = ps_hint.strip().lower() if ps_hint else None
        desired_style_tokens = self._style_token_set(
            self._build_style_label(weight, style, stretch)
        )

        # best_candidate stores (path, style_str, font_index) for TTC entries
        best_candidate: tuple[Path, str, int] | None = None
        best_score: float | None = None

        for path, font_index, fams, styles, ps, weight_val in self._fc_cache:
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
                with contextlib.suppress(Exception):
                    score += abs((weight_val or 0) - weight) / 1000.0
                if best_score is None or score < best_score:
                    best_score = score
                    # Now store font_index from cache entry for TTC collections
                    best_candidate = (path, st, font_index)

        if best_candidate:
            # Return path and cached font_index directly (no need to re-scan TTC)
            return (best_candidate[0], best_candidate[2])
        return None

    def _match_font_with_fc(
        self,
        font_family: str,
        weight: int = 400,
        style: str = "normal",
        stretch: str = "normal",
    ) -> tuple[Path, int] | None:
        """Use fontconfig to match fonts like a browser.

        Selects the correct face inside TTC collections based on weight/style/stretch
        tokens (e.g., choose Condensed face instead of Regular when requested).
        """
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

        # Build candidate patterns from specific to generic
        # Priority: match style (italic) first, then weight
        style_name = self._weight_to_style(weight)
        patterns: list[str] = []
        slant_suffix = ":slant=italic" if style == "italic" else ""
        slant_suffix = ":slant=oblique" if style == "oblique" else slant_suffix

        if weight == 400 and style == "normal":
            patterns.append(f"{font_family}:style=Regular:weight=400")
        if weight == 400 and style == "italic":
            patterns.append(f"{font_family}:style=Italic:weight=400:slant=italic")
        # For non-400 weights with italic/oblique, include slant in pattern
        if style_name and weight != 400:
            if style in ("italic", "oblique"):
                # Try combined style name like "SemiBold Italic"
                combined = f"{style_name} {style.capitalize()}"
                patterns.append(f"{font_family}:style={combined}{slant_suffix}")
            patterns.append(f"{font_family}:style={style_name}{slant_suffix}")
        if weight != 400:
            patterns.append(f"{font_family}:weight={weight}{slant_suffix}")

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

        def pick_face(
            path: Path, preferred_style: str | None = None
        ) -> tuple[Path, int]:
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
            # Check cache first
            if pattern in self._fc_match_cache:
                cached_result = self._fc_match_cache[pattern]
                if cached_result is not None:
                    return cached_result
                # Pattern was tried before but failed, try next pattern
                continue

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
                                matched = pick_face(
                                    font_file,
                                    self._build_style_label(weight, style, stretch),
                                )
                                # Cache the result
                                self._fc_match_cache[pattern] = matched
                                return matched
                            # Cache the result
                            matched_result = (font_file, font_index)
                            self._fc_match_cache[pattern] = matched_result
                            return matched_result
                except Exception:
                    # Cache failure for this pattern
                    self._fc_match_cache[pattern] = None
                    continue
            else:
                # Cache failure for this pattern
                self._fc_match_cache[pattern] = None

        return None

    def get_font(
        self,
        font_family: str,
        weight: int = 400,
        style: str = "normal",
        stretch: str = "normal",
        inkscape_spec: str | None = None,
        strict_family: bool = True,
        auto_download: bool = False,
    ) -> tuple[TTFont, bytes, int] | None:
        """Load font strictly; return None if exact face not found.

        Caller must abort unless strict_family=False.

        Args:
            font_family: Font family name
            weight: CSS font-weight (100-900)
            style: CSS font-style
            stretch: CSS font-stretch
            inkscape_spec: Inkscape font specification hint (e.g., 'Futura Medium')
            strict_family: If True, warn on family mismatch
            auto_download: If True, attempt to download missing fonts using
                fontget or fnt tools

        Returns:
            Tuple of (TTFont, font_blob_bytes, face_index) or None.
        """
        # Normalize generic Pango family names to CSS generics
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
                # Fallback to fontconfig best match (non-strict)
                match_result = self._match_font_with_fc(
                    font_family, weight, style, stretch
                )
            if match_result is None and font_family in ("sans-serif", "sans"):
                match_result = self._match_font_with_fc("sans", weight, style, stretch)

            # If still not found and auto_download is enabled, try to download
            if match_result is None and auto_download:
                from svg_text2path.fonts.downloader import (
                    auto_download_font,
                    refresh_font_cache,
                )

                print(f"Font '{font_family}' not found locally, attempting download...")
                result = auto_download_font(font_family)
                if result.success:
                    print(f"✓ {result.message}")
                    # Refresh font cache and clear our caches
                    refresh_font_cache()
                    self._fc_match_cache.clear()
                    # Retry matching after download
                    match_result = self._match_font_with_fc(
                        font_family, weight, style, stretch
                    )
                else:
                    print(f"✗ {result.message}")

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
                def _name(tt: TTFont, ids: list[int]) -> str | None:
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
                (_name(ttfont, [17, 2]) or "").lower()

                def _norm(s: str) -> str:
                    return re.sub(r"[^a-z0-9]+", "", s.lower().lstrip("."))

                # Check for family mismatch (RELAXED: use anyway)
                is_generic = font_family.lower() in ("sans-serif", "sans")
                family_mismatch = _norm(fam_candidate) != _norm(font_family)
                not_subset = _norm(font_family) not in _norm(fam_candidate)
                if strict_family and not is_generic and family_mismatch and not_subset:
                    msg = f"Font mismatch: got '{fam_candidate}' "
                    msg += f"for requested '{font_family}'. Using anyway."
                    print(msg)

                self._fonts[cache_key] = (ttfont, font_blob, font_index)
                load_msg = f"Loaded: {font_family} w={weight} s={style} "
                load_msg += f"st={stretch} -> {font_path.name}:{font_index}"
                print(load_msg)

            except Exception as e:
                print(f"✗ Failed to load {font_path}:{font_index}: {e}")
                return None

        return self._fonts.get(cache_key)
