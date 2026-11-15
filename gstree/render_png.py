"""把目录结构树渲染成 PNG 图片（与界面共用几何、配色与图标）。"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import replace

from PIL import Image, ImageDraw, ImageFont

from . import icons
from .layout import flatten
from .model import Node, ScanStats, human_size
from .theme import LIGHT, Metrics, Palette, scaled_metrics

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_FALLBACK = "C:/Windows/Fonts/segoeui.ttf"

MAX_SIDE = 24000  # 单边像素上限，超过则自动降低倍率
MAX_LABEL_W = 1500  # 单行文字最大宽度（base 像素，会乘以倍率）


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in ((FONT_BOLD if bold else FONT_PATH), FONT_PATH, FONT_FALLBACK):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> str:
    if font.getlength(text) <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.getlength(text[:mid] + "…") <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"


def _display(node: Node) -> str:
    return node.label + (" …" if node.skipped and node.is_dir else "")


def render_png(
    root: Node,
    stats: ScanStats | None = None,
    out_path: str | None = None,
    palette: Palette = LIGHT,
    scale: float = 2.0,
    source: str | None = None,
    when: _dt.datetime | None = None,
    include_header: bool = True,
) -> tuple[Image.Image, tuple[int, int]]:
    """渲染并可选保存 PNG。返回 (图像, (宽, 高))。"""
    scale = max(1.0, float(scale))
    metrics = scaled_metrics(scale)
    rows = flatten(root, metrics)

    # 超高时自动降倍率，避免生成一张开不动的图
    est_h = len(rows) * metrics.row_h + 260
    if est_h > MAX_SIDE:
        scale = max(1.0, scale * (MAX_SIDE / est_h) * 0.95)
        metrics = scaled_metrics(scale)
        rows = flatten(root, metrics)

    label_font = _load_font(max(10, int(round(12 * scale))))
    title_font = _load_font(max(13, int(round(17 * scale))), bold=True)
    sub_font = _load_font(max(9, int(round(10.5 * scale))))
    chip_font = _load_font(max(9, int(round(10 * scale))), bold=True)

    pad = int(round(26 * scale))
    max_label_px = MAX_LABEL_W * scale

    # ---- 先量文字，再定画布宽度 -------------------------------------
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    widths: list[float] = []
    labels: list[str] = []
    for row in rows:
        text = _fit_text(probe, _display(row.node), label_font, max_label_px)
        labels.append(text)
        widths.append(metrics.x_text(row.depth) + label_font.getlength(text))

    content_w = int(max(widths) + pad) if widths else int(480 * scale)
    src_line = source or root.path
    title_w = int(title_font.getlength("目录结构树")) + int(chip_font.getlength("GST")) + int(180 * scale)
    header_w = max(title_w, int(sub_font.getlength(src_line)) + pad * 2)
    width = max(int(520 * scale), content_w, header_w + pad)

    # ---- 头部 / 底部高度 --------------------------------------------
    head_h = 0
    if include_header:
        head_h = int(round(96 * scale))
    foot_h = int(round(54 * scale))
    height = head_h + int(round(18 * scale)) + len(rows) * metrics.row_h + metrics.pad_v * 2 + foot_h
    height = min(height, MAX_SIDE)
    width = min(width, MAX_SIDE)

    img = Image.new("RGBA", (width, height), palette.canvas_bg)
    draw = ImageDraw.Draw(img)

    y = 0
    if include_header:
        # 标题 + 品牌胶囊
        draw.text((pad, int(22 * scale)), "目录结构树", font=title_font, fill=palette.text, anchor="la")
        title_w_px = title_font.getlength("目录结构树")
        chip_h = int(24 * scale)
        chip_x = pad + title_w_px + int(12 * scale)
        chip_w = int(chip_font.getlength("GST") + 22 * scale)
        draw.rounded_rectangle(
            [chip_x, int(22 * scale) + int(2 * scale), chip_x + chip_w, int(22 * scale) + chip_h],
            radius=chip_h // 2,
            fill=palette.chip_bg,
            outline=palette.border_soft,
        )
        draw.text(
            (chip_x + chip_w / 2, int(22 * scale) + chip_h / 2 + int(1 * scale)),
            "GST",
            font=chip_font,
            fill=palette.accent,
            anchor="mm",
        )
        # 根路径
        path_text = _fit_text(probe, src_line, sub_font, width - pad * 2)
        draw.text((pad, int(54 * scale)), path_text, font=sub_font, fill=palette.text_dim, anchor="la")
        # 统计
        if stats is not None:
            stamp = (when or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
            info = f"{stats.dirs} 个文件夹 · {stats.files} 个文件 · {human_size(stats.total_bytes)} · {stamp}"
            draw.text((pad, int(72 * scale)), info, font=sub_font, fill=palette.text_faint, anchor="la")
        draw.line([(pad, head_h - 1), (width - pad, head_h - 1)], fill=palette.border_soft, width=max(1, int(scale)))
        y = head_h + int(10 * scale)

    base_y = y + metrics.pad_v
    guide_w = max(1, int(round(scale)))
    icon_px = metrics.icon
    icon_cache: dict[str, Image.Image] = {}

    for row, label in zip(rows, labels):
        node = row.node
        top = base_y + row.y
        cy = top + metrics.row_h // 2
        depth = row.depth

        # 祖先竖线
        if depth > 0:
            for level, cont in enumerate(row.guides):
                if cont:
                    gx = metrics.x_spine(level + 1)
                    draw.line([(gx, top), (gx, top + metrics.row_h)], fill=palette.guide, width=guide_w)
            sx = metrics.x_spine(depth)
            draw.line([(sx, top), (sx, cy)], fill=palette.guide, width=guide_w)
            if not row.last:
                draw.line([(sx, cy), (sx, top + metrics.row_h)], fill=palette.guide, width=guide_w)
            draw.line([(sx, cy), (metrics.x_icon(depth) - int(2 * scale), cy)], fill=palette.guide, width=guide_w)

        # 图标
        cat = icons.category_for(node)
        icon = icon_cache.get(cat)
        if icon is None:
            icon = icons.get_icon(cat, icon_px)
            icon_cache[cat] = icon
        ix = metrics.x_icon(depth)
        img.alpha_composite(icon, (ix, cy - icon_px // 2))

        color = palette.text
        if node.is_dir:
            color = palette.text
        if node.error:
            color = palette.warn
        draw.text(
            (metrics.x_text(depth), cy),
            label,
            font=label_font,
            fill=color,
            anchor="lm",
        )

    # ---- 底部 -------------------------------------------------------
    foot_y = height - foot_h
    draw.line([(pad, foot_y), (width - pad, foot_y)], fill=palette.border_soft, width=max(1, int(scale)))
    left = "以 .fd 结尾的节点为文件夹（含空文件夹）"
    draw.text((pad, foot_y + int(16 * scale)), left, font=sub_font, fill=palette.text_faint, anchor="la")
    right = "Generated by GST"
    draw.text((width - pad, foot_y + int(16 * scale)), right, font=sub_font, fill=palette.text_faint, anchor="ra")

    if out_path:
        folder = os.path.dirname(os.path.abspath(out_path))
        if folder and not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        img.convert("RGB").save(out_path, "PNG", optimize=True)

    return img, (width, height)
