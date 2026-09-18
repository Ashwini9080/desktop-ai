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


import datetime
import time


def _resolve_project_root() -> Path:
    """Return the project root directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def _resolve_log_dir() -> Path:
    """Return the directory where log files should be written.

    When frozen by PyInstaller, sys.executable is the .exe file; the log
    folder sits next to it.  When running from source, it sits next to
    the project root (parent of this file's parent).
    """
    log_dir = _resolve_project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


_PERF_FILE = _resolve_project_root() / "performance.log"
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


def log_performance(step: str, duration: float, detail: str = "") -> None:
    """Record timing for a pipeline stage to performance.log without printing to console.

    Args:
        step: Name of the stage (e.g. RECORDING, TRANSCRIPTION, CLASSIFICATION, EXECUTION, SPEAKING).
        duration: Elapsed time in seconds.
        detail: Optional context string.
    """
    try:
        now_str = datetime.datetime.now().strftime(_DATE_FORMAT)
        line = f"{now_str} | [{step.upper():<14}] {duration:6.2f}s"
        if detail:
            line += f" | {detail}"
        line += "\n"

        with open(_PERF_FILE, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception:
        pass

