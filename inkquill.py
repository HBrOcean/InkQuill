#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inkquill.py —— 图片转黑白线稿图（输入 / 输出格式一致）

把 PNG / JPG / JPEG / BMP / WEBP / TIF / TIFF 等常见位图，转成「白底黑线」的
黑白线稿图（位图，保持原格式）。适合做激光切割底图、手绘线稿、简笔画、
印章 / 剪影、漫画线稿、上色底稿等。

四种模式：
  lineart  手绘线稿   —— XDoG 提取线条，白底黑线，最像手绘/描线
  edge     轮廓描线   —— Canny 边缘，勾勒物体边界
  binary   黑白二值   —— 阈值二值化（Otsu / 手动 / 自适应），印章·剪影·漫画感
  gray     灰度       —— 直接转灰度（保留明暗层次）

两种输出色彩：
  纯黑白    最终结果只含黑、白两色（干净的纯线条）
  灰度      保留浅灰过渡（更柔和，像铅笔稿）

用法：
  图形界面：  python inkquill.py
  命令行：    python inkquill.py 图片.png                      # 生成 图片_lineart.png
              python inkquill.py 图片.png -o 线稿.png --mode edge
              python inkquill.py 图片文件夹/ -o 输出目录/       # 批量
              python inkquill.py "*.jpg" --mode binary --invert
              python inkquill.py 扫描件.jpg --mode binary --adaptive

依赖：pip install opencv-python numpy pillow
版本：1.1
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, replace

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    sys.stderr.write("缺少依赖 opencv-python，请先运行：pip install opencv-python numpy pillow\n")
    raise

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:  # pragma: no cover
    sys.stderr.write("缺少依赖 pillow，请先运行：pip install opencv-python numpy pillow\n")
    raise


__version__ = "1.1"

SUPPORTED = (".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".webp", ".tif", ".tiff")

MODES = {
    "lineart": "手绘线稿 (XDoG)",
    "edge": "轮廓描线 (Canny)",
    "binary": "黑白二值",
    "gray": "灰度",
}
COLOR_MODES = {
    "binary": "纯黑白",
    "gray": "灰度",
}

# 一键预设：名称 → 参数覆盖（None 表示手动/自定义）
PRESETS = {
    "自定义": None,
    "照片线稿": dict(mode="lineart", color="gray", detail=0.75, dilate=0, blur=0, simplify=12, contrast=1.12),
    "清爽描边": dict(mode="lineart", color="binary", detail=0.7, dilate=0, blur=1, simplify=20),
    "印章剪影": dict(mode="binary", color="binary", auto_thresh=True, adaptive=False, simplify=25, invert=False),
    "扫描文档": dict(mode="binary", color="binary", adaptive=True, simplify=30, invert=False),
    "铅笔素描": dict(mode="lineart", color="gray", detail=0.6, blur=1, simplify=14, contrast=1.2),
}

K3 = np.ones((3, 3), np.uint8)


# ======================================================================
# 参数
# ======================================================================
@dataclass
class Params:
    mode: str = "lineart"           # lineart / edge / binary / gray
    color: str = "binary"           # binary(纯黑白) / gray(灰度)
    detail: float = 0.7             # 细节丰富度 0~1（lineart）
    dilate: int = 0                 # 线条加粗半径 0~3
    blur: int = 0                   # 预柔化去高频噪点 0~5（0/1=关闭）
    simplify: int = 15              # 去噪：剔除小于该面积的碎点（像素面积）
    thresh: int = 128               # 手动阈值（binary，auto=off 且 adaptive=off）
    auto_thresh: bool = True        # binary 用 Otsu 自动阈值
    adaptive: bool = False          # binary 用自适应阈值（光照不均 / 扫描件）
    canny_low: int = 40             # edge 低阈值
    canny_high: int = 120           # edge 高阈值
    contrast: float = 1.0           # 对比度增强 0.5~2.0（gray / lineart 灰度输出）
    invert: bool = False            # 黑白反转（黑底图）
    trim: bool = False              # 自动裁掉四周白边
    margin: int = 0                 # 裁白边后额外留白像素
    max_size: int = 2400            # 处理分辨率最长边上限，0=不限


# ======================================================================
# 图像读写（Pillow 负责 I/O：兼容中文路径、EXIF、多格式）
# ======================================================================
def pil_to_rgb(im: Image.Image) -> np.ndarray:
    """任意 PIL 图像 → RGB ndarray（透明区按白底合成）。"""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    return np.array(im)


def load_rgb(path: str) -> np.ndarray:
    """读取图片为 RGB ndarray，自动按 EXIF 校正方向。"""
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return pil_to_rgb(im)


def save_image(arr: np.ndarray, path: str) -> None:
    """保存结果，按目标扩展名选择编码（保持与输入一致）。"""
    ext = os.path.splitext(path)[1].lower()
    im = Image.fromarray(arr)
    if ext in (".jpg", ".jpeg", ".jfif"):
        im.convert("RGB").save(path, quality=95, subsampling=0)
    elif ext == ".png":
        im.save(path)
    elif ext == ".webp":
        im.save(path, quality=95, method=6)
    elif ext in (".tif", ".tiff"):
        im.save(path, compression="tiff_lzw")
    else:
        im.save(path)


# ======================================================================
# 核心算法
# ======================================================================
def to_gray(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _presmooth(gray: np.ndarray, blur: int) -> np.ndarray:
    if blur and blur > 1:
        return cv2.GaussianBlur(gray, (0, 0), (blur - 1) * 0.8)
    return gray


def _enhance(img: np.ndarray, contrast: float) -> np.ndarray:
    if abs(contrast - 1.0) < 1e-3:
        return img
    f = img.astype(np.float32) / 255.0
    f = np.clip((f - 0.5) * contrast + 0.5, 0.0, 1.0)
    return (f * 255.0).astype(np.uint8)


def xdog_lineart(gray: np.ndarray, detail: float = 0.7, blur: int = 0) -> np.ndarray:
    """XDoG（扩展高斯差分）线稿，返回白底黑线灰度图（背景 255，线条偏黑）。"""
    g = _presmooth(gray, blur).astype(np.float32) / 255.0
    detail = float(np.clip(detail, 0.0, 1.0))

    sigma = 0.75 + 0.9 * (1.0 - detail)
    k = 1.6
    gamma = 0.98
    g1 = cv2.GaussianBlur(g, (0, 0), sigma)
    g2 = cv2.GaussianBlur(g, (0, 0), sigma * k)
    dog = g1 - gamma * g2

    # 按幅度归一化，使阈值与图像整体对比度无关（避免整图全白/全黑）
    scale = float(np.percentile(np.abs(dog), 98)) + 1e-8
    d = dog / scale

    eps = -0.03
    p = 6.0 + 16.0 * detail
    res = np.where(d >= eps, 1.0, 1.0 + np.tanh(p * (d - eps)))
    return (np.clip(res, 0.0, 1.0) * 255.0).astype(np.uint8)


def edge_lineart(gray: np.ndarray, low: int = 40, high: int = 120, blur: int = 0) -> np.ndarray:
    g = _presmooth(gray, blur)
    edges = cv2.Canny(g, int(low), int(high))
    return (255 - edges).astype(np.uint8)


def binary_image(gray: np.ndarray, thresh: int = 128, auto: bool = True, blur: int = 0,
                 adaptive: bool = False) -> np.ndarray:
    """二值化（Otsu / 手动 / 自适应），返回纯黑白图（暗部为黑、亮部为白）。"""
    g = _presmooth(gray, blur)
    if adaptive:
        bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 10)
    elif auto:
        _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        _, bw = cv2.threshold(g, int(thresh), 255, cv2.THRESH_BINARY)
    return bw.astype(np.uint8)


def clean_binary(whitebg: np.ndarray, thresh: int = 180, min_area: int = 0, close_k: int = 3) -> np.ndarray:
    """白底黑线图整理成干净纯黑白：阈值提纯 → 闭运算补缝 → 剔除碎点。"""
    lin = (whitebg < thresh).astype(np.uint8)
    if close_k and close_k > 1:
        lin = cv2.morphologyEx(lin, cv2.MORPH_CLOSE, np.ones((close_k, close_k), np.uint8))
    if min_area and min_area > 0:
        n, lab, stats, _ = cv2.connectedComponentsWithStats(lin, 8)
        if n > 1:
            keep = np.zeros_like(lin)
            for i in range(1, n):
                if stats[i, cv2.CC_STAT_AREA] >= min_area:
                    keep[lab == i] = 1
            lin = keep
    return np.where(lin > 0, 0, 255).astype(np.uint8)


def _dilate_lines(img: np.ndarray, iters: int) -> np.ndarray:
    if iters <= 0:
        return img
    dark = cv2.dilate(255 - img, K3, iterations=int(iters))
    return (255 - dark).astype(np.uint8)


def trim_white(img: np.ndarray, thresh: int = 250, margin: int = 0) -> np.ndarray:
    mask = img < thresh
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return img
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    if margin > 0:
        h, w = img.shape[:2]
        y0 = max(0, y0 - margin); x0 = max(0, x0 - margin)
        y1 = min(h - 1, y1 + margin); x1 = min(w - 1, x1 + margin)
    return img[y0:y1 + 1, x0:x1 + 1]


def _to_bw(img: np.ndarray) -> np.ndarray:
    return np.where(img < 128, 0, 255).astype(np.uint8)


# ======================================================================
# 单张处理
# ======================================================================
def process_rgb(rgb: np.ndarray, p: Params) -> np.ndarray:
    """对 RGB 数组跑完整流程，返回结果数组（灰度或纯黑白）。"""
    gray = to_gray(rgb)
    h, w = gray.shape[:2]

    scale = 1.0
    if p.max_size and max(h, w) > p.max_size:
        scale = p.max_size / float(max(h, w))
        gray = cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))),
                          interpolation=cv2.INTER_AREA)

    if p.mode == "lineart":
        res = xdog_lineart(gray, p.detail, p.blur)
        if p.color == "binary":
            res = clean_binary(res, thresh=180, min_area=p.simplify, close_k=3)
        else:
            res = _enhance(res, p.contrast)
        res = _dilate_lines(res, p.dilate)

    elif p.mode == "edge":
        res = edge_lineart(gray, p.canny_low, p.canny_high, p.blur)
        if p.color == "binary":
            res = clean_binary(res, thresh=128, min_area=p.simplify, close_k=0)
        res = _dilate_lines(res, p.dilate)

    elif p.mode == "binary":
        res = binary_image(gray, p.thresh, p.auto_thresh, p.blur, p.adaptive)
        if p.simplify > 0:
            res = clean_binary(res, thresh=128, min_area=p.simplify, close_k=0)

    else:  # gray
        res = _enhance(gray, p.contrast)
        if p.color == "binary":
            res = clean_binary(res, thresh=128, min_area=p.simplify, close_k=0)

    if p.invert:
        res = 255 - res

    if p.color == "binary":
        res = _to_bw(res)

    if scale != 1.0:
        interp = cv2.INTER_NEAREST if p.color == "binary" else cv2.INTER_LINEAR
        res = cv2.resize(res, (w, h), interpolation=interp)

    if p.trim:
        res = trim_white(res, margin=p.margin)

    return res


def output_path_for(src: str, out, is_batch: bool, suffix: str = "_lineart") -> str:
    stem, ext = os.path.splitext(os.path.basename(src))
    if out is None:
        return os.path.join(os.path.dirname(src), stem + suffix + ext)
    if not is_batch and os.path.splitext(out)[1]:
        return out
    os.makedirs(out, exist_ok=True)
    return os.path.join(out, stem + suffix + ext)


def convert_file(src: str, dst: str, p: Params, force: bool = True) -> str:
    try:
        if os.path.exists(dst) and not force:
            return "skip"
        rgb = load_rgb(src)
        res = process_rgb(rgb, p)
        if res is None or res.size == 0:
            return "empty"
        save_image(res, dst)
        return "ok"
    except Exception as e:  # noqa
        return "error: %s" % e


def gather_inputs(items) -> list:
    files = []
    for it in items:
        if os.path.isdir(it):
            for name in sorted(os.listdir(it)):
                fp = os.path.join(it, name)
                if os.path.isfile(fp) and name.lower().endswith(SUPPORTED):
                    files.append(fp)
        elif any(ch in it for ch in "*?["):
            for fp in sorted(glob.glob(it)):
                if os.path.isfile(fp) and fp.lower().endswith(SUPPORTED):
                    files.append(fp)
        elif os.path.isfile(it):
            files.append(it)
        else:
            sys.stderr.write("跳过（找不到）：%s\n" % it)
    return files


# ======================================================================
# 命令行
# ======================================================================
def _process_one(job):
    src, dst, p, force = job
    return src, convert_file(src, dst, p, force)


def run_cli(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="inkquill",
        description="图片转黑白线稿图（输入输出格式一致）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("inputs", nargs="*", help="图片 / 目录 / 通配符，可多个；留空则打开图形界面")
    ap.add_argument("-o", "--output", default=None, help="输出文件（单张）或输出目录")
    ap.add_argument("--mode", choices=list(MODES), default="lineart", help="转换模式")
    ap.add_argument("--color", choices=list(COLOR_MODES), default="binary", help="输出色彩")
    ap.add_argument("--preset", choices=[k for k, v in PRESETS.items() if v], default=None,
                    help="套用预设（会覆盖相关参数）")
    ap.add_argument("--detail", type=float, default=0.7, help="细节丰富度 0~1（lineart）")
    ap.add_argument("--dilate", type=int, default=0, help="线条加粗半径 0~3")
    ap.add_argument("--blur", type=int, default=0, help="预柔化去噪 0~5（0/1=关闭）")
    ap.add_argument("--simplify", type=int, default=15, help="去噪：剔除小于该像素面积的碎点")
    ap.add_argument("--thresh", type=int, default=128, help="手动阈值（binary）")
    ap.add_argument("--auto", dest="auto_thresh", action="store_true", help="binary 用 Otsu 自动阈值")
    ap.add_argument("--no-auto", dest="auto_thresh", action="store_false", help="binary 用手动阈值")
    ap.add_argument("--adaptive", action="store_true", help="binary 用自适应阈值（扫描件/光照不均）")
    ap.add_argument("--canny-low", type=int, default=40, help="edge 低阈值")
    ap.add_argument("--canny-high", type=int, default=120, help="edge 高阈值")
    ap.add_argument("--contrast", type=float, default=1.0, help="对比度增强 0.5~2.0")
    ap.add_argument("--invert", action="store_true", help="黑白反转（黑底图用）")
    ap.add_argument("--trim", action="store_true", help="自动裁掉四周白边")
    ap.add_argument("--margin", type=int, default=0, help="裁白边后额外留白像素")
    ap.add_argument("--suffix", default="_lineart", help="输出文件名后缀")
    ap.add_argument("--max-size", type=int, default=2400, help="处理分辨率最长边上限，0=不限")
    ap.add_argument("-f", "--force", dest="force", action="store_true", help="覆盖已存在输出")
    ap.add_argument("--no-overwrite", dest="force", action="store_false", help="已存在则跳过")
    ap.add_argument("-j", "--jobs", type=int, default=0, help="批量并发进程数，0=自动")
    ap.add_argument("--gui", choices=["auto", "qt", "tk"], default="auto",
                    help="图形界面后端（无输入参数启动界面时生效；默认自动：优先 Qt）")
    ap.add_argument("--version", action="version", version="inkquill %s" % __version__)
    ap.set_defaults(auto_thresh=True, force=True)

    a = ap.parse_args(argv)
    if not a.inputs:
        return launch_gui(backend=a.gui)

    p = Params(mode=a.mode, color=a.color, detail=a.detail, dilate=a.dilate, blur=a.blur,
               simplify=a.simplify, thresh=a.thresh, auto_thresh=a.auto_thresh,
               adaptive=a.adaptive, canny_low=a.canny_low, canny_high=a.canny_high,
               contrast=a.contrast, invert=a.invert, trim=a.trim, margin=a.margin,
               max_size=a.max_size)
    if a.preset and PRESETS.get(a.preset):
        for k, v in PRESETS[a.preset].items():
            setattr(p, k, v)

    files = gather_inputs(a.inputs)
    if not files:
        sys.stderr.write("没有找到可处理的图片。\n")
        return 2

    is_batch = len(files) > 1
    jobs = [(src, output_path_for(src, a.output, is_batch, a.suffix), p, a.force) for src in files]

    if len(jobs) > 1 and a.jobs != 1:
        workers = a.jobs if a.jobs and a.jobs > 0 else min(os.cpu_count() or 4, 8)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_process_one, jobs))
    else:
        results = [_process_one(j) for j in jobs]

    n_ok = n_fail = 0
    for src, status in results:
        if status == "ok":
            n_ok += 1
            print("[完成] %s" % src)
        elif status == "skip":
            print("[跳过] 已存在：%s" % src)
        elif status == "empty":
            n_fail += 1
            print("[空结果] %s（试试换模式，或调 --thresh / --invert）" % src)
        else:
            n_fail += 1
            print("[失败] %s -> %s" % (src, status))

    print("—— 共 %d 张，成功 %d，失败 %d ——" % (len(files), n_ok, n_fail))
    return 0 if n_fail == 0 else 1


# ======================================================================
# 图形界面
# ======================================================================
def _qt_available() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except Exception:
        return False


_QT_QSS = """
QWidget { font-size: 13px; }
QGroupBox { border:1px solid #dcdcdc; border-radius:8px; margin-top:12px; padding:8px 8px 4px 8px; }
QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 4px; color:#555; }
QPushButton { background:#f6f6f6; border:1px solid #d0d0d0; border-radius:8px; padding:7px 12px; }
QPushButton:hover { background:#ededed; }
QPushButton:pressed { background:#e2e2e2; }
QPushButton#primary { background:#5b8def; color:#ffffff; border:1px solid #5b8def; font-weight:600; }
QPushButton#primary:hover { background:#4a7de0; border-color:#4a7de0; }
QPushButton#primary:pressed { background:#3f6fce; }
QComboBox, QListWidget { border:1px solid #d0d0d0; border-radius:6px; padding:3px; background:white; }
QSlider::groove:horizontal { height:4px; background:#dddddd; border-radius:2px; }
QSlider::sub-page:horizontal { background:#5b8def; border-radius:2px; }
QSlider::handle:horizontal { width:14px; margin:-6px 0; background:#5b8def; border-radius:7px; }
"""


def _run_qt_gui(test: bool = False) -> int:
    """PySide6 / Qt 图形界面。"""
    from PySide6.QtCore import Qt, QThread, Signal, QTimer
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
        QSlider, QCheckBox, QRadioButton, QButtonGroup, QListWidget,
        QVBoxLayout, QHBoxLayout, QGroupBox, QFileDialog, QMessageBox,
    )

    def np_to_pixmap(arr: np.ndarray) -> "QPixmap":
        arr = np.ascontiguousarray(arr)
        if arr.ndim == 2:
            h, w = arr.shape
            qimg = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            h, w, ch = arr.shape
            qimg = QImage(arr.data, w, h, ch * w, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    class Worker(QThread):
        ok = Signal(int, object)
        err = Signal(int, str)

        def __init__(self, rgb, params, token):
            super().__init__()
            self._rgb = rgb
            self._params = params
            self._token = token

        def run(self):
            try:
                self.ok.emit(self._token, process_rgb(self._rgb, self._params))
            except Exception as e:  # noqa
                self.err.emit(self._token, str(e))

    class Preview(QLabel):
        def __init__(self):
            super().__init__()
            self.setMinimumSize(280, 280)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setStyleSheet("background:#fafafa; border:1px solid #dcdcdc; border-radius:6px; color:#999;")
            self._pm = None
            self.setText("（未加载）")

        def set_image(self, arr):
            self._pm = np_to_pixmap(arr)
            self._rescale()

        def clear_image(self):
            self._pm = None
            self.setPixmap(QPixmap())
            self.setText("（未加载）")

        def _rescale(self):
            if self._pm is None:
                return
            self.setPixmap(self._pm.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

        def resizeEvent(self, e):
            super().resizeEvent(e)
            self._rescale()

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("InkQuill · 墨羽 —— 图片转黑白线稿图  v%s" % __version__)
            self.resize(1240, 820)
            self.setMinimumSize(1000, 680)
            self.files = []
            self.idx = -1
            self.src_rgb = None
            self.result = None
            self._token = 0
            self._worker = None
            self._t0 = 0.0
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(180)
            self._timer.timeout.connect(self.render)
            self.setAcceptDrops(True)
            self._build()
            self._sync_mode()

        # ---------- 构建 ----------
        def _build(self):
            central = QWidget()
            self.setCentralWidget(central)
            root = QHBoxLayout(central)
            root.setContentsMargins(12, 12, 12, 12)
            root.setSpacing(12)

            left = QWidget()
            left.setFixedWidth(350)
            lv = QVBoxLayout(left)
            lv.setSpacing(8)

            t = QLabel("InkQuill")
            t.setStyleSheet("font-size:22px; font-weight:700;")
            s = QLabel("图片 → 黑白线稿图（输出与输入同格式）")
            s.setStyleSheet("color:#888;")
            lv.addWidget(t)
            lv.addWidget(s)

            g1 = QGroupBox("预设")
            h1 = QHBoxLayout(g1)
            self.cb_preset = QComboBox()
            self.cb_preset.addItems(list(PRESETS))
            self.cb_preset.currentTextChanged.connect(self.on_preset)
            h1.addWidget(self.cb_preset)
            lv.addWidget(g1)

            g2 = QGroupBox("图片（可直接拖入窗口）")
            v2 = QVBoxLayout(g2)
            b_pick = QPushButton("选择图片…")
            b_pick.clicked.connect(self.pick)
            self.listw = QListWidget()
            self.listw.setMaximumHeight(110)
            self.listw.currentRowChanged.connect(self.on_select)
            r2 = QHBoxLayout()
            b_rm = QPushButton("移除选中")
            b_rm.clicked.connect(self.remove_sel)
            b_cl = QPushButton("清空")
            b_cl.clicked.connect(self.clear_all)
            r2.addWidget(b_rm)
            r2.addWidget(b_cl)
            v2.addWidget(b_pick)
            v2.addWidget(self.listw)
            v2.addLayout(r2)
            lv.addWidget(g2)

            g3 = QGroupBox("模式与参数")
            v3 = QVBoxLayout(g3)
            mr = QHBoxLayout()
            mr.addWidget(QLabel("模式"))
            self.cb_mode = QComboBox()
            self.cb_mode.addItems([MODES[k] for k in MODES])
            self.cb_mode.currentIndexChanged.connect(lambda _: self._sync_mode())
            mr.addWidget(self.cb_mode, 1)
            v3.addLayout(mr)

            cr = QHBoxLayout()
            cr.addWidget(QLabel("输出色彩"))
            self.rb_bw = QRadioButton("纯黑白")
            self.rb_gray = QRadioButton("灰度")
            self.rb_bw.setChecked(True)
            self.rb_bw.setToolTip("结果只有黑、白两色，线条最干净利落")
            self.rb_gray.setToolTip("保留浅灰过渡，边缘更柔和（更像铅笔稿）")
            self._colorgrp = QButtonGroup(self)
            self._colorgrp.addButton(self.rb_bw)
            self._colorgrp.addButton(self.rb_gray)
            self.rb_bw.toggled.connect(self.schedule)
            cr.addWidget(self.rb_bw)
            cr.addWidget(self.rb_gray)
            cr.addStretch(1)
            v3.addLayout(cr)

            self._rows = {}
            self.sl_detail = self._add_slider(v3, "detail", "细节", 0, 100, 70)
            self.sl_dilate = self._add_slider(v3, "dilate", "加粗", 0, 3, 0)
            self.sl_blur = self._add_slider(v3, "blur", "柔化", 0, 5, 0)
            self.sl_simplify = self._add_slider(v3, "simplify", "简化", 0, 100, 15)
            self.sl_thresh = self._add_slider(v3, "thresh", "阈值", 0, 255, 128)
            self.sl_clow = self._add_slider(v3, "clow", "边低", 0, 255, 40)
            self.sl_chigh = self._add_slider(v3, "chigh", "边高", 0, 255, 120)
            self.sl_contrast = self._add_slider(v3, "contrast", "对比", 50, 200, 100)

            self.chk_auto = QCheckBox("自动阈值 (Otsu)")
            self.chk_auto.setChecked(True)
            self.chk_adaptive = QCheckBox("自适应阈值（扫描件/光照不均）")
            self.chk_invert = QCheckBox("反相（黑底图）")
            self.chk_trim = QCheckBox("裁白边")
            for c in (self.chk_auto, self.chk_adaptive, self.chk_invert, self.chk_trim):
                c.toggled.connect(self.schedule)
                v3.addWidget(c)
            lv.addWidget(g3)

            g4 = QGroupBox("输出")
            v4 = QVBoxLayout(g4)
            b_save = QPushButton("保存当前…")
            b_save.setObjectName("primary")
            b_save.clicked.connect(self.save_current)
            b_batch = QPushButton("批量处理全部…")
            b_batch.setObjectName("primary")
            b_batch.clicked.connect(self.batch)
            v4.addWidget(b_save)
            v4.addWidget(b_batch)
            lv.addWidget(g4)
            lv.addStretch(1)

            right = QWidget()
            rv = QVBoxLayout(right)
            rv.setSpacing(6)
            tr = QHBoxLayout()
            t1 = QLabel("原图")
            t2 = QLabel("黑白线稿（结果）")
            t1.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tr.addWidget(t1, 1)
            tr.addWidget(t2, 1)
            self.pv_src = Preview()
            self.pv_res = Preview()
            pr = QHBoxLayout()
            pr.addWidget(self.pv_src, 1)
            pr.addWidget(self.pv_res, 1)
            rv.addLayout(tr)
            rv.addLayout(pr, 1)

            root.addWidget(left)
            root.addWidget(right, 1)

            self.status = QLabel("就绪：点「选择图片…」，或把图片拖进窗口。")
            self.status.setStyleSheet("color:#0a7a4a; padding:4px;")
            self.statusBar().addWidget(self.status)

        def _add_slider(self, parent, key, label, lo, hi, val):
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            name = QLabel(label)
            name.setFixedWidth(44)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(val)
            vlab = QLabel(str(val))
            vlab.setFixedWidth(34)
            vlab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sl.valueChanged.connect(lambda x, lb=vlab: (lb.setText(str(x)), self.schedule()))
            row.addWidget(name)
            row.addWidget(sl, 1)
            row.addWidget(vlab)
            parent.addWidget(box)
            self._rows[key] = box
            return sl

        # ---------- 状态 ----------
        def _sync_mode(self):
            key = list(MODES)[self.cb_mode.currentIndex()]
            show = {
                "lineart": ("detail", "dilate", "blur", "simplify", "contrast"),
                "edge": ("dilate", "blur", "simplify", "clow", "chigh"),
                "binary": ("thresh", "blur", "simplify"),
                "gray": ("contrast", "blur", "simplify"),
            }[key]
            for k, box in self._rows.items():
                box.setVisible(k in show)
            is_bin = (key == "binary")
            self.chk_auto.setEnabled(is_bin)
            self.chk_adaptive.setEnabled(is_bin)
            self.schedule()

        def current_params(self) -> Params:
            return Params(
                mode=list(MODES)[self.cb_mode.currentIndex()],
                color="gray" if self.rb_gray.isChecked() else "binary",
                detail=self.sl_detail.value() / 100.0,
                dilate=self.sl_dilate.value(),
                blur=self.sl_blur.value(),
                simplify=self.sl_simplify.value(),
                thresh=self.sl_thresh.value(),
                auto_thresh=self.chk_auto.isChecked(),
                adaptive=self.chk_adaptive.isChecked(),
                canny_low=self.sl_clow.value(),
                canny_high=self.sl_chigh.value(),
                contrast=self.sl_contrast.value() / 100.0,
                invert=self.chk_invert.isChecked(),
                trim=self.chk_trim.isChecked(),
            )

        # ---------- 交互 ----------
        def on_preset(self, name):
            cfg = PRESETS.get(name)
            if not cfg:
                return
            if "mode" in cfg:
                self.cb_mode.setCurrentIndex(list(MODES).index(cfg["mode"]))
            if "color" in cfg:
                (self.rb_gray if cfg["color"] == "gray" else self.rb_bw).setChecked(True)
            if "detail" in cfg:
                self.sl_detail.setValue(round(cfg["detail"] * 100))
            if "dilate" in cfg:
                self.sl_dilate.setValue(cfg["dilate"])
            if "blur" in cfg:
                self.sl_blur.setValue(cfg["blur"])
            if "simplify" in cfg:
                self.sl_simplify.setValue(cfg["simplify"])
            if "contrast" in cfg:
                self.sl_contrast.setValue(round(cfg.get("contrast", 1.0) * 100))
            if "auto_thresh" in cfg:
                self.chk_auto.setChecked(cfg["auto_thresh"])
            if "adaptive" in cfg:
                self.chk_adaptive.setChecked(cfg["adaptive"])
            if "invert" in cfg:
                self.chk_invert.setChecked(cfg["invert"])
            self._sync_mode()

        def pick(self):
            paths, _ = QFileDialog.getOpenFileNames(
                self, "选择图片", "",
                "图片 (*.png *.jpg *.jpeg *.jfif *.bmp *.webp *.tif *.tiff);;所有文件 (*)")
            if not paths:
                return
            for p in paths:
                if p not in self.files:
                    self.files.append(p)
                    self.listw.addItem(os.path.basename(p))
            self.listw.setCurrentRow(len(self.files) - 1)

        def _add_paths(self, paths):
            added = False
            for p in paths:
                if p.lower().endswith(SUPPORTED) and p not in self.files:
                    self.files.append(p)
                    self.listw.addItem(os.path.basename(p))
                    added = True
            if added:
                self.listw.setCurrentRow(len(self.files) - 1)

        def remove_sel(self):
            rows = sorted({i.row() for i in self.listw.selectedIndexes()}, reverse=True)
            for r in rows:
                self.listw.takeItem(r)
                del self.files[r]
            if self.files:
                self.listw.setCurrentRow(min(self.idx, len(self.files) - 1))
            else:
                self.clear_all()

        def clear_all(self):
            self.files.clear()
            self.listw.clear()
            self.idx = -1
            self.src_rgb = None
            self.result = None
            self.pv_src.clear_image()
            self.pv_res.clear_image()
            self.status.setText("列表已清空。")

        def on_select(self, row):
            if row < 0 or row >= len(self.files):
                return
            self.idx = row
            try:
                self.src_rgb = load_rgb(self.files[row])
            except Exception as e:
                QMessageBox.critical(self, "读取失败", str(e))
                return
            self.pv_src.set_image(self.src_rgb)
            self.schedule()

        # ---------- 预览 ----------
        def schedule(self):
            if hasattr(self, "_timer"):
                self._timer.start()

        def render(self):
            if self.src_rgb is None:
                return
            self._token += 1
            token = self._token
            self.result = None
            self._t0 = time.time()
            self.status.setText("处理中…")
            w = Worker(self.src_rgb, self.current_params(), token)
            w.ok.connect(self.on_ok)
            w.err.connect(self.on_err)
            self._worker = w
            w.start()

        def on_ok(self, token, res):
            if token != self._token:
                return
            self.result = res
            self.pv_res.set_image(res)
            h, w = res.shape[:2]
            p = self.current_params()
            self.status.setText("已生成：%d × %d ｜ %s / %s ｜ 用时 %.2fs" % (
                w, h, MODES[p.mode], COLOR_MODES[p.color], time.time() - self._t0))

        def on_err(self, token, msg):
            if token != self._token:
                return
            self.status.setText("处理出错：%s" % msg)

        # ---------- 拖拽 ----------
        def dragEnterEvent(self, e):
            if e.mimeData().hasUrls():
                e.acceptProposedAction()

        def dropEvent(self, e):
            self._add_paths([u.toLocalFile() for u in e.mimeData().urls()])

        # ---------- 输出 ----------
        def save_current(self):
            if self.result is None or self.idx < 0:
                QMessageBox.information(self, "提示", "请先选择图片并生成预览。")
                return
            src = self.files[self.idx]
            stem, ext = os.path.splitext(os.path.basename(src))
            dst, _ = QFileDialog.getSaveFileName(
                self, "保存线稿",
                os.path.join(os.path.dirname(src), stem + "_lineart" + ext),
                "同输入格式 (*%s);;PNG (*.png);;JPEG (*.jpg);;所有文件 (*)" % ext)
            if not dst:
                return
            try:
                save_image(self.result, dst)
                self.status.setText("已保存：%s" % dst)
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))

        def batch(self):
            if not self.files:
                QMessageBox.information(self, "提示", "请先选择图片。")
                return
            outdir = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
            if not outdir:
                return
            p = self.current_params()
            ok = fail = 0
            for i, src in enumerate(self.files):
                self.status.setText("批量处理 %d/%d …" % (i + 1, len(self.files)))
                QApplication.processEvents()
                st = convert_file(src, output_path_for(src, outdir, True), p, force=True)
                ok += (st == "ok")
                fail += (st != "ok")
            self.status.setText("批量完成：成功 %d，失败 %d → %s" % (ok, fail, outdir))
            QMessageBox.information(self, "批量处理", "完成：成功 %d，失败 %d\n输出目录：%s" % (ok, fail, outdir))

    app = QApplication.instance() or QApplication(sys.argv)
    try:
        app.setStyle("Fusion")
        app.setStyleSheet(_QT_QSS)
    except Exception:
        pass
    win = MainWindow()

    if test:
        synth = np.full((320, 420, 3), 255, np.uint8)
        cv2.rectangle(synth, (60, 60), (300, 250), (0, 0, 0), 6)
        cv2.circle(synth, (330, 90), 40, (0, 0, 0), 6)
        win.files = ["<self-test>"]
        win.idx = 0
        win.src_rgb = synth
        win.pv_src.set_image(synth)
        ok_all = True
        for mode in list(MODES):
            win.cb_mode.setCurrentIndex(list(MODES).index(mode))
            win._sync_mode()
            win.render()
            for _ in range(400):
                app.processEvents()
                if win.result is not None and not win.status.text().startswith("处理中"):
                    break
                time.sleep(0.02)
            h, w = (win.result.shape[:2] if win.result is not None else (0, 0))
            good = win.result is not None and (w, h) == (420, 320)
            ok_all = ok_all and good
            print("  [%s] Qt 预览 %-8s → %s" % ("OK" if good else "!!", mode, (w, h)))
        win.resize(1240, 820)
        win.show()
        app.processEvents()
        shot = os.environ.get("INKQUILL_SHOT", "/tmp/inkquill_qt.png")
        win.grab().save(shot)
        print("Qt GUI 自检 %s（界面截图：%s）" % ("通过" if ok_all else "失败", shot))
        return 0 if ok_all else 1

    win.show()
    return app.exec()


def launch_gui(test: bool = False, backend: str = "auto") -> int:
    """图形界面入口。backend: auto（优先 Qt）/ qt / tk。"""
    if backend == "auto":
        backend = "qt" if _qt_available() else "tk"
    if backend == "qt":
        if not _qt_available():
            sys.stderr.write("未安装 PySide6，无法使用 Qt 界面。安装：pip install PySide6\n")
            return 2
        return _run_qt_gui(test)
    return _run_tk_gui(test)


def _run_tk_gui(test: bool = False) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except Exception as e:  # pragma: no cover
        sys.stderr.write("无法启动图形界面（%s）。可直接用命令行：python inkquill.py 图片.png\n" % e)
        return 2

    class App:
        def __init__(self, root):
            self.root = root
            root.title("InkQuill —— 图片转黑白线稿图  v%s" % __version__)
            root.geometry("1200x800")
            root.minsize(980, 660)

            self.files = []
            self.current_idx = 0
            self.src_img = None
            self.result_arr = None
            self._tk_src = None
            self._tk_res = None
            self._preview_after = None
            self._executor = ThreadPoolExecutor(max_workers=1)
            self._preview_token = 0

            self._build_vars()
            self._build_ui()
            self._on_mode_change()
            root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---------- 变量 ----------
        def _build_vars(self):
            self.v_preset = tk.StringVar(value="自定义")
            self.v_mode = tk.StringVar(value="lineart")
            self.v_color = tk.StringVar(value="binary")
            self.v_detail = tk.DoubleVar(value=70)
            self.v_dilate = tk.IntVar(value=0)
            self.v_blur = tk.IntVar(value=0)
            self.v_simplify = tk.IntVar(value=15)
            self.v_thresh = tk.DoubleVar(value=128)
            self.v_auto = tk.BooleanVar(value=True)
            self.v_adaptive = tk.BooleanVar(value=False)
            self.v_canny_low = tk.DoubleVar(value=40)
            self.v_canny_high = tk.DoubleVar(value=120)
            self.v_contrast = tk.DoubleVar(value=100)
            self.v_invert = tk.BooleanVar(value=False)
            self.v_trim = tk.BooleanVar(value=False)
            self.v_status = tk.StringVar(value="就绪：点「选择图片…」加载图片。")

        # ---------- 界面 ----------
        def _build_ui(self):
            root = self.root
            root.columnconfigure(1, weight=1)
            root.rowconfigure(0, weight=1)

            left = ttk.Frame(root, padding=10)
            left.grid(row=0, column=0, sticky="ns")
            right = ttk.Frame(root, padding=10)
            right.grid(row=0, column=1, sticky="nsew")

            ttk.Label(left, text="InkQuill", font=("", 16, "bold")).pack(anchor="w")
            ttk.Label(left, text="图片 → 黑白线稿图", foreground="#666").pack(anchor="w", pady=(0, 8))

            # 预设
            prow = ttk.Frame(left); prow.pack(fill="x", pady=(0, 6))
            ttk.Label(prow, text="预设", width=8).pack(side="left")
            self.cb_preset = ttk.Combobox(prow, state="readonly", width=16, values=list(PRESETS))
            self.cb_preset.current(0)
            self.cb_preset.pack(side="left", fill="x", expand=True)
            self.cb_preset.bind("<<ComboboxSelected>>", self.on_preset)

            ttk.Button(left, text="选择图片…", command=self.on_pick).pack(fill="x")
            fl = ttk.Frame(left)
            fl.pack(fill="both", expand=False, pady=6)
            self.lst = tk.Listbox(fl, height=5, activestyle="none", selectmode="extended")
            self.lst.pack(side="left", fill="both", expand=True)
            sb = ttk.Scrollbar(fl, orient="vertical", command=self.lst.yview)
            sb.pack(side="right", fill="y")
            self.lst.config(yscrollcommand=sb.set)
            self.lst.bind("<<ListboxSelect>>", self.on_select)
            lstbtn = ttk.Frame(left); lstbtn.pack(fill="x")
            ttk.Button(lstbtn, text="移除选中", command=self.on_remove).pack(side="left", fill="x", expand=True)
            ttk.Button(lstbtn, text="清空", command=self.on_clear).pack(side="left", fill="x", expand=True)

            box = ttk.LabelFrame(left, text="模式与参数", padding=8)
            box.pack(fill="x", pady=8)

            row = ttk.Frame(box); row.pack(fill="x")
            ttk.Label(row, text="模式", width=8).pack(side="left")
            self.cb_mode = ttk.Combobox(row, state="readonly", width=16, values=[MODES[k] for k in MODES])
            self.cb_mode.current(0)
            self.cb_mode.pack(side="left", fill="x", expand=True)
            self.cb_mode.bind("<<ComboboxSelected>>", lambda e: self._on_mode_change())

            row = ttk.Frame(box); row.pack(fill="x", pady=(6, 0))
            ttk.Label(row, text="输出色彩", width=8).pack(side="left")
            for key, label in COLOR_MODES.items():
                ttk.Radiobutton(row, text=label, value=key, variable=self.v_color,
                                command=self.schedule_preview).pack(side="left", padx=(0, 10))

            self.s_detail = self._slider(box, "细节", self.v_detail, 0, 100)
            self.s_dilate = self._slider(box, "加粗", self.v_dilate, 0, 3)
            self.s_blur = self._slider(box, "柔化", self.v_blur, 0, 5)
            self.s_simplify = self._slider(box, "简化", self.v_simplify, 0, 100)
            self.s_thresh = self._slider(box, "阈值", self.v_thresh, 0, 255)
            self.s_canny_low = self._slider(box, "边低", self.v_canny_low, 0, 255)
            self.s_canny_high = self._slider(box, "边高", self.v_canny_high, 0, 255)
            self.s_contrast = self._slider(box, "对比", self.v_contrast, 50, 200)

            opt = ttk.Frame(box); opt.pack(fill="x", pady=(4, 0))
            self.chk_auto = ttk.Checkbutton(opt, text="自动阈值 (Otsu)", variable=self.v_auto,
                                            command=self.schedule_preview)
            self.chk_auto.pack(anchor="w")
            self.chk_adaptive = ttk.Checkbutton(opt, text="自适应阈值（扫描件/光照不均）",
                                                variable=self.v_adaptive, command=self.schedule_preview)
            self.chk_adaptive.pack(anchor="w")
            ttk.Checkbutton(opt, text="反相（黑底图）", variable=self.v_invert,
                            command=self.schedule_preview).pack(anchor="w")
            ttk.Checkbutton(opt, text="裁白边", variable=self.v_trim,
                            command=self.schedule_preview).pack(anchor="w")

            btns = ttk.Frame(left); btns.pack(fill="x", pady=(6, 0))
            ttk.Button(btns, text="保存当前…", command=self.on_save_current).pack(fill="x", pady=2)
            ttk.Button(btns, text="批量处理全部…", command=self.on_batch).pack(fill="x", pady=2)

            ttk.Label(left, textvariable=self.v_status, wraplength=310,
                      foreground="#0a6", justify="left").pack(anchor="w", pady=(8, 0))

            right.columnconfigure(0, weight=1)
            right.columnconfigure(1, weight=1)
            right.rowconfigure(1, weight=1)
            ttk.Label(right, text="原图", anchor="center").grid(row=0, column=0, sticky="ew")
            ttk.Label(right, text="黑白线稿（结果）", anchor="center").grid(row=0, column=1, sticky="ew")
            self.cv_src = tk.Canvas(right, bg="#f0f0f0", highlightthickness=1, highlightbackground="#ccc")
            self.cv_src.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
            self.cv_res = tk.Canvas(right, bg="#f0f0f0", highlightthickness=1, highlightbackground="#ccc")
            self.cv_res.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
            self.cv_src.bind("<Configure>", lambda e: self._draw_canvas(self.cv_src, self._tk_src))
            self.cv_res.bind("<Configure>", lambda e: self._draw_canvas(self.cv_res, self._tk_res))

            self._mode_sliders = {
                "lineart": [self.s_detail, self.s_dilate, self.s_blur, self.s_simplify, self.s_contrast],
                "edge": [self.s_dilate, self.s_blur, self.s_simplify, self.s_canny_low, self.s_canny_high],
                "binary": [self.s_thresh, self.s_blur, self.s_simplify],
                "gray": [self.s_contrast, self.s_blur, self.s_simplify],
            }

        def _slider(self, parent, label, var, lo, hi):
            row = ttk.Frame(parent); row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, width=8).pack(side="left")
            val = ttk.Label(row, width=4, anchor="e")
            val.pack(side="right")
            sc = ttk.Scale(row, from_=lo, to=hi, orient="horizontal", variable=var,
                           command=lambda v, lb=val: (lb.config(text="%g" % round(float(v))),
                                                      self.schedule_preview()))
            sc.pack(side="left", fill="x", expand=True, padx=4)
            val.config(text="%g" % round(float(var.get())))
            return sc

        def _set_var(self, var, value):
            var.set(value)

        def on_preset(self, _e=None):
            name = self.cb_preset.get()
            cfg = PRESETS.get(name)
            if not cfg:
                return
            if "mode" in cfg:
                self.cb_mode.current(list(MODES).index(cfg["mode"]))
            if "color" in cfg:
                self.v_color.set(cfg["color"])
            if "detail" in cfg:
                self.v_detail.set(round(cfg["detail"] * 100))
            if "dilate" in cfg:
                self.v_dilate.set(cfg["dilate"])
            if "blur" in cfg:
                self.v_blur.set(cfg["blur"])
            if "simplify" in cfg:
                self.v_simplify.set(cfg["simplify"])
            if "contrast" in cfg:
                self.v_contrast.set(round(cfg.get("contrast", 1.0) * 100))
            if "auto_thresh" in cfg:
                self.v_auto.set(cfg["auto_thresh"])
            if "adaptive" in cfg:
                self.v_adaptive.set(cfg["adaptive"])
            if "invert" in cfg:
                self.v_invert.set(cfg["invert"])
            self._refresh_slider_labels()
            self._on_mode_change()

        def _refresh_slider_labels(self):
            for var, sc in [(self.v_detail, self.s_detail), (self.v_dilate, self.s_dilate),
                            (self.v_blur, self.s_blur), (self.v_simplify, self.s_simplify),
                            (self.v_thresh, self.s_thresh), (self.v_canny_low, self.s_canny_low),
                            (self.v_canny_high, self.s_canny_high), (self.v_contrast, self.s_contrast)]:
                try:
                    sc.set(var.get())
                except Exception:
                    pass

        def current_params(self) -> Params:
            return Params(
                mode=list(MODES)[self.cb_mode.current()],
                color=self.v_color.get(),
                detail=self.v_detail.get() / 100.0,
                dilate=int(round(self.v_dilate.get())),
                blur=int(round(self.v_blur.get())),
                simplify=int(round(self.v_simplify.get())),
                thresh=int(round(self.v_thresh.get())),
                auto_thresh=bool(self.v_auto.get()),
                adaptive=bool(self.v_adaptive.get()),
                canny_low=int(round(self.v_canny_low.get())),
                canny_high=int(round(self.v_canny_high.get())),
                contrast=self.v_contrast.get() / 100.0,
                invert=bool(self.v_invert.get()),
                trim=bool(self.v_trim.get()),
            )

        def _on_mode_change(self):
            key = list(MODES)[self.cb_mode.current()]
            for k, sliders in self._mode_sliders.items():
                on = (k == key)
                for s in sliders:
                    try:
                        s.state(["!disabled"] if on else ["disabled"])
                    except Exception:
                        pass
            is_bin = (key == "binary")
            for c in (self.chk_auto, self.chk_adaptive):
                try:
                    c.state(["!disabled"] if is_bin else ["disabled"])
                except Exception:
                    pass
            self.schedule_preview()

        # ---------- 选图 ----------
        def on_pick(self):
            paths = filedialog.askopenfilenames(
                title="选择图片",
                filetypes=[("图片", "*.png *.jpg *.jpeg *.jfif *.bmp *.webp *.tif *.tiff"),
                           ("所有文件", "*.*")])
            if not paths:
                return
            for p in paths:
                if p not in self.files:
                    self.files.append(p)
                    self.lst.insert("end", os.path.basename(p))
            self.current_idx = len(self.files) - 1
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(self.current_idx)
            self.load_current()

        def on_remove(self):
            sel = list(self.lst.curselection())
            for i in reversed(sel):
                self.lst.delete(i)
                del self.files[i]
            if self.files:
                self.current_idx = min(self.current_idx, len(self.files) - 1)
                self.lst.selection_clear(0, "end")
                self.lst.selection_set(self.current_idx)
                self.load_current()
            else:
                self.on_clear()

        def on_clear(self):
            self.files.clear(); self.lst.delete(0, "end")
            self.src_img = None; self.result_arr = None
            self._tk_src = self._tk_res = None
            self.cv_src.delete("all"); self.cv_res.delete("all")
            self.v_status.set("列表已清空。")

        def on_select(self, _e=None):
            sel = self.lst.curselection()
            if sel:
                self.current_idx = sel[0]
                self.load_current()

        def load_current(self):
            if not self.files:
                return
            try:
                self.src_img = Image.fromarray(load_rgb(self.files[self.current_idx]))
            except Exception as e:
                messagebox.showerror("读取失败", "%s\n%s" % (self.files[self.current_idx], e))
                return
            self._tk_src = self._fit_tk(self.src_img, self.cv_src)
            self._draw_canvas(self.cv_src, self._tk_src)
            self.schedule_preview()

        # ---------- 预览（后台线程处理，UI 不卡） ----------
        def schedule_preview(self):
            if self._preview_after:
                try:
                    self.root.after_cancel(self._preview_after)
                except Exception:
                    pass
            self._preview_after = self.root.after(200, self.render_preview)

        def render_preview(self):
            self._preview_after = None
            if self.src_img is None:
                return
            self._preview_token += 1
            token = self._preview_token
            rgb = np.array(self.src_img)
            p = self.current_params()
            self.v_status.set("处理中…")
            t0 = time.time()
            fut = self._executor.submit(process_rgb, rgb, p)
            self._poll_result(fut, token, p, t0)

        def _poll_result(self, fut, token, p, t0):
            if token != self._preview_token:
                return
            if not fut.done():
                self.root.after(40, lambda: self._poll_result(fut, token, p, t0))
                return
            try:
                res = fut.result()
            except Exception as e:
                self.v_status.set("处理出错：%s" % e)
                return
            self.result_arr = res
            self._tk_res = self._fit_tk(Image.fromarray(res), self.cv_res)
            self._draw_canvas(self.cv_res, self._tk_res)
            h, w = res.shape[:2]
            self.v_status.set("已生成：%d × %d ｜ %s / %s ｜ 用时 %.2fs" % (
                w, h, MODES[p.mode], COLOR_MODES[p.color], time.time() - t0))

        def _fit_tk(self, im: Image.Image, canvas):
            cw = max(canvas.winfo_width(), 320)
            ch = max(canvas.winfo_height(), 320)
            w, h = im.size
            s = min(cw / w, ch / h, 1.0)
            disp = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS) if s < 1 else im
            if disp.mode not in ("RGB", "RGBA", "L"):
                disp = disp.convert("RGB")
            return ImageTk.PhotoImage(disp)

        def _draw_canvas(self, canvas, photo):
            canvas.delete("all")
            if photo is None:
                return
            canvas.create_image(canvas.winfo_width() // 2, canvas.winfo_height() // 2, image=photo)

        # ---------- 保存 ----------
        def on_save_current(self):
            if self.result_arr is None or not self.files:
                messagebox.showinfo("提示", "请先选择图片并生成预览。")
                return
            src = self.files[self.current_idx]
            stem, ext = os.path.splitext(os.path.basename(src))
            dst = filedialog.asksaveasfilename(
                title="保存线稿", defaultextension=ext,
                initialfile=stem + "_lineart" + ext, initialdir=os.path.dirname(src),
                filetypes=[("同输入格式 (*%s)" % ext, "*" + ext), ("PNG", "*.png"),
                           ("JPEG", "*.jpg"), ("所有文件", "*.*")])
            if not dst:
                return
            try:
                save_image(self.result_arr, dst)
                self.v_status.set("已保存：%s" % dst)
            except Exception as e:
                messagebox.showerror("保存失败", str(e))

        def on_batch(self):
            if not self.files:
                messagebox.showinfo("提示", "请先选择图片。")
                return
            outdir = filedialog.askdirectory(title="选择输出文件夹")
            if not outdir:
                return
            p = self.current_params()
            ok = fail = 0
            n = len(self.files)
            for i, src in enumerate(self.files):
                self.v_status.set("批量处理 %d/%d …" % (i + 1, n))
                self.root.update_idletasks()
                st = convert_file(src, output_path_for(src, outdir, True), p, force=True)
                ok += (st == "ok")
                fail += (st != "ok")
            self.v_status.set("批量完成：成功 %d，失败 %d → %s" % (ok, fail, outdir))
            messagebox.showinfo("批量处理", "完成：成功 %d，失败 %d\n输出目录：%s" % (ok, fail, outdir))

        def _on_close(self):
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                pass
            self.root.destroy()

    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    app = App(root)

    if test:
        root.update_idletasks(); root.update()
        synth = np.full((320, 420, 3), 255, np.uint8)
        cv2.rectangle(synth, (60, 60), (300, 250), (0, 0, 0), 6)
        cv2.circle(synth, (330, 90), 40, (0, 0, 0), 6)
        app.files = ["<self-test>"]
        app.src_img = Image.fromarray(synth)
        ok_all = True
        for mode in list(MODES):
            app.cb_mode.current(list(MODES).index(mode))
            app._on_mode_change()
            app.render_preview()
            # 等待异步预览完成
            for _ in range(100):
                root.update()
                if app.result_arr is not None and not app.v_status.get().startswith("处理中"):
                    break
                time.sleep(0.02)
            h, w = (app.result_arr.shape[:2] if app.result_arr is not None else (0, 0))
            good = app.result_arr is not None and (w, h) == (420, 320)
            ok_all = ok_all and good
            print("  [%s] GUI 预览 %-8s → %s" % ("OK" if good else "!!", mode, (w, h)))
        app._executor.shutdown(wait=True)
        root.destroy()
        print("GUI 自检 %s" % ("通过" if ok_all else "失败"))
        return 0 if ok_all else 1

    root.mainloop()
    return 0


# ======================================================================
# 自检（无需图形界面）
# ======================================================================
def _selftest() -> int:
    print("inkquill selftest …")
    try:
        from skimage import data
        src = data.camera()
        if src.ndim == 2:
            src = cv2.cvtColor(src, cv2.COLOR_GRAY2RGB)
    except Exception:
        src = np.full((360, 480, 3), 255, np.uint8)
        cv2.circle(src, (150, 180), 90, (40, 40, 40), 6)
        cv2.rectangle(src, (280, 90), (430, 270), (10, 10, 10), 8)
        cv2.putText(src, "Line", (70, 330), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 6)

    base = Params(max_size=0)
    tests = [("lineart", "binary"), ("lineart", "gray"), ("edge", "binary"),
             ("binary", "binary"), ("gray", "gray")]
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest")
    os.makedirs(outdir, exist_ok=True)
    all_ok = True
    for mode, color in tests:
        res = process_rgb(src, replace(base, mode=mode, color=color))
        save_image(res, os.path.join(outdir, "%s_%s.png" % (mode, color)))
        uniq = len(np.unique(res))
        ok = res.shape[:2] == src.shape[:2] and res.dtype == np.uint8 and uniq > 1
        all_ok = all_ok and ok
        print("  [%s] %-16s 灰度级=%d %s" % ("OK" if ok else "!!",
              "%s_%s" % (mode, color), uniq, "" if ok else "← 异常"))
    # 自适应阈值单独验证
    res = process_rgb(src, replace(base, mode="binary", adaptive=True))
    ok = len(np.unique(res)) > 1
    all_ok = all_ok and ok
    print("  [%s] %-16s 灰度级=%d" % ("OK" if ok else "!!", "binary_adaptive", len(np.unique(res))))
    print("selftest %s，结果在：%s" % ("通过" if all_ok else "失败", outdir))
    return 0 if all_ok else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        return _selftest()
    if argv and argv[0] == "--gui-selftest":
        return launch_gui(test=True)
    return run_cli(argv)


if __name__ == "__main__":
    sys.exit(main())
