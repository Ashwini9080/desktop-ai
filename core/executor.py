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


import ctypes

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

BLOCKED_MAIL_DOMAINS = ["mail.google.com", "gmail.com", "outlook.live.com", "mail.yahoo.com"]


def _send_media_key(vk_code: int) -> None:
    """Simulate a Windows multimedia keypress."""
    try:
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
    except Exception as e:
        pass


def spotify_play_pause() -> str:
    """Toggle play/pause for Spotify / active media player."""
    _send_media_key(VK_MEDIA_PLAY_PAUSE)
    return "Toggled Spotify play/pause."


def spotify_next() -> str:
    """Skip to next track on Spotify."""
    _send_media_key(VK_MEDIA_NEXT_TRACK)
    return "Skipped to next track on Spotify."


def spotify_prev() -> str:
    """Go to previous track on Spotify."""
    _send_media_key(VK_MEDIA_PREV_TRACK)
    return "Playing previous track on Spotify."


def spotify_search(query: str) -> str:
    """Search and play query on Spotify safely via spotify: URI."""
    if not query:
        return "Error: No search query provided for Spotify."
    try:
        webbrowser.open(f"spotify:search:{query}")
        return f"Searching and playing '{query}' on Spotify."
    except Exception as e:
        return f"Error opening Spotify search: {e}"


def launch_app(name: str) -> str:
    """Load config/apps.json, look up the exe path for name, and open it.

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

    exe_path = os.path.expandvars(exe_path)

    try:
        if "--" in exe_path or "/" in exe_path or " " in exe_path:
            subprocess.Popen(exe_path, shell=True)
        else:
            os.startfile(exe_path)
        return f"Successfully launched '{name}'."
    except Exception as e:
        return f"Error launching '{name}' with path '{exe_path}': {e}"


def open_url(url: str) -> str:
    """Open the URL in the default browser using webbrowser.open(url).

    Blocks any attempt to open Gmail or personal mail to protect user privacy.
    """
    if not url:
        return "Error: No URL provided."

    target_url = url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    # Privacy Protection
    for domain in BLOCKED_MAIL_DOMAINS:
        if domain in target_url.lower():
            return "Privacy Protection: Access to Gmail and Personal Mail is restricted and cannot be opened."

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
    """Search YouTube for query, or directly play the first result via pywhatkit."""
    if not query:
        return "Error: No search query provided for YouTube."

    try:
        import pywhatkit
        pywhatkit.playonyt(query)
        return f"Playing '{query}' on YouTube via pywhatkit."
    except Exception:
        pass

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
      - 'launch_app'         : calls launch_app(target)
      - 'open_url'           : calls open_url(target)
      - 'open_folder'        : calls open_explorer(target)
      - 'search_youtube'     : calls search_youtube(target)
      - 'search_google'      : calls search_google(target)
      - 'spotify_play_pause' : toggles Spotify play/pause
      - 'spotify_next'       : skips to next song
      - 'spotify_prev'       : previous song
      - 'spotify_search'     : searches and plays song on Spotify
      - 'blocked_privacy'    : refuses access to private data (Gmail / Mail)
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
    elif action == "spotify_play_pause":
        return spotify_play_pause()
    elif action == "spotify_next":
        return spotify_next()
    elif action == "spotify_prev":
        return spotify_prev()
    elif action == "spotify_search":
        return spotify_search(target)
    elif action == "blocked_privacy":
        return "Privacy Protection: Gmail aur Personal Mail access restricted hai. Main aapke mail ko touch nahi karunga."
    else:
        return (
            f"Error: Unknown action '{action}'."
        )
