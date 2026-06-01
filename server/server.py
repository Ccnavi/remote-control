#!/usr/bin/env python3
"""
Remote Control - WebSocket Relay Server
轻量级远程控制中继服务器
架构: 端到端加密，服务器只做 WebSocket 中继
"""

import asyncio
import json
import logging
import argparse
import time
from dataclasses import dataclass, field
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("relay")

# ============================================================
# 房间/对等管理
# ============================================================

@dataclass
class Peer:
    ws: WebSocketServerProtocol
    peer_id: str
    role: str  # "host" or "viewer"
    room: str
    connected_at: float = field(default_factory=time.time)

class Room:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.host: Optional[Peer] = None
        self.viewers: dict[str, Peer] = {}

    def add_peer(self, peer: Peer):
        if peer.role == "host":
            if self.host and self.host.ws.open:
                log.warning(f"房间 {self.room_id} 已有主机，替换旧连接")
            self.host = peer
        elif peer.role == "viewer":
            self.viewers[peer.peer_id] = peer

    def remove_peer(self, peer_id: str):
        if self.host and self.host.peer_id == peer_id:
            log.info(f"主机 {peer_id} 离开房间 {self.room_id}")
            self.host = None
            # 通知所有观察者
            for vid, v in list(self.viewers.items()):
                if v.ws.open:
                    asyncio.ensure_future(send_msg(v.ws, {
                        "type": "host_left",
                        "room": self.room_id
                    }))
            return
        if peer_id in self.viewers:
            log.info(f"观察者 {peer_id} 离开房间 {self.room_id}")
            del self.viewers[peer_id]

    @property
    def is_empty(self) -> bool:
        return self.host is None and len(self.viewers) == 0

    @property
    def peer_count(self) -> int:
        count = 0
        if self.host:
            count += 1
        return count + len(self.viewers)

# ============================================================
# 消息转发
# ============================================================

async def send_msg(ws, data: dict):
    """安全发送 JSON 消息"""
    try:
        if ws.open:
            await ws.send(json.dumps(data))
    except websockets.exceptions.WebSocketException:
        pass

async def broadcast_to_viewers(room: Room, data: dict, exclude: str = None):
    """广播给房间内所有观察者"""
    for vid, v in list(room.viewers.items()):
        if vid == exclude:
            continue
        await send_msg(v.ws, data)

# ============================================================
# 连接处理
# ============================================================

rooms: dict[str, Room] = {}
MAX_ROOMS = 100
MAX_VIEWERS_PER_ROOM = 10

async def handle_client(ws: WebSocketServerProtocol):
    """处理单个客户端连接"""
    peer_id = f"p{int(time.time() * 1000) % 100000:05d}"
    peer: Optional[Peer] = None
    current_room: Optional[Room] = None

    try:
        async for message in ws:
            try:
                msg = json.loads(message)
            except json.JSONDecodeError:
                await send_msg(ws, {"type": "error", "msg": "无效的 JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "register":
                # 注册到房间
                role = msg.get("role", "viewer")
                room_id = msg.get("room", "default")

                if role not in ("host", "viewer"):
                    await send_msg(ws, {"type": "error", "msg": "角色必须是 host 或 viewer"})
                    continue

                if room_id not in rooms:
                    if len(rooms) >= MAX_ROOMS:
                        await send_msg(ws, {"type": "error", "msg": "服务器房间已满"})
                        continue
                    rooms[room_id] = Room(room_id)

                room = rooms[room_id]

                if role == "host" and room.host is not None and room.host.ws.open:
                    # 已存在活跃主机，拒绝
                    await send_msg(ws, {"type": "error", "msg": f"房间 {room_id} 已有主机"})
                    continue

                if role == "viewer" and len(room.viewers) >= MAX_VIEWERS_PER_ROOM:
                    await send_msg(ws, {"type": "error", "msg": "观察者已满"})
                    continue

                peer = Peer(ws=ws, peer_id=peer_id, role=role, room=room_id)
                room.add_peer(peer)
                current_room = room

                log.info(f"[{room_id}] {role} {peer_id} 加入 (共 {room.peer_count} 人)")

                # 回复注册成功
                await send_msg(ws, {
                    "type": "registered",
                    "peer_id": peer_id,
                    "role": role,
                    "room": room_id,
                })

                # 通知观察者：主机已就绪
                if role == "host":
                    await broadcast_to_viewers(room, {
                        "type": "host_ready",
                        "room": room_id,
                    })

                # 通知主机：观察者列表
                if role == "viewer" and room.host:
                    await send_msg(room.host.ws, {
                        "type": "viewer_joined",
                        "viewer_id": peer_id,
                    })

            elif msg_type == "frame":
                # 主机 -> 观察者：转发视频帧
                if not peer or peer.role != "host":
                    await send_msg(ws, {"type": "error", "msg": "只有主机可以发送画面"})
                    continue

                # 广播给房间内所有观察者
                room = rooms.get(peer.room)
                if room:
                    frame_msg = {
                        "type": "frame",
                        "data": msg.get("data"),
                        "timestamp": msg.get("timestamp", int(time.time() * 1000)),
                    }
                    await broadcast_to_viewers(room, frame_msg)

            elif msg_type == "input":
                # 观察者 -> 主机：转发输入事件
                if not peer or peer.role != "viewer":
                    await send_msg(ws, {"type": "error", "msg": "只有观察者可以发送输入"})
                    continue

                room = rooms.get(peer.room)
                if room and room.host and room.host.ws.open:
                    input_msg = {
                        "type": "input",
                        "source": peer.peer_id,
                        "event": msg.get("event"),
                        "data": msg.get("data"),
                    }
                    await send_msg(room.host.ws, input_msg)

            elif msg_type == "ping":
                await send_msg(ws, {"type": "pong", "ts": int(time.time() * 1000)})

            else:
                await send_msg(ws, {"type": "error", "msg": f"未知消息类型: {msg_type}"})

    except websockets.exceptions.WebSocketException:
        pass
    except Exception as e:
        log.error(f"处理消息错误: {e}")
    finally:
        # 清理断开连接的客户端
        if current_room:
            current_room.remove_peer(peer_id)
            if current_room.is_empty:
                del rooms[current_room.room_id]
                log.info(f"房间 {current_room.room_id} 已清空删除")
        log.info(f"客户端 {peer_id} 断开")

# ============================================================
# 状态查看
# ============================================================

async def status_reporter():
    """定期打印服务器状态"""
    while True:
        await asyncio.sleep(30)
        total = sum(r.peer_count for r in rooms.values())
        if total > 0 or rooms:
            log.info(f"状态: {len(rooms)} 房间, {total} 客户端在线")

# ============================================================
# 启动
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Remote Control Relay Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("relay").setLevel(logging.DEBUG)

    log.info(f"中继服务器启动: {args.host}:{args.port}")

    async def start():
        async with websockets.serve(handle_client, args.host, args.port):
            log.info(f"WebSocket 服务运行中 ws://{args.host}:{args.port}")
            await status_reporter()

    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        log.info("服务器关闭")

if __name__ == "__main__":
    main()
