"""Speech-to-text (STT) and text-to-speech (TTS) engine.

STT: Records audio at 16 kHz mono int16 with Voice Activity Detection (VAD)
     and hotkey release detection. Transcribes via Groq Whisper API
     (whisper-large-v3-turbo) primed with Hinglish sample prompt and auto-language
     detection, falling back to local faster-whisper on failure or timeout.

TTS: Microsoft edge-tts (en-GB-ThomasNeural) — real-time MP3 streaming playback
     via PyAV and sounddevice.OutputStream for minimum latency.
"""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

import av
import edge_tts
import keyboard
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from groq import Groq
from playsound import playsound
from faster_whisper import WhisperModel

from core.logger import get_logger, log_performance

log = get_logger(__name__)

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_CORE_DIR)
load_dotenv(dotenv_path=Path(os.path.join(_BASE_DIR, "config", ".env")))

# Audio config — Whisper expects 16 kHz mono 16-bit PCM
HOTKEY             = "f9"
SAMPLE_RATE        = 16_000
CHANNELS           = 1
DTYPE              = "int16"
CHUNK_DURATION_SEC = 0.1   # 100ms per audio chunk
CHUNK_SAMPLES      = int(SAMPLE_RATE * CHUNK_DURATION_SEC)  # 1600 samples
SILENCE_LIMIT_SEC  = 1.2   # ~1.2s silence marks end of speech
MAX_RECORD_SEC     = 10.0  # Max duration guard
INITIAL_WAIT_SEC   = 3.5   # Abort if no speech begins within 3.5s

GROQ_MODEL         = "whisper-large-v3-turbo"
LOCAL_MODEL_SIZE   = "base"
LOCAL_COMPUTE_TYPE = "int8"

# Hinglish prompt to prime Whisper to expect mixed Hindi-English commands
HINGLISH_PROMPT    = (
    "antigravity kholo, chrome kholo, news batao, stock market kaisa hai, youtube pe gaana bajao"
)

_TTS_VOICE = "en-GB-ThomasNeural"

# Load faster-whisper WhisperModel ONCE at module level (outside any function) for reuse
_whisper_model: Optional[WhisperModel] = None
try:
    log.info("Loading faster-whisper WhisperModel (%s, %s) at module level...", LOCAL_MODEL_SIZE, LOCAL_COMPUTE_TYPE)
    _whisper_model = WhisperModel(LOCAL_MODEL_SIZE, compute_type=LOCAL_COMPUTE_TYPE)
    log.info("faster-whisper WhisperModel loaded successfully.")
except Exception as _exc:
    log.warning("Could not pre-load faster-whisper model at module import: %s", _exc)
    _whisper_model = None


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

def listen_once(max_duration: float = MAX_RECORD_SEC) -> str:
    """Record audio with 16kHz mono VAD and hotkey detection, then transcribe.

    Keeps recording in 100ms chunks:
      - Automatically stops after detecting ~1.2 seconds of silence after speech starts.
      - Automatically stops when hotkey (F9) is released (if it was held down).
      - Safety exits if no speech is heard within 3.5s or max_duration is reached.

    Returns transcribed text, or empty string if nothing was captured.
    """
    log.info("Recording audio with VAD (16kHz mono) … speak now!")
    rec_start = time.time()

    hotkey_held_initially = False
    try:
        hotkey_held_initially = bool(keyboard.is_pressed(HOTKEY))
    except Exception:
        pass

    frames: list[np.ndarray] = []
    has_speech_started = False
    silence_duration = 0.0
    stop_reason = "max_duration"
    ambient_baseline = 200.0
    threshold = 450.0

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE) as stream:
            while (time.time() - rec_start) < max_duration:
                chunk, overflowed = stream.read(CHUNK_SAMPLES)
                if overflowed:
                    log.warning("Audio stream overflowed")
                frames.append(chunk.copy())
                elapsed = time.time() - rec_start

                # Stop if hotkey was held at start and is now released (minimum 0.3s)
                if hotkey_held_initially and elapsed >= 0.3:
                    try:
                        if not keyboard.is_pressed(HOTKEY):
                            stop_reason = "hotkey_released"
                            break
                    except Exception:
                        pass

                # Calculate RMS volume of 100ms chunk
                chunk_float = chunk.astype(np.float64)
                chunk_rms = float(np.sqrt(np.mean(chunk_float ** 2)))

                # Establish ambient noise baseline from first couple of chunks
                if len(frames) <= 2:
                    ambient_baseline = max(chunk_rms, 100.0)
                    threshold = max(450.0, ambient_baseline * 2.0)

                # VAD silence / speech detection logic
                if not has_speech_started:
                    if chunk_rms >= threshold:
                        has_speech_started = True
                        silence_duration = 0.0
                    elif elapsed >= INITIAL_WAIT_SEC:
                        stop_reason = "initial_silence_timeout"
                        break
                else:
                    if chunk_rms < threshold:
                        silence_duration += CHUNK_DURATION_SEC
                        if silence_duration >= SILENCE_LIMIT_SEC:
                            stop_reason = "silence_detected"
                            break
                    else:
                        silence_duration = 0.0

    except Exception as exc:
        log.error("Microphone recording error: %s", exc)
        return ""

    rec_time = time.time() - rec_start
    log_performance("RECORDING", rec_time, f"reason={stop_reason} speech_detected={has_speech_started}")
    log.info("Recording stopped (%.2fs, reason: %s).", rec_time, stop_reason)

    if not frames:
        log.warning("No audio captured.")
        return ""

    if not has_speech_started and stop_reason != "hotkey_released":
        log.warning("No speech detected during recording window.")
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
            log.warning("Groq failed or timed out (%s), falling back to local model.", exc)
    else:
        log.info("GROQ_API_KEY not set — using local faster-whisper.")
    return _transcribe_local(wav_path)


def _transcribe_groq(wav_path: str, api_key: str) -> str:
    t0 = time.time()
    client = Groq(api_key=api_key, timeout=5.0)
    with open(wav_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=GROQ_MODEL,
            file=("audio.wav", f, "audio/wav"),
            prompt=HINGLISH_PROMPT,
            language=None,
            response_format="text",
            timeout=5.0,
        )
    result = resp if isinstance(resp, str) else resp.text
    t_trans = time.time() - t0
    log_performance("TRANSCRIPTION", t_trans, f"engine=groq result={result!r}")
    return result


def _transcribe_local(wav_path: str) -> str:
    global _whisper_model
    t0 = time.time()
    if _whisper_model is None:
        log.info("Initializing faster-whisper WhisperModel as fallback...")
        _whisper_model = WhisperModel(LOCAL_MODEL_SIZE, compute_type=LOCAL_COMPUTE_TYPE)
    segments, _ = _whisper_model.transcribe(wav_path, beam_size=5, initial_prompt=HINGLISH_PROMPT, language=None)
    result = " ".join(seg.text for seg in segments)
    t_trans = time.time() - t0
    log_performance("TRANSCRIPTION", t_trans, f"engine=faster-whisper result={result!r}")
    return result


# ---------------------------------------------------------------------------
# TTS (Streaming via PyAV & sounddevice)
# ---------------------------------------------------------------------------

async def _speak_streaming_async(text: str) -> None:
    codec = av.CodecContext.create("mp3", "r")
    stream: Optional[sd.OutputStream] = None
    communicate = edge_tts.Communicate(text, voice=_TTS_VOICE)

    try:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and chunk.get("data"):
                packets = codec.parse(chunk["data"])
                for packet in packets:
                    frames = codec.decode(packet)
                    for frame in frames:
                        if stream is None:
                            ch_count = (
                                len(frame.layout.channels)
                                if (hasattr(frame, "layout") and frame.layout)
                                else 1
                            )
                            stream = sd.OutputStream(
                                samplerate=frame.sample_rate,
                                channels=ch_count,
                                dtype="int16",
                            )
                            stream.start()
                        arr = frame.to_ndarray()
                        if arr.ndim == 2:
                            stream.write(arr.T)
                        else:
                            stream.write(arr.reshape(-1, 1))
    finally:
        if stream is not None:
            stream.stop()
            stream.close()


async def _speak_file_fallback(text: str) -> None:
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        await edge_tts.Communicate(text, voice=_TTS_VOICE).save(tmp_path)
        playsound(tmp_path)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def speak(text: str) -> None:
    """Synthesise and play text using edge-tts with real-time streaming. Thread-safe."""
    text = (text or "").strip()
    if not text:
        return
    log.info("speak: %r", text)
    t0 = time.time()
    try:
        asyncio.run(_speak_streaming_async(text))
    except Exception as exc:
        log.warning("Edge-TTS streaming playback encountered error (%s), trying file fallback.", exc)
        try:
            asyncio.run(_speak_file_fallback(text))
        except Exception as exc2:
            log.error("TTS failed completely: %s", exc2)
    elapsed = time.time() - t0
    log_performance("SPEAKING", elapsed, f"chars={len(text)} text={text!r}")


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
