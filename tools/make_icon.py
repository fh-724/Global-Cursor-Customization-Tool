"""生成 MouseFX 图标（assets/icon.ico + assets/icon.png）。

用法：
    python tools/make_icon.py

风格：粉→紫→靛蓝对角渐变圆角方块 + 纯白圆角鼠标指针。
箭头刻意做厚（头宽 72 / 柄宽 18，按 100×140 网格），转角用模糊+阈值磨圆，
扁平强对比，16px 列表视图下也认得出。

换配色只需改 BACKGROUND_STOPS。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 2048  # 超采样画布
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

# 粉 → 紫 → 靛蓝（对角）
BACKGROUND_STOPS = [
    (0.0, (244, 114, 182)),
    (0.5, (168, 85, 247)),
    (1.0, (79, 70, 229)),
]
ARROW_COLOR = (255, 255, 255)

RADIUS_RATIO = 0.235   # 方块圆角占画布比例
ARROW_HEIGHT_RATIO = 0.56
ARROW_CORNER = 0.014   # 箭头转角圆润程度

# 加粗后的指针轮廓（100 × 140 网格）
ARROW = [
    (0, 0), (0, 86), (24, 62), (38, 96), (56, 88), (40, 56), (72, 56),
]


def linear_gradient(size: int, stops: list[tuple[float, tuple[int, int, int]]],
                    start: tuple[float, float] = (0.1, 0.0),
                    end: tuple[float, float] = (0.9, 1.0)) -> Image.Image:
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    vx, vy = end[0] - start[0], end[1] - start[1]
    t = ((xs / size - start[0]) * vx + (ys / size - start[1]) * vy) / (vx * vx + vy * vy)
    t = np.clip(t, 0.0, 1.0)

    channels = np.zeros((size, size, 3), np.float32)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        seg = (t >= t0) & (t <= t1)
        local = np.clip((t - t0) / max(t1 - t0, 1e-6), 0.0, 1.0)
        for ch in range(3):
            channels[..., ch] = np.where(
                seg, c0[ch] + (c1[ch] - c0[ch]) * local, channels[..., ch]
            )
    return Image.fromarray(channels.astype(np.uint8), "RGB")


def rounded_polygon_mask(points: list[tuple[float, float]], size: int,
                         radius: float) -> Image.Image:
    """先画实心多边形，再用「模糊 + 阈值 + 膨胀」把尖角磨圆并补回尺寸。"""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    blur = int(max(3, radius))
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    mask = mask.point(lambda v: 255 if v >= 150 else 0)
    grow = int(blur * 0.75) * 2 + 1
    return mask.filter(ImageFilter.MaxFilter(grow))


def arrow_mask(size: int) -> Image.Image:
    xs = [p[0] for p in ARROW]
    ys = [p[1] for p in ARROW]
    box_w, box_h = max(xs), max(ys)

    h = size * ARROW_HEIGHT_RATIO
    w = h * (box_w / box_h)
    # 箭头视觉重心偏左上，往右下轻推一点才是居中
    ox = (size - w) / 2 + size * 0.02
    oy = (size - h) / 2 + size * 0.01
    pts = [(ox + x / box_w * w, oy + y / box_h * h) for x, y in ARROW]
    return rounded_polygon_mask(pts, size, radius=size * ARROW_CORNER)


def build() -> Image.Image:
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    bg = linear_gradient(S, BACKGROUND_STOPS).convert("RGBA")
    card = Image.new("L", (S, S), 0)
    ImageDraw.Draw(card).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=int(S * RADIUS_RATIO), fill=255
    )
    canvas.paste(bg, (0, 0), card)

    canvas.paste(Image.new("RGBA", (S, S), ARROW_COLOR + (255,)), (0, 0), arrow_mask(S))
    return canvas


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    art = build()

    art.resize((512, 512), Image.LANCZOS).save(OUT_DIR / "icon.png")
    art.resize((1024, 1024), Image.LANCZOS).save(OUT_DIR / "icon-1024.png")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    frames = [art.resize(size, Image.LANCZOS) for size in sizes]
    frames[0].save(
        OUT_DIR / "icon.ico",
        format="ICO",
        sizes=sizes,
        append_images=frames[1:],
    )
    print(f"已生成: {OUT_DIR / 'icon.ico'}")


if __name__ == "__main__":
    main()
