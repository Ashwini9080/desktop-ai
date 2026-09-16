"""Gemini Fallback module.

Queries Google Generative AI for reasoning, complex queries, or general desktop
assistant answers when local rules don't match.

Uses the new ``google-genai`` SDK (google.genai), which replaced the deprecated
``google-generativeai`` (google.generativeai) package.

Fallback chain:
    1. Gemini (gemini-3.6-flash)  — primary
    2. Groq   (llama-4-scout)      — if Gemini hits 429 rate-limit or any error

All print() calls replaced with file logging (core.logger).
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from core.logger import get_logger

log = get_logger(__name__)

# Load .env from config/ directory — works regardless of cwd
_ENV_PATH = Path(__file__).resolve().parent.parent / "config" / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Original conversational assistant class (updated to new SDK, API preserved)
# ─────────────────────────────────────────────────────────────────────────────

class GeminiAssistant:
    """Handles general conversational queries and complex agent tasks via Gemini."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-3.6-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> Optional[genai.Client]:
        if self._client is None and self.api_key:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def ask(self, prompt: str) -> str:
        """Send prompt to Gemini model and return text response."""
        if not self.api_key:
            return "Gemini API key not configured. Please set GEMINI_API_KEY in config/.env."
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            log.error("Gemini ask() error: %s", e)
            return f"Error communicating with Gemini: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Shared config
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a desktop assistant intent parser. Your ONLY job is to convert a user's \
natural-language command (which may be Hinglish, Hindi, or English) into a \
single-line JSON object — nothing else.

Respond with EXACTLY this JSON format, no extra text, no markdown, no explanation:
{"action": "<action>", "target": "<target>"}

Allowed values for "action":
  - "launch_app"    -> open a desktop application (e.g. Chrome, Notepad, VS Code)
  - "open_url"      -> open a website in the browser (use a full https:// URL as target)
  - "open_folder"   -> open a folder in the file explorer
  - "search_google"  -> search Google for target query
  - "search_youtube" -> search YouTube for target query
  - null            -> for general questions, facts, news, chat, or information queries

Rules:
  - If the user is asking a question or seeking information (e.g. "who is richest person", "what is AI", "tell me news"), return {"action": null, "target": null}.
  - "target" must be a non-empty string when action is not null.
  - NEVER include any text outside the JSON object.
"""

_ALLOWED_ACTIONS = {"launch_app", "open_url", "open_folder", "search_google", "search_youtube"}

_NULL_RESULT: dict = {"action": None, "target": None}


def _strip_code_fence(text: str) -> str:
    """Remove optional ```json ... ``` or ``` ... ``` wrapping from a string."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_and_validate(raw: str) -> dict:
    """Strip fences, parse JSON, validate action+target. Returns _NULL_RESULT on failure or null action."""
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("JSON parse error: %s | raw: %r", exc, raw)
        return _NULL_RESULT

    action = parsed.get("action")
    target = parsed.get("target")

    if action is None or action == "null":
        return _NULL_RESULT

    if action not in _ALLOWED_ACTIONS:
        log.warning("Invalid action: %r", action)
        return _NULL_RESULT

    if not isinstance(target, str) or not target.strip():
        log.warning("Empty/invalid target: %r", target)
        return _NULL_RESULT

    return {"action": action, "target": target.strip()}


# ─────────────────────────────────────────────────────────────────────────────
# Groq fallback (secondary)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_with_groq(text: str) -> dict:
    """Fallback: use Groq API (qwen/qwen3.8-27b) to resolve the command.

    Called automatically when Gemini fails (rate-limit or any error).
    Returns parsed action dict or _NULL_RESULT.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        log.warning("Groq fallback skipped — GROQ_API_KEY not set in config/.env")
        return _NULL_RESULT

    try:
        from groq import Groq  # lazy import — groq package optional
    except ImportError:
        log.error("Groq fallback skipped — 'groq' package not installed.")
        return _NULL_RESULT

    log.info("Resolving intent with Groq …")
    try:
        client = Groq(api_key=groq_key)
        chat = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            temperature=0.0,
            max_tokens=128,
        )
        raw = chat.choices[0].message.content or ""
        return _parse_and_validate(raw)
    except Exception as exc:
        log.error("Groq error: %s", exc)
        return _NULL_RESULT


# ─────────────────────────────────────────────────────────────────────────────
# Primary resolver — Gemini first, Groq fallback
# ─────────────────────────────────────────────────────────────────────────────

def resolve_with_gemini(text: str) -> dict:
    """Resolve a natural-language command into a structured action dict.

    Tries Gemini (gemini-3.6-flash) first.
    If Gemini hits a rate-limit (429) or any other error, automatically
    falls back to Groq (llama-4-scout-17b-16e-instruct).

    Returns::

        {"action": "launch_app" | "open_url" | "open_folder", "target": "<str>"}

    On total failure returns ``{"action": None, "target": None}``.

    Args:
        text: Raw user command in any language (English / Hinglish / Hindi).
    """
    # ── Step 1: Try Gemini ──────────────────────────────────────────────────
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        log.warning("GEMINI_API_KEY not set — skipping Gemini, trying Groq …")
        return _resolve_with_groq(text)

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=256,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        raw = response.text
        result = _parse_and_validate(raw)

        # If parse/validation passed, return immediately
        if result["action"] is not None:
            log.info("Gemini answered: %s", result)
            return result

        # Parse failed or was null — still try Groq
        return _resolve_with_groq(text)

    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            log.warning("Gemini rate-limited (429) → switching to Groq …")
        else:
            log.error("Gemini error: %s → trying Groq fallback …", exc)
        return _resolve_with_groq(text)


# ─────────────────────────────────────────────────────────────────────────────
# Conversational Q&A — Siri / Alexa style
# ─────────────────────────────────────────────────────────────────────────────

_QA_SYSTEM_PROMPT = """\
You are a helpful voice assistant like Siri or Alexa. \
Answer the user's question directly and conversationally in Hinglish \
(mix of Hindi and English), in 2-3 short sentences max. \
Do NOT return JSON. Give a natural, spoken answer — friendly and concise.\
"""


def answer_question(question: str) -> str:
    """Answer a general question conversationally (Siri/Alexa style).

    Tries Groq (qwen/qwen3.8-27b) first for instant 0.5s response;
    falls back to Gemini (gemini-3.6-flash) if Groq is unavailable.

    Args:
        question: The user's natural-language question (any language).

    Returns:
        A short, spoken plain-text answer in Hinglish.
    """
    # ── Try Groq first (ultra-fast: ~0.5s) ───────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq  # lazy import

            client_g = Groq(api_key=groq_key)
            chat = client_g.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[
                    {"role": "system", "content": _QA_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.7,
                max_tokens=256,
            )
            answer = (chat.choices[0].message.content or "").strip()
            if answer:
                log.info("answer_question → Groq replied (%d chars)", len(answer))
                return answer
        except Exception as exc:
            log.warning("answer_question Groq error: %s → falling back to Gemini …", exc)

    # ── Fallback to Gemini ────────────────────────────────────────────────────
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=_QA_SYSTEM_PROMPT,
                    temperature=0.7,
                    max_output_tokens=256,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )
            answer = (response.text or "").strip()
            if answer:
                log.info("answer_question → Gemini replied (%d chars)", len(answer))
                return answer
        except Exception as exc:
            log.error("answer_question Gemini error: %s", exc)

    return "Maafi chahta hoon, abhi yeh jawab nahi de sakta. Thodi der mein dobara try karein."

