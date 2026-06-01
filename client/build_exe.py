#!/usr/bin/env python3
"""
打包脚本：将 remote_control.py 打包为 Windows exe
用法: python build_exe.py
"""

import os
import sys
import subprocess
import shutil

def build():
    """用 PyInstaller 打包"""
    print("=== 打包 RemoteControl ===")

    # 图标（如果有）
    icon_path = "icon.ico" if os.path.exists("icon.ico") else None

    cmd = [
        "pyinstaller",
        "--onefile",
        "--windowed",        # 无控制台窗口
        "--name", "RemoteControl",
        "--clean",
        "--noconfirm",
        "--add-data", "requirements.txt;.",
    ]

    if icon_path:
        cmd.extend(["--icon", icon_path])

    # 添加隐藏导入（PyInstaller 有时检测不到）
    cmd.extend(["--hidden-import", "websocket"])
    cmd.append("remote_control.py")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("打包失败:")
        print(result.stderr)
        return False

    exe_path = os.path.join("dist", "RemoteControl.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"✓ 打包成功: {exe_path} ({size_mb:.1f} MB)")
        return True
    return False


def main():
    try:
        import PyInstaller
    except ImportError:
        print("安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 清理旧构建
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    for f in os.listdir("."):
        if f.endswith(".spec"):
            os.remove(f)

    build()
    print("\n完成！exe 文件在 dist/RemoteControl.exe")


if __name__ == "__main__":
    main()
