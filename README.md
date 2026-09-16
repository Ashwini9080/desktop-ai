# Desktop AI Assistant

A modular Python desktop assistant featuring voice control, intent classification, local app execution, and Gemini AI fallback.

---

## 📁 Project Structure

```text
desktop-ai/
├── main.py                    # Application entry point and coordination loop
├── config/
│   ├── apps.json              # Mapping of application names to executable paths
│   └── .env                   # Environment variables and API keys
├── core/
│   ├── voice.py               # Speech recognition (STT) and synthesis (TTS)
│   ├── intent_classifier.py   # Intent determination and entity parsing
│   ├── gemini_fallback.py     # Fallback query answering with Google Gemini
│   └── executor.py            # Local desktop actions and application execution
├── requirements.txt           # Python dependencies
├── .gitignore                 # Excludes .env, __pycache__, and *.pyc
└── README.md                  # Project documentation and guide
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ installed
- Microphone & audio output for voice features

### 2. Setup Virtual Environment
```bash
python -m venv venv
# On Windows PowerShell:
venv\Scripts\Activate.ps1
# On Windows CMD:
venv\Scripts\activate.bat
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration

#### Environment Variables (`config/.env`)
Add your API keys to [`config/.env`](file:///c:/Users/ASHWINI/Downloads/desktop_ai/config/.env):
```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

#### Application Mappings (`config/apps.json`)
Configure your local application paths in [`config/apps.json`](file:///c:/Users/ASHWINI/Downloads/desktop_ai/config/apps.json):
```json
{
  "antigravity": "C:\\Users\\ASHWINI\\AppData\\Local\\Programs\\antigravity\\antigravity.exe",
  "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "notepad": "C:\\Windows\\System32\\notepad.exe",
  "calculator": "calc.exe",
  "vscode": "code"
}
```

---

## 💻 Running the Assistant

```bash
python main.py
```
