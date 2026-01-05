"""Custom exceptions for svg-text2path.

All exceptions inherit from Text2PathError for easy catching.
"""

from typing import Any


class Text2PathError(Exception):
    """Base exception for all svg-text2path errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize with message and optional details dict."""
        super().__init__(message)
        self.message = message
        self.details = details or {}


class FontNotFoundError(Text2PathError):
    """Raised when a required font cannot be found."""

    def __init__(
        self,
        font_family: str,
        weight: int = 400,
        style: str = "normal",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with font specification."""
        message = f"Font not found: {font_family} (weight={weight}, style={style})"
        super().__init__(message, details)
        self.font_family = font_family
        self.weight = weight
        self.style = style


class SVGParseError(Text2PathError):
    """Raised when SVG parsing fails."""

    def __init__(
        self,
        message: str,
        source: str | None = None,
        line: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with parse error details."""
        full_message = message
        if source:
            full_message = f"{message} (source: {source})"
        if line:
            full_message = f"{full_message} at line {line}"
        super().__init__(full_message, details)
        self.source = source
        self.line = line


class ConversionError(Text2PathError):
    """Raised when text-to-path conversion fails."""

    def __init__(
        self,
        message: str,
        element_id: str | None = None,
        text_content: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with conversion error details."""
        full_message = message
        if element_id:
            full_message = f"{message} (element: {element_id})"
        super().__init__(full_message, details)
        self.element_id = element_id
        self.text_content = text_content


class FormatNotSupportedError(Text2PathError):
    """Raised when input format is not supported."""

    def __init__(
        self,
        format_type: str,
        supported_formats: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with format details."""
        message = f"Format not supported: {format_type}"
        if supported_formats:
            message = f"{message}. Supported: {', '.join(supported_formats)}"
        super().__init__(message, details)
        self.format_type = format_type
        self.supported_formats = supported_formats or []


class RemoteResourceError(Text2PathError):
    """Raised when fetching remote resources fails."""

    def __init__(
        self,
        url: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with remote resource details."""
        message = f"Failed to fetch remote resource: {url}"
        if status_code:
            message = f"{message} (status: {status_code})"
        super().__init__(message, details)
        self.url = url
        self.status_code = status_code


class ToolNotFoundError(Text2PathError):
    """Raised when an external tool is not available."""

    def __init__(
        self,
        tool_name: str,
        install_hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with tool details."""
        message = f"External tool not found: {tool_name}"
        if install_hint:
            message = f"{message}. Install with: {install_hint}"
        super().__init__(message, details)
        self.tool_name = tool_name
        self.install_hint = install_hint
