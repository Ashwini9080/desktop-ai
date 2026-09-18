"""Time-aware startup greeting for the assistant."""

from __future__ import annotations

import os
from datetime import datetime

from core.logger import get_logger

log = get_logger(__name__)


def get_greeting() -> str:
    """Return a context-aware greeting based on the current hour and user name."""
    name = os.getenv("USER_NAME", "").strip() or "Sir"
    hour = datetime.now().hour

    if 5 <= hour < 12:
        msg = f"Good morning, {name}. Systems are up and running. What shall we accomplish today?"
    elif 12 <= hour < 17:
        msg = f"Good afternoon, {name}. All systems online. How may I assist you?"
    elif 17 <= hour < 22:
        msg = f"Good evening, {name}. Ready and standing by. What do you need?"
    else:
        msg = f"Still up, {name}? It is quite late. I am at your service nonetheless."

    log.debug("Greeting: %r (hour=%d)", msg[:40], hour)
    return msg
