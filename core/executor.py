"""Executor module for Desktop AI Assistant.

Handles launching local applications, opening URLs in the browser,
opening File Explorer, and searching YouTube / Google.
"""

import json
import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "apps.json"


def launch_app(name: str) -> str:
    """Load config/apps.json, look up the exe path for name, and open it using os.startfile(path).

    If the app name isn't found in the JSON or path is invalid, returns an error message.
    """
    if not name:
        return "Error: App name was not provided."

    target_key = name.strip().lower()

    # Load apps mapping from config/apps.json
    config_path = CONFIG_FILE if CONFIG_FILE.exists() else Path("config/apps.json")

    if not config_path.exists():
        return f"Error: Config file not found at {config_path}."

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            apps: Dict[str, str] = json.load(f)
    except Exception as e:
        return f"Error reading {config_path}: {e}"

    if target_key not in apps:
        return f"Error: App '{name}' not found in {config_path.name}."

    exe_path = apps[target_key]
    if not exe_path:
        return f"Error: Executable path for '{name}' is empty in {config_path.name}."

    try:
        os.startfile(exe_path)
        return f"Successfully launched '{name}' ({exe_path})."
    except Exception as e:
        return f"Error launching '{name}' with path '{exe_path}': {e}"


def open_url(url: str) -> str:
    """Open the URL in the default browser using webbrowser.open(url)."""
    if not url:
        return "Error: No URL provided."

    # Prepend http/https if missing
    target_url = url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    try:
        opened = webbrowser.open(target_url)
        return f"Successfully opened URL: {target_url}" if opened else f"Failed to open URL: {target_url}"
    except Exception as e:
        return f"Error opening URL '{target_url}': {e}"


def open_explorer(path: str = None) -> str:
    """Open Windows File Explorer at path if given, otherwise opens it at the default location."""
    try:
        subprocess.run(["explorer", path or ""], check=False)
        return f"Successfully opened File Explorer at '{path or 'default location'}'."
    except Exception as e:
        return f"Error opening File Explorer: {e}"


def search_youtube(query: str) -> str:
    """Search YouTube for query, or directly play the first result via pywhatkit.

    If pywhatkit is installed, uses pywhatkit.playonyt(query) to auto-play the
    first result. Otherwise falls back to opening YouTube search results in the
    default browser.
    """
    if not query:
        return "Error: No search query provided for YouTube."

    try:
        import pywhatkit  # optional dependency
        pywhatkit.playonyt(query)
        return f"Playing '{query}' on YouTube via pywhatkit."
    except ImportError:
        pass  # pywhatkit not installed — fall back to browser
    except Exception as e:
        pass  # pywhatkit failed — fall back to browser

    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    opened = webbrowser.open(url)
    return f"Opened YouTube search for '{query}'." if opened else f"Failed to open YouTube search."


def search_google(query: str) -> str:
    """Open Google search results for query in the default browser."""
    if not query:
        return "Error: No search query provided for Google."

    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    opened = webbrowser.open(url)
    return f"Opened Google search for '{query}'." if opened else f"Failed to open Google search."


def execute(action_dict: Dict[str, Any]) -> str:
    """Execute an action specified by action_dict.

    Supported actions:
      - 'launch_app'    : calls launch_app(target)
      - 'open_url'      : calls open_url(target)
      - 'open_folder'   : calls open_explorer(target)
      - 'search_youtube': calls search_youtube(target)
      - 'search_google' : calls search_google(target)
    """
    if not isinstance(action_dict, dict):
        return "Error: action_dict must be a dictionary."

    action = action_dict.get("action")
    target = action_dict.get("target", "") or ""

    if action == "launch_app":
        return launch_app(target)
    elif action == "open_url":
        return open_url(target)
    elif action == "open_folder":
        return open_explorer(target)
    elif action == "search_youtube":
        return search_youtube(target)
    elif action == "search_google":
        return search_google(target)
    else:
        return (
            f"Error: Unknown action '{action}'. "
            "Supported: 'launch_app', 'open_url', 'open_folder', "
            "'search_youtube', 'search_google'."
        )
