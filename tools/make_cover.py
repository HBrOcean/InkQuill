#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 assets/cover.jpg 生成：
  - assets/cover_named.jpg   方形封面（带项目名，README 顶部 banner 用）
  - assets/social_preview.png GitHub 社交预览图（1280x640）

用法：  python tools/make_cover.py
依赖：  Pillow、numpy；字体默认用 Linux 自带的 DejaVu，
        其他系统可把 BOLD / REG 改成系统里存在的字体路径。
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Windows 控制台默认编码非 UTF-8，打印中文前先统一切换，避免 UnicodeEncodeError。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SRC = os.path.join(ASSETS, "cover.jpg")

BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

TITLE = "InkQuill"
SUBTITLE = "picture · lines · ink"
TAGLINE = ["Turn a picture into clean", "black & white line art."]

INK = (16, 16, 16)
GREY = (95, 95, 95)


def center_text(draw, text, font, y, fill, width):
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (bbox[2] - bbox[0])) // 2 - bbox[0], y), text, font=font, fill=fill)


def main():
    if not os.path.exists(SRC):
        raise SystemExit("找不到 %s" % SRC)
    src = Image.open(SRC).convert("RGB")

    # 取四角平均色做画布底色，让图形与背景无缝衔接
    a = np.array(src)
    corners = np.concatenate([
        a[0:20, 0:20].reshape(-1, 3), a[0:20, -20:].reshape(-1, 3),
        a[-20:, 0:20].reshape(-1, 3), a[-20:, -20:].reshape(-1, 3)])
    bg = tuple(int(x) for x in corners.mean(0))

    # 方形封面
    C = 1024
    canvas = Image.new("RGB", (C, C), bg)
    gsize = 600
    canvas.paste(src.resize((gsize, gsize), Image.LANCZOS), ((C - gsize) // 2, 96))
    d = ImageDraw.Draw(canvas)
    center_text(d, TITLE, ImageFont.truetype(BOLD, 118), 726, INK, C)
    center_text(d, SUBTITLE, ImageFont.truetype(REG, 36), 888, GREY, C)
    canvas.save(os.path.join(ASSETS, "cover_named.jpg"), quality=95)

    # 社交预览图
    SW, SH = 1280, 640
    sp = Image.new("RGB", (SW, SH), bg)
    g2 = 392
    sp.paste(src.resize((g2, g2), Image.LANCZOS), (92, (SH - g2) // 2))
    d2 = ImageDraw.Draw(sp)
    d2.text((560, 186), TITLE, font=ImageFont.truetype(BOLD, 100), fill=INK)
    f2 = ImageFont.truetype(REG, 32)
    for i, line in enumerate(TAGLINE):
        d2.text((564, 322 + i * 46), line, font=f2, fill=(80, 80, 80))
    sp.save(os.path.join(ASSETS, "social_preview.png"))

    print("已生成：assets/cover_named.jpg、assets/social_preview.png")


if __name__ == "__main__":
    main()
