"""Plain text and data URI input handler for SVG content.

Handles .txt files, data URIs (base64 and URL-encoded), and raw SVG strings.
"""

from __future__ import annotations

import base64
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote, unquote
from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

# File size limits to prevent memory exhaustion
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
MAX_DATA_URI_SIZE = 10 * 1024 * 1024  # 10MB max for data URIs

if TYPE_CHECKING:
    pass  # ElementTree imported above for cast()


class PlaintextHandler(FormatHandler):
    """Handler for plain text files and data URIs containing SVG.

    This handler supports three input formats:
    1. Plain text files (.txt) containing raw SVG markup
    2. Data URIs with base64 encoding (data:image/svg+xml;base64,...)
    3. Data URIs with URL encoding (data:image/svg+xml,...)

    The handler preserves the original encoding format when serializing back to
    ensure round-trip compatibility with data URIs.

    Attributes:
        _original_format (str | None): Tracks original data URI encoding format.
            Can be "base64", "urlencoded", or None for raw SVG content.
    """

    # Track original format for serialization
    _original_format: str | None = None  # "base64", "urlencoded", or None for raw

    def __init__(self) -> None:
        """Initialize handler with optional config."""
        super().__init__()

    def _get_effective_max_file_size(self) -> int | None:
        """Get the effective max file size based on config.

        Returns:
            int | None: Max file size in bytes, or None if limits are disabled.
        """
        if self.config and self.config.security.ignore_size_limits:
            return None
        if self.config and self.config.security.max_file_size_mb:
            return self.config.security.max_file_size_mb * 1024 * 1024
        return MAX_FILE_SIZE

    def _get_effective_max_data_uri_size(self) -> int | None:
        """Get the effective max data URI size based on config.

        Returns:
            int | None: Max data URI size in bytes, or None if limits are disabled.
        """
        if self.config and self.config.security.ignore_size_limits:
            return None
        # Data URIs use same limit as files or default
        if self.config and self.config.security.max_file_size_mb:
            return self.config.security.max_file_size_mb * 1024 * 1024
        return MAX_DATA_URI_SIZE

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports.

        Returns:
            list[InputFormat]: List containing PLAINTEXT and DATA_URI formats.
        """
        return [InputFormat.PLAINTEXT, InputFormat.DATA_URI]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Determines if the source is a .txt file, data URI (base64 or URL-encoded),
        or a raw SVG string. Performs detection based on file extension, data URI
        prefix (data:image/svg+xml), or file path checking.

        Args:
            source (Any): Input source to check. Can be a Path object, string file
                path, data URI string, or raw SVG markup.

        Returns:
            bool: True if source is a .txt file, data URI with image/svg+xml MIME
                type, or valid file path to a .txt file. False otherwise.
        """
        if isinstance(source, Path):
            return source.suffix.lower() == ".txt"

        if isinstance(source, str):
            # Check for data URI
            if source.strip().lower().startswith("data:image/svg+xml"):
                return True

            # Check if it's a .txt file path
            if not source.startswith("<"):
                path = Path(source)
                if path.is_file() and path.suffix.lower() == ".txt":
                    return True

        return False

    def parse(self, source: str | Path) -> ElementTree:
        """Parse plain text or data URI into an ElementTree.

        Reads content from the source, automatically detects and decodes data URIs
        (both base64 and URL-encoded formats), extracts SVG markup, and parses it
        into an ElementTree. Tracks the original encoding format for round-trip
        serialization.

        Args:
            source (str | Path): Input source. Can be:
                - Path object to a .txt file
                - String file path to a .txt file
                - Data URI with base64 encoding (data:image/svg+xml;base64,...)
                - Data URI with URL encoding (data:image/svg+xml,...)
                - Raw SVG markup string

        Returns:
            ElementTree: Parsed XML ElementTree representing the SVG document.

        Raises:
            SVGParseError: If SVG content cannot be parsed or is invalid XML.
            FileNotFoundError: If source is a file path that doesn't exist.
        """
        # Reset original format tracking
        self._original_format = None

        # Get the content as string
        content = self._get_content(source)

        # Attempt to extract SVG from the content
        svg_content = self._extract_svg(content)

        # Parse the SVG content
        try:
            return cast(ElementTree, ET.parse(StringIO(svg_content)))
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG content: {e}") from e
        except Exception as e:
            raise SVGParseError(f"Error processing SVG content: {e}") from e

    def serialize(self, tree: ElementTree, target: str | Path) -> Path:
        """Write ElementTree to plain text file, preserving original encoding.

        Serializes the ElementTree to SVG markup and writes it to a file. If the
        original input was a data URI, re-encodes the output using the same format
        (base64 or URL-encoded) to maintain round-trip compatibility. Registers
        common SVG namespaces to avoid ns0: prefixes in output.

        Args:
            tree (ElementTree): The XML ElementTree to serialize.
            target (str | Path): Output file path where the content will be written.

        Returns:
            Path: Path object pointing to the written file.
        """
        path = Path(target) if isinstance(target, str) else target

        # Register SVG namespaces
        self._register_namespaces()

        # Serialize tree to string
        output = StringIO()
        tree.write(output, encoding="unicode", xml_declaration=True)
        svg_string = output.getvalue()

        # Re-encode if original was data URI
        if self._original_format == "base64":
            content = "data:image/svg+xml;base64," + base64.b64encode(
                svg_string.encode("utf-8")
            ).decode("ascii")
        elif self._original_format == "urlencoded":
            content = "data:image/svg+xml," + quote(svg_string, safe="")
        else:
            content = svg_string

        # Write to file
        path.write_text(content, encoding="utf-8")
        return path

    def _get_content(self, source: str | Path) -> str:
        """Read content from source, handling both files and raw strings.

        Determines whether the source is a file path or raw content. For file paths,
        reads the file content. For strings, detects if it's a file path (non-data URI,
        non-SVG markup) and reads it if the file exists, otherwise returns the string
        as-is (data URI or raw SVG markup).

        Args:
            source (str | Path): Input source. Can be:
                - Path object to a file
                - String file path
                - Data URI string
                - Raw SVG markup string

        Returns:
            str: Content read from file or the raw string itself.

        Raises:
            FileNotFoundError: If source is a Path that doesn't exist.
        """
        if isinstance(source, Path):
            if not source.is_file():
                raise FileNotFoundError(f"File not found: {source}")
            # Check file size before reading to prevent memory exhaustion
            max_size = self._get_effective_max_file_size()
            if max_size is not None:
                file_size = source.stat().st_size
                if file_size > max_size:
                    raise SVGParseError(
                        f"File too large: {file_size} bytes (max: {max_size})"
                    )
            return source.read_text(encoding="utf-8")

        if isinstance(source, str):
            # Check if it's a file path
            if not source.startswith("<") and not source.startswith("data:"):
                path = Path(source)
                if path.is_file():
                    # Check file size before reading to prevent memory exhaustion
                    max_size = self._get_effective_max_file_size()
                    if max_size is not None:
                        file_size = path.stat().st_size
                        if file_size > max_size:
                            raise SVGParseError(
                                f"File too large: {file_size} bytes (max: {max_size})"
                            )
                    return path.read_text(encoding="utf-8")

            # It's raw content (data URI or SVG string)
            return source

    def _extract_svg(self, content: str) -> str:
        """Extract SVG from content, decoding data URIs if necessary.

        Analyzes the content to detect the format (raw SVG, data URI at start, or
        embedded data URI) and extracts the SVG markup. For data URIs, delegates to
        _decode_data_uri for base64 or URL decoding. Sets _original_format to track
        the encoding type.

        Args:
            content (str): Raw content string that may contain:
                - Data URI at the beginning (data:image/svg+xml...)
                - Raw SVG markup (starting with <svg or <?xml)
                - Embedded data URI within other text

        Returns:
            str: Extracted and decoded SVG markup as a string.

        Raises:
            SVGParseError: If no valid SVG content is found in the input.
        """
        content = content.strip()

        # Check for data URI
        if content.lower().startswith("data:image/svg+xml"):
            return self._decode_data_uri(content)

        # Check if content is raw SVG
        if "<svg" in content.lower() or content.startswith("<?xml"):
            return content

        # Content might contain a data URI somewhere
        data_uri_start = content.lower().find("data:image/svg+xml")
        if data_uri_start != -1:
            # Extract the data URI portion
            data_uri = content[data_uri_start:]
            # Find the end (whitespace, quote, or end of string)
            for i, char in enumerate(data_uri):
                if char in (" ", "\t", "\n", "'", '"', ")"):
                    data_uri = data_uri[:i]
                    break
            return self._decode_data_uri(data_uri)

        raise SVGParseError("No SVG content found in plain text")

    def _decode_data_uri(self, data_uri: str) -> str:
        """Decode a data URI to SVG string.

        Parses the data URI format, detects the encoding type (base64 or URL-encoded),
        and decodes the content accordingly. Sets _original_format to "base64" or
        "urlencoded" to track the encoding for round-trip serialization.

        Data URI format: data:[<mediatype>][;base64],<data>
        - Base64: data:image/svg+xml;base64,<base64-encoded-svg>
        - URL-encoded: data:image/svg+xml,<url-encoded-svg>

        Args:
            data_uri (str): Data URI string with format:
                - data:image/svg+xml;base64,<base64-content>
                - data:image/svg+xml,<url-encoded-content>

        Returns:
            str: Decoded SVG markup as UTF-8 string.

        Raises:
            SVGParseError: If data URI format is invalid (missing prefix, missing
                comma separator, or decoding fails).
        """
        # Remove data:image/svg+xml prefix
        if not data_uri.lower().startswith("data:image/svg+xml"):
            raise SVGParseError("Invalid data URI: must start with data:image/svg+xml")

        # Find the comma separating metadata from content
        comma_idx = data_uri.find(",")
        if comma_idx == -1:
            raise SVGParseError("Invalid data URI: missing comma separator")

        metadata = data_uri[:comma_idx].lower()
        encoded_content = data_uri[comma_idx + 1 :]

        # Check data URI size before decoding to prevent memory exhaustion
        max_size = self._get_effective_max_data_uri_size()
        if max_size is not None and len(encoded_content) > max_size:
            raise SVGParseError(
                f"Data URI too large: {len(encoded_content)} bytes (max: {max_size})"
            )

        # Check encoding type
        if ";base64" in metadata:
            self._original_format = "base64"
            try:
                return base64.b64decode(encoded_content).decode("utf-8")
            except Exception as e:
                raise SVGParseError(f"Failed to decode base64 data URI: {e}") from e
        else:
            # URL-encoded
            self._original_format = "urlencoded"
            try:
                return unquote(encoded_content)
            except Exception as e:
                msg = f"Failed to decode URL-encoded data URI: {e}"
                raise SVGParseError(msg) from e

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces to avoid ns0: prefixes in output.

        Registers standard SVG-related XML namespaces with ElementTree to ensure
        proper namespace prefixes are used in serialized output. This prevents
        ElementTree from generating generic ns0:, ns1:, etc. prefixes.

        Registered namespaces:
            - "" (default): http://www.w3.org/2000/svg
            - svg: http://www.w3.org/2000/svg
            - xlink: http://www.w3.org/1999/xlink
            - inkscape: http://www.inkscape.org/namespaces/inkscape
            - sodipodi: http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd
        """
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "svg": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
            "inkscape": "http://www.inkscape.org/namespaces/inkscape",
            "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
