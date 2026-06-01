#!/usr/bin/env python3
"""
RemoteControl Web Client v4.0
Web-based UI served locally, browser renders the interface
"""

import asyncio
import json
import time
import base64
import io
import os
import sys
import logging
import webbrowser
import threading
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from aiohttp import web

try:
    import mss
except ImportError:
    mss = None
try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
try:
    import pyautogui
except ImportError:
    pyautogui = None
try:
    from pynput.keyboard import Controller, Key
except ImportError:
    Controller = None
    Key = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("webclient")

# =========================================================================
# 内嵌 Web UI (完整 HTML/CSS/JS)
# =========================================================================

WEB_UI = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RemoteControl</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
       background: #0d0d1a; color: #c8c8d4; height:100vh; overflow:hidden; user-select:none; }
::-webkit-scrollbar { width:4px; } ::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:#2a2a4a; border-radius:2px; }

/* Layout */
#app { display:flex; height:100vh; }
#sidebar { width:240px; min-width:240px; background:#16213e; display:flex; flex-direction:column;
           border-right:1px solid #0f3460; }
#main { flex:1; display:flex; flex-direction:column; background:#0d0d1a; position:relative; }
#chatPanel { width:260px; min-width:260px; background:#16213e; border-left:1px solid #0f3460;
             display:none; flex-direction:column; }

/* Sidebar */
.sidebar-inner { padding:16px; overflow-y:auto; flex:1; }
.logo { font-size:16px; font-weight:700; color:#e0e0ff; margin-bottom:16px; display:flex; align-items:center; gap:8px; }
.status-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.section-title { font-size:10px; color:#6a6a8a; text-transform:uppercase; letter-spacing:1.5px;
                 margin:16px 0 8px 0; font-weight:600; }
.input-group { margin-bottom:8px; }
.input-group label { display:block; font-size:11px; color:#8888bb; margin-bottom:4px; }
.input-group input, .input-group select { width:100%; padding:10px 12px; background:#0f3460;
    border:1px solid #1a4a7a; border-radius:6px; color:#e0e0ff; font-size:13px; outline:none;
    transition:border .2s; }
.input-group input:focus { border-color:#4CAF50; }
.input-group input::placeholder { color:#4a6a8a; }

.mode-toggle { display:flex; background:#1a1a35; border-radius:8px; padding:2px; margin:8px 0; }
.mode-toggle button { flex:1; padding:8px; border:none; background:transparent; color:#6a6a8a;
    font-size:13px; cursor:pointer; border-radius:6px; transition:all .2s; font-weight:500; }
.mode-toggle button.active { background:#4CAF50; color:#fff; }

.btn { display:block; width:100%; padding:10px; border:none; border-radius:6px; font-size:13px;
       font-weight:600; cursor:pointer; transition:all .2s; margin-bottom:6px; }
.btn-primary { background:#4CAF50; color:#fff; }
.btn-primary:hover { background:#45a049; }
.btn-primary:disabled { background:#2a3a2a; color:#6a6a8a; cursor:not-allowed; }
.btn-danger { background:#f44336; color:#fff; }
.btn-action { background:#0f3460; color:#c8c8d4; border:1px solid #1a4a7a; }
.btn-action:hover { background:#1a4a7a; color:#fff; }
.btn-sm { padding:6px 12px; font-size:12px; display:inline-block; width:auto; }

.pills { display:flex; gap:4px; margin:8px 0; }
.pills button { flex:1; padding:6px 10px; border:1px solid #2a2a4a; border-radius:14px;
    background:transparent; color:#6a6a8a; font-size:11px; cursor:pointer; transition:all .2s; }
.pills button.active { background:#4CAF50; color:#fff; border-color:#4CAF50; }
.pills button:hover:not(.active) { border-color:#4CAF50; color:#4CAF50; }

.opt-row { display:flex; gap:8px; align-items:center; margin:6px 0; }
.opt-row label { font-size:11px; color:#8888bb; min-width:36px; }
.opt-row input[type=range] { flex:1; accent-color:#4CAF50; }
.opt-row .val { font-size:12px; color:#e0e0ff; min-width:24px; }
.opt-row select, .opt-row input[type=number] { background:#0f3460; border:1px solid #1a4a7a;
    border-radius:4px; color:#e0e0ff; padding:4px 8px; font-size:12px; outline:none; }

/* Main viewer */
#placeholder { display:flex; flex-direction:column; align-items:center; justify-content:center;
    flex:1; color:#333; text-align:center; gap:8px; }
#placeholder h2 { font-size:22px; color:#444; }
#placeholder p { font-size:13px; color:#555; line-height:1.8; }
#screenCanvas { display:none; flex:1; cursor:crosshair; background:#0d0d1a; }

/* Floating toolbar */
#toolbar { display:none; position:absolute; bottom:12px; left:50%; transform:translateX(-50%);
    background:rgba(22,33,62,0.92); backdrop-filter:blur(8px); border-radius:10px;
    padding:4px 8px; align-items:center; gap:2px; z-index:100; }
#toolbar button { background:transparent; border:none; color:#c8c8d4; padding:6px 8px;
    border-radius:4px; cursor:pointer; font-size:16px; transition:background .2s; }
#toolbar button:hover { background:rgba(76,175,80,0.2); }
#toolbar .sep { width:1px; height:20px; background:#2a2a4a; margin:0 6px; }
#toolbar .info { font-size:11px; color:#6a6a8a; padding:0 8px; }

/* Chat */
#chatMessages { flex:1; overflow-y:auto; padding:10px; font-size:12px; }
.chat-msg { margin-bottom:6px; }
.chat-msg .name { font-weight:600; }
.chat-input-row { display:flex; padding:8px; gap:6px; border-top:1px solid #0f3460; }
.chat-input-row input { flex:1; padding:8px 10px; background:#0f3460; border:1px solid #1a4a7a;
    border-radius:6px; color:#e0e0ff; font-size:12px; outline:none; }
.chat-input-row button { padding:8px 14px; background:#4CAF50; border:none; border-radius:6px;
    color:#fff; font-size:12px; cursor:pointer; }

/* Toggle switch */
.toggle-wrap { display:flex; align-items:center; gap:6px; margin:4px 0; font-size:12px; cursor:pointer; }
.toggle { width:36px; height:20px; background:#2a2a4a; border-radius:10px; position:relative;
    transition:background .2s; cursor:pointer; flex-shrink:0; }
.toggle.active { background:#4CAF50; }
.toggle .knob { width:16px; height:16px; background:#fff; border-radius:50%; position:absolute;
    top:2px; left:2px; transition:all .2s; }
.toggle.active .knob { left:18px; }

/* notifications */
.notif { position:fixed; top:16px; right:16px; background:#1a1a35; border:1px solid #0f3460;
    border-radius:8px; padding:12px 20px; color:#e0e0ff; font-size:13px; z-index:999;
    animation: slideIn .3s; max-width:300px; }
@keyframes slideIn { from { transform:translateX(100%); opacity:0; } to { transform:translateX(0); opacity:1; } }
</style>
</head>
<body>
<div id="app">
  <!-- Sidebar -->
  <div id="sidebar">
    <div class="sidebar-inner">
      <div class="logo"><span class="status-dot" id="statusDot" style="background:#666"></span>RemoteControl</div>

      <div class="section-title">连接</div>
      <div class="input-group">
        <label>服务器地址</label>
        <input id="serverInput" value="ws://47.92.148.99:8500">
      </div>
      <div class="input-group">
        <label>房间名</label>
        <input id="roomInput" value="default" placeholder="两端一致">
      </div>
      <div class="input-group">
        <label>密码</label>
        <input id="pwdInput" type="password" placeholder="可选">
      </div>

      <div class="mode-toggle" id="modeToggle">
        <button id="modeViewer" class="active">👁 主控</button>
        <button id="modeHost">🖥 被控</button>
      </div>

      <button class="btn btn-primary" id="connectBtn">📡 连接</button>

      <div class="section-title">被控端设置</div>
      <div class="pills" id="presetPills">
        <button data-json='{"q":20,"f":5,"s":25}'>流畅</button>
        <button data-json='{"q":45,"f":12,"s":50}' class="active">均衡</button>
        <button data-json='{"q":75,"f":22,"s":80}'>高清</button>
      </div>

      <div class="opt-row"><label>画质</label><input type="range" min="10" max="95" value="45" id="qualitySlider"><span class="val" id="qualityVal">45</span></div>
      <div class="opt-row"><label>帧率</label><input type="number" value="12" min="1" max="30" id="fpsInput" style="width:50px">
        <label style="margin-left:8px">缩放</label>
        <select id="scaleSelect"><option>25%</option><option selected>50%</option><option>75%</option><option>100%</option></select>
      </div>
      <div class="opt-row">
        <label>显示器</label><input type="number" value="1" min="1" max="4" style="width:50px">
        <div class="toggle-wrap" style="margin-left:auto"><span>隐私屏</span><div class="toggle" id="privacyToggle"><div class="knob"></div></div></div>
      </div>

      <div class="section-title" style="margin-top:12px">主控端设置</div>
      <div class="opt-row"><label>缩放</label>
        <select id="scaleMode" style="flex:1"><option>等比</option><option>拉伸</option><option>原始</option><option>适应宽度</option></select>
      </div>
      <button class="btn btn-action btn-sm" id="fullscreenBtn" style="width:auto">⛶ 全屏</button>
      <div id="viewerInfo" style="font-size:11px;color:#6a6a8a;margin-top:4px">等待连接...</div>

      <div class="section-title" style="margin-top:12px">工具</div>
      <button class="btn btn-action btn-sm" id="fileBtn">📁 传文件</button>
      <button class="btn btn-action btn-sm" id="chatBtn">💬 聊天</button>

      <div style="text-align:center;margin-top:auto;padding-top:16px;font-size:10px;color:#4a4a6a">v4.0.0</div>
    </div>
  </div>

  <!-- Main -->
  <div id="main">
    <div id="placeholder">
      <h2>🔗 RemoteControl</h2>
      <p>选择模式 → 输入房间名 → 点击连接<br>
      🖥 被控：共享本机 &nbsp; 👁 主控：查看远程</p>
    </div>
    <canvas id="screenCanvas"></canvas>
    <div id="toolbar">
      <button title="全屏" id="tbFullscreen">⛶</button>
      <button title="传文件" id="tbFile">📁</button>
      <button title="聊天" id="tbChat">💬</button>
      <button title="刷新" id="tbRefresh">🔄</button>
      <div class="sep"></div>
      <span class="info" id="tbQuality"></span>
      <span class="info" id="tbFps"></span>
      <div class="sep"></div>
      <button title="断开" id="tbDisconnect" style="color:#f44336">✕</button>
    </div>
  </div>

  <!-- Chat -->
  <div id="chatPanel">
    <div style="padding:12px 14px;font-size:14px;font-weight:600;color:#e0e0ff;border-bottom:1px solid #0f3460">💬 聊天</div>
    <div id="chatMessages"></div>
    <div class="chat-input-row">
      <input id="chatInput" placeholder="输入消息..." autocomplete="off">
      <button id="chatSend">发送</button>
    </div>
  </div>
</div>

<script>
// ============== State ==============
const state = {
  connected: false,
  role: 'viewer',
  ws: null,
  localWs: null,
  canvas: document.getElementById('screenCanvas'),
  ctx: document.getElementById('screenCanvas').getContext('2d'),
  remoteW: 1920, remoteH: 1080,
  frameCount: 0,
  fpsTime: Date.now(),
  currentFps: 0,
  lastMouseSend: 0,
  fileBuffers: {},
  chatVisible: false,
  fullscreen: false,
};

// ============== WebSocket to Local Backend ==============
function connectLocal() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${window.location.host}/ws`;
  state.localWs = new WebSocket(url);
  state.localWs.onopen = () => { notify('本地已连接'); };
  state.localWs.onmessage = e => {
    try { handleLocalMsg(JSON.parse(e.data)); } catch(_) {}
  };
  state.localWs.onclose = () => setTimeout(connectLocal, 2000);
}

function sendLocal(msg) {
  if (state.localWs && state.localWs.readyState === WebSocket.OPEN) {
    state.localWs.send(JSON.stringify(msg));
  }
}

function handleLocalMsg(msg) {
  switch (msg.type) {
    case 'frame':
      const b64 = msg.data;
      const img = new Image();
      img.onload = () => { drawFrame(img); };
      img.src = 'data:image/jpeg;base64,' + b64;
      break;
    case 'connected':
      setConnected(true);
      break;
    case 'disconnected':
      setConnected(false);
      break;
    case 'chat':
      addChat(msg.name || '未知', msg.text || '');
      break;
    case 'notify':
      notify(msg.text);
      break;
  }
}

// ============== Canvas Rendering ==============
function drawFrame(img) {
  const c = state.canvas;
  const mode = document.getElementById('scaleMode').value;
  const parent = c.parentElement;
  const pw = parent.clientWidth, ph = parent.clientHeight;

  state.remoteW = img.naturalWidth;
  state.remoteH = img.naturalHeight;

  let dw, dh;
  if (mode === '原始') { dw = img.naturalWidth; dh = img.naturalHeight; }
  else if (mode === '拉伸') { dw = pw; dh = ph; }
  else if (mode === '适应宽度') { dw = pw; dh = img.naturalHeight * pw / img.naturalWidth; }
  else { // 等比
    const r = Math.min(pw / img.naturalWidth, ph / img.naturalHeight);
    dw = img.naturalWidth * r; dh = img.naturalHeight * r;
  }

  c.width = pw; c.height = ph;
  const ctx = state.ctx;
  ctx.fillStyle = '#0d0d1a'; ctx.fillRect(0, 0, pw, ph);
  const ox = (pw - dw) / 2, oy = (ph - dh) / 2;
  ctx.drawImage(img, ox, oy, dw, dh);

  state.frameCount++;
  const now = Date.now();
  if (now - state.fpsTime > 2000) {
    state.currentFps = state.frameCount / ((now - state.fpsTime) / 1000);
    state.fpsTime = now;
    state.frameCount = 0;
    document.getElementById('tbFps').textContent = `${Math.round(state.currentFps)}fps`;
    document.getElementById('viewerInfo').textContent =
      `${img.naturalWidth}×${img.naturalHeight} | ${Math.round(state.currentFps)}fps | ${Math.round(dw)}×${Math.round(dh)}`;
  }
}

// ============== Connection ==============
function setConnected(v) {
  state.connected = v;
  const dot = document.getElementById('statusDot');
  const btn = document.getElementById('connectBtn');
  dot.style.background = v ? '#4CAF50' : '#f44336';
  btn.textContent = v ? '🔴 断开' : '📡 连接';
  btn.classList.toggle('btn-primary', !v);
  btn.classList.toggle('btn-danger', v);
  if (v) {
    state.canvas.style.display = 'block';
    document.getElementById('placeholder').style.display = 'none';
    document.getElementById('toolbar').style.display = 'flex';
  } else {
    state.canvas.style.display = 'none';
    document.getElementById('placeholder').style.display = 'flex';
    document.getElementById('toolbar').style.display = 'none';
  }
}

function toggleConnection() {
  if (state.connected) {
    sendLocal({type: 'disconnect'});
    return;
  }
  const server = document.getElementById('serverInput').value.trim();
  const room = document.getElementById('roomInput').value.trim();
  const pwd = document.getElementById('pwdInput').value;
  const role = document.getElementById('modeHost').classList.contains('active') ? 'host' : 'viewer';
  if (!server || !room) return notify('请输入服务器和房间名');
  state.role = role;
  sendLocal({type: 'connect', server, room, password: pwd, role});
  notify(`正在连接 ${room}...`);
}

// ============== Mouse / Keyboard ==============
state.canvas.addEventListener('mousedown', e => {
  if (!state.connected || state.role !== 'viewer') return;
  const {x,y} = canvasToRemote(e);
  sendLocal({type:'input', event:'click', data:{x,y,button:['left','middle','right'][e.button]||'left'}});
});
state.canvas.addEventListener('mousemove', e => {
  if (!state.connected || state.role !== 'viewer') return;
  const now = Date.now();
  if (now - state.lastMouseSend < 50) return;
  state.lastMouseSend = now;
  const {x,y} = canvasToRemote(e);
  sendLocal({type:'input', event:'mousemove', data:{x,y}});
});
state.canvas.addEventListener('wheel', e => {
  if (!state.connected || state.role !== 'viewer') return;
  const {x,y} = canvasToRemote(e);
  sendLocal({type:'input', event:'scroll', data:{x,y,amount:Math.sign(e.deltaY)}});
  e.preventDefault();
}, {passive:false});
document.addEventListener('keydown', e => {
  if (!state.connected || state.role !== 'viewer') return;
  if (e.ctrlKey && e.altKey) {
    if (e.key === 'q' || e.key === 'Q') { toggleFullscreen(); return; }
    if (e.key === 'x' || e.key === 'X') { toggleConnection(); return; }
  }
  const key = mapKey(e.key);
  if (key) sendLocal({type:'input', event:'keypress', data:{key}});
});

function canvasToRemote(e) {
  const rect = state.canvas.getBoundingClientRect();
  const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
  // Map through the displayed image area
  const mode = document.getElementById('scaleMode').value;
  const pw = rect.width, ph = rect.height;
  let dw = state.remoteW, dh = state.remoteH;
  if (mode === '等比') {
    const r = Math.min(pw/dw, ph/dh);
    dw *= r; dh *= r;
  } else if (mode === '原始') { /* no scale */ }
  else if (mode === '适应宽度') { dh = state.remoteH * pw / state.remoteW; dw = pw; }
  else { dw = pw; dh = ph; }
  const ox = (pw - dw) / 2, oy = (ph - dh) / 2;
  const rx = Math.round((cx - ox) / dw * state.remoteW);
  const ry = Math.round((cy - oy) / dh * state.remoteH);
  return {x: Math.max(0,rx), y: Math.max(0,ry)};
}

function mapKey(key) {
  const m = {'Enter':'enter','Tab':'tab','Escape':'escape','Backspace':'backspace',
    'ArrowUp':'up','ArrowDown':'down','ArrowLeft':'left','ArrowRight':'right',
    'Delete':'delete','Home':'home','End':'end','PageUp':'pageup','PageDown':'pagedown',
    'Control':'ctrl','Alt':'alt','Shift':'shift','CapsLock':'capslock',' ':'space'};
  return m[key] || (key.length === 1 ? key : '');
}

// ============== UI Events ==============
document.getElementById('connectBtn').addEventListener('click', toggleConnection);
document.getElementById('modeViewer').addEventListener('click', () => setMode('viewer'));
document.getElementById('modeHost').addEventListener('click', () => setMode('host'));

function setMode(m) {
  document.querySelectorAll('#modeToggle button').forEach(b => b.classList.remove('active'));
  document.getElementById(m === 'viewer' ? 'modeViewer' : 'modeHost').classList.add('active');
  if (state.connected && state.role !== m) toggleConnection();
}

// Presets
document.querySelectorAll('#presetPills button').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('#presetPills button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    const d = JSON.parse(b.dataset.json);
    document.getElementById('qualitySlider').value = d.q;
    document.getElementById('qualityVal').textContent = d.q;
    document.getElementById('fpsInput').value = d.f;
    document.getElementById('scaleSelect').value = d.s + '%';
  });
});

document.getElementById('qualitySlider').addEventListener('input', e => {
  document.getElementById('qualityVal').textContent = e.target.value;
  document.querySelectorAll('#presetPills button').forEach(x => x.classList.remove('active'));
});

// Quality slider from host to local
function syncHostSettings() {
  if (state.role !== 'host') return;
  const q = parseInt(document.getElementById('qualitySlider').value);
  const f = parseInt(document.getElementById('fpsInput').value);
  const s = parseInt(document.getElementById('scaleSelect').value);
  const m = parseInt(document.querySelector('#sidebar input[type=number]').value) || 1;
  const p = document.getElementById('privacyToggle').classList.contains('active');
  sendLocal({type:'host_settings', quality:q, fps:f, scale:s/100, monitor:m, privacy:p});
}
document.getElementById('qualitySlider').addEventListener('change', syncHostSettings);
document.getElementById('fpsInput').addEventListener('change', syncHostSettings);
document.getElementById('scaleSelect').addEventListener('change', syncHostSettings);

// Privacy toggle
document.getElementById('privacyToggle').addEventListener('click', () => {
  document.getElementById('privacyToggle').classList.toggle('active');
  syncHostSettings();
});

// Fullscreen
document.getElementById('fullscreenBtn').addEventListener('click', toggleFullscreen);
document.getElementById('tbFullscreen').addEventListener('click', toggleFullscreen);
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.getElementById('main').requestFullscreen();
    document.getElementById('fullscreenBtn').textContent = '✕ 退出全屏';
    document.getElementById('toolbar').style.display = 'none';
  } else {
    document.exitFullscreen();
    document.getElementById('fullscreenBtn').textContent = '⛶ 全屏';
    if (state.connected) document.getElementById('toolbar').style.display = 'flex';
  }
}

// Chat
document.getElementById('chatBtn').addEventListener('click', () => toggleChat());
document.getElementById('tbChat').addEventListener('click', () => toggleChat());
document.getElementById('chatSend').addEventListener('click', sendChat);
document.getElementById('chatInput').addEventListener('keydown', e => { if (e.key === 'Enter') sendChat(); });

function toggleChat() {
  state.chatVisible = !state.chatVisible;
  document.getElementById('chatPanel').style.display = state.chatVisible ? 'flex' : 'none';
  document.getElementById('chatBtn').textContent = state.chatVisible ? '✕ 聊天' : '💬 聊天';
}

function sendChat() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text || !state.connected) return;
  const target = state.role === 'viewer' ? 'host' : 'all';
  sendLocal({type:'chat', text, target});
  addChat('我', text);
  input.value = '';
}

function addChat(name, text) {
  const msgs = document.getElementById('chatMessages');
  const d = document.createElement('div');
  d.className = 'chat-msg';
  const color = name === '我' ? '#4CAF50' : '#2196F3';
  d.innerHTML = `<span class="name" style="color:${color}">${name}:</span> ${escapeHtml(text)}`;
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
}

function escapeHtml(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// File
document.getElementById('fileBtn').addEventListener('click', () => {
  if (!state.connected) return notify('请先连接');
  sendLocal({type:'pick_file'});
});
document.getElementById('tbFile').addEventListener('click', () => document.getElementById('fileBtn').click());

// Toolbar buttons
document.getElementById('tbDisconnect').addEventListener('click', toggleConnection);
document.getElementById('tbRefresh').addEventListener('click', () => {
  if (state.connected) notify('已刷新');
});

// Notifications
function notify(text) {
  const n = document.createElement('div');
  n.className = 'notif'; n.textContent = text;
  document.body.appendChild(n);
  setTimeout(() => { n.style.opacity='0'; n.style.transition='opacity .3s'; setTimeout(() => n.remove(),300); }, 3000);
}

// Init
connectLocal();

// Canvas resize handler
window.addEventListener('resize', () => {
  if (state.connected) {
    state.canvas.style.display = 'none';
    state.canvas.style.display = 'block';
  }
});
</script>
</body>
</html>
"""

# =========================================================================
# Python Backend
# =========================================================================

class ClientBackend:
    """Python backend: Web UI server + native screen capture + input simulation"""

    def __init__(self):
        self.relay_ws = None
        self.role = "viewer"
        self.connected = False
        self._host_quality = 45
        self._host_fps = 12
        self._host_scale = 0.5
        self._host_monitor = 1
        self._privacy = False
        self._running = True
        self._capture_task = None
        self._browser_ws = set()

    # ---------- aiohttp server ----------

    async def start(self, port: int = 8887):
        app = web.Application()
        app.router.add_get("/", self._serve_html)
        app.router.add_get("/ws", self._browser_ws_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        log.info(f"Web UI: http://127.0.0.1:{port}")
        webbrowser.open(f"http://127.0.0.1:{port}")

        # Keep running
        while self._running:
            await asyncio.sleep(1)

    def stop(self):
        self._running = False
        self._disconnect_relay()

    async def _serve_html(self, request):
        return web.Response(text=WEB_UI, content_type="text/html")

    # ---------- Browser WebSocket ----------

    async def _browser_ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._browser_ws.add(ws)
        log.info("浏览器已连接")

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._handle_browser_msg(data, ws)
                except Exception as e:
                    log.error(f"浏览器消息错误: {e}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break

        self._browser_ws.discard(ws)
        if not self._browser_ws:
            self._disconnect_relay()
        log.info("浏览器断开")

        return ws

    async def _send_browser(self, data: dict):
        """发送消息到所有浏览器"""
        for ws in list(self._browser_ws):
            try:
                await ws.send_json(data)
            except:
                self._browser_ws.discard(ws)

    async def _handle_browser_msg(self, msg: dict, ws):
        """处理来自浏览器的消息"""
        t = msg.get("type")

        if t == "connect":
            self.role = msg.get("role", "viewer")
            asyncio.ensure_future(self._connect_relay(
                msg.get("server"), msg.get("room"),
                msg.get("password", ""), msg.get("role"),
            ))

        elif t == "disconnect":
            self._disconnect_relay()
            await self._send_browser({"type": "disconnected"})

        elif t == "input":
            # Forward to relay server -> host
            if self.relay_ws and self.connected and self.role == "viewer":
                await self.relay_ws.send_json({
                    "type": "input",
                    "event": msg.get("event"),
                    "data": msg.get("data"),
                })

        elif t == "chat":
            if self.relay_ws and self.connected:
                await self.relay_ws.send_json({
                    "type": "chat",
                    "text": msg.get("text", ""),
                    "target": msg.get("target", "all"),
                })

        elif t == "host_settings":
            self._host_quality = msg.get("quality", 45)
            self._host_fps = msg.get("fps", 12)
            self._host_scale = msg.get("scale", 0.5)
            self._host_monitor = msg.get("monitor", 1)
            self._privacy = msg.get("privacy", False)

        elif t == "pick_file":
            # Can't open file dialog from async context easily
            await self._send_browser({"type": "notify", "text": "文件传输: 请在 Python 端实现"})

    # ---------- Relay WebSocket ----------

    async def _connect_relay(self, server: str, room: str, password: str, role: str):
        """连接到中继服务器"""
        self._disconnect_relay()
        try:
            async with aiohttp.ClientSession() as session:
                # Convert ws:// to http:// for aiohttp
                url = server.replace("ws://", "http://").replace("wss://", "https://")
                async with session.ws_connect(url, autoclose=False, autoping=True) as ws:
                    self.relay_ws = ws
                    self.connected = True
                    await self._send_browser({"type": "connected"})

                    # Register
                    reg = {"type": "register", "role": role, "room": room}
                    if password:
                        reg["password"] = password
                    await ws.send_json(reg)

                    # Start capture if host
                    if role == "host":
                        self._capture_task = asyncio.ensure_future(self._capture_loop())

                    # Message loop
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                await self._handle_relay_msg(data)
                            except:
                                pass
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            break

        except Exception as e:
            log.error(f"中继连接失败: {e}")
            await self._send_browser({"type": "notify", "text": f"连接失败: {e}"})

        self.connected = False
        if self._capture_task:
            self._capture_task.cancel()
            self._capture_task = None
        self.relay_ws = None
        await self._send_browser({"type": "disconnected"})

    def _disconnect_relay(self):
        if self.relay_ws:
            asyncio.ensure_future(self.relay_ws.close())
            self.relay_ws = None
        self.connected = False
        if self._capture_task:
            self._capture_task.cancel()
            self._capture_task = None

    async def _handle_relay_msg(self, msg: dict):
        t = msg.get("type")

        if t == "frame":
            # Forward to browser
            await self._send_browser({
                "type": "frame",
                "data": msg.get("data"),
                "timestamp": msg.get("timestamp"),
            })

        elif t == "chat":
            await self._send_browser({
                "type": "chat",
                "text": msg.get("text"),
                "name": msg.get("name", "远程"),
            })

        elif t == "input":
            # Remote input on this machine (we are host)
            event = msg.get("event")
            data = msg.get("data", {})
            self._handle_input(event, data)

        elif t == "clipboard":
            text = msg.get("text", "")
            if text:
                try:
                    import pyperclip
                    pyperclip.copy(text)
                except:
                    pass

        elif t == "error":
            await self._send_browser({"type": "notify", "text": f"错误: {msg.get('msg')}"})

        elif t == "host_left":
            await self._send_browser({"type": "notify", "text": "主机已断开"})
            self._disconnect_relay()

    # ---------- Screen Capture (Host mode) ----------

    async def _capture_loop(self):
        """定时捕获屏幕并发送到中继"""
        if not mss or not Image:
            log.error("缺少 mss/Pillow")
            return

        while self.connected:
            try:
                start = time.time()
                interval = 1.0 / max(self._host_fps, 1)

                if self._privacy:
                    pil = Image.new("RGB", (640, 360), (20, 20, 30))
                else:
                    with mss.mss() as sct:
                        mon = sct.monitors[min(self._host_monitor, len(sct.monitors) - 1)]
                        img = sct.grab(mon)
                        pil = Image.frombytes("RGB", img.size, img.rgb)
                        if self._host_scale < 1.0:
                            w, h = pil.size
                            pil = pil.resize((int(w * self._host_scale), int(h * self._host_scale)),
                                            Image.LANCZOS)

                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=self._host_quality, optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode()

                if self.relay_ws and self.connected:
                    await self.relay_ws.send_json({
                        "type": "frame", "data": b64,
                        "timestamp": int(time.time() * 1000),
                    })

                elapsed = time.time() - start
                await asyncio.sleep(max(0, interval - elapsed))

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"捕获错误: {e}")
                await asyncio.sleep(1)

    # ---------- Input Simulation (Host mode) ----------

    def _handle_input(self, event: str, data: dict):
        if not pyautogui:
            return
        try:
            if event == "click":
                pyautogui.click(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "mousemove":
                pyautogui.moveTo(data["x"], data["y"])
            elif event == "mousedown":
                pyautogui.mouseDown(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "mouseup":
                pyautogui.mouseUp(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "scroll":
                pyautogui.scroll(data.get("amount", 1), x=data["x"], y=data["y"])
            elif event == "keypress" and Controller:
                kb = Controller()
                key = data.get("key", "")
                special = {"enter":Key.enter, "return":Key.enter, "tab":Key.tab,
                    "escape":Key.esc, "esc":Key.esc, "backspace":Key.backspace,
                    "space":Key.space, "ctrl":Key.ctrl, "alt":Key.alt, "shift":Key.shift,
                    "up":Key.up, "down":Key.down, "left":Key.left, "right":Key.right,
                    "delete":Key.delete, "home":Key.home, "end":Key.end,
                    "pageup":Key.page_up, "pagedown":Key.page_down}
                if len(key) == 1:
                    kb.press(key); kb.release(key)
                elif key.lower() in special:
                    kb.press(special[key.lower()]); kb.release(special[key.lower()])
        except Exception as e:
            log.error(f"输入处理: {e}")


# =========================================================================
# Main
# =========================================================================

def main():
    port = 8887

    backend = ClientBackend()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(backend.start(port))
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()
        loop.close()

    print("客户端已退出")


if __name__ == "__main__":
    main()
