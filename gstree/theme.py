"""配色、字体与几何度量（Tk 视图与 PNG 导出共用同一套间距规则）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    key: str
    name: str
    bg: str
    panel: str
    panel_alt: str
    border: str
    border_soft: str
    text: str
    text_dim: str
    text_faint: str
    accent: str
    accent_hover: str
    accent_text: str
    row_hover: str
    row_selected: str
    guide: str
    hit_bg: str
    warn: str
    ok: str
    canvas_bg: str
    chip_bg: str


LIGHT = Palette(
    key="light",
    name="浅色",
    bg="#F1F4F9",
    panel="#FFFFFF",
    panel_alt="#F7FAFD",
    border="#D9E1EC",
    border_soft="#E8EEF6",
    text="#16202E",
    text_dim="#61708A",
    text_faint="#94A3B0",
    accent="#2563EB",
    accent_hover="#1D4ED8",
    accent_text="#FFFFFF",
    row_hover="#EEF5FF",
    row_selected="#DBEAFE",
    guide="#C8D5E4",
    hit_bg="#FEF0C7",
    warn="#C2410C",
    ok="#15803D",
    canvas_bg="#FFFFFF",
    chip_bg="#EDF2F9",
)

DARK = Palette(
    key="dark",
    name="深色",
    bg="#0E1524",
    panel="#17202F",
    panel_alt="#1C2637",
    border="#2A3648",
    border_soft="#222C3C",
    text="#E7EEF8",
    text_dim="#9BAAC1",
    text_faint="#6B7C96",
    accent="#3B82F6",
    accent_hover="#60A5FA",
    accent_text="#FFFFFF",
    row_hover="#1E2B40",
    row_selected="#22395C",
    guide="#39465B",
    hit_bg="#4A3510",
    warn="#FB923C",
    ok="#4ADE80",
    canvas_bg="#111A28",
    chip_bg="#1E283A",
)

PALETTES = {"light": LIGHT, "dark": DARK}


@dataclass(frozen=True)
class Metrics:
    """树绘制度量，单位：像素。"""

    row_h: int = 26
    indent: int = 30
    icon: int = 17
    gap: int = 8
    pad_l: int = 16
    pad_v: int = 10

    def x_icon(self, depth: int) -> int:
        return self.pad_l + depth * self.indent

    def x_text(self, depth: int) -> int:
        return self.x_icon(depth) + self.icon + self.gap

    def x_spine(self, depth: int) -> int:
        """depth>=1 时，父节点竖直连线的 x 坐标（父图标中心）。"""
        return self.x_icon(max(0, depth - 1)) + self.icon // 2


def scaled_metrics(scale: float, base_row: int = 26) -> Metrics:
    """按 DPI/导出倍率缩放度量。"""
    return Metrics(
        row_h=max(16, int(round(base_row * scale))),
        indent=int(round(30 * scale)),
        icon=max(12, int(round(17 * scale))),
        gap=int(round(8 * scale)),
        pad_l=int(round(16 * scale)),
        pad_v=int(round(10 * scale)),
    )


#: 优先使用的界面字体（Windows 上都有）
FONT_CANDIDATES = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "SimHei", "Arial")


def pick_font_family(available: set[str] | None = None) -> str:
    if not available:
        return FONT_CANDIDATES[0]
    lowered = {name.lower(): name for name in available}
    for candidate in FONT_CANDIDATES:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return FONT_CANDIDATES[-1]
