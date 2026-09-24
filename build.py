#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py —— InkQuill 跨平台一键打包

在哪个系统上运行，就打出那个系统的可执行程序：
  Windows  →  dist/inkquill.exe
  macOS    →  dist/inkquill.app
  Linux    →  dist/inkquill

用法：  python build.py
注意：PyInstaller 不支持交叉编译——Windows 的 exe 必须在 Windows 上打，
      macOS 的 app 必须在 macOS 上打。想一次拿到三平台，用仓库里的
      GitHub Actions 工作流（.github/workflows/build.yml）。

可选：把图标放到项目根目录会自动使用（Windows: icon.ico，macOS: icon.icns）。
"""
import os
import subprocess
import sys

# Windows 控制台默认编码是 cp1252 / GBK，直接打印中文会抛 UnicodeEncodeError。
# 统一把标准输出 / 错误流改成 UTF-8，保证在 GitHub Actions 的 Windows 上也能正常跑。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(ROOT, "inkquill.py")
NAME = "inkquill"

# 排除运行时不相关的重型库，显著减小体积（实测 273MB → 116MB）
EXCLUDES = [
    "scipy", "pandas", "matplotlib", "sklearn", "sympy", "IPython",
    "notebook", "jupyter", "pytest", "pyarrow", "plotly", "numba",
    "llvmlite", "spacy", "gensim", "unittest", "pydoc", "turtle",
    "tkinter.test", "pip",
    # 排除用不到的 Qt 大模块，显著减小体积
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtBluetooth", "PySide6.QtPositioning",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtWebSockets",
    "PySide6.QtWebChannel", "PySide6.QtNfc", "PySide6.QtRemoteObjects",
    "PySide6.QtTextToSpeech", "PySide6.QtHelp",
]


def check_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未检测到 PyInstaller，正在安装 …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyinstaller"])


def main() -> int:
    print("=" * 56)
    print(" InkQuill 打包工具")
    print(" 系统：%s    Python：%s" % (sys.platform, sys.version.split()[0]))
    print("=" * 56)

    if not check_tkinter():
        print("⚠ 当前 Python 缺少 tkinter，打包出的程序将无法显示图形界面。")
        print("  Linux：sudo apt-get install -y python3-tk")
        print("  macOS：brew install python-tk")
        print("  Windows：重装 Python 时勾选 tcl/tk 组件。\n")

    ensure_pyinstaller()

    args = [
        ENTRY, "--noconfirm", "--clean", "--onefile", "--name", NAME,
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", ROOT,
    ]
    for m in EXCLUDES:
        args += ["--exclude-module", m]

    if sys.platform == "win32":
        args.append("--windowed")
        ico = os.path.join(ROOT, "icon.ico")
        if os.path.exists(ico):
            args += ["--icon", ico]
    elif sys.platform == "darwin":
        args.append("--windowed")
        icns = os.path.join(ROOT, "icon.icns")
        if os.path.exists(icns):
            args += ["--icon", icns]

    args.append("--noupx")

    print("\n开始打包，首次会慢一些（含 OpenCV，体积约 100MB 级）…\n")
    from PyInstaller.__main__ import run
    try:
        run(args)
    except SystemExit as e:
        if e.code not in (0, None):
            print("\n✗ 打包失败。")
            return int(e.code)

    dist = os.path.join(ROOT, "dist")
    print("\n✓ 完成！产物目录：%s" % dist)
    if os.path.isdir(dist):
        for f in sorted(os.listdir(dist)):
            fp = os.path.join(dist, f)
            size = os.path.getsize(fp) / (1024 * 1024) if os.path.isfile(fp) else 0
            print("   - %s (%.1f MB)" % (f, size))
    print("\n提示：产物可直接分发，目标机器无需安装 Python。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
