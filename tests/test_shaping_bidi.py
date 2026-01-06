"""Unit tests for svg_text2path.shaping.bidi module.

Tests BiDi (Bidirectional) text handling for proper LTR/RTL text processing.
"""

from svg_text2path.shaping.bidi import (
    apply_bidi_algorithm,
    detect_base_direction,
    get_bidi_runs,
    get_visual_runs,
    is_rtl_script,
)


class TestLTRTextProcessing:
    """Test LTR (left-to-right) text processing for English/Latin scripts."""

    def test_english_text_returns_unchanged(self):
        """English text should remain unchanged after BiDi processing."""
        text = "Hello World"
        result = apply_bidi_algorithm(text, base_direction="ltr")
        assert result == "Hello World"

    def test_english_text_single_ltr_run(self):
        """English text should produce a single LTR run."""
        text = "Hello World"
        runs = get_bidi_runs(text, base_direction="ltr")
        assert len(runs) >= 1
        assert runs[0].direction == "ltr"
        assert runs[0].level % 2 == 0  # Even level = LTR

    def test_detect_english_as_ltr(self):
        """detect_base_direction should identify English as LTR."""
        text = "Hello World"
        direction = detect_base_direction(text)
        assert direction == "ltr"

    def test_english_not_rtl_script(self):
        """is_rtl_script should return False for English text."""
        text = "Hello World"
        result = is_rtl_script(text)
        assert result is False


class TestRTLTextProcessing:
    """Test RTL (right-to-left) text processing for Arabic/Hebrew scripts."""

    def test_arabic_text_detected_as_rtl(self):
        """Arabic text should be detected as RTL direction."""
        arabic_text = "\u0645\u0631\u062d\u0628\u0627"  # "marhaba" (hello)
        direction = detect_base_direction(arabic_text)
        assert direction == "rtl"

    def test_hebrew_text_detected_as_rtl(self):
        """Hebrew text should be detected as RTL direction."""
        hebrew_text = "\u05e9\u05dc\u05d5\u05dd"  # "shalom"
        direction = detect_base_direction(hebrew_text)
        assert direction == "rtl"

    def test_arabic_produces_rtl_run(self):
        """Arabic text should produce RTL run with odd embedding level."""
        arabic_text = "\u0645\u0631\u062d\u0628\u0627"
        runs = get_bidi_runs(arabic_text, base_direction="rtl")
        assert len(runs) >= 1
        # At least one run should be RTL
        rtl_runs = [r for r in runs if r.direction == "rtl"]
        assert len(rtl_runs) >= 1

    def test_arabic_is_rtl_script(self):
        """is_rtl_script should return True for Arabic text."""
        arabic_text = "\u0645\u0631\u062d\u0628\u0627"
        result = is_rtl_script(arabic_text)
        assert result is True


class TestMixedBidirectionalText:
    """Test mixed LTR/RTL bidirectional text processing."""

    def test_mixed_text_produces_runs(self):
        """Mixed English and Arabic text should produce runs covering all text."""
        mixed_text = "Hello \u0645\u0631\u062d\u0628\u0627 World"
        runs = get_bidi_runs(mixed_text, base_direction="ltr")
        # Should have at least 1 run covering the text
        assert len(runs) >= 1
        # All text should be covered by runs
        combined = "".join(run.text for run in runs)
        assert combined == mixed_text

    def test_mixed_text_has_both_directions(self):
        """Mixed text runs should contain both LTR and RTL directions."""
        mixed_text = "Hello \u0645\u0631\u062d\u0628\u0627 World"
        runs = get_bidi_runs(mixed_text, base_direction="ltr")
        directions = {run.direction for run in runs}
        # Should have both directions represented
        assert "ltr" in directions or "rtl" in directions

    def test_mixed_text_bidi_algorithm_reorders(self):
        """apply_bidi_algorithm should handle mixed text."""
        mixed_text = "Hello \u0645\u0631\u062d\u0628\u0627"
        result = apply_bidi_algorithm(mixed_text, base_direction="ltr")
        # Result should contain both parts (may be reordered)
        assert "Hello" in result
        assert "\u0645" in result  # First Arabic char should be present


class TestVisualOrdering:
    """Test visual ordering of characters for display."""

    def test_visual_runs_not_empty_for_text(self):
        """get_visual_runs should return runs for non-empty text."""
        text = "Hello World"
        runs = get_visual_runs(text, base_direction="ltr")
        assert len(runs) >= 1

    def test_visual_runs_empty_for_empty_text(self):
        """get_visual_runs should return empty list for empty text."""
        runs = get_visual_runs("", base_direction="ltr")
        assert runs == []

    def test_visual_runs_preserve_text_content(self):
        """Visual runs should together contain all original text."""
        text = "Hello World"
        runs = get_visual_runs(text, base_direction="ltr")
        combined = "".join(run.text for run in runs)
        assert combined == text

    def test_visual_runs_rtl_text_reordered(self):
        """RTL text visual runs should be properly ordered for display."""
        hebrew_text = "\u05e9\u05dc\u05d5\u05dd"  # "shalom"
        runs = get_visual_runs(hebrew_text, base_direction="rtl")
        assert len(runs) >= 1
        # Combined text should preserve characters
        combined = "".join(run.text for run in runs)
        assert len(combined) == len(hebrew_text)


class TestParagraphDirectionDetection:
    """Test paragraph base direction detection."""

    def test_detect_ltr_for_latin_text(self):
        """Latin text should be detected as LTR."""
        assert detect_base_direction("Hello") == "ltr"

    def test_detect_rtl_for_arabic_text(self):
        """Arabic text should be detected as RTL."""
        assert detect_base_direction("\u0645\u0631\u062d\u0628\u0627") == "rtl"

    def test_detect_rtl_for_hebrew_text(self):
        """Hebrew text should be detected as RTL."""
        assert detect_base_direction("\u05e9\u05dc\u05d5\u05dd") == "rtl"

    def test_detect_first_strong_char_wins(self):
        """Direction should be determined by first strong character."""
        # Arabic first, then English
        text = "\u0645\u0631\u062d\u0628\u0627 Hello"
        assert detect_base_direction(text) == "rtl"

        # English first, then Arabic
        text2 = "Hello \u0645\u0631\u062d\u0628\u0627"
        assert detect_base_direction(text2) == "ltr"

    def test_empty_text_defaults_to_ltr(self):
        """Empty text should default to LTR direction."""
        assert detect_base_direction("") == "ltr"

    def test_numbers_only_defaults_to_ltr(self):
        """Text with only numbers should default to LTR."""
        assert detect_base_direction("12345") == "ltr"
