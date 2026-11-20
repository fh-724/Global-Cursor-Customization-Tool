"""生成 MouseFX 图标（assets/icon.ico + assets/icon.png）。

用法：
    python tools/make_icon.py

设计：深色圆角底 + 青→紫→粉渐变光标箭头 + 光晕 + 星芒，
16px 下仍能读成"鼠标指针"。
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 1024  # 超采样画布尺寸
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

CYAN = (34, 211, 238)
VIOLET = (168, 85, 247)
PINK = (244, 114, 182)


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def linear_gradient(size: int, stops: list[tuple[float, tuple[int, int, int]]],
                    start: tuple[float, float] = (0.15, 0.05),
                    end: tuple[float, float] = (0.9, 0.95)) -> Image.Image:
    """沿对角线生成多段线性渐变。"""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    vx, vy = end[0] - start[0], end[1] - start[1]
    t = ((xs / size - start[0]) * vx + (ys / size - start[1]) * vy) / (vx * vx + vy * vy)
    t = np.clip(t, 0.0, 1.0)

    channels = np.zeros((size, size, 3), dtype=np.float32)
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


def radial_glow(size: int, center: tuple[float, float], radius: float,
                color: tuple[int, int, int], peak_alpha: int) -> Image.Image:
    """椭圆形软光斑。"""
    layer = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(layer)
    cx, cy = center[0] * size, center[1] * size
    steps = 26
    for i in range(steps, 0, -1):
        k = i / steps
        alpha = int(peak_alpha * (1.0 - k) ** 2.2)
        r = radius * size * k
        d.ellipse([cx - r, cy - r * 0.9, cx + r, cy + r * 0.9], fill=alpha)
    layer = layer.filter(ImageFilter.GaussianBlur(size * 0.02))
    glow = Image.new("RGBA", (size, size), color + (0,))
    glow.putalpha(layer)
    return glow


def cursor_polygon(width: float, height: float, origin: tuple[float, float]) -> list[tuple[float, float]]:
    """标准箭头指针轮廓，按目标尺寸缩放。"""
    base = [(0.00, 0.00), (0.00, 0.70), (0.17, 0.55), (0.29, 0.83),
            (0.42, 0.77), (0.30, 0.50), (0.50, 0.50)]
    ox, oy = origin
    return [(ox + x * width, oy + y * height) for x, y in base]


def sparkle(size: int, center: tuple[float, float], radius: float,
            color: tuple[int, int, int], alpha: int = 235) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    pts = []
    for i in range(8):
        ang = -math.pi / 2 + i * math.pi / 4
        r = radius if i % 2 == 0 else radius * 0.26
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    d.polygon(pts, fill=color + (alpha,))
    return layer


def build() -> Image.Image:
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # 1) 深色圆角底 + 对角青→紫渐变
    bg = linear_gradient(
        S,
        [(0.0, (10, 14, 26)), (0.45, (18, 20, 44)), (1.0, (28, 18, 48))],
    ).convert("RGBA")
    canvas.paste(bg, (0, 0), rounded_mask(S, 208))

    # 2) 两团光晕：左上青、右下粉
    canvas.alpha_composite(radial_glow(S, (0.24, 0.2), 0.42, CYAN, 120))
    canvas.alpha_composite(radial_glow(S, (0.82, 0.86), 0.38, PINK, 105))

    # 3) 指针箭头（带外发光）
    # 基础轮廓的包围盒是 0.50 × 0.83，保持这个长宽比才像真指针，不能被拉伸
    poly_h = 760.0
    poly_w = poly_h * (0.50 / 0.83)
    ox, oy = (S - poly_w) / 2 + 14, (S - poly_h) / 2 + 4
    poly = cursor_polygon(poly_w, poly_h, (ox, oy))

    arrow_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(arrow_mask).polygon(poly, fill=255)

    halo = Image.new("RGBA", (S, S), CYAN + (0,))
    halo.putalpha(arrow_mask.filter(ImageFilter.GaussianBlur(S * 0.035)))
    halo.putalpha(halo.getchannel("A").point(lambda v: int(v * 0.85)))
    canvas.alpha_composite(halo)

    # 4) 描边：用掩膜膨胀生成等宽描边，比画折线干净（转角圆滑、无缺口）
    stroke_white = arrow_mask.filter(ImageFilter.MaxFilter(19))
    stroke_navy = arrow_mask.filter(ImageFilter.MaxFilter(35))
    canvas.paste(Image.new("RGBA", (S, S), (9, 12, 24, 240)), (0, 0), stroke_navy)
    canvas.paste(Image.new("RGBA", (S, S), (255, 255, 255, 243)), (0, 0), stroke_white)

    # 5) 箭头本体：青 → 紫 → 粉
    fill = linear_gradient(S, [(0.0, CYAN), (0.5, VIOLET), (1.0, PINK)],
                           start=(0.3, 0.1), end=(0.72, 0.95)).convert("RGBA")
    canvas.paste(fill, (0, 0), arrow_mask)

    # 6) 星芒点缀
    canvas.alpha_composite(sparkle(S, (785, 250), 74, CYAN))
    canvas.alpha_composite(sparkle(S, (250, 760), 58, PINK))
    canvas.alpha_composite(sparkle(S, (840, 690), 34, (255, 255, 255), 200))

    return canvas


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    art = build()

    png = art.resize((512, 512), Image.LANCZOS)
    png.save(OUT_DIR / "icon.png")
    art.resize((1024, 1024), Image.LANCZOS).save(OUT_DIR / "icon-1024.png")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    frames = [art.resize(s, Image.LANCZOS) for s in sizes]
    frames[0].save(
        OUT_DIR / "icon.ico",
        format="ICO",
        sizes=sizes,
        append_images=frames[1:],
    )
    print(f"已生成: {OUT_DIR / 'icon.ico'}")
    print(f"已生成: {OUT_DIR / 'icon.png'}")


if __name__ == "__main__":
    main()
