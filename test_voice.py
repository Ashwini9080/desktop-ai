"""Quick test for voice.py components — no hotkey / no Admin needed."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("config/.env"))

# ── 1. TTS test ──────────────────────────────────────────────────────────────
print("\n[1/3] Testing pyttsx3 TTS …")
try:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.say("Hello! Voice module is working.")
    engine.runAndWait()
    print("     ✅ TTS OK — aapne awaaz suni?")
except Exception as e:
    print(f"     ❌ TTS error: {e}")

# ── 2. Microphone / sounddevice test ─────────────────────────────────────────
print("\n[2/3] Testing sounddevice microphone (3 second recording) …")
try:
    import sounddevice as sd
    import numpy as np
    import wave, tempfile

    duration = 3  # seconds
    print("     🎙️  Abhi 3 second record ho raha hai — kuch bolo!")
    audio = sd.rec(int(duration * 16000), samplerate=16000,
                   channels=1, dtype="int16")
    sd.wait()
    print(f"     ✅ Microphone OK — {len(audio)} frames recorded")

    # Save temp WAV for Groq test below
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(audio.tobytes())

except Exception as e:
    print(f"     ❌ Microphone error: {e}")
    tmp_path = None

# ── 3. Groq Whisper API test ─────────────────────────────────────────────────
print("\n[3/3] Testing Groq Whisper API …")
api_key = os.getenv("GROQ_API_KEY", "").strip()
if not api_key:
    print("     ⚠️  GROQ_API_KEY .env mein nahi mila — skip")
elif not tmp_path:
    print("     ⚠️  Microphone recording nahi thi — skip")
else:
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        with open(tmp_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=("audio.wav", f, "audio/wav"),
                response_format="text",
            )
        text = result if isinstance(result, str) else result.text
        print(f"     ✅ Groq OK — Transcribed: {text!r}")

        # Speak back the result
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.say(f"Got it: {text}")
        engine.runAndWait()

    except Exception as e:
        print(f"     ❌ Groq error: {e}")
    finally:
        try: os.unlink(tmp_path)
        except: pass

print("\n✅ Test complete!\n")
