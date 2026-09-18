"""Mobile Web Server for Desktop AI Assistant.

Provides a mobile-friendly web UI and REST API so users can control their
desktop assistant from a smartphone or any device on the same local network.

Features:
  - Route '/' (GET)       : Mobile-optimized glassmorphism web interface.
  - Route '/command' (POST): Receives JSON {"text": "..."}, validates X-App-Password,
                            and forwards to handle_command().
  - Port 5000 on 0.0.0.0.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import tkinter as tk
from typing import Any, Callable, Optional

from flask import Flask, jsonify, render_template_string, request

from core.logger import get_logger

log = get_logger(__name__)

# Suppress verbose Flask request logs
logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__)

# References set upon server start
_root_window: Optional[tk.Tk] = None
_command_handler: Optional[Callable[[str, tk.Tk], str]] = None


def get_local_ip() -> str:
    """Detect local LAN IPv4 address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Desktop AI — Remote</title>
  <style>
    :root {
      --bg: #0d0a1a;
      --card-bg: rgba(30, 27, 46, 0.7);
      --card-border: rgba(168, 85, 247, 0.25);
      --accent: #a855f7;
      --accent-hover: #9333ea;
      --accent-glow: rgba(168, 85, 247, 0.4);
      --text: #f3e8ff;
      --subtext: #a89bc2;
      --success: #10b981;
      --error: #ef4444;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(124, 58, 237, 0.18) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.15) 0px, transparent 50%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 20px 16px 40px;
    }

    .container {
      width: 100%;
      max-width: 480px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    /* Header */
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 6px;
    }

    .logo-group {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .logo-icon {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, #7c3aed, #c084fc);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: 18px;
      color: #fff;
      box-shadow: 0 4px 14px var(--accent-glow);
    }

    .logo-text {
      font-size: 19px;
      font-weight: 700;
      letter-spacing: -0.3px;
    }

    .status-badge {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      color: var(--success);
    }

    .status-dot {
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--success);
    }

    /* Glass Card */
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 20px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
    }

    .card-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--subtext);
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-bottom: 12px;
    }

    /* Password Input */
    .input-row {
      display: flex;
      gap: 10px;
    }

    input, textarea {
      width: 100%;
      background: rgba(15, 12, 27, 0.6);
      border: 1px solid rgba(168, 85, 247, 0.3);
      border-radius: 14px;
      padding: 14px 16px;
      font-size: 15px;
      color: #fff;
      outline: none;
      transition: all 0.2s ease;
    }

    input:focus, textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }

    textarea {
      min-height: 90px;
      resize: none;
      line-height: 1.4;
    }

    /* Buttons */
    .btn {
      background: linear-gradient(135deg, #7c3aed, #a855f7);
      color: #fff;
      border: none;
      border-radius: 14px;
      padding: 14px 22px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.2s ease;
      box-shadow: 0 4px 16px var(--accent-glow);
      margin-top: 12px;
      width: 100%;
    }

    .btn:active {
      transform: scale(0.98);
      filter: brightness(0.9);
    }

    .btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    /* Quick Action Chips */
    .chips-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
    }

    .chip {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 12px 14px;
      color: var(--text);
      font-size: 13px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
      text-align: left;
    }

    .chip:active {
      background: rgba(168, 85, 247, 0.15);
      border-color: var(--accent);
      transform: scale(0.97);
    }

    /* Response Box */
    .response-box {
      margin-top: 14px;
      padding: 14px;
      background: rgba(15, 12, 27, 0.7);
      border: 1px solid rgba(168, 85, 247, 0.2);
      border-radius: 14px;
      font-size: 14px;
      line-height: 1.5;
      display: none;
    }

    .response-box.show {
      display: block;
      animation: fadeIn 0.3s ease;
    }

    .response-status {
      font-size: 11px;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }

    .response-status.ok { color: var(--success); }
    .response-status.err { color: var(--error); }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <div class="header">
      <div class="logo-group">
        <div class="logo-icon">AI</div>
        <div class="logo-text">Desktop Remote</div>
      </div>
      <div class="status-badge">
        <span class="status-dot"></span> Online
      </div>
    </div>

    <!-- Password Settings -->
    <div class="card">
      <div class="card-title">Security Key</div>
      <input type="password" id="appPassword" placeholder="Enter Mobile App Password" />
    </div>

    <!-- Command Input -->
    <div class="card">
      <div class="card-title">Send Command</div>
      <textarea id="commandText" placeholder="e.g. open chrome, play kesariya on spotify, latest news, India richest person..."></textarea>
      <button class="btn" id="sendBtn" onclick="sendCommand()">
        <span>🚀 Send Command</span>
      </button>

      <div class="response-box" id="responseBox">
        <div class="response-status" id="responseStatus"></div>
        <div class="response-msg" id="responseMsg"></div>
      </div>
    </div>

    <!-- Quick Controls -->
    <div class="card">
      <div class="card-title">Quick Controls</div>
      <div class="chips-grid">
        <div class="chip" onclick="quickAction('pause spotify')">⏯️ Play / Pause</div>
        <div class="chip" onclick="quickAction('next song')">⏭️ Next Track</div>
        <div class="chip" onclick="quickAction('open spotify')">🎵 Open Spotify</div>
        <div class="chip" onclick="quickAction('open vscode')">💻 Open VS Code</div>
        <div class="chip" onclick="quickAction('open chrome')">🌐 Open Chrome</div>
        <div class="chip" onclick="quickAction('bbc news')">📰 BBC News</div>
        <div class="chip" onclick="quickAction('ndtv news')">📰 NDTV News</div>
        <div class="chip" onclick="quickAction('stock market batao')">📈 Stocks</div>
      </div>
    </div>
  </div>

  <script>
    // Load saved password
    const pwdInput = document.getElementById('appPassword');
    const savedPwd = localStorage.getItem('desktop_ai_pwd');
    if (savedPwd) {
      pwdInput.value = savedPwd;
    }
    pwdInput.addEventListener('input', () => {
      localStorage.setItem('desktop_ai_pwd', pwdInput.value.trim());
    });

    async function sendCommand(overrideText = null) {
      const text = overrideText || document.getElementById('commandText').value.trim();
      const password = pwdInput.value.trim();
      const btn = document.getElementById('sendBtn');
      const resBox = document.getElementById('responseBox');
      const resStatus = document.getElementById('responseStatus');
      const resMsg = document.getElementById('responseMsg');

      if (!text) {
        alert('Please enter a command.');
        return;
      }

      btn.disabled = true;
      btn.innerHTML = '<span>⏳ Running...</span>';
      resBox.className = 'response-box';

      try {
        const response = await fetch('/command', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-App-Password': password,
          },
          body: JSON.stringify({ text: text })
        });

        const data = await response.json();

        resBox.classList.add('show');
        if (response.ok) {
          resStatus.className = 'response-status ok';
          resStatus.innerText = 'Success (200 OK)';
          resMsg.innerText = data.message || 'Command executed.';
          if (!overrideText) document.getElementById('commandText').value = '';
        } else {
          resStatus.className = 'response-status err';
          resStatus.innerText = `Error (${response.status})`;
          resMsg.innerText = data.message || 'Unauthorized or failed.';
        }
      } catch (err) {
        resBox.classList.add('show');
        resStatus.className = 'response-status err';
        resStatus.innerText = 'Network Error';
        resMsg.innerText = 'Could not reach Desktop AI. Make sure you are on the same Wi-Fi.';
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>🚀 Send Command</span>';
      }
    }

    function quickAction(cmd) {
      document.getElementById('commandText').value = cmd;
      sendCommand(cmd);
    }
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def home():
    """Serve the mobile control web application."""
    return render_template_string(_HTML_TEMPLATE)


@app.route("/command", methods=["POST"])
def post_command():
    """Accept and execute command from remote phone."""
    expected_password = os.getenv("MOBILE_APP_PASSWORD", "").strip()

    # Password check
    client_password = request.headers.get("X-App-Password", "").strip()
    if expected_password and client_password != expected_password:
        log.warning("Unauthorized mobile command attempt. Invalid X-App-Password.")
        return jsonify({
            "status": "error",
            "message": "Unauthorized. Invalid or missing X-App-Password."
        }), 401

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()

    if not text:
        return jsonify({"status": "error", "message": "No command text provided."}), 400

    log.info("Mobile command received: %r", text)

    if _command_handler:
        # Execute command through the main pipeline
        try:
            import inspect
            sig = inspect.signature(_command_handler)
            if len(sig.parameters) == 1:
                result = _command_handler(text)
            else:
                result = _command_handler(text, _root_window)
            return jsonify({
                "status": "ok",
                "message": result or f"Executed: {text}"
            }), 200
        except Exception as exc:
            log.error("Mobile command execution error: %s", exc)
            return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "error", "message": "Assistant engine not initialized."}), 503


@app.route("/whatsapp", methods=["POST", "GET"])
def whatsapp_endpoint():
    """Twilio WhatsApp webhook endpoint."""
    if request.method == "GET":
        return "Desktop AI WhatsApp Webhook is active.", 200

    from core.whatsapp_bot import process_whatsapp_message

    body = request.values.get("Body", "")
    sender = request.values.get("From", "")

    if not _command_handler:
        return "Assistant engine not initialized.", 503

    def _execute(cmd: str) -> str:
        import inspect
        sig = inspect.signature(_command_handler)
        if len(sig.parameters) == 1:
            return _command_handler(cmd)
        else:
            return _command_handler(cmd, _root_window)

    twiml_resp = process_whatsapp_message(body, sender, _execute)
    return twiml_resp, 200, {"Content-Type": "application/xml"}


def start_mobile_server(root: Optional[Any] = None, handler: Optional[Callable[..., str]] = None, port: int = 5000) -> None:
    """Start the Flask server on 0.0.0.0:port."""
    global _root_window, _command_handler
    _root_window = root
    _command_handler = handler

    ip = get_local_ip()
    log.info("=" * 60)
    log.info("📱 Mobile Web Server started!")
    log.info("👉 On your phone (same Wi-Fi), open: http://%s:%d", ip, port)
    log.info("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
