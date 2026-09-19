"""Action Validation Layer for Desktop AI Assistant.

Ensures strict security boundaries before any action reaches the executor:
1. Allowlist filtering of permitted action names.
2. Target payload type and length bounds checking (< 200 chars).
3. Shell metacharacter injection blocking (; , & , | , ` , $() ).
4. URL scheme and netloc validation for open_url.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("desktop_ai.validator")

# Permitted actions allowlist
ALLOWED_ACTIONS: set[str] = {
    "launch_app",
    "open_url",
    "open_folder",
    "search_google",
    "search_youtube",
    "get_news",
    "get_outlet_news",
    "get_stock_movers",
    "media_control",
    "make_call",
}

# Dangerous shell metacharacters that could indicate command injection
SHELL_METACHARACTERS: tuple[str, ...] = (";", "&", "|", "`", "$(")


def validate_action(action_dict: dict[str, Any]) -> dict[str, Any] | None:
    """Validate an action dictionary against security and allowlist rules.

    Args:
        action_dict: Dictionary with 'action' and optional 'target' keys.

    Returns:
        The validated action_dict if all checks pass, else None.
    """
    if not isinstance(action_dict, dict):
        log.warning("Validation rejected: action_dict is not a dictionary.")
        return None

    action = action_dict.get("action")
    target = action_dict.get("target")

    # Map legacy / internal spotify actions to media_control
    if action in {"spotify_play_pause", "spotify_next", "spotify_prev", "spotify_search"}:
        action = "media_control"
        action_dict = dict(action_dict)
        action_dict["action"] = "media_control"

    # 1. Action allowlist check
    if action not in ALLOWED_ACTIONS:
        log.warning("Validation rejected: action %r is not in allowlist.", action)
        return None

    # 2. Target type, length (< 200 chars), and shell metacharacter checks
    if target is not None:
        if not isinstance(target, str):
            log.warning("Validation rejected: target must be a string or None, got %s.", type(target).__name__)
            return None

        if len(target) >= 200:
            log.warning("Validation rejected: target length (%d) exceeds 200 characters limit.", len(target))
            return None

        for meta in SHELL_METACHARACTERS:
            if meta in target:
                log.warning("Validation rejected: target contains dangerous shell metacharacter %r.", meta)
                return None

    # 3. For open_url, validate well-formed URL with valid scheme and netloc
    if action == "open_url":
        if not target or not isinstance(target, str):
            log.warning("Validation rejected: open_url target is missing or not a string.")
            return None

        try:
            parsed = urlparse(target)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                log.warning("Validation rejected: malformed URL %r (scheme=%r, netloc=%r).", target, parsed.scheme, parsed.netloc)
                return None
        except Exception as e:
            log.warning("Validation rejected: error parsing URL %r: %s", target, e)
            return None

    return action_dict
