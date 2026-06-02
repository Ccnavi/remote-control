#!/usr/bin/env python3
"""
RemoteControl - PyQt5 远程桌面客户端
ToDesk 风格暗色主题 | 主控/被控一体
"""

import sys, json, time, base64, io, os, logging, threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QFrame,
    QTextEdit, QMessageBox, QSystemTrayIcon, QMenu, QAction,
    QSlider, QCheckBox, QSpinBox, QFileDialog, QScrollArea,
    QRadioButton, QStackedWidget,
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QColor, QPalette, QWheelEvent, QCursor

try: import websocket
except: websocket = None
try: import mss
except: mss = None
try: from PIL import Image, ImageDraw
except: Image = None
try: import pyautogui
except: pyautogui = None
try: from pynput.keyboard import Controller, Key
except: Controller = Key = None

APP_VER = "3.1.2"
SERVER = "ws://47.92.148.99:8500"
log = logging.getLogger("rc")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ============ 样式 ============
STYLE = """
QMainWindow, QWidget { background:#1c1c1e; color:#f0f0f0; }
QFrame#sidebar { background:#262628; border-right:1px solid #38383a; }
QFrame#section { background:#2c2c2e; border-radius:6px; border:1px solid #38383a; }
QLabel { color:#f0f0f0; font-size:12px; }
QLabel#h2 { color:#98989e; font-size:10px; font-weight:600; letter-spacing:.8px; }
QLineEdit, QComboBox { background:#1c1c1e; color:#f0f0f0; border:1px solid #38383a;
    border-radius:5px; padding:7px 10px; font-size:12px; }
QLineEdit:focus { border-color:#0070F9; }
QPushButton { border:none; border-radius:5px; padding:7px; font-size:12px; font-weight:600; }
QPushButton#primary { background:#0070F9; color:#fff; }
QPushButton#primary:hover { background:#0058d0; }
QPushButton#primary:disabled { background:#1c2a40; color:#666; }
QPushButton#danger { background:#ff3b30; color:#fff; }
QPushButton#plain { background:#1c1c1e; color:#98989e; border:1px solid #38383a; }
QPushButton#plain:hover { background:#38383a; color:#f0f0f0; }
QRadioButton { color:#98989e; font-size:12px; spacing:6px; }
QRadioButton::indicator { width:14px; height:14px; border-radius:7px; border:2px solid #38383a; }
QRadioButton::indicator:checked { background:#0070F9; border-color:#0070F9; }
QCheckBox { color:#98989e; font-size:11px; }
QCheckBox::indicator { width:14px; height:14px; border-radius:3px; border:2px solid #38383a; }
QCheckBox::indicator:checked { background:#0070F9; border-color:#0070F9; }
QSlider::groove:horizontal { height:3px; background:#38383a; border-radius:1px; }
QSlider::handle:horizontal { background:#0070F9; width:12px; height:12px; margin:-4px 0; border-radius:6px; }
QSlider::sub-page:horizontal { background:#0070F9; border-radius:1px; }
QSpinBox { background:#1c1c1e; color:#f0f0f0; border:1px solid #38383a; border-radius:4px; padding:3px 6px; font-size:11px; }
QScrollBar:vertical { background:transparent; width:4px; }
QScrollBar::handle:vertical { background:#38383a; border-radius:2px; min-height:30px; }
"""

# ============ WebSocket 线程 ============
class WSThread(QThread):
    recv = pyqtSignal(dict)
    conn = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.server = self.room = self.role = self.password = ""
        self.ws = None; self._run = False; self._recon = False

    def go(self, server, room, role, password=""):
        self.server = server; self.room = room; self.role = role; self.password = password
        self._recon = True; self.start()

    def stop(self):
        self._recon = False; self._run = False
        if self.ws:
            try: self.ws.close()
            except: pass
            self.ws = None

    def send(self, d):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(d)); return True
        except: pass
        return False

    def run(self):
        while self._recon:
            self._run = True; self.conn.emit(False, "连接中...")
            try:
                self.ws = websocket.WebSocketApp(self.server,
                    on_open=self._open, on_message=self._msg,
                    on_error=self._err, on_close=self._close)
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except: pass
            if self._recon:
                self.conn.emit(False, "断线重连...")
                time.sleep(3)
        self.conn.emit(False, "已断开")

    def _open(self, ws):
        self.conn.emit(True, "已连接")
        r = {"type":"register","role":self.role,"room":self.room}
        if self.password: r["password"] = self.password
        self.send(r)

    def _msg(self, ws, m):
        try: self.recv.emit(json.loads(m))
        except: pass
    def _err(self, ws, e): pass
    def _close(self, ws, *a): self._run = False

# ============ 屏幕捕获线程 ============
class CapThread(QThread):
    frame = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self._run = False; self.q = 45; self.fps = 12; self.mon = 1
        self.scale = 0.5; self.privacy = False; self._times = []

    def start_cap(self, q=45, fps=12, mon=1, scale=0.5):
        self.q = q; self.fps = fps; self.mon = mon; self.scale = scale
        self.privacy = False; self._run = True; self.start()

    def stop_cap(self): self._run = False
    def set_q(self, q): self.q = max(10, min(95, q))
    def add_t(self, t): self._times.append(t); self._times[:] = self._times[-30:]
    def lat(self):
        if len(self._times) < 5: return 0
        n = time.time(); return sum(n-t for t in self._times[-10:]) / min(len(self._times[-10:]), 10)

    def run(self):
        if not mss or not Image: return
        iv = 1.0 / max(self.fps, 1)
        with mss.mss() as sct:
            while self._run:
                try:
                    s = time.time()
                    if self.privacy:
                        pil = Image.new("RGB", (640,360), (28,28,30))
                    else:
                        mon = sct.monitors[min(self.mon, len(sct.monitors)-1)]
                        im = sct.grab(mon); pil = Image.frombytes("RGB", im.size, im.rgb)
                        if self.scale < 1.0:
                            pil = pil.resize((int(pil.width*self.scale), int(pil.height*self.scale)), Image.LANCZOS)
                    buf = io.BytesIO()
                    pil.save(buf, format="JPEG", quality=self.q, optimize=True)
                    self.frame.emit(buf.getvalue())
                    e = time.time() - s
                    if iv - e > 0: time.sleep(iv - e)
                except Exception as ex: log.error(f"cap: {ex}"); time.sleep(1)

# ============ 画面标签 ============
class ScreenLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = None; self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setStyleSheet("background:#0d0d1a; border:none;")
    def mousePressEvent(self, e):
        if self.app: self.app._v_mouse(e, "click")
    def mouseReleaseEvent(self, e):
        if self.app: self.app._v_mouse(e, "mouseup")
    def mouseDoubleClickEvent(self, e):
        if self.app: self.app._v_mouse(e, "click")
    def mouseMoveEvent(self, e):
        if self.app: self.app._v_move(e)
    def wheelEvent(self, e):
        if self.app: self.app._v_wheel(e)
    def keyPressEvent(self, e):
        if self.app:
            k = self.app._k_name(e.key())
            if k: self.app._v_key(k)
        super().keyPressEvent(e)

# ============ 主窗口 ============
class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"RemoteControl v{APP_VER}")
        self.resize(1200, 800); self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)
        self.setPalette(self._pal())

        # state
        self.role = "viewer"; self.ok = False
        self.rx, self.ry = 1920, 1080
        self.fc = 0; self.fts = time.time(); self.fps = 0
        self.jpg = None; self._pend = False; self._lm = 0
        self._fbuf = {}; self._ffn = {}

        # threads
        self.ws = WSThread()
        self.ws.recv.connect(self._on_msg)
        self.ws.conn.connect(self._on_conn)
        self.cap = CapThread()
        self.cap.frame.connect(self._on_cap)

        # UI
        self._ui()
        self._tray()

        # timers
        self._ft = QTimer(); self._ft.timeout.connect(self._disp)
        self._st = QTimer(); self._st.timeout.connect(self._stbar); self._st.start(2000)

    def _pal(self):
        p = QPalette()
        for r, c in [(QPalette.Window, QColor("#1c1c1e")), (QPalette.WindowText, QColor("#f0f0f0")),
            (QPalette.Base, QColor("#1c1c1e")), (QPalette.Text, QColor("#f0f0f0")),
            (QPalette.Button, QColor("#2c2c2e")), (QPalette.ButtonText, QColor("#f0f0f0")),
            (QPalette.Highlight, QColor("#0070F9"))]:
            p.setColor(r, c)
        return p

    # ========== UI ==========
    def _ui(self):
        c = QWidget(); self.setCentralWidget(c)
        root = QHBoxLayout(c); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # sidebar
        sb = QFrame(); sb.setObjectName("sidebar"); sb.setFixedWidth(260)
        scroll = QScrollArea(); scroll.setWidget(sb); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent;border:none;")

        v = QVBoxLayout(sb); v.setContentsMargins(12,12,12,12); v.setSpacing(8)

        # logo
        top = QHBoxLayout()
        self.dot = QLabel("●"); self.dot.setStyleSheet("color:#666;font-size:10px;")
        top.addWidget(self.dot)
        tl = QLabel("RemoteControl"); tl.setStyleSheet("font-size:14px;font-weight:700;")
        top.addWidget(tl); top.addStretch()
        v.addLayout(top)

        def sec(title):
            l = QLabel(title); l.setObjectName("h2"); v.addWidget(l)

        # connect
        sec("连接")
        self.srv = QLineEdit(SERVER); v.addWidget(self.srv)
        self.room = QLineEdit("default"); self.room.setPlaceholderText("房间号"); v.addWidget(self.room)
        self.pwd = QLineEdit(); self.pwd.setEchoMode(QLineEdit.Password); self.pwd.setPlaceholderText("密码(可选)"); v.addWidget(self.pwd)

        mt = QHBoxLayout()
        self.mv = QRadioButton("主控"); self.mh = QRadioButton("被控"); self.mv.setChecked(True)
        self.mv.toggled.connect(self._mode); self.mh.toggled.connect(self._mode)
        mt.addWidget(self.mv); mt.addWidget(self.mh); mt.addStretch(); v.addLayout(mt)

        self.btn = QPushButton("连接"); self.btn.setObjectName("primary")
        self.btn.clicked.connect(self._toggle); v.addWidget(self.btn)

        # host settings
        sec("被控端")
        self.hf = QFrame(); self.hf.setObjectName("section")
        hv = QVBoxLayout(self.hf); hv.setContentsMargins(10,10,10,10); hv.setSpacing(5)

        pr = QHBoxLayout()
        self.bf = QPushButton("流畅"); self.bb = QPushButton("均衡"); self.bh = QPushButton("高清")
        for b in [self.bf, self.bb, self.bh]:
            b.setObjectName("plain"); b.setCheckable(True); b.setFixedHeight(26)
            b.setStyleSheet("QPushButton{background:#1c1c1e;color:#98989e;border:1px solid #38383a;border-radius:12px;padding:3px 10px;font-size:11px}\
                QPushButton:checked{background:#0070F9;color:#fff;border-color:#0070F9}")
        self.bb.setChecked(True)
        self.bf.clicked.connect(lambda: self._preset(20,5,25))
        self.bb.clicked.connect(lambda: self._preset(45,12,50))
        self.bh.clicked.connect(lambda: self._preset(75,22,80))
        pr.addWidget(self.bf); pr.addWidget(self.bb); pr.addWidget(self.bh)
        hv.addLayout(pr)

        or1 = QHBoxLayout()
        or1.addWidget(QLabel("画质"))
        self.qs = QSlider(Qt.Horizontal); self.qs.setRange(10,95); self.qs.setValue(45)
        self.ql = QLabel("45"); self.qs.valueChanged.connect(lambda v: self.ql.setText(str(v)))
        or1.addWidget(self.qs); or1.addWidget(self.ql); hv.addLayout(or1)

        or2 = QHBoxLayout()
        or2.addWidget(QLabel("帧率"))
        self.fs = QSpinBox(); self.fs.setRange(1,30); self.fs.setValue(12); or2.addWidget(self.fs)
        or2.addWidget(QLabel("缩放"))
        self.sc = QComboBox(); self.sc.addItems(["25%","50%","75%","100%"]); self.sc.setCurrentIndex(1); or2.addWidget(self.sc)
        hv.addLayout(or2)

        or3 = QHBoxLayout()
        or3.addWidget(QLabel("显示器"))
        self.ms = QSpinBox(); self.ms.setRange(1,4); self.ms.setValue(1); or3.addWidget(self.ms)
        self.pk = QCheckBox("隐私屏"); self.pk.toggled.connect(lambda c: setattr(self.cap, 'privacy', c)); or3.addWidget(self.pk)
        or3.addStretch(); hv.addLayout(or3)

        self.hf.setEnabled(False); v.addWidget(self.hf)

        # viewer settings
        sec("主控端")
        self.vf = QFrame(); self.vf.setObjectName("section")
        vv = QVBoxLayout(self.vf); vv.setContentsMargins(10,10,10,10); vv.setSpacing(5)

        or4 = QHBoxLayout()
        or4.addWidget(QLabel("缩放"))
        self.sm = QComboBox(); self.sm.addItems(["等比","拉伸","原始","适应宽度"]); or4.addWidget(self.sm)
        vv.addLayout(or4)
        self.fs_btn = QPushButton("全屏"); self.fs_btn.setObjectName("plain")
        self.fs_btn.clicked.connect(self._fullscreen); vv.addWidget(self.fs_btn)
        self.vi = QLabel("--"); self.vi.setStyleSheet("color:#666;font-size:10px;"); vv.addWidget(self.vi)
        self.vf.setEnabled(False); v.addWidget(self.vf)

        # tools
        sec("工具")
        tr = QHBoxLayout()
        self.fb = QPushButton("文件"); self.fb.setObjectName("plain"); self.fb.clicked.connect(self._file_dlg)
        self.cb = QPushButton("聊天"); self.cb.setObjectName("plain"); self.cb.setCheckable(True); self.cb.toggled.connect(self._chat_tog)
        tr.addWidget(self.fb); tr.addWidget(self.cb); v.addLayout(tr)

        v.addStretch()
        vl = QLabel(f"v{APP_VER}"); vl.setStyleSheet("color:#444;font-size:9px;text-align:center;")
        vl.setAlignment(Qt.AlignCenter); v.addWidget(vl)

        # right: viewer
        r = QFrame(); r.setObjectName("screen")
        rv = QVBoxLayout(r); rv.setContentsMargins(0,0,0,0); rv.setSpacing(0)

        self.sl = ScreenLabel(); self.sl.app = self; self.sl.setAlignment(Qt.AlignCenter)
        self.ph = QLabel("连接后显示远程画面"); self.ph.setAlignment(Qt.AlignCenter)
        self.ph.setStyleSheet("color:#333;font-size:14px;")
        self.vs = QStackedWidget(); self.vs.addWidget(self.ph); self.vs.addWidget(self.sl)
        rv.addWidget(self.vs, 1)

        # floating toolbar
        tb = QFrame(); tb.setStyleSheet("QFrame{background:rgba(38,38,40,220);border-radius:6px;}\
            QPushButton{background:transparent;border:none;color:#98989e;padding:4px 8px;font-size:14px;border-radius:3px;}\
            QPushButton:hover{background:#38383a;color:#f0f0f0;}")
        tbh = QHBoxLayout(tb); tbh.setContentsMargins(4,2,4,2); tbh.setSpacing(0)

        def tb_btn(txt, tip, cb):
            b = QPushButton(txt); b.setToolTip(tip); b.clicked.connect(cb); tbh.addWidget(b); return b
        tb_btn("⛶", "全屏", self._fullscreen)
        tb_btn("\U0001f4c1", "文件", self._file_dlg)
        tb_btn("\U0001f4ac", "聊天", lambda: self.cb.toggle())
        s1 = QLabel("|"); s1.setStyleSheet("color:#38383a;padding:0 4px;"); tbh.addWidget(s1)
        self.tq = QLabel(""); self.tq.setStyleSheet("color:#666;font-size:10px;padding:0 6px;"); tbh.addWidget(self.tq)
        self.tf = QLabel(""); self.tf.setStyleSheet("color:#666;font-size:10px;padding:0 6px;"); tbh.addWidget(self.tf)
        s2 = QLabel("|"); s2.setStyleSheet("color:#38383a;padding:0 4px;"); tbh.addWidget(s2)
        tb_btn("✕", "断开", self._disc)
        tb.setFixedHeight(30)
        rv.addWidget(tb)

        # chat panel
        self.cp = QFrame(); self.cp.setObjectName("sidebar")
        self.cp.setFixedWidth(250); self.cp.hide()
        cv = QVBoxLayout(self.cp); cv.setContentsMargins(10,10,10,10); cv.setSpacing(6)
        cv.addWidget(QLabel("聊天"))
        self.cm = QTextEdit(); self.cm.setReadOnly(True); cv.addWidget(self.cm)
        ci = QHBoxLayout()
        self.ci = QLineEdit(); self.ci.setPlaceholderText("输入...")
        self.ci.returnPressed.connect(self._chat_send); ci.addWidget(self.ci)
        cs = QPushButton("发送"); cs.setObjectName("primary"); cs.setFixedWidth(52)
        cs.clicked.connect(self._chat_send); ci.addWidget(cs); cv.addLayout(ci)

        root.addWidget(scroll); root.addWidget(r, 1); root.addWidget(self.cp)
        self._preset(45,12,50)

    # ========== tray ==========
    def _tray(self):
        self.ti = QSystemTrayIcon(self)
        pm = QPixmap(16,16); pm.fill(QColor("#0070F9"))
        self.ti.setIcon(QIcon(pm)); self.ti.setToolTip("RemoteControl")
        m = QMenu()
        m.addAction("显示", lambda: (self.showNormal(), self.activateWindow()))
        self.ta = m.addAction("连接"); self.ta.triggered.connect(self._toggle)
        m.addSeparator(); m.addAction("退出", self.close)
        self.ti.setContextMenu(m)
        self.ti.activated.connect(lambda r: r==QSystemTrayIcon.DoubleClick and (self.showNormal(), self.activateWindow()))

    # ========== connection ==========
    def _toggle(self):
        if self._pend: return
        if self.ok: self._disc(); return
        sv = self.srv.text().strip(); rm = self.room.text().strip()
        if not sv or not rm: return
        self.role = "host" if self.mh.isChecked() else "viewer"
        self.btn.setEnabled(False); self.btn.setText("连接中..."); self._pend = True
        self.ws.go(sv, rm, self.role, self.pwd.text())

    def _disc(self):
        self._ft.stop(); self.jpg = None
        self.cap.stop_cap(); self.cap.wait(1500)
        self.ws._recon = False; self.ws.stop(); self.ws.wait(1500)
        self.ok = False; self.vs.setCurrentIndex(0); self.sl.clear()
        self.btn.setText("连接"); self.btn.setEnabled(True)
        self.btn.setObjectName("primary"); self.btn.style().unpolish(self.btn); self.btn.style().polish(self.btn)
        self.dot.setStyleSheet("color:#666;font-size:10px;")

    def _on_conn(self, ok, st):
        self.ok = ok
        if ok:
            self.btn.setText("断开"); self.btn.setEnabled(True); self._pend = False
            self.btn.setObjectName("danger"); self.btn.style().unpolish(self.btn); self.btn.style().polish(self.btn)
            self.dot.setStyleSheet("color:#36BA78;font-size:10px;")
            if self.role == "host":
                scale_map = {"25%":.25,"50%":.5,"75%":.75,"100%":1.0}
                self.cap.start_cap(self.qs.value(), self.fs.value(), self.ms.value(), scale_map.get(self.sc.currentText(), .5))
            else:
                self.vs.setCurrentIndex(1); self._ft.start(50); self.jpg = None
        else:
            if self.ws._recon:
                self.btn.setText("重连中..."); self.btn.setEnabled(False)
            else:
                self.btn.setText("连接"); self.btn.setEnabled(True); self._pend = False
                self.btn.setObjectName("primary"); self.btn.style().unpolish(self.btn); self.btn.style().polish(self.btn)
                self.dot.setStyleSheet("color:#ff3b30;font-size:10px;")

    def _mode(self):
        h = self.mh.isChecked(); v = self.mv.isChecked()
        self.hf.setEnabled(h); self.vf.setEnabled(v)
        if self.ok: self._disc()

    # ========== messages ==========
    def _on_msg(self, m):
        t = m.get("type")
        if t == "frame":
            d = m.get("data","")
            if d:
                try: self.jpg = base64.b64decode(d)
                except: pass
        elif t == "chat":
            self._chat_rcv(m.get("text",""), m.get("name","?"))
        elif t == "clipboard":
            t2 = m.get("text","")
            if t2:
                try: QApplication.clipboard().setText(t2)
                except: pass
        elif t == "input":
            self._remote_in(m.get("event",""), m.get("data",{}))
        elif t == "file_chunk":
            fid = m.get("file_id",""); c = m.get("chunk",""); fnl = m.get("final",False)
            if fid not in self._fbuf: self._fbuf[fid] = bytearray()
            if c: self._fbuf[fid].extend(base64.b64decode(c))
            if fnl:
                n = self._ffn.get(fid,"?"); sz = len(self._fbuf[fid])
                log.info(f"received: {n} ({sz/1024:.0f}KB)")
                self._fbuf.pop(fid,None); self._ffn.pop(fid,None)
        elif t == "file_meta":
            fid = m.get("file_id",""); fn = m.get("name",""); sz = m.get("size",0)
            self._ffn[fid] = fn
            self.ws.send({"type":"file_accept","file_id":fid})
        elif t == "viewer_joined":
            self.ta.setText(f"观察者加入")
        elif t == "host_ready":
            self.ta.setText("主机就绪")
        elif t == "host_left":
            self.vs.setCurrentIndex(0)
            QMessageBox.information(self,"断开","主机已断开")
        elif t == "error":
            QMessageBox.warning(self,"错误",m.get("msg",""))

    def _disp(self):
        if not self.jpg or self.role != "viewer": return
        try:
            pm = QPixmap(); pm.loadFromData(self.jpg, "JPEG")
            if pm.isNull(): return
            self.rx, self.ry = pm.width(), pm.height()
            mode = self.sm.currentText(); ls = self.sl.size()
            if mode == "原始": s = pm
            elif mode == "拉伸": s = pm.scaled(ls, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            elif mode == "适应宽度":
                w = ls.width(); h = int(pm.height() * w / max(pm.width(),1))
                s = pm.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            else: s = pm.scaled(ls, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.sl.setPixmap(s)
            self.fc += 1
            if time.time() - self.fts >= 2:
                self.fps = self.fc / (time.time() - self.fts)
                self.fts = time.time(); self.fc = 0
            if self.fc % 3 == 0:
                self.vi.setText(f"{self.rx}x{self.ry}  {self.fps:.0f}fps")
        except: pass

    def _on_cap(self, data):
        t = time.time(); self.cap.add_t(t)
        b = base64.b64encode(data).decode()
        self.ws.send({"type":"frame","data":b,"timestamp":int(t*1000)})
        lat = self.cap.lat()
        if self.cap._run and lat > 0.3:
            nq = max(15, self.cap.q - 5)
            if nq != self.cap.q: self.cap.set_q(nq); self.qs.setValue(nq)
        elif lat < 0.08 and self.cap.q < 60:
            nq = min(70, self.cap.q + 3)
            if nq != self.cap.q: self.cap.set_q(nq); self.qs.setValue(nq)

    def _stbar(self):
        if self.ok:
            self.tf.setText(f"{int(self.fps)}fps" if self.role=="viewer" else f"{self.fs.value()}fps")
            self.tq.setText(f"{self.cap.q}p" if self.role=="host" else "")
        else:
            self.tq.setText(""); self.tf.setText("")

    # ========== presets ==========
    def _preset(self, q, f, s):
        self.qs.setValue(q); self.fs.setValue(f)
        self.sc.setCurrentIndex({25:0,50:1,75:2,80:2,100:3}.get(s,1))
        for b in [self.bf,self.bb,self.bh]: b.setChecked(False)
        {20:self.bf,45:self.bb,75:self.bh}.get(q,self.bb).setChecked(True)

    # ========== toolbar ==========
    def _fullscreen(self):
        if self.isFullScreen():
            self.showNormal(); self.fs_btn.setText("全屏")
        else:
            self.showFullScreen(); self.fs_btn.setText("退出全屏")

    # ========== chat ==========
    def _chat_tog(self, v):
        self.cp.setVisible(v)

    def _chat_send(self):
        t = self.ci.text().strip()
        if not t or not self.ok: return
        tg = "host" if self.role == "viewer" else "all"
        self.ws.send({"type":"chat","text":t,"target":tg})
        self.cm.append(f"<b style='color:#36BA78'>我:</b> {t}")
        self.ci.clear()

    def _chat_rcv(self, t, n):
        self.cm.append(f"<b style='color:#0070F9'>{n}:</b> {t}")

    # ========== file ==========
    def _file_dlg(self):
        if not self.ok: return
        p, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if p: self._send_files(p)

    def _send_files(self, paths):
        for fp in paths:
            fn = os.path.basename(fp); fs = os.path.getsize(fp)
            fid = f"f{int(time.time()*1000)}"
            tg = "host" if self.role == "viewer" else "viewer"
            self.ws.send({"type":"file_meta","file_id":fid,"name":fn,"size":fs,"target":tg})
            off = 0; CHUNK = 64*1024
            with open(fp, "rb") as f:
                while off < fs:
                    c = f.read(CHUNK); b = base64.b64encode(c).decode()
                    fnl = (off+len(c)) >= fs
                    self.ws.send({"type":"file_chunk","file_id":fid,"chunk":b,"offset":off,"final":fnl,"target":tg})
                    off += len(c)
            log.info(f"sent: {fn} ({fs/1024:.0f}KB)")

    # ========== mouse/keyboard ==========
    def _v_mouse(self, e, et):
        if not self.ok or self.role != "viewer": return
        x, y = self._map(e.x(), e.y())
        b = {1:"left",2:"right",4:"middle"}.get(e.button(),"left")
        self.ws.send({"type":"input","event":et,"data":{"x":x,"y":y,"button":b}})

    def _v_move(self, e):
        if not self.ok or self.role != "viewer": return
        x, y = self._map(e.x(), e.y()); n = time.time()
        if n - self._lm > 0.05:
            self._lm = n; self.ws.send({"type":"input","event":"mousemove","data":{"x":x,"y":y}})

    def _v_wheel(self, e):
        if not self.ok or self.role != "viewer": return
        x, y = self._map(e.x(), e.y())
        self.ws.send({"type":"input","event":"scroll","data":{"x":x,"y":y,"amount":e.angleDelta().y()//120}})

    def _v_key(self, k):
        if not self.ok or self.role != "viewer": return
        self.ws.send({"type":"input","event":"keypress","data":{"key":k}})

    def _map(self, lx, ly):
        if not self.sl.pixmap(): return (lx, ly)
        p = self.sl.pixmap(); pw, ph = p.width(), p.height()
        lw, lh = self.sl.width(), self.sl.height()
        if pw == 0 or ph == 0: return (lx, ly)
        ox, oy = (lw-pw)//2, (lh-ph)//2
        return (max(0,int((lx-ox)/pw*self.rx)), max(0,int((ly-oy)/ph*self.ry)))

    def _k_name(self, k):
        m = {Qt.Key_Enter:"enter",Qt.Key_Return:"enter",Qt.Key_Tab:"tab",Qt.Key_Escape:"escape",
            Qt.Key_Backspace:"backspace",Qt.Key_Space:"space",Qt.Key_Up:"up",Qt.Key_Down:"down",
            Qt.Key_Left:"left",Qt.Key_Right:"right",Qt.Key_Delete:"delete",Qt.Key_Home:"home",
            Qt.Key_End:"end",Qt.Key_PageUp:"pageup",Qt.Key_PageDown:"pagedown",
            Qt.Key_Control:"ctrl",Qt.Key_Alt:"alt",Qt.Key_Shift:"shift",Qt.Key_CapsLock:"capslock"}
        return m.get(k, chr(k) if 32<=k<=126 else "")

    def _remote_in(self, ev, d):
        if not pyautogui: return
        try:
            if ev=="click": pyautogui.click(x=d["x"],y=d["y"],button=d.get("button","left"))
            elif ev=="mousemove": pyautogui.moveTo(d["x"],d["y"])
            elif ev=="scroll": pyautogui.scroll(d.get("amount",1),x=d["x"],y=d["y"])
            elif ev=="keypress" and Controller:
                kb = Controller(); key = d.get("key","")
                sp = {"enter":Key.enter,"return":Key.enter,"tab":Key.tab,"escape":Key.esc,
                    "backspace":Key.backspace,"space":Key.space,"ctrl":Key.ctrl,"alt":Key.alt,
                    "shift":Key.shift,"up":Key.up,"down":Key.down,"left":Key.left,"right":Key.right,
                    "delete":Key.delete,"home":Key.home,"end":Key.end,"pageup":Key.page_up,"pagedown":Key.page_down}
                if len(key)==1: kb.press(key); kb.release(key)
                elif key.lower() in sp: kb.press(sp[key.lower()]); kb.release(sp[key.lower()])
        except: pass

    # ========== close ==========
    def closeEvent(self, e):
        if self.role == "host" and self.ok:
            e.ignore(); self.hide(); self.ti.show()
            self.ti.showMessage("RemoteControl","后台运行中",QSystemTrayIcon.Information,2000)
            return
        self._ft.stop(); self.cap.stop_cap(); self.cap.wait(1000)
        self.ws._recon=False; self.ws.stop(); self.ws.wait(1000)
        e.accept()

# ============ main ============
if __name__ == "__main__":
    QApplication.setStyle("Fusion")
    app = QApplication(sys.argv); app.setApplicationName("RemoteControl")
    if not websocket or not mss:
        print("Need: pip install websocket-client mss")
        sys.exit(1)
    w = MainWin(); w.show(); sys.exit(app.exec_())
