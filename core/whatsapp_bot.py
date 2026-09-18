"""WhatsApp Bot integration for Desktop AI Assistant.

Receives incoming WhatsApp messages via Twilio Webhook, checks sender authorization,
executes commands through the core pipeline, and responds back via WhatsApp.
"""

from __future__ import annotations

import html
import os
from typing import Callable, Optional

from core.logger import get_logger

log = get_logger(__name__)


def process_whatsapp_message(
    body: str,
    from_number: str,
    command_handler: Callable[[str], str],
) -> str:
    """Process an incoming WhatsApp message and return TwiML XML response.

    Args:
        body: Text content of the WhatsApp message.
        from_number: Sender WhatsApp ID, e.g. "whatsapp:+919876543210".
        command_handler: Function to execute the command string (handle_command).

    Returns:
        TwiML XML response string for Twilio.
    """
    body = (body or "").strip()
    raw_sender = from_number.replace("whatsapp:", "").strip()
    log.info("Incoming WhatsApp message from %s: %r", raw_sender, body)

    # ── Security Check: Allowed phone number whitelist ────────────────────────
    allowed_number = os.getenv("ALLOWED_PHONE_NUMBER", "").strip().replace("whatsapp:", "").replace(" ", "")
    if allowed_number and raw_sender != allowed_number:
        log.warning("Blocked WhatsApp command from unauthorized number: %s (Allowed: %s)", raw_sender, allowed_number)
        reply = "[Unauthorized] Your phone number is not permitted to control this PC."
        return _format_twiml(reply)

    if not body:
        return _format_twiml("[Desktop AI] is standing by. Send a command like 'open chrome', 'news', or 'lock pc'.")

    # ── Execute command through the main pipeline ─────────────────────────────
    try:
        log.info("Executing WhatsApp command: %r", body)
        result_msg = command_handler(body)
        if not result_msg:
            result_msg = f"Executed: {body}"
    except Exception as exc:
        log.error("WhatsApp command execution error: %s", exc)
        result_msg = f"Error executing command: {exc}"

    reply = f"[Desktop AI]:\n{result_msg}"
    return _format_twiml(reply)


def _format_twiml(message: str) -> str:
    """Format response as valid TwiML XML."""
    escaped_msg = html.escape(message)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"    <Message>{escaped_msg}</Message>\n"
        "</Response>"
    )
