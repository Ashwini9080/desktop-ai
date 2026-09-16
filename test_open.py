"""Voice-based OPEN command tester — No Admin / No Hotkey needed.

Enter daba ke record shuru hoga (3 seconds), phir auto-transcribe aur execute karega.

Supported commands:
  - "open chrome" / "chrome kholo"
  - "open youtube" / "youtube kholo"
  - "open google" / "google kholo"
  - "open github" / "github kholo"
  - "open youtube.com"
  - "downloads folder kholo" / "open downloads folder"
  - "open file explorer" / "file manager khol"
  - "open notepad" / "open calculator"
  - "exit" / "band karo" — program band karo
"""

import os
import tempfile
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

load_dotenv(Path("config/.env"))

from core.intent_classifier import classify
from core.executor import execute
import pyttsx3
from groq import Groq

# ── Config ──────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16_000
CHANNELS    = 1
DTYPE       = "int16"
DURATION    = 4          # seconds to record per press
GROQ_MODEL  = "whisper-large-v3-turbo"

EXIT_WORDS = {"exit", "band karo", "band kar", "quit", "bye", "stop",
              "exit.", "bye.", "stop."}

BANNER = """
╔══════════════════════════════════════════════════════╗
║        🎙️  Voice OPEN Command Tester                 ║
║  Enter dabao → bolo command → auto-execute hoga      ║
║  "exit" ya "band karo" bolne se band hoga            ║
╚══════════════════════════════════════════════════════╝
"""

# ── TTS ──────────────────────────────────────────────────────────────────────
_tts = None

def speak(text: str):
    global _tts
    if _tts is None:
        _tts = pyttsx3.init()
        _tts.setProperty("rate", 175)
        _tts.setProperty("volume", 1.0)
    print(f"🔊 {text}")
    _tts.say(text)
    _tts.runAndWait()


# ── Record + Transcribe ───────────────────────────────────────────────────────
def record_and_transcribe() -> str:
    """Record DURATION seconds of audio and transcribe via Groq Whisper."""
    print(f"   🔴 Recording {DURATION} seconds … bolo!")
    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    sd.wait()
    print("   ⏹  Done recording.")

    # Save to temp WAV
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()

    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    # Transcribe via Groq
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    text = ""
    try:
        if api_key:
            client = Groq(api_key=api_key)
            with open(tmp_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model=GROQ_MODEL,
                    file=("audio.wav", f, "audio/wav"),
                    response_format="text",
                )
            text = result if isinstance(result, str) else result.text
        else:
            print("   ⚠️  GROQ_API_KEY nahi mila!")
    except Exception as e:
        print(f"   ❌ Transcription error: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return text.strip()


# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    print(BANNER)
    speak("Voice command tester ready. Enter dabao aur koi open command bolo.")

    while True:
        try:
            input("\n▶  Enter dabao jab bolne ke liye ready ho … ")
        except (EOFError, KeyboardInterrupt):
            speak("Band kar raha hoon. Bye!")
            break

        # Step 1: Record + Transcribe
        text = record_and_transcribe()

        if not text:
            print("   [!] Kuch suna nahi — phir try karo.")
            speak("Kuch suna nahi, dobara koshish karo.")
            continue

        print(f"\n🎤 Suna  : {text!r}")

        # Step 2: Exit check
        if text.strip().lower() in EXIT_WORDS:
            speak("Theek hai, band kar raha hoon. Bye!")
            print("✅ Exiting.")
            break

        # Step 3: Classify
        action = classify(text)
        print(f"🧠 Intent: {action}")

        if action is None:
            msg = f"Yeh command samajh nahi aaya: {text}"
            print(f"   [?] {msg}")
            speak(msg)
            continue

        # Step 4: Execute
        result = execute(action)
        print(f"⚙️  Result: {result}")

        act = action.get("action", "")
        tgt = action.get("target") or ""

        if "Error" in result:
            speak(f"Error aa gaya. {result}")
        elif act == "open_url":
            speak(f"Khol diya: {tgt}")
        elif act == "launch_app":
            speak(f"{tgt} launch kar diya.")
        elif act == "open_folder":
            speak("File explorer khol diya.")
        else:
            speak("Ho gaya!")


if __name__ == "__main__":
    main()
