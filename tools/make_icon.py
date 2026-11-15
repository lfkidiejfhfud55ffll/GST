"""生成应用图标 assets/gst.ico 与 assets/gst.png（只用 Pillow，可重复执行）。"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from gstree.theme import LIGHT  # noqa: E402

ACCENT = LIGHT.accent
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> Image.Image:
    N = size * 8
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, N - 1, N - 1], radius=int(N * 0.24), fill=ACCENT)

    if size <= 24:
        # 小尺寸用简化的白色文件夹剪影，保证可辨识
        w = int(N * 0.52)
        x0 = (N - w) / 2
        y0 = int(N * 0.34)
        d.rounded_rectangle([x0, y0 + int(N * 0.06), x0 + w, y0 + int(N * 0.42)], radius=int(N * 0.05), fill="#FFFFFF")
        d.rounded_rectangle(
            [x0 + int(w * 0.06), y0, x0 + int(w * 0.44), y0 + int(N * 0.14)], radius=int(N * 0.04), fill="#FFFFFF"
        )
    else:
        text = "GST"
        font = None
        for name in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"):
            try:
                font = ImageFont.truetype(name, int(N * 0.34))
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()
        left, top, right, bottom = d.textbbox((0, 0), text, font=font)
        d.text(
            ((N - (right - left)) / 2 - left, (N - (bottom - top)) / 2 - top - N * 0.02),
            text,
            font=font,
            fill="#FFFFFF",
        )
    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    out_dir = os.path.join(ROOT, "assets")
    os.makedirs(out_dir, exist_ok=True)
    frames = [draw(s) for s in SIZES]
    ico = os.path.join(out_dir, "gst.ico")
    frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in SIZES])
    frames[-1].save(os.path.join(out_dir, "gst.png"), format="PNG")
    print("written", ico)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
