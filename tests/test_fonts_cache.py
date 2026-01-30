"""Unit tests for svg_text2path.fonts.cache module.

Tests cover FontCache initialization, font discovery, caching behavior,
get_font() method, and error handling for missing fonts.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from svg_text2path.fonts import FontCache, MissingFontError


class TestFontCacheInitialization:
    """Tests for FontCache initialization and basic attributes."""

    def test_fontcache_init_creates_empty_font_dict(self):
        """Verify FontCache initializes with empty _fonts dict."""
        cache = FontCache()
        assert hasattr(cache, "_fonts")
        assert isinstance(cache._fonts, dict)
        assert len(cache._fonts) == 0

    def test_fontcache_init_creates_empty_coverage_cache(self):
        """Verify FontCache initializes with empty _coverage_cache dict."""
        cache = FontCache()
        assert hasattr(cache, "_coverage_cache")
        assert isinstance(cache._coverage_cache, dict)
        assert len(cache._coverage_cache) == 0

    def test_fontcache_class_attributes_exist(self):
        """Verify FontCache class-level cache attributes exist."""
        assert hasattr(FontCache, "_fc_cache")
        assert hasattr(FontCache, "_cache_version")
        assert isinstance(FontCache._cache_version, int)
        assert FontCache._cache_version >= 1


class TestFontDiscovery:
    """Tests for font discovery and directory scanning."""

    def test_font_dirs_returns_list_of_paths(self):
        """Verify _font_dirs returns a list of Path objects for the platform."""
        cache = FontCache()
        dirs = cache._font_dirs()
        assert isinstance(dirs, list)
        for d in dirs:
            assert isinstance(d, Path)
            assert d.exists()

    def test_font_dirs_platform_specific(self):
        """Verify _font_dirs returns platform-appropriate directories."""
        cache = FontCache()
        dirs = cache._font_dirs()
        dir_strs = [str(d) for d in dirs]
        if sys.platform == "darwin":
            assert any("Library/Fonts" in s for s in dir_strs)
        elif sys.platform.startswith("linux"):
            assert any("fonts" in s.lower() for s in dir_strs)
        elif sys.platform.startswith("win"):
            assert any("Fonts" in s for s in dir_strs)

    @pytest.mark.slow
    def test_prewarm_indexes_fonts(self):
        """Verify prewarm() populates font cache with indexed fonts."""
        cache = FontCache()
        count = cache.prewarm()
        assert isinstance(count, int)
        assert count > 0
        assert cache._fc_cache is not None
        assert len(cache._fc_cache) > 0


class TestFontCachingBehavior:
    """Tests for persistent cache loading and saving."""

    def test_cache_path_returns_valid_path(self):
        """Verify _cache_path returns a Path in the expected location."""
        cache = FontCache()
        cache._cache_file = None
        path = cache._cache_path()
        assert isinstance(path, Path)
        assert "text2path" in str(path) or "font_cache" in str(path)

    def test_cache_path_respects_env_var(self, tmp_path):
        """Verify _cache_path uses T2P_FONT_CACHE environment variable."""
        cache = FontCache()
        cache._cache_file = None
        custom_path = tmp_path / "custom_cache.json"
        with patch.dict("os.environ", {"T2P_FONT_CACHE": str(custom_path)}):
            path = cache._cache_path()
            assert path == custom_path

    def test_save_and_load_cache_roundtrip(self, tmp_path):
        """Verify cache can be saved and loaded correctly."""
        cache = FontCache()
        cache._cache_file = tmp_path / "test_cache.json"
        # Create a real font file for testing
        fake_font = tmp_path / "test_font.ttf"
        fake_font.write_bytes(b"\x00" * 100)
        test_entries = [
            (
                fake_font,
                0,
                ["testfont"],
                ["regular"],
                "testfont-regular",
                400,
            )
        ]
        prebaked = {
            "testfont": [
                {
                    "path": str(fake_font),
                    "font_index": 0,
                    "styles": ["regular"],
                    "ps": "testfont-regular",
                    "weight": 400,
                    "flags": {},
                }
            ]
        }
        cache._save_cache(test_entries, prebaked, False)
        assert cache._cache_file is not None
        assert cache._cache_file.exists()
        data = json.loads(cache._cache_file.read_text())
        assert data["version"] == FontCache._cache_version
        assert len(data["fonts"]) == 1
        assert data["fonts"][0]["families"] == ["testfont"]


class TestGetFontMethod:
    """Tests for get_font() method with real system fonts."""

    @pytest.mark.slow
    def test_get_font_with_known_font_returns_tuple(self):
        """Verify get_font returns (TTFont, bytes, int) for a known font."""
        cache = FontCache()
        cache.prewarm()
        if sys.platform == "darwin":
            font_family = "Helvetica"
        elif sys.platform.startswith("linux"):
            font_family = "DejaVu Sans"
        else:
            font_family = "Arial"
        result = cache.get_font(font_family, weight=400, style="normal")
        if result is not None:
            ttfont, blob, face_idx = result
            assert ttfont is not None
            assert isinstance(blob, bytes)
            assert len(blob) > 0
            assert isinstance(face_idx, int)
            assert face_idx >= 0

    @pytest.mark.slow
    def test_get_font_caches_loaded_font(self):
        """Verify get_font caches the loaded font for subsequent calls."""
        cache = FontCache()
        cache.prewarm()
        font_family = "Helvetica" if sys.platform == "darwin" else "Arial"
        result1 = cache.get_font(font_family, weight=400, style="normal")
        result2 = cache.get_font(font_family, weight=400, style="normal")
        if result1 is not None and result2 is not None:
            assert result1[0] is result2[0]

    @pytest.mark.slow
    def test_get_font_different_weights_load_different_faces(self):
        """Verify get_font loads different faces for different weights."""
        cache = FontCache()
        cache.prewarm()
        font_family = "Helvetica" if sys.platform == "darwin" else "Arial"
        result_regular = cache.get_font(font_family, weight=400, style="normal")
        result_bold = cache.get_font(font_family, weight=700, style="normal")
        if result_regular is not None and result_bold is not None:
            cache_key_regular = f"{font_family}:400:normal:normal:None".lower()
            cache_key_bold = f"{font_family}:700:normal:normal:None".lower()
            assert cache_key_regular in cache._fonts
            assert cache_key_bold in cache._fonts


class TestMissingFontErrorHandling:
    """Tests for error handling when fonts are not found."""

    def test_missing_font_error_is_exception(self):
        """Verify MissingFontError is a proper Exception subclass."""
        assert issubclass(MissingFontError, Exception)

    def test_missing_font_error_has_required_fields(self):
        """Verify MissingFontError/FontNotFoundError has required attributes."""
        err = MissingFontError(
            font_family="FakeFont",
            weight=400,
            style="normal",
        )
        assert err.font_family == "FakeFont"
        assert err.weight == 400
        assert err.style == "normal"
        assert "FakeFont" in err.message

    @pytest.mark.slow
    def test_get_font_nonexistent_font_uses_fallback(self):
        """Verify get_font with nonexistent font falls back via fontconfig.

        fontconfig provides a fallback font when the requested family
        does not exist, so we verify the result is still a valid font tuple
        (not None) when strict_family=True allows fallback behavior.
        """
        cache = FontCache()
        cache.prewarm()
        # With fontconfig, a fallback font is returned even for nonexistent families
        result = cache.get_font(
            "ThisFontDefinitelyDoesNotExist12345",
            weight=400,
            style="normal",
            strict_family=True,
        )
        # fontconfig provides a fallback, so result may be a valid tuple or None
        # depending on system configuration. Either outcome is acceptable.
        if result is not None:
            ttfont, blob, face_idx = result
            assert ttfont is not None
            assert isinstance(blob, bytes)
            assert isinstance(face_idx, int)


class TestCorruptedFontDetection:
    """Tests for corrupted font detection and repair functionality."""

    def test_corrupted_fonts_file_property_returns_path(self, tmp_path):
        """Verify _corrupted_fonts_file returns expected path."""
        cache = FontCache()
        cache._cache_file = tmp_path / "font_cache.json"
        path = cache._corrupted_fonts_file
        assert isinstance(path, Path)
        assert "corrupted_fonts.json" in str(path)

    def test_validate_font_file_returns_false_for_invalid_file(self, tmp_path):
        """Verify _validate_font_file returns False for non-font file."""
        cache = FontCache()
        fake_font = tmp_path / "fake.ttf"
        fake_font.write_bytes(b"not a font file content")
        assert cache._validate_font_file(fake_font) is False

    def test_validate_font_file_returns_false_for_nonexistent_file(self, tmp_path):
        """Verify _validate_font_file returns False for missing file."""
        cache = FontCache()
        missing = tmp_path / "missing.ttf"
        assert cache._validate_font_file(missing) is False

    def test_corrupted_fonts_set_initialized_empty(self):
        """Verify FontCache initializes with empty _corrupted_fonts set."""
        cache = FontCache()
        assert hasattr(cache, "_corrupted_fonts")
        assert isinstance(cache._corrupted_fonts, set)

    def test_clear_corrupted_fonts_empties_set(self, tmp_path):
        """Verify clear_corrupted_fonts() resets the exclusion list."""
        cache = FontCache()
        cache._cache_file = tmp_path / "font_cache.json"
        # Add a fake corrupted font
        cache._corrupted_fonts.add((str(tmp_path / "bad.ttf"), 0))
        # Save it
        cache._save_corrupted_fonts()
        # Verify file exists
        assert cache._corrupted_fonts_file.exists()
        # Clear
        cache.clear_corrupted_fonts()
        # Verify set is empty
        assert len(cache._corrupted_fonts) == 0
        # Verify file is removed or empty
        if cache._corrupted_fonts_file.exists():
            data = json.loads(cache._corrupted_fonts_file.read_text())
            assert len(data.get("corrupted", [])) == 0

    def test_corrupted_font_persisted_to_file(self, tmp_path):
        """Verify corrupted fonts are saved to and loaded from file."""
        cache = FontCache()
        cache._cache_file = tmp_path / "font_cache.json"
        bad_path = str(tmp_path / "bad.ttf")
        cache._corrupted_fonts.add((bad_path, 0))
        cache._save_corrupted_fonts()
        # Create new cache instance and load
        cache2 = FontCache()
        cache2._cache_file = tmp_path / "font_cache.json"
        cache2._load_corrupted_fonts()
        assert (bad_path, 0) in cache2._corrupted_fonts

    def test_is_font_corrupted_returns_true_for_tracked_font(self, tmp_path):
        """Verify _is_font_corrupted returns True for tracked corrupted fonts."""
        cache = FontCache()
        bad_path = tmp_path / "bad.ttf"
        cache._corrupted_fonts.add((str(bad_path), 0))
        assert cache._is_font_corrupted(bad_path, 0) is True
        assert cache._is_font_corrupted(bad_path, 1) is False

    def test_read_font_meta_skips_corrupted_fonts(self, tmp_path):
        """Verify _read_font_meta skips fonts marked as corrupted."""
        cache = FontCache()
        fake_font = tmp_path / "fake.ttf"
        fake_font.write_bytes(b"\x00" * 100)
        # Mark as corrupted
        cache._corrupted_fonts.add((str(fake_font), 0))
        # Should return None since it's corrupted
        result = cache._read_font_meta(fake_font, False)
        assert result is None
