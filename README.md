# ⚡ Desktop AI Assistant

A high-performance, modular Python desktop assistant featuring voice control, instant intent classification (English + Hinglish), local app automation, real-time market analysis, news feeds, and mobile remote control.

---

## 🚀 Quick Start (Windows)

### Option 1: One-Click Setup (Recommended)
1. **Clone or Download** this repository.
2. Double-click **`setup.bat`**  
   *(Creates a virtual environment, installs dependencies, prepares `config/.env`, and runs system diagnostics).*
3. Double-click **`run.bat`** to start the assistant!

---

### Option 2: Manual Setup

```bash
# 1. Clone the repository
git clone https://github.com/Ashwini9080/desktop-ai.git
cd desktop-ai

# 2. Create and activate a virtual environment
python -m venv venv
# Windows CMD:
venv\Scripts\activate.bat
# Windows PowerShell:
venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template
copy config\.env.example config\.env

# 5. Verify system health
python doctor.py

# 6. Run the assistant
python main.py
```

---

## 🩺 System Diagnostic Tool

Before reporting issues or after installing dependencies, run the built-in diagnostic tool:

```bash
python doctor.py
```

The doctor verifies:
- Python version (>= 3.10)
- All required libraries & optional AI SDKs
- Audio hardware (Microphone & Speaker detection)
- Configuration file syntax (`apps.json` and `.env`)

---

## ⚙️ Configuration

### 1. Environment Variables (`config/.env`)

Copy `config/.env.example` to `config/.env` and configure your settings:

```env
# Spoken name in greetings (e.g., "Good morning, Ash")
USER_NAME=Ash

# Groq API Key (Free: https://console.groq.com)
# Used for ultra-fast Whisper speech-to-text and instant Q&A
GROQ_API_KEY=your_groq_api_key_here

# Gemini API Key (Free: https://aistudio.google.com/apikey)
# Used for complex reasoning & fallback intent matching
GEMINI_API_KEY=your_gemini_api_key_here

# Mobile Remote Control Password (protects local web interface)
MOBILE_APP_PASSWORD=your_mobile_password_here
```

> **Note:** Desktop AI works out-of-the-box in **Local Mode** even without API keys. Local app launching, website shortcuts, Spotify media controls, news feeds, and stock analysis work immediately.

### 2. Custom App Shortcuts (`config/apps.json`)

Map custom names or voice triggers to executables or Windows commands:

```json
{
  "chrome": "\"%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe\"",
  "notepad": "%SystemRoot%\\System32\\notepad.exe",
  "calculator": "calc.exe",
  "vscode": "%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe",
  "spotify": "%LOCALAPPDATA%\\Microsoft\\WindowsApps\\Spotify.exe"
}
```

---

## 🎯 Key Features & Controls

| Feature | How to Use |
| :--- | :--- |
| **Slim Input Bar** | Always-on-top bar at the top of your screen. Type any command and press `Enter`. Press `Esc` to clear. |
| **Voice Hotkey** | Press **`Ctrl+Shift+A`** to trigger microphone recording, then speak your command. |
| **System Tray** | Right-click the purple AI tray icon in your taskbar to Show/Hide the input bar or safely Quit. |
| **Silent Startup** | Double-click **`launch_silent.vbs`** (or create a shortcut in your `shell:startup` folder) to run in the background with no command prompt window. |
| **Mobile Remote** | Open `http://<your-pc-ip>:5000` from your phone or tablet on the same Wi-Fi to control your desktop remotely. |
| **News Headlines** | Say/Type `"news"`, `"tech news"`, or `"business news"` to view an interactive headline popup and hear the audio summary. |
| **Stock Market Analysis** | Say/Type `"stock movers"` or `"market update"` for live NSE/BSE top gainers, losers, and 52-week high breakouts. |
| **MCP Server** | Run `python mcp_server.py` to expose all desktop tools via Model Context Protocol over SSE at `http://127.0.0.1:8000/sse` for Claude Desktop / custom agents. |
| **Privacy Protection** | Built-in guardian blocks accidental or unauthorized access to Gmail and personal email accounts. |

---

## 📁 Project Architecture

```text
desktop-ai/
├── main.py                 # Application coordination loop, input bar, tray icon
├── mcp_server.py           # Model Context Protocol (MCP) server (SSE on :8000)
├── doctor.py               # Preflight system health check & diagnostics
├── setup.bat               # 1-Click Windows setup script
├── run.bat                 # 1-Click launch script (auto venv detection)
├── launch_silent.vbs       # Background launch script without console window
├── requirements.txt        # Clean Python dependencies
├── config/
│   ├── apps.json           # Application executable mappings
│   └── .env.example        # Environment variable template
├── core/
│   ├── intent_classifier.py# Fast regex rules for Hinglish/English commands
│   ├── executor.py         # Subprocess launcher, browser URLs, media keys
│   ├── voice.py            # STT (Groq Whisper) & TTS (Edge-TTS)
│   ├── gemini_fallback.py  # Google Gemini & Groq fallback Q&A
│   ├── news.py             # RSS news aggregation (RSS feeds)
│   ├── news_ui.py          # Tkinter dark-mode news popup
│   ├── stocks.py           # Stock market analysis (yfinance)
│   ├── greeting.py         # Time-aware context greetings
│   ├── mobile_server.py    # Flask mobile remote control server
│   └── logger.py           # Rotating file logger
└── logs/
    └── .gitkeep            # Persists logs directory in git
```

---

## ❓ Troubleshooting

- **Microphone not capturing speech:**  
  Run `python doctor.py` to ensure Windows has granted microphone permissions to Python.
- **Edge-TTS audio not playing:**  
  Edge-TTS requires an active internet connection to synthesize high-definition speech.
- **Mobile remote not opening on phone:**  
  Ensure both your PC and phone are connected to the same Wi-Fi network and Windows Firewall permits inbound connections on port 5000.
