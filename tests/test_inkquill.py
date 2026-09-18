# -*- coding: utf-8 -*-
"""InkQuill 单元测试。"""
import os
import sys
from dataclasses import replace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inkquill as K  # noqa: E402

BASE = K.Params(max_size=0)


@pytest.fixture
def photo():
    """一张真实灰度照片（skimage 内置图），取不到时退回合成图。"""
    try:
        from skimage import data
        return K.cv2.cvtColor(data.camera(), K.cv2.COLOR_GRAY2RGB)
    except Exception:
        img = np.full((200, 300, 3), 255, np.uint8)
        K.cv2.rectangle(img, (40, 40), (200, 160), (0, 0, 0), 4)
        K.cv2.circle(img, (250, 90), 30, (0, 0, 0), 4)
        return img


@pytest.mark.parametrize("mode,color", [
    ("lineart", "binary"), ("lineart", "gray"),
    ("edge", "binary"), ("binary", "binary"), ("gray", "gray"),
])
def test_modes_keep_size_and_type(photo, mode, color):
    res = K.process_rgb(photo, replace(BASE, mode=mode, color=color))
    assert res.shape[:2] == photo.shape[:2]
    assert res.dtype == np.uint8
    assert len(np.unique(res)) > 1


def test_pure_bw_is_two_tone(photo):
    res = K.process_rgb(photo, replace(BASE, mode="lineart", color="binary"))
    assert set(np.unique(res)).issubset({0, 255})


def test_adaptive_threshold_binary(photo):
    res = K.process_rgb(photo, replace(BASE, mode="binary", adaptive=True))
    assert set(np.unique(res)).issubset({0, 255})


def test_invert_flips(photo):
    a = K.process_rgb(photo, replace(BASE, mode="lineart", color="binary"))
    b = K.process_rgb(photo, replace(BASE, mode="lineart", color="binary", invert=True))
    assert np.array_equal(a, 255 - b)


def test_trim_removes_white_border():
    canvas = np.full((400, 500, 3), 255, np.uint8)
    canvas[100:300, 150:350] = 0
    res = K.process_rgb(canvas, replace(BASE, mode="binary", color="binary", trim=True))
    assert res.shape[0] < 400 and res.shape[1] < 500


def test_max_size_limits_processing_but_keeps_output_size(photo):
    p = replace(BASE, max_size=64)
    res = K.process_rgb(photo, p)
    assert res.shape[:2] == photo.shape[:2]


def test_save_load_roundtrip(tmp_path):
    img = np.full((64, 64, 3), 255, np.uint8)
    K.cv2.circle(img, (32, 32), 20, (0, 0, 0), 3)
    res = K.process_rgb(img, replace(BASE, mode="lineart", color="binary"))
    path = str(tmp_path / "out.png")
    K.save_image(res, path)
    assert os.path.exists(path)
    assert K.load_rgb(path).shape[:2] == (64, 64)


def test_presets_are_wired():
    assert "扫描文档" in K.PRESETS
    assert K.PRESETS["扫描文档"]["adaptive"] is True
    assert K.PRESETS["印章剪影"]["mode"] == "binary"
