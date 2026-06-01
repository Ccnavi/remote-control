#!/usr/bin/env python3
"""
Remote Control - 远程控制客户端
支持主控/被控双模式，图形化界面
"""

import sys
import json
import time
import base64
import threading
import logging
import io
import os
from datetime import datetime

# 第三方库
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QGroupBox,
    QTextEdit, QMessageBox, QSystemTrayIcon, QMenu, QAction,
    QSplitter, QFrame, QSlider, QCheckBox, QSpinBox,
    QTabWidget, QStatusBar, QGridLayout, QRadioButton,
    QButtonGroup, QStackedWidget,
)
from PyQt5.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSize, QRect,
)
from PyQt5.QtGui import (
    QPixmap, QImage, QIcon, QFont, QColor, QPalette,
    QWheelEvent, QCursor, QPainter,
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
    from PIL import Image
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

# ============================================================
# 配置
# ============================================================

APP_NAME = "RemoteControl"
APP_VERSION = "1.0.0"
DEFAULT_SERVER = "ws://47.92.148.99:8500"
DEFAULT_ROOM = "default"

# ============================================================
# 日志
# ============================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rc")

# ============================================================
# 工作线程
# ============================================================

class WebSocketThread(QThread):
    """WebSocket 连接线程"""
    message_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.server_url = ""
        self.room = ""
        self.role = "viewer"  # "host" or "viewer"
        self.ws = None
        self.running = False
        self._should_reconnect = False
        self._reconnect_delay = 3

    def connect(self, server_url: str, room: str, role: str):
        self.server_url = server_url
        self.room = room
        self.role = role
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

    def send(self, data: dict):
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
                self.connection_changed.emit(False, f"断线重连中 ({self._reconnect_delay}s)")
                time.sleep(self._reconnect_delay)

        self.connection_changed.emit(False, "已断开")

    def _on_open(self, ws):
        log.info(f"WebSocket 已连接: {self.server_url}")
        self.connection_changed.emit(True, f"已连接 ({self.role})")
        # 注册
        self.send({
            "type": "register",
            "role": self.role,
            "room": self.room,
        })

    def _on_message(self, ws, message):
        try:
            msg = json.loads(message)
            self.message_received.emit(msg)
        except json.JSONDecodeError:
            pass

    def _on_error(self, ws, error):
        log.error(f"WebSocket 错误: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        log.warning("WebSocket 连接关闭")
        self.running = False


class ScreenCaptureThread(QThread):
    """屏幕捕获线程（仅被控模式）"""
    frame_captured = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self.running = False
        self.quality = 60
        self.fps = 15
        self.monitor = 1
        self.scale_factor = 0.5  # 默认 50%

    def start_capture(self, quality=60, fps=15, monitor=1, scale_factor=0.5):
        self.quality = quality
        self.fps = fps
        self.monitor = monitor
        self.scale_factor = scale_factor
        self.running = True
        self.start()

    def stop_capture(self):
        self.running = False

    def run(self):
        if not mss or not Image:
            log.error("缺少 mss 或 Pillow 库，无法捕获屏幕")
            return

        interval = 1.0 / self.fps
        with mss.mss() as sct:
            while self.running:
                try:
                    start = time.time()
                    monitor = sct.monitors[self.monitor]
                    img = sct.grab(monitor)
                    pil_img = Image.frombytes("RGB", img.size, img.rgb)

                    # 缩放
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
                    log.error(f"屏幕捕获失败: {e}")
                    time.sleep(1)


# ============================================================
# 主窗口 UI
# ============================================================

class RemoteControlApp(QMainWindow):
    """远程控制主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 750)
        self.setMinimumSize(800, 500)

        # 状态
        self.current_role = "viewer"  # "host" | "viewer"
        self.connected = False
        self.remote_resolution = (1920, 1080)
        self.disp_size = (1100, 750)
        self.frame_count = 0
        self.fps_timer_elapsed = time.time()
        self.current_fps = 0

        # 线程
        self.ws_thread = WebSocketThread()
        self.ws_thread.message_received.connect(self._on_message)
        self.ws_thread.connection_changed.connect(self._on_connection_changed)

        self.capture_thread = ScreenCaptureThread()
        self.capture_thread.frame_captured.connect(self._on_frame_captured)

        # 当前帧缓存
        self.latest_jpeg = None

        # 构建 UI
        self._build_ui()

        # 定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status_bar)
        self.status_timer.start(2000)

        # 连接状态防抖
        self._pending_connection = False

    # ---------- UI 构建 ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ========== 左侧面板 ==========
        left_panel = QFrame()
        left_panel.setFixedWidth(280)
        left_panel.setStyleSheet("""
            QFrame { background: #2b2b3d; border-right: 1px solid #3d3d5c; }
            QGroupBox { color: #ccc; border: 1px solid #3d3d5c; border-radius: 6px;
                        margin-top: 12px; font-size: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #aaa; font-size: 12px; }
            QLineEdit, QComboBox { background: #1e1e2e; color: #eee; border: 1px solid #3d3d5c;
                                   border-radius: 4px; padding: 6px 8px; font-size: 13px; }
            QPushButton { border-radius: 4px; padding: 8px; font-size: 13px; font-weight: bold; }
            QRadioButton { color: #ccc; font-size: 13px; spacing: 6px; }
            QSpinBox { background: #1e1e2e; color: #eee; border: 1px solid #3d3d5c;
                       border-radius: 4px; padding: 4px; }
            QCheckBox { color: #ccc; font-size: 12px; }
        """)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 10, 12, 10)
        left_layout.setSpacing(8)

        # 标题
        title = QLabel("🔗 远程控制")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff; padding: 8px 0;")
        left_layout.addWidget(title)

        # ====== 连接设置 ======
        conn_group = QGroupBox("连接设置")
        conn_layout = QVBoxLayout(conn_group)
        conn_layout.setSpacing(6)

        conn_layout.addWidget(QLabel("服务器地址:"))
        self.server_input = QLineEdit(DEFAULT_SERVER)
        conn_layout.addWidget(self.server_input)

        conn_layout.addWidget(QLabel("房间名:"))
        self.room_input = QLineEdit(DEFAULT_ROOM)
        conn_layout.addWidget(self.room_input)

        # 模式选择
        conn_layout.addWidget(QLabel("模式:"))
        mode_layout = QHBoxLayout()
        self.mode_viewer = QRadioButton("👁 主控端")
        self.mode_host = QRadioButton("🖥 被控端")
        self.mode_viewer.setChecked(True)
        mode_layout.addWidget(self.mode_viewer)
        mode_layout.addWidget(self.mode_host)
        conn_layout.addLayout(mode_layout)
        self.mode_viewer.toggled.connect(self._on_mode_changed)
        self.mode_host.toggled.connect(self._on_mode_changed)

        # 连接按钮
        self.connect_btn = QPushButton("📡 连接")
        self.connect_btn.setStyleSheet("""
            QPushButton { background: #4CAF50; color: white; }
            QPushButton:hover { background: #45a049; }
            QPushButton:disabled { background: #555; color: #888; }
        """)
        self.connect_btn.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self.connect_btn)

        left_layout.addWidget(conn_group)

        # ====== 被控端设置 ======
        host_group = QGroupBox("被控端设置")
        host_layout = QVBoxLayout(host_group)
        host_layout.setSpacing(6)

        # 速度模式预设
        speed_layout = QHBoxLayout()
        self.btn_fast = QPushButton("🚀 流畅")
        self.btn_balanced = QPushButton("⚖️ 均衡")
        self.btn_quality = QPushButton("🎨 高清")
        self.btn_fast.setStyleSheet("background:#4CAF50; color:white;")
        self.btn_balanced.setStyleSheet("background:#FF9800; color:white;")
        self.btn_quality.setStyleSheet("background:#f44336; color:white;")
        self.btn_fast.clicked.connect(lambda: self._set_preset(20, 5, 50))
        self.btn_balanced.clicked.connect(lambda: self._set_preset(40, 10, 80))
        self.btn_quality.clicked.connect(lambda: self._set_preset(70, 20, 100))
        speed_layout.addWidget(self.btn_fast)
        speed_layout.addWidget(self.btn_balanced)
        speed_layout.addWidget(self.btn_quality)
        host_layout.addLayout(speed_layout)

        self.preset_label = QLabel("当前: 均衡模式")
        self.preset_label.setStyleSheet("color:#FF9800; font-weight:bold;")
        host_layout.addWidget(self.preset_label)

        # 画质
        q_layout = QHBoxLayout()
        q_layout.addWidget(QLabel("画质:"))
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(10, 95)
        self.quality_slider.setValue(40)
        self.quality_label = QLabel("40")
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_label.setText(str(v)))
        q_layout.addWidget(self.quality_slider)
        q_layout.addWidget(self.quality_label)
        host_layout.addLayout(q_layout)

        f_layout = QHBoxLayout()
        f_layout.addWidget(QLabel("帧率:"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        self.fps_spin.setValue(10)
        f_layout.addWidget(self.fps_spin)
        host_layout.addLayout(f_layout)

        s_layout = QHBoxLayout()
        s_layout.addWidget(QLabel("缩放:"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["原始", "75%", "50% (推荐)", "25%"])
        self.scale_combo.setCurrentIndex(2)  # 50%
        s_layout.addWidget(self.scale_combo)
        host_layout.addLayout(s_layout)

        m_layout = QHBoxLayout()
        m_layout.addWidget(QLabel("显示器:"))
        self.monitor_spin = QSpinBox()
        self.monitor_spin.setRange(1, 4)
        self.monitor_spin.setValue(1)
        m_layout.addWidget(self.monitor_spin)
        host_layout.addLayout(m_layout)

        host_group.setEnabled(False)
        left_layout.addWidget(host_group)

        # ====== 快捷键 ======
        tip_group = QGroupBox("快捷键")
        tip_layout = QVBoxLayout(tip_group)
        tip_layout.setSpacing(4)
        tip_layout.addWidget(QLabel("Ctrl+Alt+Q  退出全屏"))
        tip_layout.addWidget(QLabel("Ctrl+Alt+X  断开连接"))
        left_layout.addWidget(tip_group)

        # 弹性空间
        left_layout.addStretch()

        # 版本信息
        ver_label = QLabel(f"v{APP_VERSION}")
        ver_label.setStyleSheet("color: #555; font-size: 10px;")
        ver_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(ver_label)

        # ========== 右侧画面区 ==========
        right_panel = QFrame()
        right_panel.setStyleSheet("background: #111;")

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 画面显示
        self.viewer_label = RemoteScreenLabel()
        self.viewer_label.setAlignment(Qt.AlignCenter)
        self.viewer_label.setStyleSheet("background: #1a1a1a;")
        self.viewer_label.setMouseTracking(True)
        self.viewer_label.frame_widget = self

        # 连接提示文字
        self.placeholder = QLabel("⚡ 点击「连接」按钮\n\n选择主控端模式查看远程画面\n选择被控端模式共享本机屏幕")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color: #555; font-size: 16px; background: transparent;")

        # 用 QStackedWidget 切换画面和提示
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.placeholder)  # index 0
        self.view_stack.addWidget(self.viewer_label)  # index 1
        right_layout.addWidget(self.view_stack)

        # 状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666; padding: 4px 8px; font-size: 12px;")
        self.status_label.setFixedHeight(28)
        right_layout.addWidget(self.status_label)

        # 添加到主布局
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)

        # 初始化预设显示
        self._set_preset(40, 10, 80)

    # ---------- 事件处理 ----------

    def _set_preset(self, quality, fps, scale_pct):
        """设置速度预设"""
        self.quality_slider.setValue(quality)
        self.fps_spin.setValue(fps)
        scale_map = {50: 2, 80: 1, 100: 0}  # scale_pct -> combo index
        idx = scale_map.get(scale_pct, 2)
        self.scale_combo.setCurrentIndex(idx)

        names = {20: "🚀 流畅", 40: "⚖️ 均衡", 70: "🎨 高清"}
        colors = {20: "#4CAF50", 40: "#FF9800", 70: "#f44336"}
        name = names.get(quality, "自定义")
        color = colors.get(quality, "#888")
        self.preset_label.setText(f"当前: {name}")
        self.preset_label.setStyleSheet(f"color:{color}; font-weight:bold;")

    def _on_mode_changed(self):
        """模式切换"""
        is_host = self.mode_host.isChecked()
        self.findChild(QGroupBox, "").setEnabled(is_host)
        # 找到 host_group（第二个 QGroupBox）
        for w in self.findChildren(QGroupBox):
            if w.title() == "被控端设置":
                w.setEnabled(is_host)
                break

        # 如果已连接则断开
        if self.connected:
            self._toggle_connection()

    def _toggle_connection(self):
        """连接/断开切换"""
        if self._pending_connection:
            return

        if self.connected or (self.ws_thread.isRunning() and self.ws_thread.running):
            # 断开
            self._pending_connection = True
            self.disconnect_server()
            self._pending_connection = False
            return

        # 连接
        server = self.server_input.text().strip()
        room = self.room_input.text().strip()
        if not server:
            QMessageBox.warning(self, "错误", "请输入服务器地址")
            return
        if not room:
            room = DEFAULT_ROOM

        self.current_role = "host" if self.mode_host.isChecked() else "viewer"
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("⏳ 连接中...")
        self._pending_connection = True

        self.ws_thread.connect(server, room, self.current_role)

    def connect_server(self):
        """外部调用连接"""
        self._toggle_connection()

    def disconnect_server(self):
        """断开连接（安全清理所有线程）"""
        # 先停定时器
        self._stop_frame_timer()
        self.latest_jpeg = None

        # 停捕获线程
        self.capture_thread.stop_capture()
        if self.capture_thread.isRunning():
            self.capture_thread.wait(2000)

        # 断开 WebSocket
        self.ws_thread._should_reconnect = False
        self.ws_thread.disconnect()
        if self.ws_thread.isRunning():
            self.ws_thread.wait(2000)

        self.connected = False

        if self.current_role == "viewer":
            self.view_stack.setCurrentIndex(0)
            self.viewer_label.clear()
            self.viewer_label.setPixmap(QPixmap())

        self.connect_btn.setText("📡 连接")
        self.connect_btn.setEnabled(True)
        self.status_label.setText("已断开")

    def _on_connection_changed(self, connected: bool, status_text: str):
        """连接状态变化"""
        self.connected = connected
        if connected:
            self.connect_btn.setText("🔴 断开")
            self.connect_btn.setEnabled(True)
            self.status_label.setText(status_text)
            self._pending_connection = False

            # 如果是被控端模式，启动屏幕捕获
            if self.current_role == "host":
                scale_text = self.scale_combo.currentText()
                scale_map = {"原始": 1.0, "75%": 0.75, "50% (推荐)": 0.5, "25%": 0.25}
                sf = scale_map.get(scale_text, 0.5)
                self.capture_thread.start_capture(
                    quality=self.quality_slider.value(),
                    fps=self.fps_spin.value(),
                    monitor=self.monitor_spin.value(),
                    scale_factor=sf,
                )
            else:
                # 主控端，切换到画面显示，启动帧定时器
                self.view_stack.setCurrentIndex(1)
                self._start_frame_timer()
                self.latest_jpeg = None
        else:
            if self._should_reconnect():
                self.connect_btn.setText(f"⏳ {status_text}")
                self.connect_btn.setEnabled(False)
            else:
                self.connect_btn.setText("📡 连接")
                self.connect_btn.setEnabled(True)
                self._pending_connection = False

    def _should_reconnect(self) -> bool:
        return self.ws_thread._should_reconnect

    def _on_message(self, msg: dict):
        """收到 WebSocket 消息"""
        msg_type = msg.get("type")

        if msg_type == "registered":
            log.info(f"注册成功: {msg.get('role')} in room {msg.get('room')}")

        elif msg_type == "frame":
            data = msg.get("data", "")
            if data:
                try:
                    img_bytes = base64.b64decode(data)
                    self.latest_jpeg = img_bytes
                    self._display_frame(img_bytes)
                except Exception as e:
                    log.error(f"解码帧失败: {e}")

        elif msg_type == "viewer_joined":
            self.status_label.setText(f"👤 观察者 {msg.get('viewer_id', '?')} 已加入")
            log.info(f"观察者加入: {msg.get('viewer_id')}")

        elif msg_type == "host_ready":
            self.status_label.setText("🖥 主机就绪，等待画面...")
            log.info("主机就绪")

        elif msg_type == "host_left":
            self.status_label.setText("⚠️ 主机已断开")
            self.view_stack.setCurrentIndex(0)
            QMessageBox.information(self, "断开", "远程主机已断开连接")

        elif msg_type == "input":
            event = msg.get("event")
            data = msg.get("data", {})
            self._handle_remote_input(event, data)

        elif msg_type == "pong":
            pass
        elif msg_type == "error":
            self.status_label.setText(f"❌ 错误: {msg.get('msg')}")

    def _display_frame(self, jpeg_bytes: bytes):
        """缓存最新帧（由定时器拉取显示）"""
        if self.current_role != "viewer":
            return
        self.latest_jpeg = jpeg_bytes

    def _on_frame_captured(self, jpeg_bytes: bytes):
        """屏幕捕获完成（被控模式）"""
        # 发送到服务器
        b64 = base64.b64encode(jpeg_bytes).decode()
        self.ws_thread.send({
            "type": "frame",
            "data": b64,
            "timestamp": int(time.time() * 1000),
        })

    def _handle_remote_input(self, event: str, data: dict):
        """处理远程输入事件"""
        if not pyautogui:
            log.warning("缺少 pyautogui，无法处理远程输入")
            return

        try:
            if event == "mousemove":
                pyautogui.moveTo(data["x"], data["y"])
            elif event == "mousedown":
                pyautogui.mouseDown(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "mouseup":
                pyautogui.mouseUp(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "click":
                pyautogui.click(x=data["x"], y=data["y"], button=data.get("button", "left"))
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
                    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
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
            log.error(f"输入处理失败: {e}")

    def _update_status_bar(self):
        """更新状态栏"""
        if self.connected and self.current_role == "viewer":
            self.status_label.setText(
                f"🟢 {self.current_fps:.1f} FPS | "
                f"{self.remote_resolution[0]}×{self.remote_resolution[1]} | "
                f"房间: {self.room_input.text()}"
            )
        elif self.connected and self.current_role == "host":
            self.status_label.setText(
                f"🟢 正在共享屏幕 | "
                f"画质: {self.quality_slider.value()} | "
                f"帧率: {self.fps_spin.value()} FPS | "
                f"房间: {self.room_input.text()}"
            )

    # ---------- 鼠标/键盘事件转发（主控模式）----------

    def _viewer_mouse_event(self, event, event_type: str):
        """由 RemoteScreenLabel 调用的鼠标事件处理（坐标已相对 label）"""
        if not self.connected or self.current_role != "viewer":
            return

        # 映射坐标到远程分辨率
        rx, ry = self._map_to_remote(event.x(), event.y())
        btn_map = {1: "left", 2: "right", 4: "middle"}
        data = {
            "x": rx, "y": ry,
            "button": btn_map.get(event.button(), "left") if hasattr(event, 'button') else "left",
        }
        self.ws_thread.send({"type": "input", "event": event_type, "data": data})

    def _viewer_mouse_move(self, event):
        if not self.connected or self.current_role != "viewer":
            return
        rx, ry = self._map_to_remote(event.x(), event.y())
        # 限制发送频率用 last_mouse_pos
        now = time.time()
        if not hasattr(self, '_last_mouse_send') or now - self._last_mouse_send > 0.05:
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
        """将 QLabel 上的坐标映射到远程屏幕分辨率"""
        if not self.viewer_label.pixmap():
            return (label_x, label_y)

        pix = self.viewer_label.pixmap()
        pm_w, pm_h = pix.width(), pix.height()
        label_w = self.viewer_label.width()
        label_h = self.viewer_label.height()

        if pm_w == 0 or pm_h == 0:
            return (label_x, label_y)

        # 计算 QLabel 中居中的 pixmap 偏移
        x_off = (label_w - pm_w) // 2
        y_off = (label_h - pm_h) // 2

        # 映射到远程分辨率
        rx = int((label_x - x_off) / pm_w * self.remote_resolution[0])
        ry = int((label_y - y_off) / pm_h * self.remote_resolution[1])
        return (max(0, rx), max(0, ry))

    # 帧显示定时器（代替每帧实时更新，防卡死）
    def _start_frame_timer(self):
        if not hasattr(self, '_frame_timer') or self._frame_timer is None:
            self._frame_timer = QTimer()
            self._frame_timer.timeout.connect(self._display_latest_frame)
        self._frame_timer.start(50)  # 20fps 最多

    def _stop_frame_timer(self):
        if hasattr(self, '_frame_timer') and self._frame_timer:
            self._frame_timer.stop()

    def _display_latest_frame(self):
        """定时器拉取最新帧"""
        if not self.latest_jpeg:
            return
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(self.latest_jpeg, "JPEG")
            if pixmap.isNull():
                return

            self.remote_resolution = (pixmap.width(), pixmap.height())

            scaled = pixmap.scaled(
                self.viewer_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.viewer_label.setPixmap(scaled)

            self.frame_count += 1
            elapsed = time.time() - self.fps_timer_elapsed
            if elapsed >= 2:
                self.current_fps = self.frame_count / elapsed
                self.fps_timer_elapsed = time.time()
                self.frame_count = 0
        except Exception:
            pass  # 窗口销毁时忽略

    def _qt_key_to_name(self, qt_key):
        mapping = {
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
        if qt_key in mapping:
            return mapping[qt_key]
        char = chr(qt_key) if 32 <= qt_key <= 126 else ""
        return char

    # ---------- 窗口事件 ----------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.disp_size = (event.size().width(), event.size().height())

    def closeEvent(self, event):
        self._stop_frame_timer()
        self.capture_thread.stop_capture()
        self.capture_thread.wait(1000)
        self.ws_thread._should_reconnect = False
        self.ws_thread.disconnect()
        self.ws_thread.wait(1000)
        event.accept()


class RemoteScreenLabel(QLabel):
    """远程画面显示标签 - 鼠标事件直接转发"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame_widget = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

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


# ============================================================
# 入口
# ============================================================

def check_dependencies():
    missing = []
    if not websocket:
        missing.append("websocket-client")
    if not mss:
        missing.append("mss")
    if not Image:
        missing.append("Pillow")
    if not pyautogui:
        missing.append("pyautogui")

    if missing:
        print(f"缺少依赖库: {', '.join(missing)}")
        print("请运行: pip install " + " ".join(missing))
        return False
    return True


def main():
    # 暗色主题
    QApplication.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 46))
    palette.setColor(QPalette.WindowText, QColor(221, 221, 221))
    palette.setColor(QPalette.Base, QColor(25, 25, 40))
    palette.setColor(QPalette.Text, QColor(221, 221, 221))
    palette.setColor(QPalette.Button, QColor(45, 45, 65))
    palette.setColor(QPalette.ButtonText, QColor(221, 221, 221))
    palette.setColor(QPalette.Highlight, QColor(76, 175, 80))
    QApplication.setPalette(palette)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    # 检查依赖
    if not check_dependencies():
        sys.exit(1)

    window = RemoteControlApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
