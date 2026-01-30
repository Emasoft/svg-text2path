"""Unit tests for svg_text2path.fonts.downloader module.

Tests cover network availability checking, font download tool detection,
fontget/fnt integration, and automatic font downloading functionality.

Coverage: Target 70%+ effective coverage
- Network availability: is_network_available() with mocked socket
- Tool detection: is_fontget_available(), is_fnt_available(), get_available_tools()
- fontget operations: fontget_search(), fontget_install()
- fnt operations: fnt_search(), fnt_install()
- auto_download_font(): main download function with various scenarios
- refresh_font_cache(): system cache refresh

Limitations:
- Does not test actual font downloads (external dependencies mocked)
- Does not test real network connectivity
"""

import subprocess
from unittest.mock import MagicMock, patch

from svg_text2path.fonts.downloader import (
    FontDownloadResult,
    auto_download_font,
    fnt_install,
    fnt_search,
    fontget_install,
    fontget_search,
    get_available_tools,
    is_fontget_available,
    is_fnt_available,
    is_network_available,
    refresh_font_cache,
)


class TestNetworkAvailability:
    """Tests for is_network_available() function."""

    def test_network_available_returns_true_on_successful_connect(self):
        """Verify is_network_available returns True when socket connects."""
        mock_socket = MagicMock()
        with patch("svg_text2path.fonts.downloader.socket.socket", return_value=mock_socket):
            result = is_network_available(timeout=1.0)
            assert result is True
            mock_socket.connect.assert_called()
            mock_socket.close.assert_called()

    def test_network_unavailable_returns_false_on_oserror(self):
        """Verify is_network_available returns False when all connections fail."""
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = OSError("Network unreachable")
        with patch("svg_text2path.fonts.downloader.socket.socket", return_value=mock_socket):
            result = is_network_available(timeout=1.0)
            assert result is False

    def test_network_unavailable_returns_false_on_timeout(self):
        """Verify is_network_available returns False on TimeoutError."""
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = TimeoutError("Connection timed out")
        with patch("svg_text2path.fonts.downloader.socket.socket", return_value=mock_socket):
            result = is_network_available(timeout=0.5)
            assert result is False

    def test_network_available_tries_multiple_hosts(self):
        """Verify is_network_available tries fallback hosts on failure."""
        mock_socket = MagicMock()
        # First host fails, second succeeds
        mock_socket.connect.side_effect = [OSError("First failed"), None]
        with patch("svg_text2path.fonts.downloader.socket.socket", return_value=mock_socket):
            result = is_network_available(timeout=1.0)
            assert result is True
            # Should have been called twice (failed once, succeeded once)
            assert mock_socket.connect.call_count == 2


class TestToolAvailability:
    """Tests for tool availability checking functions."""

    def test_is_fontget_available_returns_true_when_on_path(self):
        """Verify is_fontget_available returns True when fontget is found."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value="/usr/local/bin/fontget"):
            result = is_fontget_available()
            assert result is True

    def test_is_fontget_available_returns_false_when_not_on_path(self):
        """Verify is_fontget_available returns False when fontget not found."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value=None):
            result = is_fontget_available()
            assert result is False

    def test_is_fnt_available_returns_true_when_on_path(self):
        """Verify is_fnt_available returns True when fnt is found."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value="/usr/local/bin/fnt"):
            result = is_fnt_available()
            assert result is True

    def test_is_fnt_available_returns_false_when_not_on_path(self):
        """Verify is_fnt_available returns False when fnt not found."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value=None):
            result = is_fnt_available()
            assert result is False

    def test_get_available_tools_returns_both_when_available(self):
        """Verify get_available_tools returns both tools when both are installed."""
        with patch("svg_text2path.fonts.downloader.shutil.which") as mock_which:
            mock_which.side_effect = lambda x: f"/usr/local/bin/{x}" if x in ("fontget", "fnt") else None
            result = get_available_tools()
            assert "fontget" in result
            assert "fnt" in result
            assert len(result) == 2

    def test_get_available_tools_returns_empty_when_none_available(self):
        """Verify get_available_tools returns empty list when no tools installed."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value=None):
            result = get_available_tools()
            assert result == []


class TestFontgetOperations:
    """Tests for fontget search and install operations."""

    def test_fontget_search_returns_empty_when_tool_unavailable(self):
        """Verify fontget_search returns empty list when fontget not available."""
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=False):
            result = fontget_search("Roboto")
            assert result == []

    def test_fontget_search_returns_fonts_on_success(self):
        """Verify fontget_search parses and returns font names."""
        mock_output = "Roboto\nRoboto Condensed\nRoboto Mono\n"
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")
                result = fontget_search("Roboto")
                assert "Roboto" in result
                assert "Roboto Condensed" in result
                assert len(result) >= 2

    def test_fontget_search_returns_empty_on_nonzero_exit(self):
        """Verify fontget_search returns empty list on failed search."""
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")
                result = fontget_search("NonexistentFont")
                assert result == []

    def test_fontget_search_handles_timeout(self):
        """Verify fontget_search handles subprocess timeout gracefully."""
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="fontget", timeout=30)
                result = fontget_search("Roboto")
                assert result == []

    def test_fontget_install_returns_failure_when_tool_unavailable(self):
        """Verify fontget_install returns failure result when fontget not available."""
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=False):
            result = fontget_install("Roboto")
            assert isinstance(result, FontDownloadResult)
            assert result.success is False
            assert result.font_family == "Roboto"
            assert "fontget not available" in result.message

    def test_fontget_install_returns_success_on_zero_exit(self):
        """Verify fontget_install returns success when subprocess succeeds."""
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="Installed", stderr="")
                result = fontget_install("Roboto")
                assert result.success is True
                assert result.font_family == "Roboto"
                assert result.tool_used == "fontget"

    def test_fontget_install_returns_failure_on_nonzero_exit(self):
        """Verify fontget_install returns failure when subprocess fails."""
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Font not found")
                result = fontget_install("NonexistentFont")
                assert result.success is False
                assert "Font not found" in result.message

    def test_fontget_install_handles_timeout(self):
        """Verify fontget_install handles subprocess timeout gracefully."""
        with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="fontget", timeout=120)
                result = fontget_install("Roboto")
                assert result.success is False
                assert "Timeout" in result.message


class TestFntOperations:
    """Tests for fnt search and install operations."""

    def test_fnt_search_returns_empty_when_tool_unavailable(self):
        """Verify fnt_search returns empty list when fnt not available."""
        with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=False):
            result = fnt_search("EB Garamond")
            assert result == []

    def test_fnt_search_returns_packages_on_success(self):
        """Verify fnt_search parses and returns package names."""
        mock_output = "fonts-ebgaramond\ngoogle-ebgaramond\n"
        with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")
                result = fnt_search("EB Garamond")
                assert "fonts-ebgaramond" in result
                assert "google-ebgaramond" in result

    def test_fnt_search_handles_timeout(self):
        """Verify fnt_search handles subprocess timeout gracefully."""
        with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="fnt", timeout=30)
                result = fnt_search("Roboto")
                assert result == []

    def test_fnt_install_returns_failure_when_tool_unavailable(self):
        """Verify fnt_install returns failure result when fnt not available."""
        with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=False):
            result = fnt_install("fonts-roboto")
            assert result.success is False
            assert "fnt not available" in result.message

    def test_fnt_install_returns_success_on_zero_exit(self):
        """Verify fnt_install returns success when subprocess succeeds."""
        with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="Installed", stderr="")
                result = fnt_install("fonts-roboto")
                assert result.success is True
                assert result.package_name == "fonts-roboto"
                assert result.tool_used == "fnt"

    def test_fnt_install_handles_subprocess_error(self):
        """Verify fnt_install handles subprocess errors gracefully."""
        with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.SubprocessError("Process failed")
                result = fnt_install("fonts-roboto")
                assert result.success is False
                assert "Error" in result.message


class TestAutoDownloadFont:
    """Tests for auto_download_font() main download function."""

    def test_auto_download_returns_failure_when_network_unavailable(self):
        """Verify auto_download_font fails gracefully when offline."""
        with patch("svg_text2path.fonts.downloader.is_network_available", return_value=False):
            result = auto_download_font("Roboto")
            assert result.success is False
            assert "no network" in result.message.lower()
            assert result.font_family == "Roboto"

    def test_auto_download_returns_failure_when_no_tools_available(self):
        """Verify auto_download_font fails when no download tools installed."""
        with patch("svg_text2path.fonts.downloader.is_network_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.get_available_tools", return_value=[]):
                result = auto_download_font("Roboto")
                assert result.success is False
                assert "No font download tools available" in result.message

    def test_auto_download_tries_fontget_first(self):
        """Verify auto_download_font prefers fontget over fnt."""
        with patch("svg_text2path.fonts.downloader.is_network_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.get_available_tools", return_value=["fontget", "fnt"]):
                with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
                    with patch("svg_text2path.fonts.downloader.fontget_install") as mock_fontget:
                        mock_fontget.return_value = FontDownloadResult(
                            success=True,
                            font_family="Roboto",
                            tool_used="fontget",
                            message="Installed",
                        )
                        result = auto_download_font("Roboto")
                        assert result.success is True
                        assert result.tool_used == "fontget"
                        mock_fontget.assert_called_once_with("Roboto")

    def test_auto_download_falls_back_to_fnt_on_fontget_failure(self):
        """Verify auto_download_font uses fnt as fallback when fontget fails."""
        with patch("svg_text2path.fonts.downloader.is_network_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.get_available_tools", return_value=["fontget", "fnt"]):
                with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=True):
                    with patch("svg_text2path.fonts.downloader.fontget_install") as mock_fontget:
                        mock_fontget.return_value = FontDownloadResult(
                            success=False,
                            font_family="Roboto",
                            tool_used="fontget",
                            message="Failed",
                        )
                        with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=True):
                            with patch("svg_text2path.fonts.downloader.fnt_search") as mock_search:
                                mock_search.return_value = ["google-roboto"]
                                with patch("svg_text2path.fonts.downloader.fnt_install") as mock_fnt:
                                    mock_fnt.return_value = FontDownloadResult(
                                        success=True,
                                        font_family="",
                                        package_name="google-roboto",
                                        tool_used="fnt",
                                        message="Installed",
                                    )
                                    result = auto_download_font("Roboto")
                                    assert result.success is True
                                    assert result.tool_used == "fnt"

    def test_auto_download_fnt_no_packages_found(self):
        """Verify auto_download_font returns failure when fnt finds no packages."""
        with patch("svg_text2path.fonts.downloader.is_network_available", return_value=True):
            with patch("svg_text2path.fonts.downloader.get_available_tools", return_value=["fnt"]):
                with patch("svg_text2path.fonts.downloader.is_fontget_available", return_value=False):
                    with patch("svg_text2path.fonts.downloader.is_fnt_available", return_value=True):
                        with patch("svg_text2path.fonts.downloader.fnt_search") as mock_search:
                            mock_search.return_value = []
                            result = auto_download_font("NonexistentFont")
                            assert result.success is False
                            assert "No font packages found" in result.message


class TestRefreshFontCache:
    """Tests for refresh_font_cache() function."""

    def test_refresh_font_cache_uses_fc_cache_when_available(self):
        """Verify refresh_font_cache calls fc-cache when available."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value="/usr/bin/fc-cache"):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = refresh_font_cache()
                assert result is True
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "fc-cache" in call_args[0]

    def test_refresh_font_cache_returns_false_when_fc_cache_unavailable(self):
        """Verify refresh_font_cache returns False when fc-cache not found."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value=None):
            result = refresh_font_cache()
            assert result is False

    def test_refresh_font_cache_handles_subprocess_error(self):
        """Verify refresh_font_cache handles subprocess errors gracefully."""
        with patch("svg_text2path.fonts.downloader.shutil.which", return_value="/usr/bin/fc-cache"):
            with patch("svg_text2path.fonts.downloader.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.SubprocessError("fc-cache failed")
                result = refresh_font_cache()
                assert result is False


class TestFontDownloadResult:
    """Tests for FontDownloadResult dataclass."""

    def test_font_download_result_default_values(self):
        """Verify FontDownloadResult has correct default values."""
        result = FontDownloadResult(success=True, font_family="Roboto")
        assert result.success is True
        assert result.font_family == "Roboto"
        assert result.package_name is None
        assert result.tool_used is None
        assert result.message == ""

    def test_font_download_result_all_fields(self):
        """Verify FontDownloadResult stores all field values correctly."""
        result = FontDownloadResult(
            success=True,
            font_family="Roboto",
            package_name="google-roboto",
            tool_used="fnt",
            message="Successfully installed",
        )
        assert result.success is True
        assert result.font_family == "Roboto"
        assert result.package_name == "google-roboto"
        assert result.tool_used == "fnt"
        assert result.message == "Successfully installed"
