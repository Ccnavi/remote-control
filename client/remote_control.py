#!/usr/bin/env python3
"""
Remote Control v3.0 - ToDesk 风格远程桌面
支持主控/被控双模式，文件传输，聊天，剪贴板同步
"""

import sys
import json
import time
import base64
import threading
import logging
import io
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QFrame,
    QTextEdit, QMessageBox, QSystemTrayIcon, QMenu, QAction,
    QSlider, QCheckBox, QSpinBox, QRadioButton,
    QStackedWidget, QScrollArea, QSizePolicy, QFileDialog,
)
from PyQt5.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSize, QPoint, QRect,
)
from PyQt5.QtGui import (
    QPixmap, QImage, QIcon, QFont, QColor, QPalette,
    QWheelEvent, QCursor, QPainter, QFontDatabase,
)

try:
    import websocket
except ImportError:
    websocket = None
try:
    import mss
except ImportError:
    mss = None
try:
    from PIL import Image, ImageDraw, ImageFont
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

APP_NAME = "RemoteControl"
APP_VERSION = "3.0.0"
DEFAULT_SERVER = "ws://47.92.148.99:8500"
DEFAULT_ROOM = "default"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rc")

# ======================== 样式表 ========================

DARK_STYLE = """
QMainWindow { background: #1a1a2e; }
QFrame#sidebar { background: #16213e; border-right: 1px solid #0f3460; }
QFrame#section { background: #1a1a35; border-radius: 8px; border: 1px solid #2a2a4a; }
QFrame#section:hover { border: 1px solid #3a3a5a; }
QFrame#chatPanel { background: #16213e; border-left: 1px solid #0f3460; }
QLabel { color: #c8c8d4; font-size: 12px; }
QLabel#title { color: #e0e0ff; font-size: 16px; font-weight: bold; }
QLabel#sectionTitle { color: #8888bb; font-size: 11px; font-weight: bold; letter-spacing: 1px; }
QLabel#statusText { color: #6666aa; font-size: 11px; }
QLineEdit, QComboBox {
    background: #0f3460; color: #e0e0ff; border: 1px solid #1a4a7a;
    border-radius: 6px; padding: 8px 12px; font-size: 13px;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #4CAF50; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid #8888bb; margin-right: 8px; }
QComboBox QAbstractItemView {
    background: #16213e; color: #e0e0ff; border: 1px solid #0f3460;
    selection-background-color: #0f3460;
}
QPushButton { border: none; border-radius: 6px; padding: 8px 16px; font-size: 13px; font-weight: bold; }
QPushButton#primary { background: #4CAF50; color: white; }
QPushButton#primary:hover { background: #45a049; }
QPushButton#danger { background: #f44336; color: white; }
QPushButton#danger:hover { background: #d32f2f; }
QPushButton#action { background: #0f3460; color: #c8c8d4; border: 1px solid #1a4a7a; }
QPushButton#action:hover { background: #1a4a7a; color: #fff; }
QPushButton#action:checked { background: #4CAF50; color: white; border: 1px solid #4CAF50; }
QPushButton#pill { background: #1a1a35; color: #8888bb; border: 1px solid #2a2a4a; border-radius: 14px; padding: 6px 14px; font-size: 12px; }
QPushButton#pill:hover { border-color: #4CAF50; color: #4CAF50; }
QPushButton#pill:checked { background: #4CAF50; color: white; border-color: #4CAF50; }
QRadioButton { color: #c8c8d4; font-size: 13px; spacing: 8px; }
QRadioButton::indicator { width: 16px; height: 16px; border-radius: 8px; border: 2px solid #4a4a6a; }
QRadioButton::indicator:checked { background: #4CAF50; border-color: #4CAF50; }
QCheckBox { color: #c8c8d4; font-size: 12px; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; border: 2px solid #4a4a6a; }
QCheckBox::indicator:checked { background: #4CAF50; border-color: #4CAF50; }
QSlider::groove:horizontal { height: 4px; background: #2a2a4a; border-radius: 2px; }
QSlider::handle:horizontal { background: #4CAF50; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #4CAF50; border-radius: 2px; }
QSpinBox { background: #0f3460; color: #e0e0ff; border: 1px solid #1a4a7a; border-radius: 6px; padding: 6px; font-size: 13px; }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #2a2a4a; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTextEdit { background: #0f3460; color: #c8c8d4; border: 1px solid #1a4a7a; border-radius: 6px; font-size: 12px; }
QFrame#viewerBg { background: #0d0d1a; border: none; }
"""


# ======================== 工具函数 ========================

def make_section(title: str, parent=None) -> tuple[QFrame, QVBoxLayout]:
    """创建一个现代风格的区块"""
    frame = QFrame()
    frame.setObjectName("section")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    header = QLabel(title)
    header.setObjectName("sectionTitle")
    layout.addWidget(header)
    return frame, layout


# ======================== WebSocket 线程 ========================

class WebSocketThread(QThread):
    message_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.server_url = ""
        self.room = ""
        self.role = "viewer"
        self.password = ""
        self.ws = None
        self.running = False
        self._should_reconnect = False
        self._reconnect_delay = 3

    def connect(self, server_url: str, room: str, role: str, password: str = ""):
        self.server_url = server_url
        self.room = room
        self.role = role
        self.password = password
        self._should_reconnect = True
        self.start()

    def disconnect(self):
        self._should_reconnect = False
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None

    def send(self, data: dict) -> bool:
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(data))
                return True
        except Exception as e:
            log.error(f"发送失败: {e}")
        return False

    def run(self):
        while self._should_reconnect:
            self.running = True
            self.connection_changed.emit(False, "连接中...")
            try:
                self.ws = websocket.WebSocketApp(
                    self.server_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                log.error(f"连接异常: {e}")
            if self._should_reconnect:
                self.connection_changed.emit(False, "断线重连中...")
                time.sleep(self._reconnect_delay)
        self.connection_changed.emit(False, "已断开")

    def _on_open(self, ws):
        self.connection_changed.emit(True, "已连接")
        reg = {"type": "register", "role": self.role, "room": self.room}
        if self.password:
            reg["password"] = self.password
        self.send(reg)

    def _on_message(self, ws, message):
        try:
            msg = json.loads(message)
            self.message_received.emit(msg)
        except json.JSONDecodeError:
            pass

    def _on_error(self, ws, error):
        log.error(f"WebSocket 错误: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.running = False


# ======================== 屏幕捕获线程 ========================

class ScreenCaptureThread(QThread):
    frame_captured = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self.running = False
        self.quality = 45
        self.fps = 12
        self.monitor = 1
        self.scale_factor = 0.5
        self.privacy_mode = False
        self.auto_adapt = True
        self._send_times = []

    def start_capture(self, quality=45, fps=12, monitor=1, scale_factor=0.5):
        self.quality = quality
        self.fps = fps
        self.monitor = monitor
        self.scale_factor = scale_factor
        self.privacy_mode = False
        self.running = True
        self.start()

    def stop_capture(self):
        self.running = False

    def set_quality(self, q: int):
        self.quality = max(10, min(95, q))

    def add_send_time(self, t: float):
        self._send_times.append(t)
        if len(self._send_times) > 30:
            self._send_times.pop(0)

    def get_avg_latency(self) -> float:
        if len(self._send_times) < 5:
            return 0.0
        now = time.time()
        deltas = [now - t for t in self._send_times[-10:]]
        return sum(deltas) / len(deltas)

    def run(self):
        if not mss or not Image:
            log.error("缺少 mss/Pillow")
            return
        interval = 1.0 / self.fps
        with mss.mss() as sct:
            while self.running:
                try:
                    start = time.time()
                    if self.privacy_mode:
                        pil_img = Image.new("RGB", (640, 360), (20, 20, 30))
                        draw = ImageDraw.Draw(pil_img)
                        draw.text((160, 160), "🔒 隐私屏已开启", fill=(100, 100, 120))
                    else:
                        mon = sct.monitors[self.monitor]
                        img = sct.grab(mon)
                        pil_img = Image.frombytes("RGB", img.size, img.rgb)
                        if self.scale_factor < 1.0:
                            w, h = pil_img.size
                            pil_img = pil_img.resize(
                                (int(w * self.scale_factor), int(h * self.scale_factor)),
                                Image.LANCZOS,
                            )
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=self.quality, optimize=True)
                    self.frame_captured.emit(buf.getvalue())
                    elapsed = time.time() - start
                    sleep_time = max(0, interval - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                except Exception as e:
                    log.error(f"捕获失败: {e}")
                    time.sleep(1)


# ======================== 远程画面标签 ========================

class RemoteScreenLabel(QLabel):
    """远程画面显示 - 支持鼠标事件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame_widget = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setStyleSheet("background: #0d0d1a; border: none;")

    def mousePressEvent(self, event):
        if self.frame_widget:
            self.frame_widget._viewer_mouse_event(event, "click")

    def mouseReleaseEvent(self, event):
        if self.frame_widget:
            self.frame_widget._viewer_mouse_event(event, "mouseup")

    def mouseDoubleClickEvent(self, event):
        if self.frame_widget:
            self.frame_widget._viewer_mouse_event(event, "click")

    def mouseMoveEvent(self, event):
        if self.frame_widget:
            self.frame_widget._viewer_mouse_move(event)

    def wheelEvent(self, event):
        if self.frame_widget:
            self.frame_widget._viewer_wheel(event)

    def keyPressEvent(self, event):
        if self.frame_widget:
            key = self.frame_widget._qt_key_to_name(event.key())
            if key:
                self.frame_widget._viewer_keypress(key)
        super().keyPressEvent(event)


# ======================== 主窗口 ========================

class RemoteControlApp(QMainWindow):
    """主窗口 - ToDesk 风格"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"RemoteControl v{APP_VERSION}")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(DARK_STYLE)

        # 状态
        self.current_role = "viewer"
        self.connected = False
        self.remote_resolution = (1920, 1080)
        self.frame_count = 0
        self.fps_timer_elapsed = time.time()
        self.current_fps = 0
        self.latest_jpeg = None
        self._pending_connection = False
        self._last_mouse_send = 0
        self._file_buffers = {}

        # 线程
        self.ws_thread = WebSocketThread()
        self.ws_thread.message_received.connect(self._on_message)
        self.ws_thread.connection_changed.connect(self._on_connection_changed)

        self.capture_thread = ScreenCaptureThread()
        self.capture_thread.frame_captured.connect(self._on_frame_captured)

        # UI
        self._build_ui()
        self._init_tray()

        # 帧显示定时器
        self._frame_timer = QTimer()
        self._frame_timer.timeout.connect(self._display_latest_frame)

        # 状态定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status_bar)
        self.status_timer.start(2000)

    # ==================== 托盘 ====================

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("RemoteControl")
        pm = QPixmap(16, 16)
        pm.fill(QColor("#4CAF50"))
        self.tray_icon.setIcon(QIcon(pm))
        menu = QMenu()
        menu.addAction("显示窗口", lambda: (self.showNormal(), self.activateWindow()))
        self.tray_connect_action = menu.addAction("📡 连接")
        self.tray_connect_action.triggered.connect(self._toggle_connection)
        menu.addSeparator()
        menu.addAction("退出", self.close)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(
            lambda r: r == QSystemTrayIcon.DoubleClick and (
                self.showNormal(), self.activateWindow(), self.tray_icon.hide()))

    # ==================== UI 构建 ====================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ========== 左侧栏 ==========
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(260)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidget(sidebar)
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sidebar_scroll.setFrameShape(QFrame.NoFrame)
        sidebar_scroll.setStyleSheet("background:transparent; border:none;")

        svbox = QVBoxLayout(sidebar)
        svbox.setContentsMargins(12, 12, 12, 12)
        svbox.setSpacing(10)

        # 标题 + 状态指示器
        header = QHBoxLayout()
        title = QLabel("RemoteControl")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color:#666; font-size:10px;")
        header.addWidget(self.status_dot)
        svbox.addLayout(header)

        # ---- 连接区 ----
        conn_frame, conn_layout = make_section("连接")
        self.server_input = QLineEdit(DEFAULT_SERVER)
        conn_layout.addWidget(self.server_input)
        self.room_input = QLineEdit(DEFAULT_ROOM)
        self.room_input.setPlaceholderText("房间名（两端一致）")
        conn_layout.addWidget(self.room_input)

        pwd_row = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("密码（可选）")
        pwd_row.addWidget(self.password_input)
        self.show_pwd_btn = QPushButton("👁")
        self.show_pwd_btn.setFixedSize(32, 32)
        self.show_pwd_btn.setObjectName("action")
        self.show_pwd_btn.setCheckable(True)
        self.show_pwd_btn.toggled.connect(
            lambda c: self.password_input.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password))
        pwd_row.addWidget(self.show_pwd_btn)
        conn_layout.addLayout(pwd_row)

        # 模式切换
        mode_row = QHBoxLayout()
        self.mode_viewer = QRadioButton("👁 主控端")
        self.mode_host = QRadioButton("🖥 被控端")
        self.mode_viewer.setChecked(True)
        self.mode_viewer.toggled.connect(self._on_mode_changed)
        self.mode_host.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_viewer)
        mode_row.addWidget(self.mode_host)
        conn_layout.addLayout(mode_row)

        self.connect_btn = QPushButton("📡 连接")
        self.connect_btn.setObjectName("primary")
        self.connect_btn.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self.connect_btn)
        svbox.addWidget(conn_frame)

        # ---- 被控设置 ----
        self.host_frame, host_layout = make_section("被控端设置")
        host_layout.setSpacing(6)

        # 画质预设
        preset_row = QHBoxLayout()
        self.btn_fast = QPushButton("流畅")
        self.btn_fast.setObjectName("pill")
        self.btn_fast.setCheckable(True)
        self.btn_fast.clicked.connect(lambda: self._set_preset(20, 5, 25))
        self.btn_balanced = QPushButton("均衡")
        self.btn_balanced.setObjectName("pill")
        self.btn_balanced.setCheckable(True)
        self.btn_balanced.setChecked(True)
        self.btn_balanced.clicked.connect(lambda: self._set_preset(45, 12, 50))
        self.btn_hd = QPushButton("高清")
        self.btn_hd.setObjectName("pill")
        self.btn_hd.setCheckable(True)
        self.btn_hd.clicked.connect(lambda: self._set_preset(75, 22, 80))
        preset_row.addWidget(self.btn_fast)
        preset_row.addWidget(self.btn_balanced)
        preset_row.addWidget(self.btn_hd)
        host_layout.addLayout(preset_row)

        # 画质滑块
        qrow = QHBoxLayout()
        qrow.addWidget(QLabel("画质"))
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(10, 95)
        self.quality_slider.setValue(45)
        self.quality_label = QLabel("45")
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_label.setText(str(v)))
        qrow.addWidget(self.quality_slider)
        qrow.addWidget(self.quality_label)
        host_layout.addLayout(qrow)

        # 帧率+缩放+显示器
        optrow = QHBoxLayout()
        optrow.addWidget(QLabel("帧率"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        self.fps_spin.setValue(12)
        optrow.addWidget(self.fps_spin)
        optrow.addWidget(QLabel("缩放"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["25%", "50%", "75%", "100%"])
        self.scale_combo.setCurrentIndex(1)
        optrow.addWidget(self.scale_combo)
        host_layout.addLayout(optrow)

        # 显示器和隐私
        botrow = QHBoxLayout()
        botrow.addWidget(QLabel("显示器"))
        self.monitor_spin = QSpinBox()
        self.monitor_spin.setRange(1, 4)
        self.monitor_spin.setValue(1)
        botrow.addWidget(self.monitor_spin)
        self.privacy_check = QCheckBox("隐私屏")
        self.privacy_check.toggled.connect(self._toggle_privacy)
        botrow.addWidget(self.privacy_check)
        host_layout.addLayout(botrow)

        self.host_frame.setEnabled(False)
        svbox.addWidget(self.host_frame)

        # ---- 主控设置 ----
        self.viewer_frame, viewer_layout = make_section("主控端设置")

        zrow = QHBoxLayout()
        zrow.addWidget(QLabel("缩放"))
        self.scale_mode = QComboBox()
        self.scale_mode.addItems(["等比", "拉伸", "原始", "适应宽度"])
        self.scale_mode.setCurrentIndex(0)
        zrow.addWidget(self.scale_mode)
        viewer_layout.addLayout(zrow)

        trow = QHBoxLayout()
        self.fullscreen_btn = QPushButton("⛶ 全屏")
        self.fullscreen_btn.setObjectName("action")
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        trow.addWidget(self.fullscreen_btn)
        viewer_layout.addLayout(trow)

        self.viewer_info = QLabel("等待连接...")
        self.viewer_info.setStyleSheet("color:#666; font-size:11px;")
        viewer_layout.addWidget(self.viewer_info)

        self.viewer_frame.setEnabled(False)
        svbox.addWidget(self.viewer_frame)

        # ---- 快捷工具 ----
        tool_frame, tool_layout = make_section("工具")

        self.btn_file = QPushButton("📁 传文件")
        self.btn_file.setObjectName("action")
        self.btn_file.clicked.connect(self._show_file_dialog)
        tool_layout.addWidget(self.btn_file)

        self.btn_chat = QPushButton("💬 聊天")
        self.btn_chat.setObjectName("action")
        self.btn_chat.setCheckable(True)
        self.btn_chat.toggled.connect(self._toggle_chat)
        tool_layout.addWidget(self.btn_chat)

        svbox.addWidget(tool_frame)
        svbox.addStretch()

        # 底部版本号
        vlabel = QLabel(f"v{APP_VERSION}")
        vlabel.setObjectName("statusText")
        vlabel.setAlignment(Qt.AlignCenter)
        svbox.addWidget(vlabel)

        # ========== 右侧画面区 ==========
        right = QFrame()
        right.setObjectName("viewerBg")
        rvbox = QVBoxLayout(right)
        rvbox.setContentsMargins(0, 0, 0, 0)
        rvbox.setSpacing(0)

        self.viewer_label = RemoteScreenLabel()
        self.viewer_label.frame_widget = self
        self.viewer_label.setAlignment(Qt.AlignCenter)

        self.placeholder = QLabel()
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setText(
            "🔗 <b>RemoteControl</b><br><br>"
            "<span style='color:#555;font-size:13px;'>"
            "选择模式 → 输入房间名 → 点击连接<br><br>"
            "🖥 被控端：共享本机屏幕<br>"
            "👁 主控端：查看远程画面</span>"
        )
        self.placeholder.setStyleSheet("color:#333; font-size:15px; background:transparent;")

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.placeholder)
        self.view_stack.addWidget(self.viewer_label)
        rvbox.addWidget(self.view_stack, 1)

        # ---- 浮动工具栏 ----
        self.toolbar = QFrame()
        self.toolbar.setStyleSheet("""
            QFrame { background: rgba(22, 33, 62, 200); border-radius: 8px; }
            QPushButton { background: transparent; color: #c8c8d4; border: none;
                         border-radius: 4px; padding: 6px 10px; font-size: 18px; }
            QPushButton:hover { background: rgba(76, 175, 80, 0.3); }
        """)
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(6, 4, 6, 4)
        tb_layout.setSpacing(2)

        def tb_btn(text, tip, cb):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(cb)
            tb_layout.addWidget(b)
            return b

        tb_btn("⛶", "全屏", self._toggle_fullscreen)
        tb_btn("📁", "传文件", self._show_file_dialog)
        tb_btn("💬", "聊天", lambda: self.btn_chat.toggle())
        tb_btn("🔄", "刷新", lambda: None)
        self.tb_quality = QLabel("45p")
        self.tb_quality.setStyleSheet("color:#888; font-size:11px; padding:0 8px;")
        tb_layout.addWidget(self.tb_quality)
        self.tb_fps = QLabel("0fps")
        self.tb_fps.setStyleSheet("color:#888; font-size:11px; padding:0 8px;")
        tb_layout.addWidget(self.tb_fps)
        tb_btn("✕", "断开", self.disconnect_server)
        self.toolbar.setFixedHeight(36)
        rvbox.addWidget(self.toolbar)

        # ========== 聊天面板 ==========
        self.chat_widget = QFrame()
        self.chat_widget.setObjectName("chatPanel")
        self.chat_widget.setFixedWidth(260)
        self.chat_widget.hide()

        cvbox = QVBoxLayout(self.chat_widget)
        cvbox.setContentsMargins(10, 10, 10, 10)
        cvbox.setSpacing(8)

        ch = QLabel("💬 聊天")
        ch.setObjectName("title")
        ch.setStyleSheet("font-size:14px;")
        cvbox.addWidget(ch)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("")
        cvbox.addWidget(self.chat_display)

        ci = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入消息...")
        self.chat_input.returnPressed.connect(self._send_chat)
        ci.addWidget(self.chat_input)

        self.chat_send_btn = QPushButton("发送")
        self.chat_send_btn.setObjectName("primary")
        self.chat_send_btn.setFixedWidth(60)
        self.chat_send_btn.clicked.connect(self._send_chat)
        ci.addWidget(self.chat_send_btn)
        cvbox.addLayout(ci)

        # ========== 组装 ==========
        root.addWidget(sidebar_scroll)
        root.addWidget(right, 1)
        root.addWidget(self.chat_widget)

        self._set_preset(45, 12, 50)

    # ==================== 连接管理 ====================

    def _toggle_connection(self):
        if self._pending_connection:
            return
        if self.connected:
            self.disconnect_server()
            return

        server = self.server_input.text().strip()
        room = self.room_input.text().strip()
        if not server or not room:
            return

        self.current_role = "host" if self.mode_host.isChecked() else "viewer"
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("⏳ 连接中...")
        self._pending_connection = True

        pwd = self.password_input.text()
        self.ws_thread.connect(server, room, self.current_role, password=pwd)

    def disconnect_server(self):
        self._frame_timer.stop()
        self.latest_jpeg = None

        self.capture_thread.stop_capture()
        if self.capture_thread.isRunning():
            self.capture_thread.wait(1500)

        self.ws_thread._should_reconnect = False
        self.ws_thread.disconnect()
        if self.ws_thread.isRunning():
            self.ws_thread.wait(1500)

        self.connected = False
        self.view_stack.setCurrentIndex(0)
        self.viewer_label.clear()
        self.connect_btn.setText("📡 连接")
        self.connect_btn.setEnabled(True)
        self.status_dot.setStyleSheet("color:#666; font-size:10px;")
        log.info("已断开")

    def _on_connection_changed(self, connected: bool, status: str):
        self.connected = connected
        if connected:
            self.connect_btn.setText("🔴 断开")
            self.connect_btn.setEnabled(True)
            self._pending_connection = False
            self.status_dot.setStyleSheet("color:#4CAF50; font-size:10px;")

            if self.current_role == "host":
                scale_text = self.scale_combo.currentText()
                scale_map = {"25%": 0.25, "50%": 0.5, "75%": 0.75, "100%": 1.0}
                sf = scale_map.get(scale_text, 0.5)
                self.capture_thread.start_capture(
                    quality=self.quality_slider.value(),
                    fps=self.fps_spin.value(),
                    monitor=self.monitor_spin.value(),
                    scale_factor=sf,
                )
            else:
                self.view_stack.setCurrentIndex(1)
                self._frame_timer.start(50)
                self.latest_jpeg = None
        else:
            if self.ws_thread._should_reconnect:
                self.connect_btn.setText("⏳ 重连中...")
                self.connect_btn.setEnabled(False)
            else:
                self.connect_btn.setText("📡 连接")
                self.connect_btn.setEnabled(True)
                self._pending_connection = False
                self.status_dot.setStyleSheet("color:#f44336; font-size:10px;")

    def _on_mode_changed(self):
        is_host = self.mode_host.isChecked()
        is_viewer = self.mode_viewer.isChecked()
        self.host_frame.setEnabled(is_host)
        self.viewer_frame.setEnabled(is_viewer)
        if self.connected:
            self.disconnect_server()

    def _on_message(self, msg: dict):
        t = msg.get("type")

        if t == "frame":
            data = msg.get("data", "")
            if data:
                try:
                    self.latest_jpeg = base64.b64decode(data)
                except:
                    pass

        elif t == "chat":
            self._on_chat_message(msg.get("text", ""), msg.get("name", "未知"))

        elif t == "clipboard":
            text = msg.get("text", "")
            if text:
                try:
                    QApplication.clipboard().setText(text)
                except:
                    pass

        elif t == "input":
            self._handle_remote_input(msg.get("event"), msg.get("data", {}))

        elif t == "file_chunk":
            fid = msg.get("file_id", "")
            chunk_b64 = msg.get("chunk", "")
            final = msg.get("final", False)
            if fid not in self._file_buffers:
                self._file_buffers[fid] = bytearray()
            if chunk_b64:
                self._file_buffers[fid].extend(base64.b64decode(chunk_b64))
            if final:
                size = len(self._file_buffers[fid])
                log.info(f"文件接收完成: {size/1024:.0f}KB")
                self._file_buffers.pop(fid, None)

        elif t == "file_meta":
            fname = msg.get("name", "")
            fsize = msg.get("size", 0)
            self.status_dot.setToolTip(f"📁 收到: {fname}")
            self.ws_thread.send({"type": "file_accept", "file_id": msg.get("file_id")})

        elif t == "viewer_joined":
            log.info(f"观察者加入: {msg.get('viewer_id')}")
        elif t == "host_ready":
            log.info("主机就绪")
        elif t == "host_left":
            self.view_stack.setCurrentIndex(0)
            QMessageBox.information(self, "断开", "远程主机已断开")
        elif t == "error":
            self.status_dot.setToolTip(f"❌ {msg.get('msg')}")
            QMessageBox.warning(self, "错误", msg.get("msg", ""))

    def _display_latest_frame(self):
        if not self.latest_jpeg or self.current_role != "viewer":
            return
        try:
            pm = QPixmap()
            pm.loadFromData(self.latest_jpeg, "JPEG")
            if pm.isNull():
                return
            self.remote_resolution = (pm.width(), pm.height())

            mode = self.scale_mode.currentText()
            ls = self.viewer_label.size()

            if mode == "原始":
                scaled = pm
            elif mode == "拉伸":
                scaled = pm.scaled(ls, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            elif mode == "适应宽度":
                w = ls.width()
                h = int(pm.height() * w / max(pm.width(), 1))
                scaled = pm.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            else:
                scaled = pm.scaled(ls, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            self.viewer_label.setPixmap(scaled)

            self.frame_count += 1
            elapsed = time.time() - self.fps_timer_elapsed
            if elapsed >= 2:
                self.current_fps = self.frame_count / elapsed
                self.fps_timer_elapsed = time.time()
                self.frame_count = 0

            if self.frame_count % 5 == 0:
                rx, ry = self.remote_resolution
                self.viewer_info.setText(f"{rx}×{ry} | {self.current_fps:.0f}fps | {scaled.width()}×{scaled.height()}")

        except:
            pass

    def _on_frame_captured(self, jpeg_bytes: bytes):
        send_time = time.time()
        self.capture_thread.add_send_time(send_time)
        b64 = base64.b64encode(jpeg_bytes).decode()
        self.ws_thread.send({
            "type": "frame", "data": b64,
            "timestamp": int(send_time * 1000),
        })

        if self.capture_thread.auto_adapt:
            lat = self.capture_thread.get_avg_latency()
            if lat > 0.3:
                new_q = max(15, self.capture_thread.quality - 5)
                if new_q != self.capture_thread.quality:
                    self.capture_thread.set_quality(new_q)
                    self.quality_slider.setValue(new_q)
            elif lat < 0.08 and self.capture_thread.quality < 60:
                new_q = min(70, self.capture_thread.quality + 3)
                if new_q != self.capture_thread.quality:
                    self.capture_thread.set_quality(new_q)
                    self.quality_slider.setValue(new_q)

    def _update_status_bar(self):
        if self.connected:
            self.tb_quality.setText(f"{self.capture_thread.quality}p" if self.current_role == "host" else "")
            self.tb_fps.setText(f"{int(self.current_fps)}fps" if self.current_role == "viewer" else
                                f"{self.fps_spin.value()}fps")
        else:
            self.tb_quality.setText("")
            self.tb_fps.setText("")

    # ==================== 预设 ====================

    def _set_preset(self, quality, fps, scale_pct):
        self.quality_slider.setValue(quality)
        self.fps_spin.setValue(fps)
        scale_map = {25: 0, 50: 1, 80: 3}
        self.scale_combo.setCurrentIndex(scale_map.get(scale_pct, 1))

        for b in [self.btn_fast, self.btn_balanced, self.btn_hd]:
            b.setChecked(False)
        if quality <= 25:
            self.btn_fast.setChecked(True)
        elif quality <= 55:
            self.btn_balanced.setChecked(True)
        else:
            self.btn_hd.setChecked(True)

    # ==================== 工具栏 ====================

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_btn.setText("⛶ 全屏")
            self.toolbar.show()
        else:
            self.showFullScreen()
            self.fullscreen_btn.setText("✕ 退出全屏")
            self.toolbar.hide()

    # ==================== 聊天 ====================

    def _toggle_chat(self, visible: bool):
        self.chat_widget.setVisible(visible)
        self.btn_chat.setText("✕ 聊天" if visible else "💬 聊天")

    def _send_chat(self):
        text = self.chat_input.text().strip()
        if not text or not self.connected:
            return
        target = "host" if self.current_role == "viewer" else "all"
        self.ws_thread.send({"type": "chat", "text": text, "target": target})
        name = "我" if self.current_role == "viewer" else "被控端"
        self.chat_display.append(f"<b style='color:#4CAF50;'>{name}:</b> {text}")
        self.chat_input.clear()

    def _on_chat_message(self, text: str, name: str):
        self.chat_display.append(f"<b style='color:#2196F3;'>{name}:</b> {text}")
        if not self.chat_widget.isVisible():
            self.btn_chat.setStyleSheet(
                "QPushButton { background: #f44336; color: white; border: none; border-radius: 4px; padding: 6px 10px; }")

    # ==================== 文件传输 ====================

    def _show_file_dialog(self):
        if not self.connected:
            QMessageBox.information(self, "提示", "请先连接")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要发送的文件")
        if paths:
            self._send_files(paths)

    def _send_files(self, paths: list):
        for fp in paths:
            fname = os.path.basename(fp)
            fsize = os.path.getsize(fp)
            fid = f"f{int(time.time() * 1000)}"

            target = "host" if self.current_role == "viewer" else "viewer"
            self.ws_thread.send({
                "type": "file_meta", "file_id": fid,
                "name": fname, "size": fsize, "target": target,
            })

            CHUNK = 64 * 1024
            offset = 0
            with open(fp, "rb") as f:
                while offset < fsize:
                    chunk = f.read(CHUNK)
                    b64 = base64.b64encode(chunk).decode()
                    final = (offset + len(chunk)) >= fsize
                    self.ws_thread.send({
                        "type": "file_chunk", "file_id": fid,
                        "chunk": b64, "offset": offset,
                        "final": final, "target": target,
                    })
                    offset += len(chunk)

            log.info(f"已发送: {fname} ({fsize/1024:.0f}KB)")

    # ==================== 隐私屏 ====================

    def _toggle_privacy(self, checked: bool):
        self.capture_thread.privacy_mode = checked

    # ==================== 鼠标事件 ====================

    def _viewer_mouse_event(self, event, event_type: str):
        if not self.connected or self.current_role != "viewer":
            return
        rx, ry = self._map_to_remote(event.x(), event.y())
        btn_map = {1: "left", 2: "right", 4: "middle"}
        data = {"x": rx, "y": ry, "button": btn_map.get(event.button(), "left")}
        self.ws_thread.send({"type": "input", "event": event_type, "data": data})

    def _viewer_mouse_move(self, event):
        if not self.connected or self.current_role != "viewer":
            return
        rx, ry = self._map_to_remote(event.x(), event.y())
        now = time.time()
        if now - self._last_mouse_send > 0.05:
            self._last_mouse_send = now
            self.ws_thread.send({
                "type": "input", "event": "mousemove",
                "data": {"x": rx, "y": ry},
            })

    def _viewer_wheel(self, event):
        if not self.connected or self.current_role != "viewer":
            return
        rx, ry = self._map_to_remote(event.x(), event.y())
        self.ws_thread.send({
            "type": "input", "event": "scroll",
            "data": {"x": rx, "y": ry, "amount": event.angleDelta().y() // 120},
        })

    def _viewer_keypress(self, key_text: str):
        if not self.connected or self.current_role != "viewer":
            return
        self.ws_thread.send({
            "type": "input", "event": "keypress", "data": {"key": key_text},
        })

    def _map_to_remote(self, label_x: int, label_y: int):
        if not self.viewer_label.pixmap():
            return (label_x, label_y)
        pix = self.viewer_label.pixmap()
        pw, ph = pix.width(), pix.height()
        lw, lh = self.viewer_label.width(), self.viewer_label.height()
        if pw == 0 or ph == 0:
            return (label_x, label_y)
        x_off = (lw - pw) // 2
        y_off = (lh - ph) // 2
        rx = int((label_x - x_off) / pw * self.remote_resolution[0])
        ry = int((label_y - y_off) / ph * self.remote_resolution[1])
        return (max(0, rx), max(0, ry))

    def _handle_remote_input(self, event: str, data: dict):
        if not pyautogui:
            return
        try:
            if event == "mousemove":
                pyautogui.moveTo(data["x"], data["y"])
            elif event == "click":
                pyautogui.click(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "mousedown":
                pyautogui.mouseDown(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "mouseup":
                pyautogui.mouseUp(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "scroll":
                pyautogui.scroll(data.get("amount", 0), x=data["x"], y=data["y"])
            elif event == "keypress" and Controller and Key:
                kb = Controller()
                key = data.get("key", "")
                special = {
                    "enter": Key.enter, "return": Key.enter,
                    "tab": Key.tab, "escape": Key.esc, "esc": Key.esc,
                    "backspace": Key.backspace, "space": Key.space,
                    "ctrl": Key.ctrl, "alt": Key.alt, "shift": Key.shift,
                    "up": Key.up, "down": Key.down,
                    "left": Key.left, "right": Key.right,
                    "delete": Key.delete, "home": Key.home, "end": Key.end,
                    "pageup": Key.page_up, "pagedown": Key.page_down,
                }
                if len(key) == 1:
                    kb.press(key)
                    kb.release(key)
                elif key.lower() in special:
                    kb.press(special[key.lower()])
                    kb.release(special[key.lower()])
        except Exception as e:
            log.error(f"输入失败: {e}")

    def _qt_key_to_name(self, qt_key):
        m = {
            Qt.Key_Enter: "enter", Qt.Key_Return: "enter",
            Qt.Key_Tab: "tab", Qt.Key_Escape: "escape",
            Qt.Key_Backspace: "backspace", Qt.Key_Space: "space",
            Qt.Key_Up: "up", Qt.Key_Down: "down",
            Qt.Key_Left: "left", Qt.Key_Right: "right",
            Qt.Key_Delete: "delete", Qt.Key_Home: "home", Qt.Key_End: "end",
            Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown",
            Qt.Key_Control: "ctrl", Qt.Key_Alt: "alt", Qt.Key_Shift: "shift",
            Qt.Key_CapsLock: "capslock",
        }
        if qt_key in m:
            return m[qt_key]
        return chr(qt_key) if 32 <= qt_key <= 126 else ""

    # ==================== 窗口事件 ====================

    def closeEvent(self, event):
        if self.current_role == "host" and self.connected:
            event.ignore()
            self.hide()
            self.tray_icon.show()
            self.tray_icon.showMessage("RemoteControl", "后台运行中", QSystemTrayIcon.Information, 2000)
            return
        self._frame_timer.stop()
        self.capture_thread.stop_capture()
        self.capture_thread.wait(1000)
        self.ws_thread._should_reconnect = False
        self.ws_thread.disconnect()
        self.ws_thread.wait(1000)
        event.accept()


# ==================== 入口 ====================

def main():
    QApplication.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(26, 26, 46))
    palette.setColor(QPalette.WindowText, QColor(200, 200, 212))
    palette.setColor(QPalette.Base, QColor(15, 52, 96))
    palette.setColor(QPalette.Text, QColor(224, 224, 255))
    palette.setColor(QPalette.Button, QColor(22, 33, 62))
    palette.setColor(QPalette.ButtonText, QColor(200, 200, 212))
    palette.setColor(QPalette.Highlight, QColor(76, 175, 80))
    QApplication.setPalette(palette)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    missing = []
    if not websocket:
        missing.append("websocket-client")
    if not mss:
        missing.append("mss")
    if missing:
        print(f"缺少: {', '.join(missing)}")
        sys.exit(1)

    w = RemoteControlApp()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
