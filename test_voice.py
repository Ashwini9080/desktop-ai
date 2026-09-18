"""Quick test for optimized voice.py components — no hotkey / no Admin needed."""

import os
from pathlib import Path
from dotenv import load_dotenv

from core.voice import speak, listen_once, HINGLISH_PROMPT

load_dotenv(Path("config/.env"))

print("\n" + "=" * 55)
print("  🎙️  Voice & Speed Optimization Component Test")
print("=" * 55)

# ── 1. TTS Streaming Test ──────────────────────────────────────────────────
print("\n[1/2] Testing Edge-TTS real-time streaming playback …")
try:
    speak("Testing real-time streaming voice playback. Speed optimization is active.")
    print("     ✅ Edge-TTS Streaming Playback OK!")
except Exception as e:
    print(f"     ❌ TTS error: {e}")

# ── 2. VAD & Whisper Test ──────────────────────────────────────────────────
print("\n[2/2] Testing listen_once() with VAD (speaks & stops on silence) …")
print("     🎙️  Kuch bolo (jaise: 'chrome kholo' ya 'news batao') — silence par apne aap rukega!")
try:
    transcribed = listen_once(max_duration=6.0)
    print(f"     ✅ VAD & Transcription complete: {transcribed!r}")
    if transcribed:
        speak(f"Aapne bola: {transcribed}")
except Exception as e:
    print(f"     ❌ Voice test error: {e}")

print("\n" + "=" * 55)
print("  ✅ Check performance.log to inspect exact step timings!")
print("=" * 55 + "\n")
