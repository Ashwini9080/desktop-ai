"""Time-aware startup greeting for the assistant."""

from __future__ import annotations

from datetime import datetime

from core.logger import get_logger

log = get_logger(__name__)

_GREETINGS: list[tuple[range, str]] = [
    (range(5, 12),  "Good morning, Ash. Systems are up and running. What shall we accomplish today?"),
    (range(12, 17), "Good afternoon, Ash. All systems online. How may I assist you?"),
    (range(17, 21), "Good evening, Ash. Ready and standing by. What do you need?"),
]

_LATE_NIGHT = "Still up, Ash? It is quite late. I am at your service nonetheless."


def get_greeting() -> str:
    """Return a context-aware greeting based on the current hour."""
    hour = datetime.now().hour
    for hour_range, message in _GREETINGS:
        if hour in hour_range:
            log.debug("Greeting: %r (hour=%d)", message[:30], hour)
            return message
    log.debug("Late-night greeting (hour=%d)", hour)
    return _LATE_NIGHT
