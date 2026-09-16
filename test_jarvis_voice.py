"""Quick test — JARVIS-like British male voice via edge-tts."""
import asyncio
import os
import tempfile

import edge_tts
from playsound import playsound

VOICES = [
    ("en-GB-RyanNeural",       "British male — closest to JARVIS"),
    ("en-GB-ThomasNeural",     "British male — alternate"),
    ("en-US-ChristopherNeural","American male — deep & authoritative"),
]

TEST_LINE = (
    "Good afternoon, Ash. All systems are online and fully operational. "
    "How may I assist you today?"
)


async def play_voice(voice: str, label: str) -> None:
    print(f"\n▶  Testing: {voice}  ({label})")
    tmp = tempfile.mktemp(suffix=".mp3")
    try:
        await edge_tts.Communicate(TEST_LINE, voice=voice).save(tmp)
        playsound(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


async def main() -> None:
    for voice, label in VOICES:
        await play_voice(voice, label)
        input("  → Press Enter for next voice...")


if __name__ == "__main__":
    asyncio.run(main())
