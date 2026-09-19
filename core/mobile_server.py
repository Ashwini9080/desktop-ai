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

from datetime import datetime
import hmac
import ipaddress
import logging
import os
import secrets
import socket
import threading
import time
import tkinter as tk
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template_string, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from core.logger import get_logger

log = get_logger(__name__)

# Suppress verbose Flask request logs
logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024  # Reject requests larger than 1KB (1024 bytes)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# In-memory session store: {token: expiry_timestamp}
_active_sessions: Dict[str, float] = {}
SESSION_TTL_SECONDS = 3600  # 1 hour validity


@app.errorhandler(429)
def ratelimit_handler(e):
    client_ip = request.remote_addr or "unknown"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.warning("[%s] Rate limit exceeded on %s from IP: %s", now_str, request.path, client_ip)
    return jsonify({
        "status": "error",
        "message": "Rate limit exceeded. Max 20 requests per minute."
    }), 429


@app.errorhandler(413)
def request_entity_too_large(e):
    client_ip = request.remote_addr or "unknown"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.warning("[%s] Request payload exceeded 1KB limit from IP: %s", now_str, client_ip)
    return jsonify({
        "status": "error",
        "message": "Request payload exceeds 1KB limit."
    }), 413


def _clean_expired_sessions() -> None:
    now = time.time()
    expired = [t for t, exp in _active_sessions.items() if now > exp]
    for t in expired:
        _active_sessions.pop(t, None)


def _create_session_token() -> str:
    _clean_expired_sessions()
    token = secrets.token_hex(24)
    _active_sessions[token] = time.time() + SESSION_TTL_SECONDS
    return token


def _validate_session_token(token: str) -> bool:
    if not token or token not in _active_sessions:
        return False
    if time.time() > _active_sessions[token]:
        _active_sessions.pop(token, None)
        return False
    return True


def _is_allowed_origin(origin: Optional[str]) -> bool:
    """Validate Origin/Referer against allowed local IP patterns to mitigate CSRF."""
    if not origin:
        return True

    try:
        parsed = urlparse(origin)
        host = parsed.hostname or ""
        if not host:
            return False

        # Allow localhost / loopback
        if host in ("localhost", "127.0.0.1", "::1"):
            return True

        # Allow server's detected local IP
        local_ip = get_local_ip()
        if host == local_ip:
            return True

        # Allow private IP ranges (e.g. 192.168.x.x, 10.x.x.x, 172.16-31.x.x)
        try:
            ip_obj = ipaddress.ip_address(host)
            if ip_obj.is_private or ip_obj.is_loopback:
                return True
        except ValueError:
            pass

        return False
    except Exception:
        return False


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


_HTML_TEMPLATE = r"""\
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

    /* Voice Call & Mic Section */
    .voice-card {
      text-align: center;
      position: relative;
      overflow: hidden;
      border: 1px solid rgba(168, 85, 247, 0.35);
      background: linear-gradient(180deg, rgba(30, 27, 46, 0.85), rgba(20, 16, 35, 0.7));
    }

    .voice-center {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 10px 0;
      gap: 12px;
    }

    .voice-mic-btn {
      position: relative;
      width: 88px;
      height: 88px;
      border-radius: 50%;
      background: linear-gradient(135deg, #7c3aed, #c084fc);
      border: 3px solid rgba(255, 255, 255, 0.2);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      box-shadow: 0 8px 28px var(--accent-glow);
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      outline: none;
      -webkit-tap-highlight-color: transparent;
    }

    .voice-mic-btn:active {
      transform: scale(0.92);
    }

    .voice-mic-btn.listening {
      background: linear-gradient(135deg, #ef4444, #f43f5e);
      box-shadow: 0 0 0 10px rgba(239, 68, 68, 0.2), 0 0 35px rgba(239, 68, 68, 0.55);
      animation: micPulse 1.4s infinite;
    }

    .voice-mic-btn .mic-icon {
      font-size: 36px;
      line-height: 1;
      pointer-events: none;
      transition: transform 0.2s ease;
    }

    .voice-status-text {
      font-size: 14px;
      font-weight: 500;
      color: var(--subtext);
      min-height: 22px;
      transition: color 0.2s ease;
      padding: 0 10px;
    }

    .voice-status-text.active {
      color: #38bdf8;
      font-weight: 600;
    }

    /* Sound Equalizer Waves */
    .sound-wave {
      display: none;
      align-items: center;
      justify-content: center;
      gap: 5px;
      height: 24px;
    }

    .sound-wave.active {
      display: flex;
    }

    .sound-wave .bar {
      width: 4px;
      height: 8px;
      background: #38bdf8;
      border-radius: 4px;
      animation: soundBar 0.9s ease-in-out infinite alternate;
    }

    .sound-wave .bar:nth-child(1) { animation-delay: 0.1s; }
    .sound-wave .bar:nth-child(2) { animation-delay: 0.25s; }
    .sound-wave .bar:nth-child(3) { animation-delay: 0.4s; }
    .sound-wave .bar:nth-child(4) { animation-delay: 0.2s; }
    .sound-wave .bar:nth-child(5) { animation-delay: 0.35s; }

    @keyframes soundBar {
      0% { height: 6px; }
      100% { height: 24px; }
    }

    @keyframes micPulse {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.45); }
      70% { box-shadow: 0 0 0 18px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }

    .voice-options {
      display: flex;
      justify-content: center;
      margin-top: 4px;
    }

    .voice-toggle-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 20px;
      padding: 6px 14px;
      font-size: 12px;
      font-weight: 600;
      color: var(--subtext);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
    }

    .voice-toggle-btn.active {
      background: rgba(168, 85, 247, 0.25);
      border-color: var(--accent);
      color: #f3e8ff;
    }

    /* ── Live Phone Call Banner ── */
    .start-call-banner {
      background: linear-gradient(135deg, #059669, #10b981);
      color: #fff;
      border: none;
      border-radius: 18px;
      padding: 18px 20px;
      font-size: 17px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      box-shadow: 0 8px 25px rgba(16, 185, 129, 0.4);
      transition: all 0.2s ease;
      width: 100%;
    }

    .start-call-banner:active {
      transform: scale(0.97);
    }

    /* ── Full Screen Phone Call Screen ── */
    .call-screen {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: radial-gradient(circle at 50% 25%, #1e153b 0%, #090712 80%);
      z-index: 9999;
      display: none;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
      padding: 48px 24px 50px;
      color: #fff;
      box-sizing: border-box;
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
    }

    .call-screen.active {
      display: flex;
      animation: callFadeIn 0.3s ease;
    }

    .call-header {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }

    .call-caller-name {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.4px;
      color: #f3e8ff;
    }

    .call-duration {
      font-size: 13px;
      font-weight: 600;
      color: #10b981;
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 4px 14px;
      border-radius: 20px;
    }

    .call-avatar-container {
      position: relative;
      width: 150px;
      height: 150px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 10px 0;
    }

    .call-avatar {
      width: 105px;
      height: 105px;
      border-radius: 50%;
      background: linear-gradient(135deg, #7c3aed, #c084fc);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 42px;
      box-shadow: 0 0 40px rgba(168, 85, 247, 0.55);
      z-index: 2;
    }

    .call-pulse-ring {
      position: absolute;
      width: 100%;
      height: 100%;
      border-radius: 50%;
      border: 2px solid rgba(168, 85, 247, 0.4);
      animation: callPulse 2s infinite cubic-bezier(0.2, 0.8, 0.2, 1);
    }

    .call-pulse-ring:nth-child(2) {
      animation-delay: 0.65s;
    }

    @keyframes callPulse {
      0% { transform: scale(0.7); opacity: 1; }
      100% { transform: scale(1.65); opacity: 0; }
    }

    .call-live-status {
      font-size: 15px;
      color: #38bdf8;
      text-align: center;
      min-height: 24px;
      font-weight: 600;
      padding: 0 10px;
    }

    .call-transcript-card {
      width: 100%;
      max-width: 360px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(168, 85, 247, 0.25);
      border-radius: 16px;
      padding: 16px;
      font-size: 14px;
      line-height: 1.5;
      max-height: 110px;
      overflow-y: auto;
      text-align: center;
      color: #e9d5ff;
    }

    .call-controls {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 26px;
      width: 100%;
    }

    .call-btn-circle {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      cursor: pointer;
      transition: all 0.2s ease;
      outline: none;
    }

    .call-btn-circle.active {
      background: rgba(168, 85, 247, 0.35);
      border-color: var(--accent);
      color: #f3e8ff;
    }

    .call-btn-end {
      width: 74px;
      height: 74px;
      border-radius: 50%;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      border: none;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      cursor: pointer;
      box-shadow: 0 8px 26px rgba(239, 68, 68, 0.45);
      transition: all 0.2s ease;
    }

    .call-btn-end:active {
      transform: scale(0.92);
    }

    @keyframes callFadeIn {
      from { opacity: 0; transform: scale(0.98); }
      to { opacity: 1; transform: scale(1); }
    }

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

    <!-- Live Phone Call Banner Button -->
    <button class="start-call-banner" onclick="startPhoneCallMode()">
      <span style="font-size: 24px;">📞</span>
      <span>Call Desktop AI (Phone Call Mode)</span>
    </button>

    <!-- Password Settings -->
    <div class="card">
      <div class="card-title">Security Key</div>
      <input type="password" id="appPassword" placeholder="Enter Mobile App Password" />
    </div>

    <!-- Voice Call & Live Mic Assistant -->
    <div class="card voice-card">
      <div class="card-title">🎙️ Push-to-Talk Mic</div>
      <div class="voice-center">
        <button class="voice-mic-btn" id="voiceMicBtn" onclick="toggleVoiceRecording()" title="Tap to talk">
          <div class="mic-icon" id="micIcon">🎙️</div>
        </button>
        <div class="voice-status-text" id="voiceStatusText">Tap mic to speak (Hindi / English)</div>
        
        <div class="sound-wave" id="soundWave">
          <span class="bar"></span>
          <span class="bar"></span>
          <span class="bar"></span>
          <span class="bar"></span>
          <span class="bar"></span>
        </div>
      </div>

      <div class="voice-options">
        <button class="voice-toggle-btn active" id="speechToggleBtn" onclick="toggleSpeechOutput()">
          <span id="speechToggleIcon">🔊</span>
          <span id="speechToggleLabel">AI Voice Response: ON</span>
        </button>
      </div>
    </div>

    <!-- Command Input -->
    <div class="card">
      <div class="card-title">Send Command</div>
      <textarea id="commandText" placeholder="e.g. open chrome, call mom, play kesariya on spotify, latest news..."></textarea>
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
        <div class="chip" onclick="quickAction('call mom')">📞 Call Mom</div>
        <div class="chip" onclick="quickAction('call rahul')">📞 Call Rahul</div>
        <div class="chip" onclick="quickAction('pause spotify')">⏯️ Play / Pause</div>
        <div class="chip" onclick="quickAction('next song')">⏭️ Next Track</div>
        <div class="chip" onclick="quickAction('open spotify')">🎵 Open Spotify</div>
        <div class="chip" onclick="quickAction('open vscode')">💻 Open VS Code</div>
        <div class="chip" onclick="quickAction('open chrome')">🌐 Open Chrome</div>
        <div class="chip" onclick="quickAction('ndtv news')">📰 NDTV News</div>
        <div class="chip" onclick="quickAction('stock market batao')">📈 Stocks</div>
        <div class="chip" onclick="quickAction('open calculator')">🔢 Calculator</div>
      </div>
    </div>
  </div>

  <!-- ── Full-Screen Phone Call Screen Overlay ── -->
  <div class="call-screen" id="phoneCallScreen">
    <div class="call-header">
      <div class="call-caller-name">Desktop AI</div>
      <div class="call-duration" id="callDurationBadge">
        <span class="status-dot"></span>
        <span id="callTimerText">Connected • 00:00</span>
      </div>
    </div>

    <div class="call-avatar-container">
      <div class="call-pulse-ring"></div>
      <div class="call-pulse-ring"></div>
      <div class="call-avatar">🤖</div>
    </div>

    <div class="call-live-status" id="callLiveStatus">Listening for your command...</div>

    <div class="call-transcript-card" id="callTranscriptCard">
      Call connected! Say: "open chrome", "play arijit singh on spotify", "ndtv news", "lock pc"...
    </div>

    <div class="sound-wave active" id="callSoundWave" style="height: 26px; margin: 8px 0;">
      <span class="bar" style="height: 10px;"></span>
      <span class="bar" style="height: 20px;"></span>
      <span class="bar" style="height: 26px;"></span>
      <span class="bar" style="height: 16px;"></span>
      <span class="bar" style="height: 22px;"></span>
    </div>

    <div class="call-controls">
      <button class="call-btn-circle active" id="callMuteBtn" onclick="toggleCallMute()" title="Mute/Unmute Mic">
        <span id="callMuteIcon">🎙️</span>
      </button>

      <button class="call-btn-end" onclick="endPhoneCallMode()" title="End Call">
        <span>🛑</span>
      </button>

      <button class="call-btn-circle active" id="callSpeakerBtn" onclick="toggleCallSpeaker()" title="Speaker">
        <span id="callSpeakerIcon">🔊</span>
      </button>
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

    // ── Voice Recognition & Audio Reply ──
    let recognition = null;
    let isRecording = false;
    let voiceReplyEnabled = true;

    // ── Phone Call Mode State ──
    let inPhoneCall = false;
    let callTimerInterval = null;
    let callSeconds = 0;
    let callRecognition = null;
    let isCallMuted = false;
    let isCallAISpeaking = false;

    function playCallAudioTone(type = 'connect') {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        if (type === 'connect') {
          osc.frequency.setValueAtTime(440, ctx.currentTime);
          osc.frequency.exponentialRampToValueAtTime(660, ctx.currentTime + 0.15);
          osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.3);
          gain.gain.setValueAtTime(0.18, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
          osc.start();
          osc.stop(ctx.currentTime + 0.45);
        } else {
          osc.frequency.setValueAtTime(660, ctx.currentTime);
          osc.frequency.exponentialRampToValueAtTime(330, ctx.currentTime + 0.25);
          gain.gain.setValueAtTime(0.2, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
          osc.start();
          osc.stop(ctx.currentTime + 0.35);
        }
      } catch (e) {}
    }

    function startPhoneCallMode() {
      const password = pwdInput.value.trim();
      let sessionToken = sessionStorage.getItem('mobile_session_token');
      if (!sessionToken && !password) {
        alert('Please enter your Remote Password first.');
        pwdInput.focus();
        return;
      }

      const SpeechClass = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechClass) {
        alert('Your browser does not support voice recognition. Please use Google Chrome on your phone.');
        return;
      }

      inPhoneCall = true;
      isCallMuted = false;
      callSeconds = 0;
      document.getElementById('phoneCallScreen').classList.add('active');
      playCallAudioTone('connect');

      // Start call timer
      updateCallTimerUI();
      callTimerInterval = setInterval(() => {
        callSeconds++;
        updateCallTimerUI();
      }, 1000);

      document.getElementById('callLiveStatus').innerText = 'Listening for your command...';
      document.getElementById('callTranscriptCard').innerText = 'Call connected! Bolen: "open chrome", "kesariya gana bajao", "call mom"...';

      // Start continuous call speech loop
      startContinuousCallRecognition();
    }

    function updateCallTimerUI() {
      const mins = String(Math.floor(callSeconds / 60)).padStart(2, '0');
      const secs = String(callSeconds % 60).padStart(2, '0');
      document.getElementById('callTimerText').innerText = `Connected • ${mins}:${secs}`;
    }

    function startContinuousCallRecognition() {
      if (!inPhoneCall || isCallMuted || isCallAISpeaking) return;

      const SpeechClass = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechClass) return;

      if (callRecognition) {
        try { callRecognition.abort(); } catch (e) {}
      }

      callRecognition = new SpeechClass();
      callRecognition.continuous = false;
      callRecognition.interimResults = true;
      callRecognition.lang = 'hi-IN';

      callRecognition.onstart = () => {
        document.getElementById('callLiveStatus').innerText = 'Listening... Speak now';
        document.getElementById('callSoundWave').classList.add('active');
      };

      callRecognition.onresult = (event) => {
        let interim = '';
        let final = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }
        const text = (final || interim).trim();
        if (text) {
          document.getElementById('callLiveStatus').innerText = `Hearing: "${text}"`;
        }
        if (final && final.trim()) {
          try { callRecognition.stop(); } catch(e) {}
          handleCallCommand(final.trim());
        }
      };

      callRecognition.onerror = (event) => {
        if (!inPhoneCall) return;
        if (event.error !== 'no-speech') {
          console.warn('Call recognition error:', event.error);
        }
        // Auto-restart if call is still active
        setTimeout(() => {
          if (inPhoneCall && !isCallMuted && !isCallAISpeaking) {
            startContinuousCallRecognition();
          }
        }, 400);
      };

      callRecognition.onend = () => {
        if (inPhoneCall && !isCallMuted && !isCallAISpeaking) {
          setTimeout(() => {
            if (inPhoneCall && !isCallMuted && !isCallAISpeaking) {
              startContinuousCallRecognition();
            }
          }, 300);
        }
      };

      try {
        callRecognition.start();
      } catch (e) {
        console.warn('Recognition start exception:', e);
      }
    }

    async function handleCallCommand(text) {
      if (!text) return;
      document.getElementById('callLiveStatus').innerText = 'Executing on PC...';
      document.getElementById('callTranscriptCard').innerHTML = `<strong>🗣️ You:</strong> "${text}"<br><em>⏳ Processing...</em>`;

      const password = pwdInput.value.trim();
      let sessionToken = sessionStorage.getItem('mobile_session_token');
      const headers = { 'Content-Type': 'application/json' };
      if (sessionToken) {
        headers['X-Session-Token'] = sessionToken;
      } else if (password) {
        headers['X-App-Password'] = password;
      }

      try {
        const response = await fetch('/command', {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ text: text })
        });
        const data = await response.json();
        if (data.token) sessionStorage.setItem('mobile_session_token', data.token);

        const replyMsg = data.message || (response.ok ? 'Command executed.' : 'Failed to execute command.');
        document.getElementById('callTranscriptCard').innerHTML = `<strong>🗣️ You:</strong> "${text}"<br><strong>🤖 AI:</strong> ${replyMsg}`;

        // Speak reply back over the call
        speakCallReply(replyMsg);
      } catch (err) {
        document.getElementById('callTranscriptCard').innerHTML = `<strong>🗣️ You:</strong> "${text}"<br><span style="color:#ef4444;">Network Error: PC unreachable</span>`;
        speakCallReply('Network error. Could not connect to desktop.');
      }
    }

    function speakCallReply(message) {
      if (!window.speechSynthesis || !voiceReplyEnabled) {
        // If voice reply disabled, immediately resume listening
        setTimeout(() => {
          if (inPhoneCall && !isCallMuted) startContinuousCallRecognition();
        }, 500);
        return;
      }

      isCallAISpeaking = true;
      document.getElementById('callLiveStatus').innerText = 'AI is speaking...';
      window.speechSynthesis.cancel();

      const cleanMsg = message.replace(/\[.*?\]/g, '').replace(/[\*_#`]/g, '').trim();
      const utter = new SpeechSynthesisUtterance(cleanMsg || 'Done');
      utter.rate = 1.05;

      const voices = window.speechSynthesis.getVoices();
      const preferred = voices.find(v => v.lang && (v.lang.includes('hi') || v.lang.includes('IN'))) || voices[0];
      if (preferred) utter.voice = preferred;

      utter.onend = () => {
        isCallAISpeaking = false;
        document.getElementById('callLiveStatus').innerText = 'Listening for your next command...';
        if (inPhoneCall && !isCallMuted) {
          startContinuousCallRecognition();
        }
      };

      utter.onerror = () => {
        isCallAISpeaking = false;
        if (inPhoneCall && !isCallMuted) {
          startContinuousCallRecognition();
        }
      };

      window.speechSynthesis.speak(utter);
    }

    function toggleCallMute() {
      isCallMuted = !isCallMuted;
      const muteBtn = document.getElementById('callMuteBtn');
      const icon = document.getElementById('callMuteIcon');
      if (isCallMuted) {
        muteBtn.classList.remove('active');
        icon.innerText = '🔇';
        document.getElementById('callLiveStatus').innerText = 'Microphone Muted';
        if (callRecognition) try { callRecognition.abort(); } catch(e) {}
      } else {
        muteBtn.classList.add('active');
        icon.innerText = '🎙️';
        document.getElementById('callLiveStatus').innerText = 'Listening...';
        startContinuousCallRecognition();
      }
    }

    function toggleCallSpeaker() {
      voiceReplyEnabled = !voiceReplyEnabled;
      const spkBtn = document.getElementById('callSpeakerBtn');
      const icon = document.getElementById('callSpeakerIcon');
      if (voiceReplyEnabled) {
        spkBtn.classList.add('active');
        icon.innerText = '🔊';
      } else {
        spkBtn.classList.remove('active');
        icon.innerText = '🔈';
        if (window.speechSynthesis) window.speechSynthesis.cancel();
      }
    }

    function endPhoneCallMode() {
      inPhoneCall = false;
      isCallAISpeaking = false;
      playCallAudioTone('end');
      if (callTimerInterval) clearInterval(callTimerInterval);
      if (callRecognition) try { callRecognition.abort(); } catch(e) {}
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      document.getElementById('phoneCallScreen').classList.remove('active');
    }

    function initSpeechRecognition() {
      const SpeechClass = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechClass) {
        return null;
      }
      const rec = new SpeechClass();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = 'hi-IN';

      rec.onstart = () => {
        isRecording = true;
        setVoiceUIActive(true);
        if (navigator.vibrate) navigator.vibrate(30);
      };

      rec.onresult = (event) => {
        let interim = '';
        let final = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }
        const text = (final || interim).trim();
        if (text) {
          document.getElementById('commandText').value = text;
          document.getElementById('voiceStatusText').innerText = `"${text}"`;
        }
        if (final && final.trim()) {
          rec.stop();
          setVoiceUIActive(false);
          sendCommand(final.trim());
        }
      };

      rec.onerror = (event) => {
        console.warn('Speech recognition error:', event.error);
        isRecording = false;
        setVoiceUIActive(false);
        const status = document.getElementById('voiceStatusText');
        if (event.error === 'not-allowed') {
          status.innerText = 'Microphone permission blocked.';
        } else if (event.error === 'no-speech') {
          status.innerText = 'No speech heard. Tap again to talk.';
        } else {
          status.innerText = `Mic error: ${event.error}`;
        }
      };

      rec.onend = () => {
        isRecording = false;
        setVoiceUIActive(false);
      };

      return rec;
    }

    function toggleVoiceRecording() {
      const status = document.getElementById('voiceStatusText');
      if (!recognition) {
        recognition = initSpeechRecognition();
      }
      if (!recognition) {
        status.innerText = 'Speech recognition not supported in this browser. Please use Chrome.';
        return;
      }

      if (isRecording) {
        try { recognition.stop(); } catch (e) {}
        isRecording = false;
        setVoiceUIActive(false);
      } else {
        try {
          recognition.start();
        } catch (e) {
          console.warn('Recognition start exception:', e);
        }
      }
    }

    function setVoiceUIActive(active) {
      const btn = document.getElementById('voiceMicBtn');
      const wave = document.getElementById('soundWave');
      const status = document.getElementById('voiceStatusText');
      const icon = document.getElementById('micIcon');

      if (active) {
        btn.classList.add('listening');
        wave.classList.add('active');
        status.classList.add('active');
        status.innerText = 'Listening... Speak now';
        icon.innerText = '🛑';
      } else {
        btn.classList.remove('listening');
        wave.classList.remove('active');
        status.classList.remove('active');
        icon.innerText = '🎙️';
        if (status.innerText.startsWith('Listening')) {
          status.innerText = 'Tap mic to speak (Hindi / English)';
        }
      }
    }

    function toggleSpeechOutput() {
      voiceReplyEnabled = !voiceReplyEnabled;
      const btn = document.getElementById('speechToggleBtn');
      const icon = document.getElementById('speechToggleIcon');
      const label = document.getElementById('speechToggleLabel');
      if (voiceReplyEnabled) {
        btn.classList.add('active');
        icon.innerText = '🔊';
        label.innerText = 'AI Voice Response: ON';
      } else {
        btn.classList.remove('active');
        icon.innerText = '🔇';
        label.innerText = 'AI Voice Response: OFF';
        if (window.speechSynthesis) window.speechSynthesis.cancel();
      }
    }

    function speakReplyOnPhone(message) {
      if (!voiceReplyEnabled || !window.speechSynthesis || !message) return;
      try {
        window.speechSynthesis.cancel();
        const cleanMsg = message.replace(/\[.*?\]/g, '').replace(/[\*_#`]/g, '').trim();
        if (!cleanMsg) return;
        const utter = new SpeechSynthesisUtterance(cleanMsg);
        utter.rate = 1.05;
        const voices = window.speechSynthesis.getVoices();
        const preferred = voices.find(v => v.lang && (v.lang.includes('hi') || v.lang.includes('IN'))) || voices[0];
        if (preferred) utter.voice = preferred;
        window.speechSynthesis.speak(utter);
      } catch (e) {
        console.warn('Speech synthesis error:', e);
      }
    }

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

      let sessionToken = sessionStorage.getItem('mobile_session_token');
      const headers = { 'Content-Type': 'application/json' };
      if (sessionToken) {
        headers['X-Session-Token'] = sessionToken;
      } else {
        if (!password) {
          alert('Please enter your Remote Password to connect.');
          btn.disabled = false;
          btn.innerHTML = '<span>🚀 Send Command</span>';
          return;
        }
        headers['X-App-Password'] = password;
      }

      try {
        const response = await fetch('/command', {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ text: text })
        });

        const data = await response.json();

        // Store new session token if issued
        if (data.token) {
          sessionStorage.setItem('mobile_session_token', data.token);
        }

        resBox.classList.add('show');
        if (response.ok) {
          resStatus.className = 'response-status ok';
          resStatus.innerText = 'Success (200 OK)';
          resMsg.innerText = data.message || 'Command executed.';
          if (!overrideText) document.getElementById('commandText').value = '';
          speakReplyOnPhone(data.message || 'Command executed.');
        } else {
          if (response.status === 401) {
            sessionStorage.removeItem('mobile_session_token');
          }
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


@app.route("/auth", methods=["POST"])
@limiter.limit("20 per minute")
def post_auth():
    """Authenticate with password and receive a short-lived 1-hour session token."""
    client_ip = request.remote_addr or "unknown"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # CSRF Origin / Referer check
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if origin and not _is_allowed_origin(origin):
        log.warning("[%s] Blocked CSRF auth attempt from IP: %s with origin: %r", now_str, client_ip, origin)
        return jsonify({"status": "error", "message": "Forbidden: Origin not allowed."}), 403

    expected_password = os.getenv("MOBILE_APP_PASSWORD", "").strip()
    if not expected_password:
        log.warning("[%s] Blocked auth from IP %s: MOBILE_APP_PASSWORD is not configured in config/.env", now_str, client_ip)
        return jsonify({"status": "error", "message": "Remote access disabled. Configure MOBILE_APP_PASSWORD."}), 403

    client_password = request.headers.get("X-App-Password", "").strip()
    if not client_password:
        data = request.get_json(silent=True) or {}
        client_password = (data.get("password") or "").strip()

    if not client_password or not hmac.compare_digest(client_password, expected_password):
        log.warning("[%s] Failed auth attempt on /auth from IP: %s", now_str, client_ip)
        return jsonify({"status": "error", "message": "Unauthorized. Invalid password."}), 401

    token = _create_session_token()
    log.info("[%s] Successful auth on /auth from IP: %s; session token issued", now_str, client_ip)
    return jsonify({
        "status": "ok",
        "token": token,
        "expires_in": SESSION_TTL_SECONDS,
        "message": "Authenticated successfully."
    }), 200


@app.route("/command", methods=["POST"])
@limiter.limit("20 per minute")
def post_command():
    """Accept and execute command from remote phone."""
    client_ip = request.remote_addr or "unknown"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. CSRF Origin / Referer check
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if origin and not _is_allowed_origin(origin):
        log.warning("[%s] Blocked CSRF command attempt from IP: %s with origin: %r", now_str, client_ip, origin)
        return jsonify({"status": "error", "message": "Forbidden: Origin not allowed."}), 403

    expected_password = os.getenv("MOBILE_APP_PASSWORD", "").strip()
    if not expected_password:
        log.warning("[%s] Blocked remote command from IP %s: MOBILE_APP_PASSWORD is not configured in config/.env", now_str, client_ip)
        return jsonify({
            "status": "error",
            "message": "Remote access disabled. Please configure MOBILE_APP_PASSWORD in config/.env."
        }), 403

    # 2. Session token / Password Authentication
    token = request.headers.get("X-Session-Token", "").strip()
    new_token = None

    if token:
        if not _validate_session_token(token):
            log.warning("[%s] Failed auth attempt on /command from IP: %s (Invalid or expired session token)", now_str, client_ip)
            return jsonify({
                "status": "error",
                "message": "Unauthorized. Invalid or expired session token."
            }), 401
    else:
        # Initial password authentication: issue session token so subsequent calls do not send raw password
        client_password = request.headers.get("X-App-Password", "").strip()
        if not client_password:
            payload_peek = request.get_json(silent=True) or {}
            client_password = (payload_peek.get("password") or "").strip()

        if client_password and hmac.compare_digest(client_password, expected_password):
            new_token = _create_session_token()
            log.info("[%s] Initial password authenticated on /command from IP: %s; session token issued", now_str, client_ip)
        else:
            log.warning("[%s] Failed auth attempt on /command from IP: %s (No valid session token or password)", now_str, client_ip)
            return jsonify({
                "status": "error",
                "message": "Unauthorized. Valid session token or X-App-Password required."
            }), 401

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()

    if not text:
        return jsonify({"status": "error", "message": "No command text provided."}), 400

    log.info("[%s] Mobile command received from IP %s: %r", now_str, client_ip, text)

    if _command_handler:
        try:
            import inspect
            sig = inspect.signature(_command_handler)
            if len(sig.parameters) == 1:
                result = _command_handler(text)
            else:
                result = _command_handler(text, _root_window)

            response_data = {
                "status": "ok",
                "message": result or f"Executed: {text}"
            }
            if new_token:
                response_data["token"] = new_token

            resp = jsonify(response_data)
            if new_token:
                resp.headers["X-Session-Token"] = new_token

            log.info("[%s] Successful command execution from IP: %s | text: %r", now_str, client_ip, text)
            return resp, 200
        except Exception as exc:
            log.error("[%s] Mobile command execution error from IP: %s: %s", now_str, client_ip, exc)
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
