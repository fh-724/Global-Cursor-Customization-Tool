"""生成 MouseFX 图标（assets/icon.ico + assets/icon.png）。

用法：
    python tools/make_icon.py

极简风格：深色圆角方块 + 纯白鼠标指针，无渐变、无光晕、无星芒。
纯扁平图形在任何尺寸下都能等比缩放，不需要单独画小尺寸版本。

想换成青色底，只改 BACKGROUND 一行即可（见文件底部 COLOR SCHEMES）。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

S = 4096  # 超采样画布（扁平图形放大再缩小，边缘更干净）
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

# 基础轮廓（Windows 指针原味比例）。
# 注意：x、y 必须用同一个基准归一化（这里都是 /18），否则箭头会被横向拉宽
ARROW_POINTS = [
    (0.000, 0.000), (0.000, 0.778), (0.194, 0.583), (0.306, 0.833),
    (0.417, 0.778), (0.306, 0.528), (0.528, 0.528),
]
ARROW_BOX = (
    max(p[0] for p in ARROW_POINTS),
    max(p[1] for p in ARROW_POINTS),
)
ARROW_RATIO = 0.62  # 箭头高度占画布的比例
RADIUS_RATIO = 0.23  # 圆角半径占画布的比例

BACKGROUND = (15, 18, 24)
ARROW_COLOR = (255, 255, 255)


def cursor_polygon(height: float, origin: tuple[float, float]) -> list[tuple[float, float]]:
    box_w, box_h = ARROW_BOX
    width = height * (box_w / box_h)
    ox, oy = origin
    return [(ox + x * width, oy + y * height) for x, y in ARROW_POINTS]


def build(background: tuple[int, int, int] | None = BACKGROUND,
          arrow: tuple[int, int, int] = ARROW_COLOR) -> Image.Image:
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    if background is not None:
        d.rounded_rectangle(
            [0, 0, S - 1, S - 1], radius=int(S * RADIUS_RATIO), fill=background + (255,)
        )

    h = S * ARROW_RATIO
    w = h * (0.50 / 0.83)
    # 箭头形状本身偏左上，往右下轻推一点点才是视觉居中
    ox = (S - w) / 2 + S * 0.025
    oy = (S - h) / 2 + S * 0.012
    d.polygon(cursor_polygon(h, (ox, oy)), fill=arrow + (255,))
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


# COLOR SCHEMES（改这里换配色）
#   A 深色底 + 白箭头：  BACKGROUND = (15, 18, 24);    ARROW_COLOR = (255, 255, 255)
#   B 青色底 + 白箭头：  BACKGROUND = (34, 211, 238);  ARROW_COLOR = (255, 255, 255)
#   C 深色底 + 青箭头：  BACKGROUND = (11, 14, 20);    ARROW_COLOR = (34, 211, 238)
#   纯透明背景：         BACKGROUND = None

if __name__ == "__main__":
    main()
