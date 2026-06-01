#!/usr/bin/env python3
"""Build RemoteControl.exe for Windows"""
import os, sys, subprocess, shutil

try:
    import PyInstaller
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

for d in ["build", "dist"]:
    if os.path.exists(d): shutil.rmtree(d)
for f in os.listdir("."):
    if f.endswith(".spec"): os.remove(f)

cmd = ["pyinstaller", "--onefile", "--windowed", "--name", "RemoteControl",
       "--clean", "--noconfirm",
       "--hidden-import", "websocket", "--hidden-import", "mss",
       "--hidden-import", "PIL", "--hidden-import", "PIL.Image",
       "--hidden-import", "pyautogui", "--hidden-import", "pynput.keyboard",
       "remote_control.py"]

result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print("Build failed:")
    print(result.stderr)
    sys.exit(1)

exe = os.path.join("dist", "RemoteControl.exe")
if os.path.exists(exe):
    size = os.path.getsize(exe) / 1024 / 1024
    print(f"OK: {exe} ({size:.1f} MB)")
else:
    print("Build failed: exe not found")
