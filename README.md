# Remote Control

自建远程控制软件，轻量级 WebSocket 中继方案。
**一个客户端，既是主控端（查看远程），也是被控端（共享本机）。**

## 架构

```
[被控端电脑]  ←→  [阿里云中继服务器 :8500]  ←→  [主控端电脑]
   共享画面         ws://47.92.148.99:8500        查看+控制
   接收输入                                    发送鼠标键盘
```

- 服务器只做消息中转，不存储画面数据
- 画面用 JPEG 压缩，WebSocket 实时传输
- 支持鼠标、键盘远程控制
- 自动重连

## 快速开始

### 1. 服务端（已部署）

```
ws://47.92.148.99:8500
```

管理员需放行阿里云安全组：**TCP 8500**

### 2. 客户端

```bash
cd client
pip install -r requirements.txt
python remote_control.py
```

打开软件后：
- **被控端**：选「被控端」→ 点「连接」→ 共享本机画面
- **主控端**：选「主控端」→ 点「连接」→ 查看远程画面

两端使用**相同的房间名**即可自动配对。

### 3. Windows 打包

```bash
cd client
pip install -r requirements.txt
python build_exe.py
```

生成单个 `dist/RemoteControl.exe`（约 30-50MB）

## 项目结构

```
remote-control/
├── server/
│   ├── server.py         # WebSocket 中继服务器
│   └── requirements.txt
├── client/
│   ├── remote_control.py # 统一客户端（主控/被控双模式）
│   ├── build_exe.py      # Windows exe 打包脚本
│   └── requirements.txt
├── proto/
│   └── protocol.md       # 通信协议文档
└── README.md
```

## 依赖

| 库 | 用途 |
|------|------|
| websocket-client | WebSocket 通信 |
| PyQt5 | 图形界面 |
| mss | 屏幕捕获 |
| Pillow | 图像处理/JPEG 压缩 |
| pyautogui | 远程输入模拟 |
| pynput | 键盘事件处理 |

## 后续优化方向

- [ ] P2P 直连（WebRTC）减少中继延迟
- [ ] H.264/H.265 硬件编码提高画质/帧率
- [ ] WSS 加密传输
- [ ] 剪贴板同步
- [ ] 文件传输
- [ ] 多显示器支持
- [ ] 连接质量自适应（动态降帧/降画质）
- [ ] 开机自启后台运行
