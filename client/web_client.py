#!/usr/bin/env python3
"""
RemoteControl Web Client v4.0
ToDesk-inspired web UI, served locally, rendered in browser.
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

import aiohttp
from aiohttp import web

try: import mss
except: mss = None
try: from PIL import Image, ImageDraw
except: Image = None
try: import pyautogui
except: pyautogui = None
try: from pynput.keyboard import Controller, Key
except: Controller = Key = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rc")

# =====================================================================
# HTML/CSS/JS - ToDesk Inspired
# =====================================================================

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>RemoteControl</title>
<style>
:root {
  --primary:#0070F9; --primary-hover:#0058d0;
  --bg:#1c1c1e; --bg2:#2c2c2e; --sidebar:#262628;
  --text:#f0f0f0; --text2:#98989e; --text3:#666670;
  --border:#38383a; --success:#36BA78; --danger:#ff3b30;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font:-apple-system,"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;overflow:hidden}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

#app{display:flex;height:100vh}
#sidebar{width:220px;min-width:220px;background:var(--sidebar);display:flex;flex-direction:column;border-right:1px solid var(--border)}
#main{flex:1;display:flex;flex-direction:column;background:var(--bg);position:relative}
#chatPanel{width:250px;background:var(--sidebar);border-left:1px solid var(--border);display:none;flex-direction:column}

.sidebar-inner{padding:12px;overflow-y:auto;flex:1}
.logo{font-size:14px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.logo .dot{width:7px;height:7px;border-radius:50%;background:var(--text3)}
.s-label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.8px;margin:12px 0 5px;font-weight:600}
.inp{margin-bottom:4px}
.inp input,.inp select{width:100%;padding:7px 9px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:12px;outline:none}
.inp input:focus{border-color:var(--primary)}
.inp input::placeholder{color:var(--text3)}

.mt{display:flex;background:var(--bg);border-radius:5px;padding:2px;margin:6px 0}
.mt button{flex:1;padding:5px;border:none;background:transparent;color:var(--text2);font-size:11px;cursor:pointer;border-radius:4px;transition:.15s;font-weight:500}
.mt button.active{background:var(--primary);color:#fff}

.btn{width:100%;padding:7px;border:none;border-radius:5px;font-size:12px;font-weight:600;cursor:pointer;transition:.15s;margin-bottom:4px}
.btn-primary{background:var(--primary);color:#fff}
.btn-primary:hover{background:var(--primary-hover)}
.btn-danger{background:var(--danger);color:#fff}
.btn-plain{background:var(--bg);color:var(--text2);border:1px solid var(--border)}
.btn-plain:hover{background:var(--border);color:var(--text)}
.btn-sm{padding:4px 10px;width:auto;display:inline-flex;align-items:center;gap:3px;font-size:11px}

.pills{display:flex;gap:3px;margin:6px 0}
.pills button{flex:1;padding:3px 8px;border:1px solid var(--border);border-radius:10px;background:transparent;color:var(--text2);font-size:10px;cursor:pointer;transition:.15s}
.pills button.active{background:var(--primary);color:#fff;border-color:var(--primary)}

.or{display:flex;gap:5px;align-items:center;margin:3px 0}
.or label{font-size:10px;color:var(--text2);min-width:28px}
.or input[type=range]{flex:1;accent-color:var(--primary);height:2px}
.or .v{font-size:10px;color:var(--text);min-width:18px;text-align:right}
.or select,.or input[type=number]{background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:2px 5px;font-size:11px;outline:none}

#placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;gap:6px;color:var(--text3)}
#screenCanvas{display:none;flex:1;cursor:crosshair}

#toolbar{display:none;position:absolute;top:10px;left:50%;transform:translateX(-50%);
  background:rgba(38,38,40,0.92);backdrop-filter:blur(8px);border:1px solid var(--border);
  border-radius:8px;padding:3px 6px;align-items:center;gap:1px;z-index:100}
#toolbar button{background:transparent;border:none;color:var(--text2);padding:5px 7px;border-radius:4px;cursor:pointer;font-size:14px;transition:.15s}
#toolbar button:hover{background:var(--bg2);color:var(--text)}
#toolbar .s{width:1px;height:16px;background:var(--border);margin:0 4px}
#toolbar .i{font-size:10px;color:var(--text3);padding:0 6px}

#chatMessages{flex:1;overflow-y:auto;padding:8px;font-size:12px}
.cm{margin-bottom:5px;line-height:1.4}
.cm .n{font-weight:600}
.cr{display:flex;padding:6px;gap:4px;border-top:1px solid var(--border)}
.cr input{flex:1;padding:6px 8px;background:var(--bg);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:11px;outline:none}
.cr button{padding:6px 12px;background:var(--primary);border:none;border-radius:5px;color:#fff;font-size:11px;cursor:pointer}

.notif{position:fixed;top:14px;right:14px;background:var(--sidebar);border:1px solid var(--border);border-radius:6px;padding:10px 16px;color:var(--text);font-size:12px;z-index:999;max-width:280px;box-shadow:0 4px 20px rgba(0,0,0,.4)}
</style>
</head>
<body>
<div id="app">
  <!-- Sidebar -->
  <div id="sidebar">
    <div class="sidebar-inner">
      <div class="logo"><span class="dot" id="statusDot"></span>RemoteControl</div>

      <div class="s-label">连接</div>
      <div class="inp"><input id="serverInput" value="ws://47.92.148.99:8500"></div>
      <div class="inp"><input id="roomInput" value="default" placeholder="房间号"></div>
      <div class="inp"><input id="pwdInput" type="password" placeholder="密码(可选)"></div>

      <div class="mt" id="modeToggle">
        <button id="modeViewer" class="active">👁 主控</button>
        <button id="modeHost">🖥 被控</button>
      </div>
      <button class="btn btn-primary" id="connectBtn">📡 连接</button>

      <div class="s-label">画质</div>
      <div class="pills" id="presetPills">
        <button data-q="20" data-f="5" data-s="25">流畅</button>
        <button data-q="45" data-f="12" data-s="50" class="active">均衡</button>
        <button data-q="75" data-f="22" data-s="80">高清</button>
      </div>
      <div class="or">
        <label>画质</label><input type="range" min="10" max="95" value="45" id="qualitySlider"><span class="v" id="qualityVal">45</span>
      </div>
      <div class="or">
        <label>帧率</label><input type="number" value="12" min="1" max="30" id="fpsInput" style="width:44px">
        <label style="margin-left:4px">缩放</label>
        <select id="scaleSelect"><option>25%</option><option selected>50%</option><option>75%</option><option>100%</option></select>
      </div>
      <div class="or">
        <label>显示器</label><input type="number" value="1" min="1" max="4" id="monitorInput" style="width:40px">
        <span style="font-size:10px;color:var(--text3);margin-left:auto;cursor:pointer" id="privacyToggle">🛡 隐私</span>
      </div>

      <div class="s-label">显示</div>
      <div class="or">
        <label>缩放</label>
        <select id="scaleMode" style="flex:1"><option>等比</option><option>拉伸</option><option>原始</option><option>适应宽度</option></select>
      </div>
      <div id="viewerInfo" style="font-size:10px;color:var(--text3);margin-top:3px">--</div>

      <div class="s-label">工具</div>
      <div style="display:flex;gap:4px">
        <button class="btn btn-plain btn-sm" id="fileBtn" style="flex:1">📁 文件</button>
        <button class="btn btn-plain btn-sm" id="chatBtn" style="flex:1">💬 聊天</button>
      </div>
      <div style="text-align:center;margin-top:10px;font-size:9px;color:var(--text3)">v4.0.2</div>
    </div>
  </div>

  <!-- Main -->
  <div id="main">
    <div id="placeholder">
      <div style="font-size:32px;margin-bottom:8px">🔗</div>
      <div style="font-size:16px;font-weight:600;color:var(--text2)">RemoteControl</div>
      <div style="font-size:11px;color:var(--text3);margin-top:6px;line-height:1.8">
        输入房间号 → 连接<br>
        👁 主控 &nbsp; 🖥 被控
      </div>
    </div>
    <canvas id="screenCanvas"></canvas>
    <div id="toolbar">
      <button title="全屏" id="tbFullscreen">⛶</button>
      <button title="文件" id="tbFile">📁</button>
      <button title="聊天" id="tbChat">💬</button>
      <span class="s"></span>
      <span class="i" id="tbQuality"></span>
      <span class="i" id="tbFps"></span>
      <span class="s"></span>
      <button title="断开" id="tbDisconnect" style="color:var(--danger)">✕</button>
    </div>
  </div>

  <!-- Chat -->
  <div id="chatPanel">
    <div style="padding:10px 12px;font-size:13px;font-weight:600;border-bottom:1px solid var(--border)">💬 聊天</div>
    <div id="chatMessages"></div>
    <div class="cr">
      <input id="chatInput" placeholder="输入..." autocomplete="off">
      <button id="chatSend">发送</button>
    </div>
  </div>
</div>

<script>
const state={connected:false,role:'viewer',ws:null,canvas:document.getElementById('screenCanvas'),
  ctx:document.getElementById('screenCanvas').getContext('2d'),remoteW:1920,remoteH:1080,
  fc:0,fts:Date.now(),fps:0,lms:0,chatVisible:false};

function connectLocal(){
  const p=location.protocol==='https:'?'wss:':'ws:';
  state.ws=new WebSocket(p+'//'+location.host+'/ws');
  state.ws.onopen=()=>notify('已连接');
  state.ws.onmessage=e=>{try{handleMsg(JSON.parse(e.data))}catch(_){}};
  state.ws.onclose=()=>setTimeout(connectLocal,2000);
}

function send(m){state.ws&&state.ws.readyState===WebSocket.OPEN&&state.ws.send(JSON.stringify(m))}

function handleMsg(m){
  switch(m.type){
    case 'frame':
      const i=new Image();
      i.onload=()=>draw(i);
      i.src='data:image/jpeg;base64,'+m.data;
      break;
    case 'connected':setConnected(true);break;
    case 'disconnected':setConnected(false);break;
    case 'chat':addChat(m.name||'?',m.text||'');break;
    case 'notify':notify(m.text);break;
  }
}

function draw(img){
  const c=state.canvas,mode=document.getElementById('scaleMode').value;
  const pw=c.parentElement.clientWidth,ph=c.parentElement.clientHeight;
  state.remoteW=img.naturalWidth;state.remoteH=img.naturalHeight;
  let dw,dh;
  if(mode==='原始'){dw=img.naturalWidth;dh=img.naturalHeight}
  else if(mode==='拉伸'){dw=pw;dh=ph}
  else if(mode==='适应宽度'){dw=pw;dh=img.naturalHeight*pw/img.naturalWidth}
  else{const r=Math.min(pw/img.naturalWidth,ph/img.naturalHeight);dw=img.naturalWidth*r;dh=img.naturalHeight*r}
  c.width=pw;c.height=ph;
  const ctx=state.ctx;
  ctx.fillStyle='#1c1c1e';ctx.fillRect(0,0,pw,ph);
  ctx.drawImage(img,(pw-dw)/2,(ph-dh)/2,dw,dh);
  state.fc++;
  const n=Date.now();
  if(n-state.fts>2000){state.fps=state.fc/((n-state.fts)/1000);state.fts=n;state.fc=0;
    document.getElementById('tbFps').textContent=Math.round(state.fps)+'fps';
    document.getElementById('viewerInfo').textContent=img.naturalWidth+'×'+img.naturalHeight+' | '+Math.round(state.fps)+'fps';}
}

function setConnected(v){
  state.connected=v;
  const dot=document.getElementById('statusDot');
  dot.style.background=v?'var(--success)':'var(--text3)';
  document.getElementById('connectBtn').textContent=v?'🔴 断开':'📡 连接';
  document.getElementById('connectBtn').className=v?'btn btn-danger':'btn btn-primary';
  if(v){state.canvas.style.display='block';document.getElementById('placeholder').style.display='none';document.getElementById('toolbar').style.display='flex'}
  else{state.canvas.style.display='none';document.getElementById('placeholder').style.display='flex';document.getElementById('toolbar').style.display='none'}
}

function toggleConn(){
  if(state.connected){send({type:'disconnect'});return}
  const s=document.getElementById('serverInput').value.trim(),r=document.getElementById('roomInput').value.trim();
  const p=document.getElementById('pwdInput').value;
  const role=document.getElementById('modeHost').classList.contains('active')?'host':'viewer';
  if(!s||!r)return notify('输入服务器和房间号');
  state.role=role;
  send({type:'connect',server:s,room:r,password:p,role});
}

// Mouse/Keyboard
state.canvas.addEventListener('mousedown',e=>{
  if(!state.connected||state.role!=='viewer')return;
  const p=mapPos(e);send({type:'input',event:'click',data:{x:p.x,y:p.y,button:['left','middle','right'][e.button]||'left'}});
});
state.canvas.addEventListener('mousemove',e=>{
  if(!state.connected||state.role!=='viewer')return;
  const n=Date.now();if(n-state.lms<50)return;state.lms=n;
  const p=mapPos(e);send({type:'input',event:'mousemove',data:{x:p.x,y:p.y}});
});
state.canvas.addEventListener('wheel',e=>{
  if(!state.connected||state.role!=='viewer')return;
  const p=mapPos(e);send({type:'input',event:'scroll',data:{x:p.x,y:p.y,amount:Math.sign(e.deltaY)}});
  e.preventDefault();
},{passive:false});
document.addEventListener('keydown',e=>{
  if(!state.connected||state.role!=='viewer')return;
  if(e.ctrlKey&&e.altKey){if(e.key==='q'||e.key==='Q')return toggleFS();if(e.key==='x'||e.key==='X')return toggleConn()}
  const k=mapKey(e.key);if(k)send({type:'input',event:'keypress',data:{key:k}});
});

function mapPos(e){
  const r=state.canvas.getBoundingClientRect(),cx=e.clientX-r.left,cy=e.clientY-r.top;
  const pw=r.width,ph=r.height,mode=document.getElementById('scaleMode').value;
  let dw=state.remoteW,dh=state.remoteH;
  if(mode==='等比'){const r2=Math.min(pw/dw,ph/dh);dw*=r2;dh*=r2}
  else if(mode==='适应宽度'){dh=state.remoteH*pw/state.remoteW;dw=pw}
  else if(mode!=='原始'){dw=pw;dh=ph}
  const ox=(pw-dw)/2,oy=(ph-dh)/2;
  return{x:Math.max(0,Math.round((cx-ox)/dw*state.remoteW)),y:Math.max(0,Math.round((cy-oy)/dh*state.remoteH))};
}
function mapKey(k){
  const m={'Enter':'enter','Tab':'tab','Escape':'escape','Backspace':'backspace',
    'ArrowUp':'up','ArrowDown':'down','ArrowLeft':'left','ArrowRight':'right',
    'Delete':'delete','Home':'home','End':'end','PageUp':'pageup','PageDown':'pagedown',
    'Control':'ctrl','Alt':'alt','Shift':'shift','CapsLock':'capslock',' ':'space'};
  return m[k]||(k.length===1?k:'');
}

// UI Events
document.getElementById('connectBtn').addEventListener('click',toggleConn);
document.getElementById('modeViewer').addEventListener('click',()=>setMode('viewer'));
document.getElementById('modeHost').addEventListener('click',()=>setMode('host'));
document.getElementById('tbDisconnect').addEventListener('click',toggleConn);
document.getElementById('tbFullscreen').addEventListener('click',toggleFS);
document.getElementById('fullscreenBtn').addEventListener('click',toggleFS);

function setMode(m){
  document.querySelectorAll('#modeToggle button').forEach(b=>b.classList.remove('active'));
  document.getElementById(m==='viewer'?'modeViewer':'modeHost').classList.add('active');
  if(state.connected&&state.role!==m)toggleConn();
}

// Presets
document.querySelectorAll('#presetPills button').forEach(b=>{
  b.addEventListener('click',()=>{
    document.querySelectorAll('#presetPills button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    document.getElementById('qualitySlider').value=b.dataset.q;
    document.getElementById('qualityVal').textContent=b.dataset.q;
    document.getElementById('fpsInput').value=b.dataset.f;
    document.getElementById('scaleSelect').value=b.dataset.s+'%';
    syncHost();
  });
});
document.getElementById('qualitySlider').addEventListener('input',e=>{
  document.getElementById('qualityVal').textContent=e.target.value;
  document.querySelectorAll('#presetPills button').forEach(x=>x.classList.remove('active'));
});
document.getElementById('qualitySlider').addEventListener('change',syncHost);
document.getElementById('fpsInput').addEventListener('change',syncHost);
document.getElementById('scaleSelect').addEventListener('change',syncHost);
document.getElementById('monitorInput').addEventListener('change',syncHost);

function syncHost(){
  if(state.role!=='host')return;
  send({type:'host_settings',quality:+document.getElementById('qualitySlider').value,
    fps:+document.getElementById('fpsInput').value,
    scale:+document.getElementById('scaleSelect').value/100,
    monitor:+document.getElementById('monitorInput').value||1,
    privacy:document.getElementById('privacyToggle').style.color==='var(--primary)'});
}

document.getElementById('privacyToggle').addEventListener('click',function(){
  this.style.color=this.style.color==='var(--primary)'?'var(--text3)':'var(--primary)';
  syncHost();
});

// FS
function toggleFS(){
  if(!document.fullscreenElement){document.getElementById('main').requestFullscreen();document.getElementById('toolbar').style.display='none'}
  else{document.exitFullscreen();if(state.connected)document.getElementById('toolbar').style.display='flex'}
}
document.addEventListener('fullscreenchange',()=>{
  if(!document.fullscreenElement&&state.connected)document.getElementById('toolbar').style.display='flex';
});

// Chat
document.getElementById('chatBtn').addEventListener('click',()=>toggleChat());
document.getElementById('tbChat').addEventListener('click',()=>toggleChat());
document.getElementById('chatSend').addEventListener('click',()=>sendChat());
document.getElementById('chatInput').addEventListener('keydown',e=>{if(e.key==='Enter')sendChat()});

function toggleChat(){
  state.chatVisible=!state.chatVisible;
  document.getElementById('chatPanel').style.display=state.chatVisible?'flex':'none';
  document.getElementById('chatBtn').textContent=state.chatVisible?'✕ 聊天':'💬 聊天';
}
function sendChat(){
  const i=document.getElementById('chatInput'),t=i.value.trim();
  if(!t||!state.connected)return;
  send({type:'chat',text:t,target:state.role==='viewer'?'host':'all'});
  addChat('我',t);i.value='';
}
function addChat(n,t){
  const m=document.getElementById('chatMessages'),d=document.createElement('div');
  d.className='cm';d.innerHTML='<span class="n" style="color:'+(n==='我'?'var(--success)':'var(--primary)')+'">'+esc(n)+':</span> '+esc(t);
  m.appendChild(d);m.scrollTop=m.scrollHeight;
}
function esc(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

// File
document.getElementById('fileBtn').addEventListener('click',()=>{if(state.connected)send({type:'pick_file'});else notify('先连接')});
document.getElementById('tbFile').addEventListener('click',()=>document.getElementById('fileBtn').click());

function notify(t){
  const n=document.createElement('div');n.className='notif';n.textContent=t;
  document.body.appendChild(n);setTimeout(()=>{n.style.opacity='0';n.style.transition='opacity .3s';setTimeout(()=>n.remove(),300)},2500);
}
connectLocal();
window.addEventListener('resize',()=>{if(state.connected){state.canvas.style.display='none';state.canvas.style.display='block'}});
</script>
</body>
</html>"""

# =====================================================================
# Python Backend
# =====================================================================

class Backend:
    def __init__(self):
        self.relay = None
        self.role = "viewer"
        self.connected = False
        self._q = 45
        self._fps2 = 12
        self._scale = 0.5
        self._mon = 1
        self._privacy = False
        self._running = True
        self._capture = None
        self._browsers = set()

    async def start(self, port=8887):
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text=HTML, content_type="text/html"))
        app.router.add_get("/ws", self._ws_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", port).start()
        log.info(f"http://127.0.0.1:{port}")
        webbrowser.open(f"http://127.0.0.1:{port}")
        while self._running:
            await asyncio.sleep(1)

    def stop(self):
        self._running = False
        self._disc()

    # Browser WS
    async def _ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._browsers.add(ws)
        log.info("browser connected")
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    await self._bmsg(json.loads(msg.data), ws)
                except: pass
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
        self._browsers.discard(ws)
        if not self._browsers:
            self._disc()
        return ws

    async def _bcast(self, data):
        for ws in list(self._browsers):
            try: await ws.send_json(data)
            except: self._browsers.discard(ws)

    async def _bmsg(self, msg, ws):
        t = msg.get("type")
        if t == "connect":
            self.role = msg.get("role")
            asyncio.ensure_future(self._relay_connect(
                msg.get("server"), msg.get("room"),
                msg.get("password", ""), msg.get("role")))
        elif t == "disconnect":
            self._disc()
            await self._bcast({"type": "disconnected"})
        elif t == "input" and self.relay and self.connected:
            await self.relay.send_json({
                "type": "input", "event": msg.get("event"),
                "data": msg.get("data")})
        elif t == "chat" and self.relay and self.connected:
            await self.relay.send_json({
                "type": "chat", "text": msg.get("text"),
                "target": msg.get("target")})
        elif t == "host_settings":
            self._q = msg.get("quality", 45)
            self._fps2 = msg.get("fps", 12)
            self._scale = msg.get("scale", 0.5)
            self._mon = msg.get("monitor", 1)
            self._privacy = msg.get("privacy", False)

    # Relay
    async def _relay_connect(self, server, room, password, role):
        self._disc()
        try:
            url = server.replace("ws://", "http://").replace("wss://", "https://")
            async with aiohttp.ClientSession() as sess:
                async with sess.ws_connect(url, autoclose=False, autoping=True) as ws:
                    self.relay = ws; self.connected = True
                    await self._bcast({"type": "connected"})
                    reg = {"type": "register", "role": role, "room": room}
                    if password: reg["password"] = password
                    await ws.send_json(reg)
                    if role == "host":
                        self._capture = asyncio.ensure_future(self._cap_loop())
                    async for m in ws:
                        if m.type == aiohttp.WSMsgType.TEXT:
                            try: await self._relay_msg(json.loads(m.data))
                            except: pass
                        elif m.type == aiohttp.WSMsgType.CLOSE: break
        except Exception as e:
            log.error(f"relay error: {e}")
            await self._bcast({"type": "notify", "text": f"失败: {e}"})
        self.connected = False
        if self._capture: self._capture.cancel(); self._capture = None
        self.relay = None
        await self._bcast({"type": "disconnected"})

    def _disc(self):
        if self.relay:
            asyncio.ensure_future(self.relay.close())
            self.relay = None
        self.connected = False
        if self._capture: self._capture.cancel(); self._capture = None

    async def _relay_msg(self, msg):
        t = msg.get("type")
        if t == "frame":
            await self._bcast({"type": "frame", "data": msg.get("data")})
        elif t == "chat":
            await self._bcast({"type": "chat", "text": msg.get("text"), "name": msg.get("name","?")})
        elif t == "input":
            self._handle_input(msg.get("event"), msg.get("data", {}))
        elif t == "error":
            await self._bcast({"type": "notify", "text": msg.get("msg")})
        elif t == "host_left":
            await self._bcast({"type": "notify", "text": "host disconnected"})
            self._disc()

    async def _cap_loop(self):
        if not mss or not Image: return
        while self.connected:
            try:
                s = time.time(); iv = 1.0 / max(self._fps2, 1)
                if self._privacy:
                    pil = Image.new("RGB", (640, 360), (28, 28, 30))
                else:
                    with mss.mss() as sct:
                        mon = sct.monitors[min(self._mon, len(sct.monitors)-1)]
                        im = sct.grab(mon)
                        pil = Image.frombytes("RGB", im.size, im.rgb)
                        if self._scale < 1.0:
                            pil = pil.resize((int(pil.width*self._scale), int(pil.height*self._scale)), Image.LANCZOS)
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=self._q, optimize=True)
                if self.relay and self.connected:
                    await self.relay.send_json({"type": "frame", "data": base64.b64encode(buf.getvalue()).decode(),
                        "timestamp": int(time.time()*1000)})
                await asyncio.sleep(max(0, iv - (time.time()-s)))
            except asyncio.CancelledError: break
            except Exception as e: log.error(f"capture: {e}"); await asyncio.sleep(1)

    def _handle_input(self, event, data):
        if not pyautogui: return
        try:
            if event == "click":
                pyautogui.click(x=data["x"], y=data["y"], button=data.get("button","left"))
            elif event == "mousemove":
                pyautogui.moveTo(data["x"], data["y"])
            elif event == "scroll":
                pyautogui.scroll(data.get("amount",1), x=data["x"], y=data["y"])
            elif event == "keypress" and Controller:
                kb = Controller(); key = data.get("key","")
                sp = {"enter":Key.enter,"return":Key.enter,"tab":Key.tab,"escape":Key.esc,
                    "esc":Key.esc,"backspace":Key.backspace,"space":Key.space,"ctrl":Key.ctrl,
                    "alt":Key.alt,"shift":Key.shift,"up":Key.up,"down":Key.down,
                    "left":Key.left,"right":Key.right,"delete":Key.delete,"home":Key.home,"end":Key.end,
                    "pageup":Key.page_up,"pagedown":Key.page_down}
                if len(key)==1: kb.press(key); kb.release(key)
                elif key.lower() in sp: kb.press(sp[key.lower()]); kb.release(sp[key.lower()])
        except Exception as e: log.error(f"input: {e}")


if __name__ == "__main__":
    b = Backend()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(b.start(8887))
    except KeyboardInterrupt: pass
    finally: b.stop(); loop.close()
