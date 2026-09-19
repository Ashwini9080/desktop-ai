"""Desktop AI — System Diagnostic & Health Check (Doctor).

Runs a quick pre-flight check to ensure the project will run smoothly
after being cloned or downloaded from GitHub.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Safe terminal encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ANSI colors for terminal
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_status(status: str, title: str, details: str = "") -> None:
    badge = {
        "OK": f"{GREEN}[OK]{RESET}",
        "WARN": f"{YELLOW}[WARN]{RESET}",
        "FAIL": f"{RED}[FAIL]{RESET}",
        "INFO": f"{BLUE}[INFO]{RESET}",
    }.get(status, f"[{status}]")
    print(f" {badge} {title}")
    if details:
        print(f"        {details}")


def check_python_version() -> bool:
    v = sys.version_info
    v_str = f"{v.major}.{v.minor}.{v.micro}"
    if v.major >= 3 and v.minor >= 10:
        print_status("OK", f"Python version: {v_str}")
        return True
    print_status("FAIL", f"Python version: {v_str}", "Requires Python 3.10 or higher.")
    return False


def check_configs(root: Path) -> bool:
    all_ok = True

    # Check apps.json
    apps_path = root / "config" / "apps.json"
    if apps_path.exists():
        try:
            with open(apps_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print_status("OK", f"config/apps.json parsed ({len(data)} apps mapped)")
        except Exception as e:
            print_status("FAIL", "config/apps.json invalid JSON", str(e))
            all_ok = False
    else:
        print_status("FAIL", "config/apps.json not found")
        all_ok = False

    # Check .env / .env.example
    env_path = root / "config" / ".env"
    env_example = root / "config" / ".env.example"

    if env_path.exists():
        print_status("OK", "config/.env exists")
    elif env_example.exists():
        print_status("WARN", "config/.env missing", "Will be auto-generated from config/.env.example on startup.")
    else:
        print_status("FAIL", "Neither config/.env nor config/.env.example found")
        all_ok = False

    # Check logs folder
    logs_dir = root / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        test_file = logs_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        print_status("OK", "logs/ directory is writable")
    except Exception as e:
        print_status("FAIL", "logs/ directory not writable", str(e))
        all_ok = False

    return all_ok


def check_dependencies() -> dict[str, bool]:
    results = {}
    packages = [
        ("dotenv", "python-dotenv"),
        ("sounddevice", "sounddevice"),
        ("numpy", "numpy"),
        ("edge_tts", "edge-tts"),
        ("playsound", "playsound"),
        ("pystray", "pystray"),
        ("PIL", "pillow"),
        ("keyboard", "keyboard"),
        ("feedparser", "feedparser"),
        ("requests", "requests"),
        ("yfinance", "yfinance"),
        ("flask", "flask"),
        ("fastmcp", "fastmcp (Model Context Protocol server)"),
        ("psutil", "psutil (System performance monitoring)"),
        ("groq", "groq (Whisper STT & instant Q&A)"),
        ("google.genai", "google-genai (Gemini fallback)"),
    ]


    missing_core = []
    missing_ai = []

    for mod, label in packages:
        try:
            __import__(mod)
            results[mod] = True
        except ImportError:
            results[mod] = False
            if "groq" in mod or "google.genai" in mod:
                missing_ai.append(label)
            else:
                missing_core.append(label)

    if not missing_core and not missing_ai:
        print_status("OK", "All required Python libraries installed")
    else:
        if missing_core:
            print_status("FAIL", f"Missing core packages: {', '.join(missing_core)}",
                         "Run: pip install -r requirements.txt")
        if missing_ai:
            print_status("WARN", f"Optional AI packages missing: {', '.join(missing_ai)}",
                         "Required only if using online LLM fallback.")

    return results


def check_audio() -> None:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        output_devs = [d for d in devices if d.get("max_output_channels", 0) > 0]

        if input_devs:
            print_status("OK", f"Microphone detected ({len(input_devs)} input device(s) found)")
        else:
            print_status("WARN", "No microphone detected", "Voice input may not capture speech.")

        if output_devs:
            print_status("OK", f"Audio output detected ({len(output_devs)} output device(s) found)")
        else:
            print_status("WARN", "No speaker detected", "Voice response (TTS) might not play.")
    except Exception as exc:
        print_status("WARN", "Audio hardware check skipped", str(exc))


def check_api_keys(root: Path) -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(root / "config" / ".env")
    except Exception:
        pass

    groq = os.getenv("GROQ_API_KEY", "").strip()
    gemini = os.getenv("GEMINI_API_KEY", "").strip()

    if groq and groq != "your_groq_api_key_here":
        print_status("OK", "GROQ_API_KEY configured (Whisper STT active)")
    else:
        print_status("INFO", "GROQ_API_KEY not set", "Free key at https://console.groq.com (fallback to local models)")

    if gemini and gemini != "your_gemini_api_key_here":
        print_status("OK", "GEMINI_API_KEY configured (Gemini reasoning active)")
    else:
        print_status("INFO", "GEMINI_API_KEY not set", "Free key at https://aistudio.google.com/apikey (local rules active)")


def main() -> None:
    print("\n" + "=" * 60)
    print(" [+] Desktop AI -- System Diagnostic & Health Check")
    print("=" * 60)

    root = Path(os.path.dirname(os.path.abspath(__file__)))

    print("\n[1] Environment & Python")
    py_ok = check_python_version()
    cfg_ok = check_configs(root)

    print("\n[2] Python Packages")
    dep_results = check_dependencies()

    print("\n[3] Audio Hardware")
    check_audio()

    print("\n[4] Cloud AI Capabilities")
    check_api_keys(root)

    print("\n" + "=" * 60)
    if py_ok and cfg_ok and all(dep_results.get(k, False) for k in ["sounddevice", "dotenv", "pystray"]):
        print(f" {GREEN}System is READY to launch!{RESET}")
        print(" Run Desktop AI using:")
        print("   - Double-click 'run.bat'")
        print("   - Or execute: python main.py")
    else:
        print(f" {RED}Some requirements need attention before running.{RESET}")
        print(" Run 'setup.bat' or 'pip install -r requirements.txt' to fix dependencies.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
