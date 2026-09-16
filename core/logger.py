"""Shared logging setup for Desktop AI Assistant.

All modules import get_logger() from here instead of using print().
Logs are written to  <project_root>/logs/desktop_ai.log
(RotatingFileHandler: 1 MB max, 3 backups).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _resolve_log_dir() -> Path:
    """Return the directory where log files should be written.

    When frozen by PyInstaller, sys.executable is the .exe file; the log
    folder sits next to it.  When running from source, it sits next to
    the project root (parent of this file's parent).
    """
    if getattr(sys, "frozen", False):
        # PyInstaller bundle — exe lives at sys.executable
        base = Path(sys.executable).parent
    else:
        # Running from source — <project_root>/logs/
        base = Path(__file__).resolve().parents[1]
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


_LOG_FILE = _resolve_log_dir() / "desktop_ai.log"

_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# One shared handler so multiple get_logger() calls don't duplicate output
_handler: RotatingFileHandler | None = None


def _get_handler() -> RotatingFileHandler:
    global _handler
    if _handler is None:
        _handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=1 * 1024 * 1024,   # 1 MB
            backupCount=3,
            encoding="utf-8",
        )
        _handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return _handler


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger that writes to the rotating log file.

    Usage::

        from core.logger import get_logger
        log = get_logger(__name__)
        log.info("App started")
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_get_handler())
        logger.setLevel(logging.DEBUG)
        logger.propagate = False   # Don't bubble up to root (avoids stderr output)
    return logger
