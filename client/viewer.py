#!/usr/bin/env python3
"""
Remote Control - Viewer (远程查看/控制端)
接收画面并显示，转发鼠标键盘事件
"""

import json
import time
import base64
import argparse
import logging
import threading

import websocket
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel,
                             QVBoxLayout, QWidget, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QByteArray
from PyQt5.QtGui import QPixmap, QImage, QWheelEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("viewer")


class FrameReceiver(QMainWindow):
    """远程画面查看窗口"""

    frame_received = pyqtSignal(bytes)

    def __init__(self, server_url: str, room: str = "default", fullscreen: bool = False):
        super().__init__()
        self.server_url = server_url
        self.room = room
        self.ws: websocket.WebSocketApp = None
        self.running = False
        self.connected = False

        # UI
        self.setWindowTitle("Remote Control Viewer")
        self.resize(1280, 720)

        # 画面显示标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1a1a1a;")
        self.image_label.setMouseTracking(True)

        # 连接状态标签
        self.status_label = QLabel("连接中...")
        self.status_label.setStyleSheet("color: #888; padding: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image_label)
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 信号连接
        self.frame_received.connect(self.display_frame)

        # 鼠标位置追踪
        self.last_mouse_pos = None
        self.display_size = (1280, 720)
        self.remote_resolution = (1920, 1080)  # 远程画面分辨率，由第一帧决定

        self.capture_start_time = time.time()
        self.frame_count = 0
        self.fps = 0

        # 定时更新 FPS 显示
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_status)
        self.fps_timer.start(2000)

        # 全屏模式
        self.is_fullscreen = fullscreen

    def display_frame(self, data: bytes):
        """显示接收到的画面帧"""
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(data, "JPEG")

            if pixmap.isNull():
                return

            self.remote_resolution = (pixmap.width(), pixmap.height())

            # 缩放以适应窗口
            scaled = pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)

            self.frame_count += 1
            elapsed = time.time() - self.capture_start_time
            if elapsed >= 2:
                self.fps = self.frame_count / elapsed
                self.capture_start_time = time.time()
                self.frame_count = 0

        except Exception as e:
            log.error(f"显示帧失败: {e}")

    def update_status(self):
        """更新状态栏"""
        if self.connected:
            self.status_label.setText(
                f"已连接 | {self.fps:.1f} FPS | "
                f"{self.remote_resolution[0]}x{self.remote_resolution[1]} | "
                f"房间: {self.room}"
            )
            self.status_label.setStyleSheet("color: #4CAF50; padding: 4px;")
        else:
            self.status_label.setText("未连接")
            self.status_label.setStyleSheet("color: #f44336; padding: 4px;")

    # ---- 鼠标事件 ----
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.send_input("mousedown", self._mouse_data(event))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.send_input("mouseup", self._mouse_data(event))

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.last_mouse_pos:
            dx = abs(event.x() - self.last_mouse_pos[0])
            dy = abs(event.y() - self.last_mouse_pos[1])
            if dx > 2 or dy > 2:  # 降低发送频率
                self.send_input("mousemove", self._mouse_data(event))
                self.last_mouse_pos = (event.x(), event.y())
        else:
            self.last_mouse_pos = (event.x(), event.y())

    def wheelEvent(self, event: QWheelEvent):
        self.send_input("scroll", {
            "x": event.x(),
            "y": event.y(),
            "amount": event.angleDelta().y() // 120,
        })

    def _mouse_data(self, event):
        """转换鼠标坐标到远程分辨率"""
        label_size = self.image_label.size()
        if self.image_label.pixmap():
            pm_size = self.image_label.pixmap().size()
            # 计算偏移（居中对齐）
            x_off = (label_size.width() - pm_size.width()) // 2
            y_off = (label_size.height() - pm_size.height()) // 2
            # 映射到远程分辨率
            if pm_size.width() > 0 and pm_size.height() > 0:
                rx = int((event.x() - x_off) / pm_size.width() * self.remote_resolution[0])
                ry = int((event.y() - y_off) / pm_size.height() * self.remote_resolution[1])
                return {"x": max(0, rx), "y": max(0, ry)}

        return {"x": event.x(), "y": event.y()}

    # ---- 键盘事件 ----
    def keyPressEvent(self, event):
        key = self._key_name(event.key())
        if key:
            self.send_input("keypress", {"key": key})
        super().keyPressEvent(event)

    def _key_name(self, qt_key):
        """Qt 键码转键名"""
        mapping = {
            Qt.Key_Enter: "enter", Qt.Key_Return: "enter",
            Qt.Key_Tab: "tab", Qt.Key_Escape: "escape",
            Qt.Key_Backspace: "backspace", Qt.Key_Space: "space",
            Qt.Key_Up: "up", Qt.Key_Down: "down",
            Qt.Key_Left: "left", Qt.Key_Right: "right",
            Qt.Key_Delete: "delete", Qt.Key_Home: "home", Qt.Key_End: "end",
            Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown",
            Qt.Key_Control: "ctrl", Qt.Key_Alt: "alt", Qt.Key_Shift: "shift",
        }
        if qt_key in mapping:
            return mapping[qt_key]
        # ASCII 字符
        char = chr(qt_key) if 32 <= qt_key <= 126 else ""
        return char

    def send_input(self, event: str, data: dict):
        """发送输入事件到服务器"""
        if not self.connected:
            return
        try:
            msg = json.dumps({
                "type": "input",
                "event": event,
                "data": data,
            })
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(msg)
        except Exception as e:
            log.error(f"发送输入事件失败: {e}")

    # ---- WebSocket ----
    def on_message(self, ws, message):
        try:
            msg = json.loads(message)
            msg_type = msg.get("type")

            if msg_type == "registered":
                self.connected = True
                log.info(f"注册成功! ID: {msg.get('peer_id')}")
                QApplication.instance().postEvent(
                    self, _StatusEvent("已连接 - 等待主机画面...")
                )

            elif msg_type == "frame":
                data = msg.get("data", "")
                if data:
                    img_bytes = base64.b64decode(data)
                    self.frame_received.emit(img_bytes)

            elif msg_type == "host_ready":
                log.info("主机已就绪")
                QApplication.instance().postEvent(
                    self, _StatusEvent("主机就绪，正在接收画面...")
                )

            elif msg_type == "host_left":
                log.warning("主机已断开")
                self.connected = False
                QApplication.instance().postEvent(
                    self, _StatusEvent("主机已断开连接")
                )

            elif msg_type == "pong":
                pass

            elif msg_type == "error":
                log.error(f"服务器错误: {msg.get('msg')}")

        except json.JSONDecodeError:
            pass

    def on_error(self, ws, error):
        log.error(f"WebSocket 错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        log.warning(f"连接关闭: {close_status_code}")
        self.connected = False
        QApplication.instance().postEvent(
            self, _StatusEvent("连接已关闭")
        )

    def on_open(self, ws):
        log.info(f"已连接到服务器: {self.server_url}")
        self.send_msg({
            "type": "register",
            "role": "viewer",
            "room": self.room,
        })

    def send_msg(self, data: dict):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(data))
        except Exception as e:
            log.error(f"发送失败: {e}")

    def connect_to_server(self):
        """连接服务器"""
        self.ws = websocket.WebSocketApp(
            self.server_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        # 在独立线程中运行 WebSocket
        threading.Thread(
            target=self.ws.run_forever,
            args=(),
            kwargs={"ping_interval": 30, "ping_timeout": 10},
            daemon=True,
        ).start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.display_size = (event.size().width(), event.size().height())


# ---- 自定义事件（用于线程间通信） ----
class _StatusEvent:
    def __init__(self, text):
        self.text = text


class StatusHandler(QApplication):
    def event(self, event):
        if isinstance(event, _StatusEvent):
            for widget in self.topLevelWidgets():
                if isinstance(widget, FrameReceiver):
                    widget.status_label.setText(event.text)
            return True
        return super().event(event)


def main():
    parser = argparse.ArgumentParser(description="Remote Control - Viewer")
    parser.add_argument("--server", default="ws://47.92.148.99:8000", help="中继服务器地址")
    parser.add_argument("--room", default="default", help="房间名")
    parser.add_argument("--fullscreen", action="store_true", help="全屏模式")
    args = parser.parse_args()

    log.info(f"启动 Viewer 模式")
    log.info(f"服务器: {args.server}")
    log.info(f"房间: {args.room}")

    app = StatusHandler(sys.argv)
    window = FrameReceiver(
        server_url=args.server,
        room=args.room,
        fullscreen=args.fullscreen,
    )
    window.show()
    window.connect_to_server()

    if args.fullscreen:
        window.showFullScreen()

    sys.exit(app.exec_())


if __name__ == "__main__":
    import sys
    main()
