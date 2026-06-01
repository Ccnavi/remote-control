#!/usr/bin/env python3
"""
Remote Control - Host (画面共享端)
捕获屏幕并通过 WebSocket 发送到中继服务器
"""

import io
import json
import time
import argparse
import logging
import threading
from queue import Queue
from dataclasses import dataclass, field

import mss
import mss.tools
from PIL import Image
import websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("host")


class ScreenCapture:
    """屏幕捕获器"""

    def __init__(self, quality: int = 60, max_fps: int = 15, monitor: int = 1):
        self.quality = quality
        self.interval = 1.0 / max_fps
        self.monitor = monitor
        self.running = False

    def capture_jpeg(self) -> bytes:
        """捕获屏幕并返回 JPEG 字节"""
        with mss.mss() as sct:
            monitor = sct.monitors[self.monitor]
            img = sct.grab(monitor)
            # 转换成 PIL Image 再保存为 JPEG
            pil_img = Image.frombytes("RGB", img.size, img.rgb)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=self.quality, optimize=True)
            return buf.getvalue()


class HostClient:
    """主机端客户端"""

    def __init__(self, server_url: str, room: str = "default",
                 quality: int = 60, max_fps: int = 15, monitor: int = 1):
        self.server_url = server_url
        self.room = room
        self.capture = ScreenCapture(quality, max_fps, monitor)
        self.ws: websocket.WebSocketApp = None
        self.running = False
        self.frame_queue: Queue = Queue(maxsize=2)

    def on_message(self, ws, message):
        """处理收到的消息"""
        try:
            msg = json.loads(message)
            msg_type = msg.get("type")

            if msg_type == "registered":
                log.info(f"注册成功! ID: {msg.get('peer_id')}, 角色: {msg.get('role')}")
                # 开始发送画面
                threading.Thread(target=self.send_loop, daemon=True).start()

            elif msg_type == "viewer_joined":
                log.info(f"观察者加入: {msg.get('viewer_id')}")

            elif msg_type == "input":
                # 收到输入事件（鼠标/键盘）
                event = msg.get("event")
                data = msg.get("data", {})
                log.debug(f"收到输入: {event} {data}")
                self.handle_input(event, data)

            elif msg_type == "pong":
                pass  # 心跳回复忽略

            elif msg_type == "error":
                log.error(f"服务器错误: {msg.get('msg')}")

        except json.JSONDecodeError:
            pass

    def handle_input(self, event: str, data: dict):
        """处理远程输入事件"""
        try:
            if event == "mousemove":
                import pyautogui
                pyautogui.moveTo(data["x"], data["y"])
            elif event == "mousedown":
                import pyautogui
                pyautogui.mouseDown(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "mouseup":
                import pyautogui
                pyautogui.mouseUp(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "click":
                import pyautogui
                pyautogui.click(x=data["x"], y=data["y"], button=data.get("button", "left"))
            elif event == "scroll":
                import pyautogui
                pyautogui.scroll(data.get("amount", 0), x=data["x"], y=data["y"])
            elif event == "keydown":
                import pyautogui
                pyautogui.keyDown(data.get("key", ""))
            elif event == "keyup":
                import pyautogui
                pyautogui.keyUp(data.get("key", ""))
            elif event == "keypress":
                from pynput.keyboard import Controller, Key
                kb = Controller()
                key = data.get("key", "")
                # 处理特殊键
                special_keys = {
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
                elif key.lower() in special_keys:
                    kb.press(special_keys[key.lower()])
                    kb.release(special_keys[key.lower()])
        except Exception as e:
            log.error(f"输入处理失败: {e}")

    def on_error(self, ws, error):
        log.error(f"WebSocket 错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        log.warning(f"连接关闭: {close_status_code} {close_msg}")
        self.running = False

    def on_open(self, ws):
        log.info(f"已连接到服务器: {self.server_url}")
        # 注册为主机
        self.send_msg({
            "type": "register",
            "role": "host",
            "room": self.room,
        })

    def send_msg(self, data: dict):
        """发送 JSON 消息"""
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(data))
        except Exception as e:
            log.error(f"发送失败: {e}")

    def send_loop(self):
        """持续发送画面帧"""
        interval = 1.0 / 15  # 15fps
        while self.running:
            try:
                start = time.time()
                jpeg_data = self.capture.capture_jpeg()
                import base64
                b64 = base64.b64encode(jpeg_data).decode()

                self.send_msg({
                    "type": "frame",
                    "data": b64,
                    "timestamp": int(time.time() * 1000),
                })

                elapsed = time.time() - start
                sleep_time = max(0, interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                log.error(f"画面捕获/发送失败: {e}")
                time.sleep(1)

    def start(self):
        """启动连接"""
        self.running = True
        # 启用 WebSocket 调试（可选）
        # websocket.enableTrace(True)

        self.ws = websocket.WebSocketApp(
            self.server_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )

        # WebSocket 运行（阻塞）
        self.ws.run_forever(ping_interval=30, ping_timeout=10)

    def stop(self):
        """停止"""
        self.running = False
        if self.ws:
            self.ws.close()


def main():
    parser = argparse.ArgumentParser(description="Remote Control - Host")
    parser.add_argument("--server", default="ws://47.92.148.99:8000", help="中继服务器地址")
    parser.add_argument("--room", default="default", help="房间名")
    parser.add_argument("--quality", type=int, default=60, help="JPEG 质量 1-100")
    parser.add_argument("--fps", type=int, default=15, help="目标帧率")
    parser.add_argument("--monitor", type=int, default=1, help="显示器编号")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("host").setLevel(logging.DEBUG)

    log.info(f"启动 Host 模式")
    log.info(f"服务器: {args.server}")
    log.info(f"房间: {args.room}")
    log.info(f"画质: {args.quality}, 帧率: {args.fps}")

    client = HostClient(
        server_url=args.server,
        room=args.room,
        quality=args.quality,
        max_fps=args.fps,
        monitor=args.monitor,
    )

    try:
        client.start()
    except KeyboardInterrupt:
        log.info("用户中断")
        client.stop()


if __name__ == "__main__":
    main()
