"""Desktop AI Assistant — Main Entry Point (no-console build).

Architecture:
  ┌───────────────────────────────────────────────────────────────┐
  │  Main thread        : Tkinter slim always-on-top input bar    │
  │  Thread – hotkey    : keyboard.add_hotkey("f9", _on_hotkey)   │
  │  Thread – tray      : pystray icon (Show/Hide + Quit)         │
  │                                                               │
  │  F9 held → listen_once() → handle_command(text)              │
  │  Enter in bar       → handle_command(text)                    │
  │  handle_command     → classify → Gemini fallback → execute   │
  │                     → root.after(0, speak, msg)  ← main thd  │
  └───────────────────────────────────────────────────────────────┘

No print() or input() calls anywhere — all debug output goes to
logs/desktop_ai.log via core.logger.
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env before any core imports ─────────────────────────────────────────
_ENV_PATH = Path(__file__).parent / "config" / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# ── Core imports ───────────────────────────────────────────────────────────────
from core.logger import get_logger
from core.voice import listen_once, speak
from core.intent_classifier import classify
from core.gemini_fallback import resolve_with_gemini, answer_question
from core.executor import execute
from core.greeting import get_greeting
from core.news import get_news, get_outlet_news, items_to_spoken_summary
from core.news_ui import show_news_popup
from core.stocks import get_stock_analysis

import keyboard          # pip install keyboard
import pystray           # pip install pystray
from PIL import Image, ImageDraw    # pip install pillow

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tray icon helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_icon_image(size: int = 64) -> Image.Image:
    """Return the tray icon image.

    Uses an existing 'icon.png' in the project root if present,
    otherwise generates a purple gradient square on-the-fly.
    """
    icon_file = Path(__file__).parent / "icon.png"
    if icon_file.exists():
        return Image.open(icon_file).resize((size, size))

    # Draw a rounded purple square with a white 'AI' centre dot
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Background gradient approximated by a filled rounded rectangle
    draw.rounded_rectangle([(2, 2), (size - 2, size - 2)], radius=12,
                            fill=(90, 50, 160))
    # Small white accent circle
    cx, cy, r = size // 2, size // 2, size // 6
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(255, 255, 255))
    return img


# ─────────────────────────────────────────────────────────────────────────────
# Core command pipeline
# ─────────────────────────────────────────────────────────────────────────────

def handle_command(text: str, root: tk.Tk) -> None:
    """Full pipeline: classify → Gemini fallback → execute → speak.

    speak() is marshalled back to the Tk main thread via root.after()
    because pyttsx3 is not thread-safe.

    Args:
        text: Raw user command string (voice or typed).
        root: The Tk root window — used for root.after() marshalling.
    """
    text = text.strip()
    if not text:
        return

    log.info("Command received: %r", text)

    # ── Step 1: Rule-based classifier (fast, no API call) ─────────────────────
    action_dict = classify(text)

    if action_dict is not None:
        log.info("Classifier matched: %s", action_dict)
    else:
        # ── Step 2: AI fallback (Gemini → Groq) ──────────────────────────────
        log.info("No rule matched — asking AI (Gemini/Groq) …")
        action_dict = resolve_with_gemini(text)

    # ── Step 3: News shortcut (bypasses execute — shows popup + speaks) ────────────
    if action_dict:
        action = action_dict.get("action")
        target = action_dict.get("target", "general")

        if action == "get_news":
            log.info("Fetching news [category=%s] …", target)
            items = get_news(str(target))
            label = str(target).replace("_", " ").title()
            spoken = items_to_spoken_summary(items, label)
            # Show popup on main thread, speak on current (daemon) thread
            root.after(0, show_news_popup, root, items, f"{label} Headlines")
            root.after(0, speak, spoken)
            return

        if action == "get_outlet_news":
            log.info("Fetching outlet news [outlet=%s] …", target)
            items = get_outlet_news(str(target))
            label = str(target).title()
            spoken = items_to_spoken_summary(items, label)
            root.after(0, show_news_popup, root, items, f"{label} Headlines")
            root.after(0, speak, spoken)
            return

        if action == "get_stock_movers":
            log.info("Running stock analysis …")
            root.after(0, speak, "Analysing the market. Please wait, this may take a moment.")
            analysis = get_stock_analysis()
            log.info("Stock analysis complete (%d chars)", len(analysis))
            root.after(0, speak, analysis)
            return

    # ── Step 4: Execute (OS actions) ────────────────────────────────────────────────────
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

        root.after(0, speak, confirmation)
    else:
        # ── Step 5: Conversational Q&A fallback (Siri / Alexa style) ────────
        log.info("No action matched — falling back to answer_question() …")
        answer = answer_question(text)
        log.info("answer_question replied: %r", answer[:80])
        root.after(0, speak, answer)


# ─────────────────────────────────────────────────────────────────────────────
# F9 hotkey listener (runs in a daemon thread)
# ─────────────────────────────────────────────────────────────────────────────

def _start_hotkey_listener(root: tk.Tk) -> None:
    """Register F9 global hotkey. Blocks via keyboard.wait() in its own thread."""

    def _on_hotkey() -> None:
        log.info("F9 pressed — starting voice recording …")
        text = listen_once()
        if text:
            # Run handle_command in its own thread so F9 thread is free again
            threading.Thread(
                target=handle_command,
                args=(text, root),
                name="CommandRunner",
                daemon=True,
            ).start()
        else:
            log.warning("No speech captured after F9.")
            root.after(0, speak, "I did not catch that. Please try again.")

    keyboard.add_hotkey("ctrl+shift+a", _on_hotkey)
    log.info("Ctrl+Shift+A hotkey registered.")
    keyboard.wait()  # blocks — runs in its own thread


# ─────────────────────────────────────────────────────────────────────────────
# Tkinter slim input bar
# ─────────────────────────────────────────────────────────────────────────────

class InputBar:
    """A slim always-on-top Tkinter window for typed commands.

    Design:
      - 420 × 44 px, no title bar, always on top
      - Draggable by clicking anywhere on the window
      - Rounded appearance via padded Entry with matching background
      - Placeholder text dims when empty, clears on focus
      - Enter key submits; Escape clears the field
    """

    WIDTH  = 500
    HEIGHT = 56
    BG     = "#1e1b2e"       # dark purple-black
    ACCENT = "#a855f7"       # bright violet (more visible)
    FG     = "#e2e0ff"       # near-white text
    PLACEHOLDER = "Type a command and press Enter…"

    def __init__(self, root: tk.Tk, on_submit):
        self.root = root
        self.on_submit = on_submit
        self._drag_x = 0
        self._drag_y = 0

        self._build()

    def _build(self) -> None:
        root = self.root

        root.overrideredirect(True)           # no title bar / decorations
        root.attributes("-topmost", True)     # always on top
        root.configure(bg=self.BG)
        root.resizable(False, False)

        # ── Position: top-centre of primary monitor ─────────────────────────
        screen_w = root.winfo_screenwidth()
        x = (screen_w - self.WIDTH) // 2
        y = 20
        root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        # ── Outer frame (acts as border / accent strip) ──────────────────────
        outer = tk.Frame(root, bg=self.ACCENT, padx=3, pady=3)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg=self.BG)
        inner.pack(fill="both", expand=True)

        # ── Small coloured dot indicator ─────────────────────────────────────
        dot = tk.Label(inner, text="●", fg=self.ACCENT, bg=self.BG,
                       font=("Segoe UI", 10))
        dot.pack(side="left", padx=(8, 0))

        # ── Text entry ────────────────────────────────────────────────────────
        self._var = tk.StringVar()
        self._entry = tk.Entry(
            inner,
            textvariable=self._var,
            font=("Segoe UI", 12),
            bg=self.BG,
            fg="#888888",            # placeholder colour initially
            insertbackground=self.FG,
            relief="flat",
            bd=0,
        )
        self._entry.pack(side="left", fill="both", expand=True, padx=(6, 10), pady=6)

        # Placeholder logic
        self._entry.insert(0, self.PLACEHOLDER)
        self._entry.bind("<FocusIn>",  self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)

        # Submit / clear bindings
        self._entry.bind("<Return>",  self._on_submit)
        self._entry.bind("<Escape>",  self._on_escape)

        # Drag bindings (on all widgets)
        for widget in (root, outer, inner, dot, self._entry):
            widget.bind("<ButtonPress-1>",   self._drag_start)
            widget.bind("<B1-Motion>",        self._drag_motion)

    # ── Placeholder helpers ──────────────────────────────────────────────────

    def _on_focus_in(self, _event) -> None:
        if self._entry.get() == self.PLACEHOLDER:
            self._entry.delete(0, "end")
            self._entry.config(fg=self.FG)

    def _on_focus_out(self, _event) -> None:
        if not self._entry.get().strip():
            self._entry.insert(0, self.PLACEHOLDER)
            self._entry.config(fg="#888888")

    # ── Submit / escape ──────────────────────────────────────────────────────

    def _on_submit(self, _event) -> None:
        text = self._var.get().strip()
        if text and text != self.PLACEHOLDER:
            self._entry.delete(0, "end")
            self._entry.config(fg="#888888")
            self._entry.insert(0, self.PLACEHOLDER)
            self._entry.selection_clear()
            # Run in background thread so Tk stays responsive
            threading.Thread(
                target=self.on_submit,
                args=(text,),
                name="CommandRunner",
                daemon=True,
            ).start()

    def _on_escape(self, _event) -> None:
        self._entry.delete(0, "end")
        self._on_focus_out(None)

    # ── Dragging ─────────────────────────────────────────────────────────────

    def _drag_start(self, event) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _drag_motion(self, event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ── Show / hide ──────────────────────────────────────────────────────────

    def show(self) -> None:
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    def hide(self) -> None:
        self.root.withdraw()

    def toggle(self) -> None:
        if self.root.state() == "withdrawn":
            self.show()
        else:
            self.hide()


# ─────────────────────────────────────────────────────────────────────────────
# System tray
# ─────────────────────────────────────────────────────────────────────────────

_tray_icon: pystray.Icon | None = None


def _build_tray(root: tk.Tk, bar: InputBar) -> pystray.Icon:
    """Build the pystray tray icon with Show/Hide and Quit menu items."""

    def _toggle_bar(icon, item) -> None:
        # pystray callbacks run on the tray thread — marshal to Tk main thread
        root.after(0, bar.toggle)

    def _quit_app(icon, item) -> None:
        log.info("Quit requested from tray.")
        icon.stop()
        root.after(0, root.destroy)

    menu = pystray.Menu(
        pystray.MenuItem("Desktop AI Assistant", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Show / Hide text box", _toggle_bar),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit_app),
    )
    img = _make_icon_image()
    return pystray.Icon("DesktopAI", img, "Desktop AI Assistant", menu)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    global _tray_icon

    log.info("Desktop AI Assistant starting up.")

    # ── Tk root (main thread) ─────────────────────────────────────────────────
    root = tk.Tk()
    root.withdraw()   # hide briefly while we build the bar

    # ── Input bar ─────────────────────────────────────────────────────────────
    bar = InputBar(root, on_submit=lambda text: handle_command(text, root))

    # Show the bar on startup
    bar.show()

    # ── Startup greeting (edge-tts runs async; do it in a daemon thread) ────────
    greeting_thread = threading.Thread(
        target=speak,
        args=(get_greeting(),),
        name="StartupGreeting",
        daemon=True,
    )
    greeting_thread.start()
    log.info("Startup greeting dispatched.")

    # ── Thread 1: Global F9 hotkey listener ───────────────────────────────────
    hotkey_thread = threading.Thread(
        target=_start_hotkey_listener,
        args=(root,),
        name="HotkeyListener",
        daemon=True,
    )
    hotkey_thread.start()

    # ── Thread 2: System tray ─────────────────────────────────────────────────
    _tray_icon = _build_tray(root, bar)
    tray_thread = threading.Thread(
        target=_tray_icon.run,
        name="TrayIcon",
        daemon=True,
    )
    tray_thread.start()

    log.info("Tkinter main loop starting.")

    # ── Main thread: Tk event loop (blocking) ─────────────────────────────────
    try:
        root.mainloop()
    finally:
        log.info("Desktop AI Assistant shut down.")
        if _tray_icon is not None:
            _tray_icon.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
