"""Logging configuration for svg-text2path.

Provides structured logging with:
- Configurable log levels
- Optional file output with rotation
- Rich console formatting (when available)
"""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Module-level logger
logger = logging.getLogger("svg_text2path")


def setup_logging(
    level: str = "WARNING",
    log_file: Path | str | None = None,
    log_dir: Path | str | None = None,
    rich_console: bool = True,
) -> logging.Logger:
    """Configure logging for svg-text2path.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Explicit log file path. Mutually exclusive with log_dir.
        log_dir: Directory for auto-named log files. Creates svg_text2path_YYYYMMDD.log.
        rich_console: Use rich formatting for console output if available.

    Returns:
        Configured logger instance.
    """
    # Clear existing handlers
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.WARNING))

    # Console handler - typed as Handler to allow RichHandler assignment
    console_handler: logging.Handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logger.level)

    # Try rich formatting if available and requested
    console_format = "%(levelname)s - %(message)s"
    if rich_console:
        try:
            from rich.logging import RichHandler

            console_handler = RichHandler(
                show_time=False,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
            )
            console_format = "%(message)s"
        except ImportError:
            pass

    console_handler.setFormatter(logging.Formatter(console_format))
    logger.addHandler(console_handler)

    # File handler (if requested)
    file_path: Path | None = None
    if log_file or log_dir:
        if log_file:
            file_path = Path(log_file)
        elif log_dir is not None:
            dir_path = Path(log_dir)
            dir_path.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            file_path = dir_path / f"svg_text2path_{date_str}.log"

        if file_path:
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)  # Always log everything to file
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(file_handler)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Optional child logger name (e.g., "fonts", "svg").
              If None, returns the main logger.

    Returns:
        Logger instance.
    """
    if name:
        return logger.getChild(name)
    return logger


class ConversionLogger:
    """Context manager for logging conversion operations.

    Tracks warnings and errors during conversion for batch reporting.
    """

    def __init__(self, source: str) -> None:
        """Initialize conversion logger.

        Args:
            source: Description of the conversion source (filename, etc.).
        """
        self.source = source
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self._log = get_logger("conversion")

    def __enter__(self) -> "ConversionLogger":
        """Enter conversion context."""
        self._log.info("Starting conversion: %s", self.source)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit conversion context, log summary."""
        if exc_type:
            self.errors.append(str(exc_val))
            self._log.error("Conversion failed for %s: %s", self.source, exc_val)
        elif self.errors:
            self._log.warning(
                "Conversion completed with %d errors: %s",
                len(self.errors),
                self.source,
            )
        elif self.warnings:
            self._log.info(
                "Conversion completed with %d warnings: %s",
                len(self.warnings),
                self.source,
            )
        else:
            self._log.info("Conversion successful: %s", self.source)
        # Don't suppress exceptions (returning None is equivalent to False)

    def warning(self, message: str, *args) -> None:
        """Log a warning."""
        formatted = message % args if args else message
        self.warnings.append(formatted)
        self._log.warning(formatted)

    def error(self, message: str, *args) -> None:
        """Log an error."""
        formatted = message % args if args else message
        self.errors.append(formatted)
        self._log.error(formatted)

    def debug(self, message: str, *args) -> None:
        """Log a debug message."""
        self._log.debug(message, *args)

    def info(self, message: str, *args) -> None:
        """Log an info message."""
        self._log.info(message, *args)
