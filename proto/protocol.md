# Remote Control 协议 v1

## 传输层
- WebSocket (ws://) 中继模式
- 服务器做消息转发，不存储画面数据
- JSON 文本帧

## 消息格式

### 注册
```json
// 客户端 -> 服务器
{"type": "register", "role": "host|viewer", "room": "房间名"}
// 服务器 -> 客户端
{"type": "registered", "peer_id": "xxx", "role": "host|viewer", "room": "房间名"}
```

### 画面帧 (Host -> Server -> Viewer)
```json
{"type": "frame", "data": "<base64 jpeg>", "timestamp": 1717000000000}
```

### 输入事件 (Viewer -> Server -> Host)
```json
{
  "type": "input",
  "event": "mousemove|mousedown|mouseup|click|scroll|keypress|keydown|keyup",
  "data": {
    "x": 100, "y": 200,
    "button": "left|right|middle",
    "amount": 1,
    "key": "a|enter|space|..."
  }
}
```

### 系统消息
```json
{"type": "ping"} -> {"type": "pong", "ts": 1717000000000}
{"type": "host_ready"}
{"type": "host_left"}
{"type": "viewer_joined", "viewer_id": "xxx"}
{"type": "error", "msg": "错误描述"}
```
