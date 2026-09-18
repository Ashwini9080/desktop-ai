"""Desktop AI Assistant — Main Entry Point (Phase 11: Minimal Luxury GUI + Terminal Dual-Mode).

Architecture:
  ┌────────────────────────────────────────────────────────────────────────┐
  │  Main thread        : pywebview window (ui/app.html, frameless,       │
  │                       bottom-right, champagne gold luxury design)     │
  │  Thread – terminal  : input('> ') loop if sys.stdin.isatty() is True  │
  │  Thread – hotkey    : keyboard.add_hotkey("f9", _on_hotkey)            │
  │  Thread – tray      : pystray icon (Show/Hide + Quit)                  │
  │  Thread – mobile    : Flask web server for remote control (port 5000) │
  │                                                                        │
  │  GUI Input Enter    ──┐                                                │
  │  GUI Mic Ring Click ──┼─→ handle_command(text)                         │
  │  Terminal input('> ')─┤    ├── classify()                              │
  │  F9 Voice Hotkey    ──┤    ├── resolve_with_gemini()                   │
  │  Mobile Web Request ──┘    ├── execute() / answer_question()           │
  │                            └── speak() + GUI feedback update           │
  └────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from typing import Optional

from dotenv import load_dotenv

# ── Load .env before any core imports (auto-bootstrap from .env.example if missing) ─
_CONFIG_DIR = Path(__file__).parent / "config"
_ENV_PATH = _CONFIG_DIR / ".env"
_ENV_EXAMPLE = _CONFIG_DIR / ".env.example"

_BOOTSTRAPPED_ENV = False
if not _ENV_PATH.exists() and _ENV_EXAMPLE.exists():
    try:
        shutil.copyfile(_ENV_EXAMPLE, _ENV_PATH)
        _BOOTSTRAPPED_ENV = True
    except Exception:
        pass

load_dotenv(dotenv_path=_ENV_PATH)

# ── Core imports ───────────────────────────────────────────────────────────────
from core.logger import get_logger, log_performance
from core.voice import listen_once, speak
from core.intent_classifier import classify
from core.gemini_fallback import resolve_with_gemini, answer_question
from core.executor import execute
from core.greeting import get_greeting
from core.news import get_news, get_outlet_news, items_to_spoken_summary
from core.stocks import get_stock_analysis
from core.mobile_server import start_mobile_server

import keyboard          # pip install keyboard
import pystray           # pip install pystray
from PIL import Image, ImageDraw    # pip install pillow
import webview           # pip install pywebview

log = get_logger(__name__)

# Global pywebview window & tray icon references
_window: Optional[webview.Window] = None
_tray_icon: Optional[pystray.Icon] = None
_is_gui_visible = True


# ─────────────────────────────────────────────────────────────────────────────
# UI Synchronization Helpers (Python -> JS)
# ─────────────────────────────────────────────────────────────────────────────

def _set_gui_listening(active: bool) -> None:
    """Toggle listening animation in the GUI window."""
    global _window
    if _window:
        try:
            val = "true" if active else "false"
            _window.evaluate_js(f"if (typeof setListening === 'function') setListening({val});")
        except Exception as exc:
            log.debug("evaluate_js setListening error: %s", exc)


def _update_gui_feedback(text: str, status: str = "STANDBY") -> None:
    """Update feedback text and status badge in the GUI window."""
    global _window
    if _window:
        try:
            safe_text = json.dumps(text)
            safe_status = json.dumps(status)
            _window.evaluate_js(
                f"if (typeof showFeedback === 'function') showFeedback({safe_text}); "
                f"if (typeof setStatus === 'function') setStatus({safe_status});"
            )
        except Exception as exc:
            log.debug("evaluate_js showFeedback error: %s", exc)


def _print_terminal_response(response: str) -> None:
    """Print assistant output to terminal if launched interactively."""
    if sys.stdin and sys.stdin.isatty():
        print(f"\n[Desktop AI]: {response}\n> ", end="", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Core Command Pipeline (Single Entry Point for GUI, Voice, Terminal & Mobile)
# ─────────────────────────────────────────────────────────────────────────────

def _speak_bg(text: str) -> None:
    """Speak asynchronously in background daemon thread without blocking command response."""
    threading.Thread(target=speak, args=(text,), daemon=True).start()


def handle_command(text: str) -> str:
    """Full pipeline: classify → Gemini fallback → execute → speak.

    Single entry point for both input paths (GUI, mobile and terminal).

    Args:
        text: Raw user command string (voice or typed).

    Returns:
        Spoken response or confirmation string.
    """
    text = text.strip()
    if not text:
        return ""

    log.info("Command received: %r", text)
    _update_gui_feedback(f"Processing: {text}", status="WORKING")

    # ── Step 1: Rule-based classifier (fast, zero latency) ───────────────────
    t_class_start = time.time()
    action_dict = classify(text)
    class_engine = "rule_based"

    if action_dict is not None:
        log.info("Classifier matched: %s", action_dict)
    else:
        # ── Step 2: AI fallback (Gemini → Groq) ──────────────────────────────
        log.info("No rule matched — asking AI (Gemini/Groq) …")
        action_dict = resolve_with_gemini(text)
        class_engine = "ai_fallback"

    t_class = time.time() - t_class_start
    log_performance("CLASSIFICATION", t_class, f"engine={class_engine} result={action_dict}")

    t_exec_start = time.time()

    # ── Step 3: News & Stocks shortcuts ──────────────────────────────────────
    if action_dict:
        action = action_dict.get("action")
        target = action_dict.get("target", "general")

        if action == "get_news":
            log.info("Fetching news [category=%s] …", target)
            items = get_news(str(target))
            label = str(target).replace("_", " ").title()
            spoken = items_to_spoken_summary(items, label)
            log_performance("EXECUTION", time.time() - t_exec_start, f"action=get_news target={target}")
            _update_gui_feedback(spoken)
            _speak_bg(spoken)
            _print_terminal_response(spoken)
            return spoken

        if action == "get_outlet_news":
            log.info("Fetching outlet news [outlet=%s] …", target)
            items = get_outlet_news(str(target))
            label = str(target).title()
            spoken = items_to_spoken_summary(items, label)
            log_performance("EXECUTION", time.time() - t_exec_start, f"action=get_outlet_news target={target}")
            _update_gui_feedback(spoken)
            _speak_bg(spoken)
            _print_terminal_response(spoken)
            return spoken

        if action == "get_stock_movers":
            log.info("Running stock analysis …")
            _update_gui_feedback("Analysing the market …", status="WORKING")
            _speak_bg("Analysing the market. Please wait, this may take a moment.")
            analysis = get_stock_analysis()
            log.info("Stock analysis complete (%d chars)", len(analysis))
            log_performance("EXECUTION", time.time() - t_exec_start, "action=get_stock_movers")
            _update_gui_feedback(analysis)
            _speak_bg(analysis)
            _print_terminal_response(analysis)
            return analysis

    # ── Step 4: Execute OS Actions ───────────────────────────────────────────
    if action_dict and action_dict.get("action") is not None:
        result_msg = execute(action_dict)
        log.info("Execute result: %s", result_msg)

        action = action_dict["action"]
        target = action_dict.get("target", "") or ""
        if action == "launch_app":
            confirmation = f"Opening {target}."
        elif action == "open_url":
            confirmation = "Opening website."
        elif action == "open_folder":
            confirmation = f"Opening {target} folder."
        elif action == "search_youtube":
            confirmation = f"Searching YouTube for {target}."
        elif action == "search_google":
            confirmation = f"Searching Google for {target}."
        elif action == "spotify_play_pause":
            confirmation = "Spotify playback toggled."
        elif action == "spotify_next":
            confirmation = "Playing next song on Spotify."
        elif action == "spotify_prev":
            confirmation = "Playing previous song on Spotify."
        elif action == "spotify_search":
            confirmation = f"Searching and playing {target} on Spotify."
        elif action == "blocked_privacy":
            confirmation = "Privacy Protection active. Your Gmail and Personal Mail will not be touched."
        else:
            confirmation = result_msg

        log_performance("EXECUTION", time.time() - t_exec_start, f"action={action} target={target}")
        _update_gui_feedback(confirmation)
        _speak_bg(confirmation)
        _print_terminal_response(confirmation)
        return confirmation
    else:
        # ── Step 5: Conversational Q&A fallback (Gemini Siri-style) ───────────
        log.info("No action matched — falling back to answer_question() …")
        answer = answer_question(text)
        log.info("answer_question replied: %r", answer[:80])
        log_performance("EXECUTION", time.time() - t_exec_start, f"action=conversational_qa query={text!r}")
        _update_gui_feedback(answer)
        _speak_bg(answer)
        _print_terminal_response(answer)
        return answer


# ─────────────────────────────────────────────────────────────────────────────
# Voice Trigger Function
# ─────────────────────────────────────────────────────────────────────────────

def _on_voice_trigger() -> None:
    """Record speech via listen_once() and route to handle_command()."""
    log.info("Voice recording initiated …")
    _set_gui_listening(True)
    try:
        text = listen_once()
        if text:
            log.info("Voice transcription received: %r", text)
            handle_command(text)
        else:
            log.warning("No speech captured.")
            speak("I did not catch that. Please try again.")
            _update_gui_feedback("No speech detected.")
    except Exception as exc:
        log.error("Voice trigger error: %s", exc)
        _update_gui_feedback("Voice error occurred.")
    finally:
        _set_gui_listening(False)


# ─────────────────────────────────────────────────────────────────────────────
# Python API Class Exposed to GUI (via window.pywebview.api)
# ─────────────────────────────────────────────────────────────────────────────

class DesktopAIAPI:
    """JS-accessible API exposed to the pywebview frontend."""

    def __init__(self):
        self._win: Optional[webview.Window] = None

    def set_window(self, win: webview.Window) -> None:
        self._win = win

    def send_command(self, text: str) -> str:
        """Called from UI when user submits command."""
        text = (text or "").strip()
        if text:
            threading.Thread(
                target=handle_command,
                args=(text,),
                name="GUICommandRunner",
                daemon=True,
            ).start()
        return "Dispatched"

    def toggle_mic(self) -> None:
        """Called from UI when user clicks mic ring."""
        threading.Thread(
            target=_on_voice_trigger,
            name="GUIVoiceRunner",
            daemon=True,
        ).start()

    def hide_window(self) -> None:
        """Hide window to tray from UI close button."""
        global _is_gui_visible
        if self._win:
            self._win.hide()
            _is_gui_visible = False

    def get_initial_data(self) -> dict:
        """Return personalized greeting and user info for UI startup."""
        name = os.getenv("USER_NAME", "").strip() or "Ash"
        hour = datetime.now().hour
        if 5 <= hour < 12:
            eyebrow = "Good Morning"
        elif 12 <= hour < 17:
            eyebrow = "Good Afternoon"
        elif 17 <= hour < 22:
            eyebrow = "Good Evening"
        else:
            eyebrow = "Late Night"
        return {"eyebrow": eyebrow, "name": f"{name}."}


# ─────────────────────────────────────────────────────────────────────────────
# Terminal Support Loop (Interactive Development Mode)
# ─────────────────────────────────────────────────────────────────────────────

def _start_terminal_listener() -> None:
    """Read terminal input in a loop when launched interactively."""
    time.sleep(1.2)  # Allow greeting & GUI window to initialize cleanly
    print("\n" + "─" * 58)
    print("  ✨ Desktop AI — Minimal Luxury Terminal Mode")
    print("  Type any command below (e.g., 'open chrome', 'search youtube lofi')")
    print("  Both GUI window and Terminal are active simultaneously.")
    print("─" * 58 + "\n")

    while True:
        try:
            cmd = input("> ")
            cmd = cmd.strip()
            if not cmd:
                continue
            if cmd.lower() in ("exit", "quit", "q"):
                print("Shutting down Desktop AI …")
                global _window, _tray_icon
                if _tray_icon:
                    _tray_icon.stop()
                if _window:
                    _window.destroy()
                os._exit(0)

            threading.Thread(
                target=handle_command,
                args=(cmd,),
                name="TerminalCommandRunner",
                daemon=True,
            ).start()
        except (EOFError, KeyboardInterrupt):
            log.info("Terminal session exited.")
            break
        except Exception as exc:
            log.error("Terminal input error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Global Hotkey Listener (F9)
# ─────────────────────────────────────────────────────────────────────────────

def _start_hotkey_listener() -> None:
    """Register F9 global hotkey."""
    def _on_hotkey() -> None:
        log.info("F9 pressed — dispatching voice recording …")
        threading.Thread(
            target=_on_voice_trigger,
            name="HotkeyVoiceRunner",
            daemon=True,
        ).start()

    try:
        keyboard.add_hotkey("f9", _on_hotkey)
        log.info("F9 global hotkey registered.")
        keyboard.wait()
    except Exception as exc:
        log.warning("Keyboard hotkey registration notice: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# System Tray Icon Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_icon_image(size: int = 64) -> Image.Image:
    """Return tray icon image (champagne gold accent)."""
    icon_file = Path(__file__).parent / "icon.png"
    if icon_file.exists():
        try:
            return Image.open(icon_file).resize((size, size))
        except Exception:
            pass

    # Draw rounded dark near-black square with champagne gold accent
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(2, 2), (size - 2, size - 2)], radius=14, fill=(19, 18, 17))
    draw.rounded_rectangle([(2, 2), (size - 2, size - 2)], radius=14, outline=(201, 169, 97), width=2)
    cx, cy, r = size // 2, size // 2, size // 5
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(201, 169, 97))
    return img


def _build_tray() -> pystray.Icon:
    """Build pystray tray icon with Show/Hide and Quit options."""
    global _window, _is_gui_visible

    def _toggle_window(icon, item) -> None:
        global _window, _is_gui_visible
        if _window:
            if _is_gui_visible:
                _window.hide()
                _is_gui_visible = False
            else:
                _window.show()
                _is_gui_visible = True

    def _quit_app(icon, item) -> None:
        log.info("Quit requested from system tray.")
        icon.stop()
        global _window
        if _window:
            try:
                _window.destroy()
            except Exception:
                pass
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Desktop AI Assistant", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Show / Hide window", _toggle_window),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit_app),
    )
    img = _make_icon_image()
    return pystray.Icon("DesktopAI", img, "Desktop AI Assistant", menu)


# ─────────────────────────────────────────────────────────────────────────────
# Main Application Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    global _window, _tray_icon

    log.info("Desktop AI Assistant starting up (Phase 11: Minimal Luxury).")
    if _BOOTSTRAPPED_ENV:
        log.warning("Created config/.env from template.")

    # ── 1. Startup greeting: speak(get_greeting()) once on startup ───────────
    greeting_text = get_greeting()
    log.info("Startup greeting: %s", greeting_text)
    greeting_thread = threading.Thread(
        target=speak,
        args=(greeting_text,),
        name="StartupGreeting",
        daemon=True,
    )
    greeting_thread.start()

    # ── 2. Terminal Support (Interactive vs No-Console check) ────────────────
    # Check if sys.stdin and sys.stdin.isatty():
    # If True: start background thread reading terminal input in a loop (input('> '))
    # If False (no-console .exe): skip entirely so it doesn't crash
    if sys.stdin and sys.stdin.isatty():
        log.info("Interactive terminal detected — launching terminal listener thread.")
        term_thread = threading.Thread(
            target=_start_terminal_listener,
            name="TerminalListener",
            daemon=True,
        )
        term_thread.start()
    else:
        log.info("No interactive terminal (no-console mode) — terminal listener skipped.")

    # ── 3. Global F9 hotkey listener ─────────────────────────────────────────
    hotkey_thread = threading.Thread(
        target=_start_hotkey_listener,
        name="HotkeyListener",
        daemon=True,
    )
    hotkey_thread.start()

    # ── 4. Mobile remote server (Flask on port 5000) ──────────────────────────
    mobile_thread = threading.Thread(
        target=start_mobile_server,
        args=(None, handle_command),
        name="MobileServer",
        daemon=True,
    )
    mobile_thread.start()

    # ── 5. Setup pywebview Window (Positioned bottom-right) ───────────────────
    try:
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
    except Exception:
        screen_w, screen_h = 1920, 1080

    win_w = 380
    win_h = 560
    pos_x = max(0, screen_w - win_w - 30)
    pos_y = max(0, screen_h - win_h - 60)

    ui_path = Path(__file__).resolve().parent / "ui" / "app.html"
    api = DesktopAIAPI()

    _window = webview.create_window(
        title="Desktop AI",
        url=str(ui_path.resolve()),
        width=win_w,
        height=win_h,
        x=pos_x,
        y=pos_y,
        frameless=True,
        on_top=True,
        background_color="#0b0b0a",
        js_api=api,
        easy_drag=False,
    )
    api.set_window(_window)

    # ── 6. System Tray Icon ──────────────────────────────────────────────────
    _tray_icon = _build_tray()
    tray_thread = threading.Thread(
        target=_tray_icon.run,
        name="TrayIcon",
        daemon=True,
    )
    tray_thread.start()

    # ── 7. Start pywebview (Main Thread GUI Event Loop) ──────────────────────
    try:
        log.info("Starting pywebview event loop.")
        webview.start()
    finally:
        log.info("Desktop AI Assistant exited.")
        if _tray_icon:
            _tray_icon.stop()
        os._exit(0)


if __name__ == "__main__":
    main()
