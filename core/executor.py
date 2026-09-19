"""Executor module for Desktop AI Assistant.

Handles launching local applications, opening URLs in the browser,
opening File Explorer, and searching YouTube / Google.
"""

import json
import os
import shlex
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_CORE_DIR)
CONFIG_FILE = Path(os.path.join(_BASE_DIR, "config", "apps.json"))

import ctypes

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

BLOCKED_MAIL_DOMAINS = ["mail.google.com", "gmail.com", "outlook.live.com", "mail.yahoo.com"]


def is_domain_match(hostname: Optional[str], domain: str) -> bool:
    """Check if hostname matches domain exactly or is a valid subdomain."""
    if not hostname or not domain:
        return False
    h = hostname.lower().strip()
    d = domain.lower().strip()
    return h == d or h.endswith("." + d)


def _send_media_key(vk_code: int) -> None:
    """Simulate a Windows multimedia keypress."""
    try:
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
    except Exception:
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


def _parse_app_command(cmd_str: str) -> list[str]:
    """Safely parse an application path and arguments for Windows without invoking a shell."""
    cmd_str = os.path.expandvars(cmd_str).strip()
    if not cmd_str:
        return []

    # Handle quoted executable path, e.g. "%ProgramFiles%\..." --arg
    if cmd_str.startswith(('"', "'")):
        quote = cmd_str[0]
        end_quote = cmd_str.find(quote, 1)
        if end_quote != -1:
            exe = cmd_str[1:end_quote]
            rest = cmd_str[end_quote + 1:].strip()
            args = shlex.split(rest, posix=False) if rest else []
            # Normalize flag arguments like --key="val" to --key=val so list2cmdline doesn't escape quotes
            normalized_args = []
            for arg in args:
                if arg.startswith(("-", "/")) and "=" in arg:
                    k, v = arg.split("=", 1)
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    normalized_args.append(f"{k}={v}")
                else:
                    normalized_args.append(arg)
            return [exe] + normalized_args

    # If unquoted string exists directly as a file on disk
    if os.path.exists(cmd_str):
        return [cmd_str]

    return shlex.split(cmd_str, posix=False)


def _save_discovered_app(target_key: str, exe_path: str) -> None:
    """Save a newly discovered app path into config/apps.json so next time it is instant."""
    config_path = CONFIG_FILE if CONFIG_FILE.exists() else Path(os.path.join(_BASE_DIR, "config", "apps.json"))
    try:
        apps: Dict[str, str] = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                apps = json.load(f)
        apps[target_key] = exe_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(apps, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _get_candidate_names(name: str) -> List[str]:
    """Generate candidate binary/alias names for PATH lookup via shutil.which."""
    cleaned = name.strip()
    target_key = cleaned.lower()
    candidates = [cleaned, target_key]

    alias_map = {
        "vs code": ["code", "vscode", "Code"],
        "vscode": ["code", "Code", "vscode"],
        "visual studio code": ["code", "vscode", "Code"],
        "code": ["code", "Code", "vscode"],
        "chrome": ["chrome", "google-chrome"],
        "google chrome": ["chrome", "google-chrome"],
        "antigravity": ["antigravity", "agy", "Antigravity IDE"],
        "antigravity ide": ["antigravity", "agy", "Antigravity IDE"],
        "calculator": ["calc", "calculator"],
        "calc": ["calc", "calculator"],
        "notepad": ["notepad"],
        "spotify": ["spotify"],
        "cmd": ["cmd"],
        "command prompt": ["cmd"],
        "terminal": ["wt", "powershell", "pwsh"],
        "powershell": ["powershell", "pwsh"],
        "edge": ["msedge"],
        "microsoft edge": ["msedge"],
    }

    if target_key in alias_map:
        for alias in alias_map[target_key]:
            if alias not in candidates:
                candidates.append(alias)

    no_space = target_key.replace(" ", "")
    if no_space not in candidates:
        candidates.append(no_space)

    return candidates


def _find_in_common_locations(name: str) -> Optional[str]:
    """Check common install locations for known apps under %LOCALAPPDATA%\\Programs\\, %PROGRAMFILES%, and %PROGRAMFILES(X86)%."""
    target_key = name.strip().lower()
    norm = target_key.replace(" ", "").replace("-", "").replace("_", "")

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    system_root = os.environ.get("SystemRoot", "C:\\Windows")

    # 1. Direct candidate paths for known popular apps
    known_app_paths: Dict[str, List[str]] = {
        "antigravity": [
            os.path.join(local_appdata, "Programs", "Antigravity IDE", "Antigravity IDE.exe"),
            os.path.join(local_appdata, "Programs", "Antigravity", "Antigravity.exe"),
            os.path.join(local_appdata, "Programs", "antigravity", "antigravity.exe"),
            os.path.join(program_files, "Antigravity IDE", "Antigravity IDE.exe"),
            os.path.join(program_files, "Antigravity", "Antigravity.exe"),
            os.path.join(program_files_x86, "Antigravity IDE", "Antigravity IDE.exe"),
        ],
        "vscode": [
            os.path.join(local_appdata, "Programs", "Microsoft VS Code", "Code.exe"),
            os.path.join(program_files, "Microsoft VS Code", "Code.exe"),
            os.path.join(program_files_x86, "Microsoft VS Code", "Code.exe"),
        ],
        "chrome": [
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe"),
        ],
        "spotify": [
            os.path.join(local_appdata, "Microsoft", "WindowsApps", "Spotify.exe"),
            os.path.join(local_appdata, "Spotify", "Spotify.exe"),
            os.path.join(local_appdata, "Programs", "Spotify", "Spotify.exe"),
            os.path.join(program_files, "WindowsApps", "Spotify.exe"),
        ],
        "edge": [
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        ],
        "brave": [
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ],
        "notepad": [
            os.path.join(system_root, "System32", "notepad.exe"),
        ],
        "calculator": [
            os.path.join(system_root, "System32", "calc.exe"),
        ],
        "notion": [
            os.path.join(local_appdata, "Programs", "Notion", "Notion.exe"),
            os.path.join(program_files, "Notion", "Notion.exe"),
        ],
        "canva": [
            os.path.join(local_appdata, "Programs", "Canva", "Canva.exe"),
            os.path.join(program_files, "Canva", "Canva.exe"),
        ],
        "discord": [
            os.path.join(local_appdata, "Programs", "Discord", "Discord.exe"),
            os.path.join(local_appdata, "Discord", "Update.exe"),
        ],
    }

    # Match against known app definitions
    for app_id, paths in known_app_paths.items():
        if norm == app_id or norm in app_id or app_id in norm:
            for path in paths:
                if path and os.path.isfile(path):
                    return path

    # 2. Dynamic directory search under common install roots
    search_roots = [
        os.path.join(local_appdata, "Programs") if local_appdata else "",
        program_files,
        program_files_x86,
    ]

    for root_dir in search_roots:
        if not root_dir or not os.path.isdir(root_dir):
            continue
        try:
            for entry in os.scandir(root_dir):
                if entry.is_dir():
                    clean_dir = entry.name.lower().replace(" ", "").replace("-", "").replace("_", "")
                    dir_match = norm in clean_dir or clean_dir in norm
                    try:
                        for sub in os.scandir(entry.path):
                            if sub.is_file() and sub.name.lower().endswith(".exe"):
                                sub_lower = sub.name.lower()
                                if any(bad in sub_lower for bad in ["unins", "uninstall", "crash_reporter", "notification_helper"]):
                                    continue
                                sub_norm = sub_lower[:-4].replace(" ", "").replace("-", "").replace("_", "")
                                if norm in sub_norm or sub_norm in norm or dir_match:
                                    return sub.path
                    except (PermissionError, FileNotFoundError):
                        pass
                elif entry.is_file() and entry.name.lower().endswith(".exe"):
                    file_lower = entry.name.lower()
                    if any(bad in file_lower for bad in ["unins", "uninstall"]):
                        continue
                    file_norm = file_lower[:-4].replace(" ", "").replace("-", "").replace("_", "")
                    if norm in file_norm or file_norm in norm:
                        return entry.path
        except (PermissionError, FileNotFoundError):
            pass

    return None


def launch_app(name: str) -> str:
    """Launch an application using a fallback discovery chain:

    1. First check config/apps.json for a configured path — if it exists and the file is valid, use it.
    2. If not configured or the file doesn't exist at that path, try to find the executable using shutil.which(name) (searches system PATH).
    3. If still not found, check a list of common install locations for known apps (e.g. AntiGravity, VS Code, Chrome) under %LOCALAPPDATA%\\Programs\\, %PROGRAMFILES%, and %PROGRAMFILES(X86)%.
    4. When an app IS found via PATH/discovery (not from apps.json), automatically save that discovered path back into apps.json so next time it's instant.
    5. If none of these find it, return friendly error: 'Mujhe {name} nahi mila, apps.json mein path add kar do.'
    """
    if not name or not name.strip():
        return "Error: App name was not provided."

    target_key = name.strip().lower()
    config_path = CONFIG_FILE if CONFIG_FILE.exists() else Path(os.path.join(_BASE_DIR, "config", "apps.json"))

    # Step 1: Check apps.json for a configured path
    apps: Dict[str, str] = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                apps = json.load(f)
        except Exception:
            apps = {}

    configured_val = apps.get(target_key, "")
    if isinstance(configured_val, str) and configured_val.strip():
        cmd_args = _parse_app_command(configured_val.strip())
        if cmd_args:
            exe_target = cmd_args[0]
            # Verify file exists on disk or resolves via PATH
            if os.path.exists(exe_target) or shutil.which(exe_target):
                try:
                    subprocess.Popen(cmd_args, shell=False)
                    return f"Successfully launched '{name}'."
                except Exception as e:
                    return f"Error launching '{name}' with path '{configured_val}': {e}"

    # Step 2: Try to find executable using shutil.which (searches system PATH)
    discovered_path: Optional[str] = None
    for candidate in _get_candidate_names(name):
        which_result = shutil.which(candidate)
        if which_result and os.path.exists(which_result):
            discovered_path = which_result
            break

    # Step 3: Check common install locations under %LOCALAPPDATA%\Programs\, %PROGRAMFILES%, and %PROGRAMFILES(X86)%
    if not discovered_path:
        discovered_path = _find_in_common_locations(name)

    # Step 4: If found via PATH/discovery (not from apps.json), automatically save into apps.json and launch
    if discovered_path:
        _save_discovered_app(target_key, discovered_path)
        launch_args = _parse_app_command(discovered_path)
        try:
            subprocess.Popen(launch_args, shell=False)
            return f"Successfully launched '{name}'."
        except Exception as e:
            return f"Error launching '{name}' with path '{discovered_path}': {e}"

    # Step 5: None found - return friendly error
    return f"Mujhe {name} nahi mila, apps.json mein path add kar do."


def open_url(url: str) -> str:
    """Open the URL in the default browser using webbrowser.open(url).

    Blocks any attempt to open Gmail or personal mail to protect user privacy.
    """
    if not url:
        return "Error: No URL provided."

    target_url = url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    # Privacy Protection: Check hostname against blocked mail domains
    try:
        parsed = urlparse(target_url)
        hostname = (parsed.hostname or "").lower()
        for domain in BLOCKED_MAIL_DOMAINS:
            if is_domain_match(hostname, domain):
                return "Privacy Protection: Access to Gmail and Personal Mail is restricted and cannot be opened."
    except Exception:
        pass

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
    elif action == "media_control":
        t = (str(target) if target else "").lower().strip()
        if "next" in t or "skip" in t:
            return spotify_next()
        elif "prev" in t or "back" in t:
            return spotify_prev()
        elif "search" in t or "play:" in t or t.startswith("play "):
            q = t.replace("play:", "").replace("search:", "").replace("play ", "").strip()
            return spotify_search(q)
        else:
            return spotify_play_pause()
    elif action == "blocked_privacy":
        return "Privacy Protection: Gmail aur Personal Mail access restricted hai. Main aapke mail ko touch nahi karunga."
    elif action in ("timeout", "speak", "message"):
        return str(target)
    else:
        return (
            f"Error: Unknown action '{action}'."
        )
