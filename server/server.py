#!/usr/bin/env python3
"""
Remote Control Server v2.0
- Room password protection
- File transfer relay
- Chat relay
- Clipboard sync
"""

import asyncio
import json
import logging
import argparse
import time
import hashlib
import os
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
# 房间管理
# ============================================================

@dataclass
class Peer:
    ws: WebSocketServerProtocol
    peer_id: str
    role: str
    room: str
    connected_at: float = field(default_factory=time.time)
    display_name: str = ""

@dataclass
class Room:
    room_id: str
    password_hash: str = ""  # sha256 of password, empty = no password
    host: Optional[Peer] = None
    viewers: dict = field(default_factory=dict)
    peers: dict = field(default_factory=dict)  # all peers by id

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return True
        return hashlib.sha256(password.encode()).hexdigest() == self.password_hash

    def add_peer(self, peer: Peer):
        self.peers[peer.peer_id] = peer
        if peer.role == "host":
            self.host = peer
        elif peer.role == "viewer":
            self.viewers[peer.peer_id] = peer

    def remove_peer(self, peer_id: str):
        self.peers.pop(peer_id, None)
        if self.host and self.host.peer_id == peer_id:
            self.host = None
            # notify viewers
            for v in list(self.viewers.values()):
                if v.ws.open:
                    asyncio.ensure_future(send_msg(v.ws, {
                        "type": "host_left", "room": self.room_id
                    }))
            return
        self.viewers.pop(peer_id, None)

    @property
    def is_empty(self) -> bool:
        return len(self.peers) == 0

    @property
    def peer_count(self) -> int:
        return len(self.peers)


# ============================================================
# 消息工具
# ============================================================

async def send_msg(ws, data: dict):
    try:
        if ws.open:
            await ws.send(json.dumps(data))
    except websockets.exceptions.WebSocketException:
        pass

async def send_binary(ws, data: bytes):
    try:
        if ws.open:
            await ws.send(data)
    except websockets.exceptions.WebSocketException:
        pass

async def broadcast_to_viewers(room: Room, data: dict, exclude: str = None):
    for vid, v in list(room.viewers.items()):
        if vid == exclude: continue
        await send_msg(v.ws, data)

async def send_to_host(room: Room, data: dict):
    if room and room.host and room.host.ws.open:
        await send_msg(room.host.ws, data)


# ============================================================
# 主处理逻辑
# ============================================================

rooms: dict[str, Room] = {}
MAX_ROOMS = 100
MAX_VIEWERS_PER_ROOM = 10

async def handle_client(ws: WebSocketServerProtocol, path: str = None):
    peer_id = f"p{int(time.time() * 1000) % 100000:05d}"
    peer: Optional[Peer] = None
    current_room: Optional[Room] = None

    try:
        async for message in ws:
            # ---- Binary message (file chunk) ----
            if isinstance(message, bytes):
                if not current_room:
                    await send_msg(ws, {"type": "error", "msg": "未注册"})
                    continue
                # Relay binary to room peers
                if peer.role == "viewer":
                    if current_room.host:
                        await send_binary(current_room.host.ws, message)
                elif peer.role == "host":
                    for v in current_room.viewers.values():
                        await send_binary(v.ws, message)
                continue

            # ---- JSON message ----
            try:
                msg = json.loads(message)
            except json.JSONDecodeError:
                await send_msg(ws, {"type": "error", "msg": "JSON 解析失败"})
                continue

            msg_type = msg.get("type")

            # -------- REGISTER --------
            if msg_type == "register":
                role = msg.get("role", "viewer")
                room_id = msg.get("room", "default")
                password = msg.get("password", "")

                if role not in ("host", "viewer"):
                    await send_msg(ws, {"type": "error", "msg": "角色无效"})
                    continue

                # Create or verify room
                if room_id not in rooms:
                    if len(rooms) >= MAX_ROOMS:
                        await send_msg(ws, {"type": "error", "msg": "服务器已满"})
                        continue
                    pwd_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""
                    rooms[room_id] = Room(room_id=room_id, password_hash=pwd_hash)
                    log.info(f"创建房间 {room_id}" + (" (密码保护)" if password else ""))

                room = rooms[room_id]

                # Check password
                if room.password_hash:
                    pwd_check = msg.get("password", "")
                    if not room.check_password(pwd_check):
                        await send_msg(ws, {"type": "error", "msg": "密码错误"})
                        continue

                # Check host conflict
                if role == "host" and room.host and room.host.ws.open:
                    await send_msg(ws, {"type": "error", "msg": "房间已有主机"})
                    continue

                # Check viewer limit
                if role == "viewer" and len(room.viewers) >= MAX_VIEWERS_PER_ROOM:
                    await send_msg(ws, {"type": "error", "msg": "观察者已满"})
                    continue

                # Register
                display_name = msg.get("name", peer_id)
                peer = Peer(ws=ws, peer_id=peer_id, role=role, room=room_id,
                           display_name=display_name)
                room.add_peer(peer)
                current_room = room

                log.info(f"[{room_id}] {role} {display_name} 加入")

                await send_msg(ws, {
                    "type": "registered",
                    "peer_id": peer_id,
                    "role": role,
                    "room": room_id,
                })

                if role == "host":
                    # Notify viewers
                    await broadcast_to_viewers(room, {
                        "type": "host_ready", "room": room_id,
                        "name": display_name,
                    })
                elif role == "viewer" and room.host:
                    await send_msg(room.host.ws, {
                        "type": "viewer_joined",
                        "viewer_id": peer_id,
                        "name": display_name,
                    })
                    # Send current peer list to new viewer
                    peer_list = []
                    if room.host:
                        peer_list.append({"id": room.host.peer_id, "role": "host",
                                         "name": room.host.display_name})
                    await send_msg(ws, {
                        "type": "peer_list",
                        "peers": peer_list,
                    })

            # -------- FRAME --------
            elif msg_type == "frame":
                if not peer or peer.role != "host" or not current_room:
                    continue
                await broadcast_to_viewers(current_room, {
                    "type": "frame",
                    "data": msg.get("data"),
                    "timestamp": msg.get("timestamp", int(time.time() * 1000)),
                })

            # -------- INPUT --------
            elif msg_type == "input":
                if not peer or peer.role != "viewer" or not current_room:
                    continue
                if current_room.host:
                    await send_msg(current_room.host.ws, {
                        "type": "input",
                        "source": peer.peer_id,
                        "event": msg.get("event"),
                        "data": msg.get("data"),
                    })

            # -------- FILE TRANSFER --------
            elif msg_type == "file_meta":
                """File transfer metadata"""
                if not current_room:
                    continue
                target = msg.get("target")  # "host" or peer_id
                target_ws = None
                if target == "host" and current_room.host:
                    target_ws = current_room.host.ws
                elif target in current_room.peers:
                    target_ws = current_room.peers[target].ws

                if target_ws:
                    await send_msg(target_ws, {
                        "type": "file_meta",
                        "file_id": msg.get("file_id"),
                        "name": msg.get("name"),
                        "size": msg.get("size"),
                        "from": peer_id,
                    })
                else:
                    await send_msg(ws, {"type": "error", "msg": "目标不在线"})

            elif msg_type == "file_chunk":
                """File data chunk (binary relay)"""
                if not current_room:
                    continue
                target = msg.get("target")
                target_ws = None
                if target == "host" and current_room.host:
                    target_ws = current_room.host.ws
                elif target in current_room.peers:
                    target_ws = current_room.peers[target].ws

                if target_ws:
                    await send_msg(target_ws, {
                        "type": "file_chunk",
                        "file_id": msg.get("file_id"),
                        "chunk": msg.get("chunk"),
                        "offset": msg.get("offset"),
                        "final": msg.get("final", False),
                    })

            elif msg_type == "file_accept":
                if not current_room or not current_room.host:
                    continue
                await send_msg(current_room.host.ws, {
                    "type": "file_accept",
                    "file_id": msg.get("file_id"),
                })

            elif msg_type == "file_reject":
                if not current_room or not current_room.host:
                    continue
                await send_msg(current_room.host.ws, {
                    "type": "file_reject",
                    "file_id": msg.get("file_id"),
                })

            # -------- CHAT --------
            elif msg_type == "chat":
                if not current_room:
                    continue
                target = msg.get("target", "all")
                if target == "host" and current_room.host:
                    await send_msg(current_room.host.ws, {
                        "type": "chat",
                        "text": msg.get("text", ""),
                        "from": peer_id,
                        "name": peer.display_name if peer else "Unknown",
                    })
                elif target == "all":
                    for p in current_room.peers.values():
                        if p.peer_id != peer_id:
                            await send_msg(p.ws, {
                                "type": "chat",
                                "text": msg.get("text", ""),
                                "from": peer_id,
                                "name": peer.display_name if peer else "Unknown",
                            })

            # -------- CLIPBOARD --------
            elif msg_type == "clipboard":
                if not current_room:
                    continue
                if peer.role == "host":
                    await broadcast_to_viewers(current_room, {
                        "type": "clipboard",
                        "text": msg.get("text", ""),
                    })
                elif peer.role == "viewer" and current_room.host:
                    await send_msg(current_room.host.ws, {
                        "type": "clipboard",
                        "text": msg.get("text", ""),
                        "from": peer_id,
                    })

            # -------- SYSTEM --------
            elif msg_type == "ping":
                await send_msg(ws, {"type": "pong", "ts": int(time.time() * 1000)})

            else:
                await send_msg(ws, {"type": "error", "msg": f"未知类型: {msg_type}"})

    except websockets.exceptions.WebSocketException:
        pass
    except Exception as e:
        log.error(f"处理异常: {e}")
    finally:
        if current_room:
            current_room.remove_peer(peer_id)
            if current_room.is_empty:
                del rooms[current_room.room_id]
                log.info(f"房间 {current_room.room_id} 已清理")
        log.info(f"客户端 {peer_id} 断开")


# ============================================================
# 启动
# ============================================================

async def status_reporter():
    while True:
        await asyncio.sleep(30)
        total = sum(r.peer_count for r in rooms.values())
        if total > 0:
            log.info(f"状态: {len(rooms)} 房间, {total} 客户端")

def main():
    parser = argparse.ArgumentParser(description="Remote Control Server v2")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8500)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("relay").setLevel(logging.DEBUG)

    log.info(f"Server v2.0 启动: {args.host}:{args.port}")

    async def start():
        async with websockets.serve(handle_client, args.host, args.port):
            log.info(f"WebSocket: ws://{args.host}:{args.port}")
            await status_reporter()

    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        log.info("服务器关闭")

if __name__ == "__main__":
    main()
