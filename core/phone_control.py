"""Android phone control module via ADB (Android Debug Bridge).

Enables device connection verification and outbound phone call triggering.
Requires USB Debugging enabled on the phone and ADB installed on the system.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional
import webbrowser

from core.logger import get_logger

log = get_logger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONTACTS_PATH = _BASE_DIR / "config" / "contacts.json"


def _ensure_adb_in_path() -> None:
    """Ensure adb executable directory is included in os.environ['PATH']."""
    import shutil
    if not shutil.which("adb"):
        # 1. Check project root platform-tools
        local_pt = _BASE_DIR / "platform-tools"
        if (local_pt / "adb.exe").is_file():
            os.environ["PATH"] = str(local_pt) + os.pathsep + os.environ.get("PATH", "")
            log.info("Appended local project %s to PATH for ADB support", local_pt)
            return

        # 2. Check WinGet Packages
        local_appdata = os.getenv("LOCALAPPDATA", "")
        if local_appdata:
            winget_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
            if winget_dir.exists():
                for exe in winget_dir.glob("**/platform-tools/adb.exe"):
                    if exe.is_file():
                        parent_dir = str(exe.parent)
                        os.environ["PATH"] = parent_dir + os.pathsep + os.environ.get("PATH", "")
                        log.info("Appended %s to PATH for ADB support", parent_dir)
                        break

_ensure_adb_in_path()





def is_device_connected() -> bool:
    """Run 'adb devices' via subprocess and verify if any authorized device is connected.

    Returns:
        True if at least one device ends with 'device' (authorized),
        False if no device, unauthorized, offline, or ADB is missing.
    """
    try:
        res = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode != 0:
            log.warning("adb devices returned non-zero exit code: %d", res.returncode)
            return False

        lines = res.stdout.strip().splitlines()
        # First line is usually header: "List of devices attached"
        for line in lines[1:]:
            line_str = line.strip()
            if not line_str:
                continue
            parts = line_str.split()
            # Match lines ending in 'device', rejecting 'unauthorized' or 'offline'
            if len(parts) >= 2:
                status = parts[1].lower()
                if status == "device":
                    log.info("Authorized ADB device detected: %s", parts[0])
                    return True
                elif status in ("unauthorized", "offline"):
                    log.warning("ADB device detected in %r state: %s", status, parts[0])

        log.debug("No authorized ADB device found in output: %r", res.stdout)
        return False
    except FileNotFoundError:
        log.warning("ADB executable not found in system PATH.")
        return False
    except subprocess.TimeoutExpired:
        log.warning("adb devices command timed out.")
        return False
    except Exception as exc:
        log.warning("Unexpected error checking ADB device status: %s", exc)
        return False


def load_contacts() -> dict[str, str]:
    """Load contact mappings from config/contacts.json (case-insensitive keys)."""
    if not _CONTACTS_PATH.exists():
        log.warning("Contacts file not found at %s", _CONTACTS_PATH)
        return {}
    try:
        with open(_CONTACTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k).lower().strip(): str(v).strip() for k, v in data.items()}
            return {}
    except Exception as exc:
        log.error("Failed to parse %s: %s", _CONTACTS_PATH, exc)
        return {}


def dial_via_phone_link(phone_number: str) -> bool:
    """Trigger call via Windows Phone Link or system default dialer using tel: protocol without USB debugging.

    Args:
        phone_number: Destination phone number string.

    Returns:
        True if the tel: URI was successfully dispatched to the OS handler, False otherwise.
    """
    clean_num = "".join(c for c in phone_number if c in "0123456789+*#")
    if not clean_num:
        log.warning("No valid digits found in phone number: %r", phone_number)
        return False

    tel_url = f"tel:{clean_num}"
    try:
        if sys.platform == "win32" and hasattr(os, "startfile"):
            os.startfile(tel_url)
            log.info("Dispatched %s via Windows startfile (Phone Link / default dialer)", tel_url)
            return True
        else:
            res = webbrowser.open(tel_url)
            log.info("Dispatched %s via webbrowser.open: %s", tel_url, res)
            return bool(res)
    except Exception as exc:
        log.warning("Failed to dispatch %s to OS dialer: %s", tel_url, exc)
        return False


def make_call(contact_name: str, phone_number: Optional[str] = None) -> str:
    """Initiate an outbound phone call on an Android device via ADB or Windows Phone Link.

    Args:
        contact_name: Contact name or phone number string.
        phone_number: Optional direct phone number. If omitted, resolved via contacts.json.

    Returns:
        Confirmation or error message.
    """
    target = (contact_name or "").strip()
    if not target and not phone_number:
        return "Please specify a contact name or phone number to call."

    resolved_number = (phone_number or "").strip()
    resolved_name = target

    # 1. Resolve phone number if not directly provided
    if not resolved_number:
        # Check if target itself is already a numerical phone number
        cleaned = target.replace("+", "").replace("-", "").replace(" ", "")
        if cleaned.isdigit() and len(cleaned) >= 7:
            resolved_number = target
            resolved_name = target
        else:
            contacts = load_contacts()
            lookup_key = target.lower()
            if lookup_key in contacts:
                resolved_number = contacts[lookup_key]
            else:
                return f"Contact '{target}' not found in contacts.json. Please add their number to config/contacts.json."

    # 2. Verify device connection before attempting call
    if not is_device_connected():
        # Fallback: Attempt Windows Phone Link (No USB Debugging needed)
        if dial_via_phone_link(resolved_number):
            log.info("No authorized ADB device; placed call to %s via Windows Phone Link", resolved_name)
            return f"No Android device connected via ADB. Calling {resolved_name} via Windows Phone Link."
        return "No Android device connected. Please connect your phone with USB debugging enabled or pair with Windows Phone Link."

    # 3. Trigger Android call intent via ADB
    log.info("Placing call to %s (%s) via ADB...", resolved_name, resolved_number)
    try:
        cmd = ["adb", "shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{resolved_number}"]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if res.returncode == 0:
            return f"Calling {resolved_name}."
        else:
            err_msg = (res.stderr or res.stdout or "").strip()
            log.error("ADB call intent failed (exit code %d): %s", res.returncode, err_msg)
            # If ADB intent fails, attempt Phone Link fallback
            if dial_via_phone_link(resolved_number):
                return f"ADB call failed ({err_msg or 'error'}). Calling {resolved_name} via Windows Phone Link."
            return f"Could not place call to {resolved_name}. ADB error: {err_msg or 'Command failed'}"
    except FileNotFoundError:
        if dial_via_phone_link(resolved_number):
            return f"ADB not installed. Calling {resolved_name} via Windows Phone Link."
        return "ADB is not installed or not in system PATH. Please install Android Platform Tools."
    except subprocess.TimeoutExpired:
        return f"ADB command timed out while attempting to call {resolved_name}."
    except Exception as exc:
        log.error("Unexpected error placing call to %s: %s", resolved_name, exc)
        return f"Failed to place call: {exc}"

