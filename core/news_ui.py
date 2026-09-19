"""Tkinter news popup — dark-purple card layout with async thumbnail loading.

Opens a frameless, always-on-top overlay displaying news cards.
Auto-closes after 15 seconds; draggable via title bar.
"""

from __future__ import annotations

import io
import threading
import tkinter as tk
import webbrowser
from typing import Optional

import requests
from PIL import Image, ImageTk

from core.logger import get_logger

log = get_logger(__name__)

# Theme
_BG       = "#1a0d2e"
_CARD_BG  = "#251545"
_ACCENT   = "#9d4edd"
_TEXT     = "#e0d4f7"
_SUBTEXT  = "#a89bc2"
_BORDER   = "#3d1f6e"
_CLOSE_FG = "#ff6b8a"

_THUMB_W      = 150
_THUMB_H      = 100
_POPUP_W      = 560
_AUTO_CLOSE_S = 15


def _fetch_thumbnail(url: str) -> Optional[ImageTk.PhotoImage]:
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img = img.resize((_THUMB_W, _THUMB_H), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as exc:
        log.debug("Thumbnail fetch failed (%s): %s", url, exc)
        return None


class _NewsPopup:
    def __init__(self, parent: tk.Tk, items: list[dict], title: str):
        self._parent = parent
        self._items  = items
        self._photos: list[ImageTk.PhotoImage] = []
        self._timer_id: Optional[str] = None
        self._remaining = _AUTO_CLOSE_S

        self._win = tk.Toplevel(parent)
        self._build(title)
        self._tick()

    def _build(self, title: str) -> None:
        w = self._win
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=_BG)
        sw = w.winfo_screenwidth()
        x = sw - _POPUP_W - 20
        y = 60
        w.geometry(f"+{x}+{y}")

        # Title bar
        bar = tk.Frame(w, bg=_ACCENT, pady=4)
        bar.pack(fill="x")
        bar.bind("<ButtonPress-1>", self._drag_start)
        bar.bind("<B1-Motion>",     self._drag_motion)
        self._dx = self._dy = 0

        tk.Label(bar, text=f"  📰  {title}", bg=_ACCENT, fg="#fff",
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=6)

        self._timer_lbl = tk.Label(bar, text=f"  ⏱ {_AUTO_CLOSE_S}s  ",
                                   bg=_ACCENT, fg="#fff", font=("Segoe UI", 9))
        self._timer_lbl.pack(side="right")

        close = tk.Label(bar, text="  ✕  ", bg=_ACCENT, fg=_CLOSE_FG,
                         font=("Segoe UI", 11, "bold"), cursor="hand2")
        close.pack(side="right", padx=4)
        close.bind("<Button-1>", lambda _: self._close())

        # Cards
        body = tk.Frame(w, bg=_BG, padx=8, pady=8)
        body.pack(fill="both", expand=True)
        for item in self._items:
            self._add_card(body, item)

        tk.Frame(w, bg=_ACCENT, height=2).pack(fill="x", side="bottom")

    def _add_card(self, parent: tk.Frame, item: dict) -> None:
        card = tk.Frame(parent, bg=_CARD_BG,
                        highlightbackground=_BORDER, highlightthickness=1,
                        pady=10, padx=10)
        card.pack(fill="x", pady=(0, 8))

        # Thumbnail
        thumb_frame = tk.Frame(card, bg=_CARD_BG, width=_THUMB_W, height=_THUMB_H)
        thumb_frame.pack_propagate(False)
        thumb_frame.pack(side="left", padx=(0, 10))

        thumb = tk.Label(thumb_frame, bg="#1e0f3a", fg=_SUBTEXT,
                         text="📰", font=("Segoe UI", 24))
        thumb.pack(fill="both", expand=True)

        article_url = item.get("url") or item.get("link")
        if article_url:
            thumb.config(cursor="hand2")
            thumb.bind("<Button-1>", lambda _, u=article_url: webbrowser.open(u))

        img_url = item.get("image_url")
        if img_url:
            threading.Thread(target=self._load_thumb, args=(thumb, img_url),
                             daemon=True).start()

        # Text
        col = tk.Frame(card, bg=_CARD_BG)
        col.pack(side="left", fill="both", expand=True)

        wrap = _POPUP_W - _THUMB_W - 60

        # Source and Published Date line
        meta_parts = []
        if item.get("source"):
            meta_parts.append(item["source"])
        if item.get("published"):
            meta_parts.append(str(item["published"]))
        if meta_parts:
            tk.Label(col, text=" • ".join(meta_parts), bg=_CARD_BG, fg=_ACCENT,
                     font=("Segoe UI", 8, "bold"), anchor="w",
                     wraplength=wrap).pack(anchor="w")

        # Headline
        hl = tk.Label(col, text=item.get("headline", ""), bg=_CARD_BG, fg=_TEXT,
                      font=("Segoe UI", 10), anchor="w", justify="left",
                      wraplength=wrap, cursor="hand2" if article_url else "")
        hl.pack(anchor="w", pady=(4, 0))

        if article_url:
            def _open_link(_event=None, u=article_url):
                try:
                    webbrowser.open(u)
                except Exception as exc:
                    log.error("Failed to open article URL %s: %s", u, exc)

            hl.bind("<Button-1>", _open_link)
            link_lbl = tk.Label(col, text="🔗 Read article ↗", bg=_CARD_BG, fg=_ACCENT,
                                font=("Segoe UI", 8, "underline"), cursor="hand2")
            link_lbl.pack(anchor="w", pady=(3, 0))
            link_lbl.bind("<Button-1>", _open_link)

    def _load_thumb(self, label: tk.Label, url: str) -> None:
        photo = _fetch_thumbnail(url)
        if photo:
            self._photos.append(photo)
            try:
                label.after(0, lambda p=photo: label.config(image=p, text=""))
            except tk.TclError:
                pass

    def _tick(self) -> None:
        if self._remaining <= 0:
            self._close()
            return
        try:
            self._timer_lbl.config(text=f"  ⏱ {self._remaining}s  ")
        except tk.TclError:
            return
        self._remaining -= 1
        self._timer_id = self._win.after(1000, self._tick)

    def _close(self) -> None:
        if self._timer_id:
            try:
                self._win.after_cancel(self._timer_id)
            except tk.TclError:
                pass
        try:
            self._win.destroy()
        except tk.TclError:
            pass

    def _drag_start(self, event: tk.Event) -> None:
        self._dx = event.x_root - self._win.winfo_x()
        self._dy = event.y_root - self._win.winfo_y()

    def _drag_motion(self, event: tk.Event) -> None:
        self._win.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")


def show_news_popup(root: Optional[tk.Tk] = None, items: Optional[list[dict]] = None, title: str = "Headlines") -> None:
    """Open the news popup. Can be called with (root, items, title) or (items=items, title=title)."""
    if isinstance(root, list):
        items, title, root = root, (items if isinstance(items, str) else "Headlines"), None
    if not items:
        return
    log.info("Opening news popup: %r (%d items)", title, len(items))
    if root is None:
        def _run_popup():
            r = tk.Tk()
            r.withdraw()
            _NewsPopup(r, items, title)
            r.mainloop()
        threading.Thread(target=_run_popup, daemon=True).start()
    else:
        _NewsPopup(root, items, title)
