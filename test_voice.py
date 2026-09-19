import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.voice import speak, listen_once, HINGLISH_PROMPT

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_BASE_DIR, "config", ".env"))

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  [*] Voice & Speed Optimization Component Test")
    print("=" * 55)

    # ── 1. TTS Streaming Test ──────────────────────────────────────────────────
    print("\n[1/2] Testing Edge-TTS real-time streaming playback …")
    try:
        speak("Testing real-time streaming voice playback. Speed optimization is active.")
        print("     [OK] Edge-TTS Streaming Playback OK!")
    except Exception as e:
        print(f"     [FAIL] TTS error: {e}")

    # ── 2. VAD & Whisper Test ──────────────────────────────────────────────────
    print("\n[2/2] Testing listen_once() with VAD (speaks & stops on silence) …")
    print("     Kuch bolo (jaise: 'chrome kholo' ya 'news batao') — silence par apne aap rukega!")
    try:
        transcribed = listen_once(max_duration=6.0)
        print(f"     [OK] VAD & Transcription complete: {transcribed!r}")
        if transcribed:
            speak(f"Aapne bola: {transcribed}")
    except Exception as e:
        print(f"     [FAIL] VAD/Whisper error: {e}")

    print("\n" + "=" * 55)
    print("  [OK] Check performance.log to inspect exact step timings!")
    print("=" * 55 + "\n")
