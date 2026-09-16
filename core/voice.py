"""Speech-to-text (STT) and text-to-speech (TTS) engine.

STT: Records audio while F9 is held, transcribes via Groq Whisper API
     (whisper-large-v3-turbo), falls back to local faster-whisper on failure.

TTS: Microsoft edge-tts (en-GB-ThomasNeural) — streams MP3 to a temp file,
     plays via playsound, then cleans up.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

import edge_tts
import keyboard
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from groq import Groq
from playsound import playsound

from core.logger import get_logger

log = get_logger(__name__)

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / "config" / ".env")

# Audio config — Whisper expects 16 kHz mono 16-bit PCM
HOTKEY             = "f9"
SAMPLE_RATE        = 16_000
CHANNELS           = 1
DTYPE              = "int16"
GROQ_MODEL         = "whisper-large-v3-turbo"
LOCAL_MODEL_SIZE   = "base"
LOCAL_COMPUTE_TYPE = "int8"

_TTS_VOICE = "en-GB-ThomasNeural"


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

def listen_once(duration: float = 4.5) -> str:
    """Record audio for `duration` seconds directly without hanging on keys, then transcribe.

    Returns transcribed text, or empty string if nothing was captured.
    """
    log.info("Recording audio for %.1f seconds … speak now!", duration)

    frames: list[np.ndarray] = []

    def _callback(indata, _frames, _time, status):
        if status:
            log.warning("Audio status: %s", status)
        frames.append(indata.copy())

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype=DTYPE, callback=_callback):
            sd.sleep(int(duration * 1000))
    except Exception as exc:
        log.error("Microphone recording error: %s", exc)
        return ""

    log.info("Recording stopped.")
    if not frames:
        log.warning("No audio captured.")
        return ""

    audio = np.concatenate(frames, axis=0)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _write_wav(tmp_path, audio)
        result = _transcribe(tmp_path).strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    log.info("Transcribed: %r", result)
    return result


def _write_wav(path: str, audio: np.ndarray) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


def _transcribe(wav_path: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if api_key:
        try:
            return _transcribe_groq(wav_path, api_key)
        except Exception as exc:
            log.warning("Groq failed (%s), falling back to local model.", exc)
    else:
        log.info("GROQ_API_KEY not set — using local faster-whisper.")
    return _transcribe_local(wav_path)


def _transcribe_groq(wav_path: str, api_key: str) -> str:
    client = Groq(api_key=api_key)
    with open(wav_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=GROQ_MODEL,
            file=("audio.wav", f, "audio/wav"),
            response_format="text",
        )
    return resp if isinstance(resp, str) else resp.text


def _transcribe_local(wav_path: str) -> str:
    from faster_whisper import WhisperModel
    model = WhisperModel(LOCAL_MODEL_SIZE, compute_type=LOCAL_COMPUTE_TYPE)
    segments, _ = model.transcribe(wav_path, beam_size=5)
    return " ".join(seg.text for seg in segments)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

async def _speak_async(text: str) -> None:
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        await edge_tts.Communicate(text, voice=_TTS_VOICE).save(tmp_path)
        playsound(tmp_path)
    except Exception as exc:
        log.error("TTS failed: %s", exc)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def speak(text: str) -> None:
    """Synthesise and play text using edge-tts. Thread-safe."""
    log.info("speak: %r", text)
    asyncio.run(_speak_async(text))


# ---------------------------------------------------------------------------
# Backward-compatible OO wrapper
# ---------------------------------------------------------------------------

class VoiceEngine:
    """Thin wrapper kept for callers that use the class interface."""

    def __init__(self, model_size: str = LOCAL_MODEL_SIZE):
        self.model_size = model_size

    def listen(self) -> str:
        return listen_once()

    def listen_once(self) -> str:
        return listen_once()

    def speak(self, text: str) -> None:
        speak(text)
