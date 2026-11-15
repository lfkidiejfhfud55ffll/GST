"""GST · 目录结构树生成器（Tkinter GUI 入口）。

用法：  ..\\venv312\\Scripts\\python.exe app.py
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from gstree import config as appconfig
from gstree import export_text
from gstree.model import ScanOptions, ScanResult, human_size, scan_path
from gstree.render_png import render_png
from gstree.theme import PALETTES, Palette, pick_font_family
from gstree.treeview import TreeView

try:  # 拖拽支持（已装上 tkinterdnd2 时启用，缺失则自动降级）
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_BASE = TkinterDnD.Tk
except Exception:  # pragma: no cover - 环境相关
    DND_FILES = None
    _DND_BASE = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
APP_TITLE = "GST · 目录结构树生成器"
SORT_LABELS = {"名称": "name", "类型": "type", "大小": "size", "修改时间": "mtime"}
SORT_KEYS = {v: k for k, v in SORT_LABELS.items()}
PNG_SCALES = {"1x": 1.0, "2x": 2.0, "3x": 3.0, "4x": 4.0}


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class _AppCore:
    """全部界面与逻辑；真正的 Tk 基类在文件末尾按是否支持拖拽决定。"""

    def __init__(self) -> None:
        super().__init__()
        self.cfg = appconfig.load()
        self.pal: Palette = PALETTES.get(str(self.cfg.get("theme")), PALETTES["light"])
        self.family = pick_font_family(set(tkfont.families(self)))
        self.f_title = (self.family, 13, "bold")
        self.f_body = (self.family, 10)
        self.f_small = (self.family, 9)
        self.f_tiny = (self.family, 8)
        self.f_brand = (self.family, 11, "bold")

        self.title(APP_TITLE)
        self.minsize(1120, 640)
        geometry = self.cfg.get("geometry") or ""
        if geometry:
            try:
                self.geometry(geometry)
            except tk.TclError:
                self.geometry("1320x880")
        else:
            self.geometry("1320x880")
        self._center_if_needed()

        self.result: ScanResult | None = None
        self._scanning = False
        self._token = 0
        self._queue: queue.Queue | None = None
        self._last_export_dir = str(self.cfg.get("last_export_dir") or "")
        self._painted: list[tuple[tk.Widget, str]] = []
        self._labels: list[tuple[tk.Label, str, str]] = []
        self._toast_after: str | None = None
        self._search_after: str | None = None

        self.style = ttk.Style(self)
        self._build_vars()
        self._build_ui()
        self._configure_styles()
        self._apply_palette()
        self._bind_keys()

        self._apply_window_chrome()
        self.after(140, self._apply_window_chrome)

        self._setup_dnd()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.cfg.get("path"):
            self.var_path.set(str(self.cfg["path"]))
        self.after(180, self._initial_scan)

    # ------------------------------------------------------------ 变量
    def _build_vars(self) -> None:
        cfg = self.cfg
        self.var_path = tk.StringVar(value="")
        self.var_depth = tk.IntVar(value=int(cfg.get("max_depth", 0) or 0))
        self.var_nodes = tk.IntVar(value=int(cfg.get("max_nodes", 6000) or 6000))
        self.var_sort = tk.StringVar(value=SORT_KEYS.get(str(cfg.get("sort_mode")), "名称"))
        self.var_hidden = tk.BooleanVar(value=bool(cfg.get("show_hidden", False)))
        self.var_ignore = tk.BooleanVar(value=bool(cfg.get("use_ignore", True)))
        self.var_dirs_first = tk.BooleanVar(value=bool(cfg.get("dirs_first", True)))
        self.var_header = tk.BooleanVar(value=bool(cfg.get("include_header", True)))
        _scale = float(cfg.get("png_scale", 2.0) or 2.0)
        _scale_label = next((k for k, v in PNG_SCALES.items() if abs(v - _scale) < 0.01), "2x")
        self.var_scale = tk.StringVar(value=_scale_label)
        self.var_search = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="就绪 · 输入路径或选择文件夹后生成结构树")
        self.var_stats = tk.StringVar(value="")
        self.var_hits = tk.StringVar(value="")

    # ------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        pal = self.pal
        self.configure(bg=pal.bg)

        # ---------------- 顶部标题栏 ----------------
        self.header = tk.Frame(self, bg=pal.panel)
        self.header.pack(fill="x", side="top")
        self._paint(self.header, "panel")

        brand = tk.Frame(self.header, bg=pal.accent, width=36, height=36)
        brand.pack(side="left", padx=(18, 10), pady=12)
        brand.pack_propagate(False)
        self._paint(brand, "accent")
        brand_label = tk.Label(brand, text="GST", bg=pal.accent, fg=pal.accent_text, font=self.f_brand)
        brand_label.pack(expand=True)
        self._label(brand_label, "accent_text", "accent")

        titles = tk.Frame(self.header, bg=pal.panel)
        titles.pack(side="left", pady=10)
        self._paint(titles, "panel")
        t1 = tk.Label(titles, text="目录结构树", bg=pal.panel, fg=pal.text, font=self.f_title)
        t1.pack(anchor="w")
        self._label(t1, "text", "panel")
        t2 = tk.Label(
            titles,
            text="把一个文件夹或文件变成可读的结构树 · 支持拖拽 · 导出 TXT / PNG",
            bg=pal.panel,
            fg=pal.text_dim,
            font=self.f_small,
        )
        t2.pack(anchor="w")
        self._label(t2, "dim", "panel")

        self.btn_theme = ttk.Button(self.header, text=self._theme_label(), style="Ghost.TButton", command=self.toggle_theme)
        self.btn_theme.pack(side="right", padx=(8, 18), pady=12)

        self.header_line = tk.Frame(self, bg=pal.border_soft, height=1)
        self.header_line.pack(fill="x", side="top")
        self._paint(self.header_line, "border_soft")

        # ---------------- 主体 ----------------
        self.body = tk.Frame(self, bg=pal.bg)
        self.body.pack(fill="both", expand=True, padx=18, pady=(14, 8))
        self._paint(self.body, "bg")

        self._build_input_card()
        self._build_tree_card()

        # ---------------- 状态栏 ----------------
        self.status_bar = tk.Frame(self, bg=pal.panel)
        self.status_bar.pack(fill="x", side="bottom")
        self._paint(self.status_bar, "panel")
        status_line = tk.Frame(self.status_bar, bg=pal.border_soft, height=1)
        status_line.pack(fill="x")
        self._paint(status_line, "border_soft")
        inner = tk.Frame(self.status_bar, bg=pal.panel)
        inner.pack(fill="x", padx=18, pady=7)
        self._paint(inner, "panel")
        self.lbl_status = tk.Label(inner, textvariable=self.var_status, bg=pal.panel, fg=pal.text_dim, font=self.f_small, anchor="w")
        self.lbl_status.pack(side="left")
        self._label(self.lbl_status, "dim", "panel")
        self.lbl_stats = tk.Label(inner, textvariable=self.var_stats, bg=pal.panel, fg=pal.text_faint, font=self.f_small, anchor="e")
        self.lbl_stats.pack(side="right")
        self._label(self.lbl_stats, "faint", "panel")

        self.progress = ttk.Progressbar(inner, mode="indeterminate", length=110, style="TProgressbar")
        self._progress_shown = False

    def _build_input_card(self) -> None:
        pal = self.pal
        outer, card = self._card(self.body, padding=14)
        outer.pack(fill="x")
        self.input_card = outer

        # ---- 第一行：路径输入 + 三个动作按钮 ----
        row1 = tk.Frame(card, bg=pal.panel)
        row1.pack(fill="x")
        self._paint(row1, "panel")

        lbl = tk.Label(row1, text="路径", bg=pal.panel, fg=pal.text_dim, font=self.f_body)
        lbl.pack(side="left", padx=(0, 10))
        self._label(lbl, "dim", "panel")

        # 右侧按钮先 pack，剩下的宽度才会全给输入框（pack 按调用顺序分配空间）
        self.btn_generate = ttk.Button(row1, text="生成结构树", style="Accent.TButton", command=self.generate)
        self.btn_generate.pack(side="right")
        self.btn_file = ttk.Button(row1, text="选择文件", style="TButton", command=self.pick_file)
        self.btn_file.pack(side="right", padx=(0, 6))
        self.btn_dir = ttk.Button(row1, text="选择文件夹", style="TButton", command=self.pick_folder)
        self.btn_dir.pack(side="right", padx=(0, 8))

        self.entry_path = ttk.Entry(row1, textvariable=self.var_path, style="Path.TEntry", font=self.f_body)
        self.entry_path.pack(side="left", fill="x", expand=True, ipady=2)
        self.entry_path.bind("<Return>", lambda e: self.generate())

        # ---- 第二行：选项（左） + 导出（右） ----
        row2 = tk.Frame(card, bg=pal.panel)
        row2.pack(fill="x", pady=(12, 0))
        self._paint(row2, "panel")

        # 右侧导出组：设置项紧贴导出按钮，语义更直观
        export_box = tk.Frame(row2, bg=pal.panel)
        export_box.pack(side="right")
        self._paint(export_box, "panel")

        # pack 顺序 = 从右往左，所以视觉上是：含标题 · 倍率 · 导出 TXT · 导出 PNG
        self.btn_png = ttk.Button(export_box, text="导出 PNG", style="TButton", command=self.export_png)
        self.btn_png.pack(side="right")
        self.btn_txt = ttk.Button(export_box, text="导出 TXT", style="TButton", command=self.export_txt)
        self.btn_txt.pack(side="right", padx=(0, 6))

        self.combo_scale = ttk.Combobox(
            export_box, values=list(PNG_SCALES), textvariable=self.var_scale,
            state="readonly", width=4, style="TCombobox", font=self.f_small,
        )
        self.combo_scale.pack(side="right", padx=(0, 8))
        scale_label = tk.Label(export_box, text="倍率", bg=pal.panel, fg=pal.text_dim, font=self.f_small)
        scale_label.pack(side="right", padx=(0, 5))
        self._label(scale_label, "dim", "panel")

        self.chk_header = ttk.Checkbutton(export_box, text="含标题", variable=self.var_header, style="TCheckbutton")
        self.chk_header.pack(side="right", padx=(0, 10))

        def opt_label(text: str) -> tk.Label:
            lab = tk.Label(row2, text=text, bg=pal.panel, fg=pal.text_dim, font=self.f_small)
            self._label(lab, "dim", "panel")
            return lab

        lab = opt_label("深度")
        lab.pack(side="left", padx=(0, 5))
        self.spin_depth = ttk.Spinbox(
            row2, from_=0, to=99, width=4, textvariable=self.var_depth, style="TSpinbox", font=self.f_small
        )
        self.spin_depth.pack(side="left", padx=(0, 10))

        lab = opt_label("节点上限")
        lab.pack(side="left", padx=(0, 5))
        self.spin_nodes = ttk.Spinbox(
            row2, from_=100, to=200000, increment=500, width=6,
            textvariable=self.var_nodes, style="TSpinbox", font=self.f_small,
        )
        self.spin_nodes.pack(side="left", padx=(0, 10))

        lab = opt_label("排序")
        lab.pack(side="left", padx=(0, 5))
        self.combo_sort = ttk.Combobox(
            row2, values=list(SORT_LABELS), textvariable=self.var_sort,
            state="readonly", width=8, style="TCombobox", font=self.f_small,
        )
        self.combo_sort.pack(side="left", padx=(0, 12))
        self.combo_sort.bind("<<ComboboxSelected>>", lambda e: self.generate())

        self.chk_dirs = ttk.Checkbutton(row2, text="文件夹优先", variable=self.var_dirs_first, style="TCheckbutton")
        self.chk_dirs.pack(side="left", padx=(0, 10))
        self.chk_ignore = ttk.Checkbutton(row2, text="跳过噪音", variable=self.var_ignore, style="TCheckbutton")
        self.chk_ignore.pack(side="left", padx=(0, 10))
        self.chk_hidden = ttk.Checkbutton(row2, text="包含隐藏项", variable=self.var_hidden, style="TCheckbutton")
        self.chk_hidden.pack(side="left")

    def _build_tree_card(self) -> None:
        pal = self.pal
        outer, card = self._card(self.body, padding=0)
        outer.pack(fill="both", expand=True, pady=(10, 0))

        toolbar = tk.Frame(card, bg=pal.panel)
        toolbar.pack(fill="x", padx=12, pady=(10, 8))
        self._paint(toolbar, "panel")

        lab = tk.Label(toolbar, text="搜索", bg=pal.panel, fg=pal.text_dim, font=self.f_small)
        lab.pack(side="left", padx=(2, 6))
        self._label(lab, "dim", "panel")

        self.entry_search = ttk.Entry(toolbar, textvariable=self.var_search, width=26, style="Search.TEntry", font=self.f_small)
        self.entry_search.pack(side="left", ipady=2)
        self.entry_search.bind("<KeyRelease>", self._on_search_key)
        self.entry_search.bind("<Return>", lambda e: self._run_search(step=False))
        self.entry_search.bind("<Escape>", lambda e: self._clear_search())

        self.lbl_hits = tk.Label(toolbar, textvariable=self.var_hits, bg=pal.panel, fg=pal.text_faint, font=self.f_small)
        self.lbl_hits.pack(side="left", padx=(8, 0))
        self._label(self.lbl_hits, "faint", "panel")

        self.btn_fold = ttk.Button(toolbar, text="全部折叠", style="Ghost.TButton", command=self.tree_collapse_all)
        self.btn_fold.pack(side="right")
        self.btn_expand = ttk.Button(toolbar, text="全部展开", style="Ghost.TButton", command=self.tree_expand_all)
        self.btn_expand.pack(side="right", padx=(0, 6))

        self.toolbar_line = tk.Frame(card, bg=pal.border_soft, height=1)
        self.toolbar_line.pack(fill="x")
        self._paint(self.toolbar_line, "border_soft")

        self.tree = TreeView(
            card,
            palette=pal,
            font_family=self.family,
            on_select=self._on_tree_select,
            on_open=self._on_tree_open,
            on_context=self._on_tree_context,
        )
        self.tree.pack(fill="both", expand=True)
        self.tree.set_placeholder("在上方输入路径，或点「选择文件夹 / 选择文件」开始")

    # -------------------------------------------------------- 主题与样式
    def _theme_label(self) -> str:
        return "浅色模式" if self.pal.key == "dark" else "深色模式"

    def _color(self, role: str) -> str:
        pal = self.pal
        return {
            "bg": pal.bg,
            "panel": pal.panel,
            "panel_alt": pal.panel_alt,
            "border": pal.border,
            "border_soft": pal.border_soft,
            "text": pal.text,
            "dim": pal.text_dim,
            "faint": pal.text_faint,
            "accent": pal.accent,
            "accent_text": pal.accent_text,
            "chip": pal.chip_bg,
            "warn": pal.warn,
            "ok": pal.ok,
        }.get(role, pal.text)

    def _paint(self, widget: tk.Widget, role: str) -> None:
        self._painted.append((widget, role))

    def _label(self, widget: tk.Label, fg_role: str, bg_role: str = "panel") -> None:
        self._labels.append((widget, fg_role, bg_role))

    def _card(self, parent: tk.Widget, padding: int = 12) -> tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(parent, bg=self.pal.border, bd=0, highlightthickness=0)
        inner = tk.Frame(outer, bg=self.pal.panel, bd=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self._paint(outer, "border")
        self._paint(inner, "panel")
        if padding <= 0:
            return outer, inner
        content = tk.Frame(inner, bg=self.pal.panel)
        content.pack(fill="both", expand=True, padx=padding, pady=padding)
        self._paint(content, "panel")
        return outer, content

    def _configure_styles(self) -> None:
        pal = self.pal
        fam = self.family
        style = self.style
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".",
            background=pal.panel,
            foreground=pal.text,
            fieldbackground=pal.panel_alt,
            font=(fam, 10),
            focuscolor=pal.panel,
        )
        style.configure("TFrame", background=pal.panel)
        style.configure("Body.TFrame", background=pal.bg)
        style.configure("Card.TFrame", background=pal.panel)
        style.configure("TLabel", background=pal.panel, foreground=pal.text)
        style.configure("Dim.TLabel", background=pal.panel, foreground=pal.text_dim)
        style.configure("Faint.TLabel", background=pal.panel, foreground=pal.text_faint)

        # 按钮
        style.configure(
            "TButton",
            background=pal.panel_alt,
            foreground=pal.text,
            bordercolor=pal.border,
            lightcolor=pal.panel_alt,
            darkcolor=pal.panel_alt,
            relief="flat",
            padding=(14, 7),
            font=(fam, 10),
        )
        style.map(
            "TButton",
            background=[("disabled", pal.panel), ("pressed", pal.chip_bg), ("active", pal.chip_bg)],
            foreground=[("disabled", pal.text_faint)],
            bordercolor=[("focus", pal.accent), ("active", pal.border)],
            lightcolor=[("active", pal.chip_bg)],
            darkcolor=[("active", pal.chip_bg)],
        )
        style.configure(
            "Accent.TButton",
            background=pal.accent,
            foreground=pal.accent_text,
            bordercolor=pal.accent,
            lightcolor=pal.accent,
            darkcolor=pal.accent,
            relief="flat",
            padding=(18, 8),
            font=(fam, 10, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", pal.border), ("pressed", pal.accent_hover), ("active", pal.accent_hover)],
            foreground=[("disabled", pal.panel_alt)],
            bordercolor=[("active", pal.accent_hover), ("disabled", pal.border)],
            lightcolor=[("active", pal.accent_hover)],
            darkcolor=[("active", pal.accent_hover)],
        )
        style.configure(
            "Ghost.TButton",
            background=pal.panel,
            foreground=pal.text_dim,
            bordercolor=pal.panel,
            lightcolor=pal.panel,
            darkcolor=pal.panel,
            relief="flat",
            padding=(10, 5),
            font=(fam, 9),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", pal.chip_bg), ("pressed", pal.border_soft)],
            foreground=[("active", pal.text)],
            lightcolor=[("active", pal.chip_bg)],
            darkcolor=[("active", pal.chip_bg)],
        )

        # 输入框
        for name in ("TEntry", "Path.TEntry", "Search.TEntry"):
            style.configure(
                name,
                fieldbackground=pal.panel_alt,
                background=pal.panel_alt,
                foreground=pal.text,
                insertcolor=pal.text,
                bordercolor=pal.border,
                lightcolor=pal.panel_alt,
                darkcolor=pal.panel_alt,
                padding=(8, 6),
            )
            style.map(
                name,
                bordercolor=[("focus", pal.accent)],
                lightcolor=[("focus", pal.accent)],
                darkcolor=[("focus", pal.accent)],
                fieldbackground=[("disabled", pal.panel)],
            )
        style.configure(
            "TSpinbox",
            fieldbackground=pal.panel_alt,
            background=pal.panel_alt,
            foreground=pal.text,
            arrowcolor=pal.text_dim,
            bordercolor=pal.border,
            lightcolor=pal.panel_alt,
            darkcolor=pal.panel_alt,
            padding=(6, 5),
        )
        style.map("TSpinbox", bordercolor=[("focus", pal.accent)], arrowcolor=[("active", pal.accent)])
        style.configure(
            "TCombobox",
            fieldbackground=pal.panel_alt,
            background=pal.panel_alt,
            foreground=pal.text,
            arrowcolor=pal.text_dim,
            bordercolor=pal.border,
            lightcolor=pal.panel_alt,
            darkcolor=pal.panel_alt,
            padding=(8, 5),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", pal.panel_alt), ("disabled", pal.panel)],
            foreground=[("readonly", pal.text)],
            bordercolor=[("focus", pal.accent)],
            arrowcolor=[("active", pal.accent)],
        )
        style.configure(
            "TCheckbutton",
            background=pal.panel,
            foreground=pal.text,
            indicatorbackground=pal.panel_alt,
            indicatorforeground=pal.accent_text,
            bordercolor=pal.border,
            focuscolor=pal.panel,
            padding=(2, 2),
            font=(fam, 9),
        )
        style.map(
            "TCheckbutton",
            background=[("active", pal.panel)],
            foreground=[("disabled", pal.text_faint)],
            indicatorbackground=[("selected", pal.accent), ("active", pal.chip_bg)],
            indicatorforeground=[("selected", pal.accent_text)],
        )

        # 滚动条
        for orient, name in (("Vertical", "Slim.Vertical.TScrollbar"), ("Horizontal", "Slim.Horizontal.TScrollbar")):
            style.configure(
                name,
                background=pal.chip_bg,
                troughcolor=pal.panel,
                bordercolor=pal.panel,
                arrowcolor=pal.text_faint,
                lightcolor=pal.chip_bg,
                darkcolor=pal.chip_bg,
                relief="flat",
                arrowsize=12,
                width=12 if orient == "Vertical" else 12,
            )
            style.map(name, background=[("active", pal.border), ("pressed", pal.text_faint)])

        style.configure("TProgressbar", background=pal.accent, troughcolor=pal.chip_bg, bordercolor=pal.chip_bg, thickness=4)

        self.option_add("*TCombobox*Listbox.background", pal.panel)
        self.option_add("*TCombobox*Listbox.foreground", pal.text)
        self.option_add("*TCombobox*Listbox.selectBackground", pal.accent)
        self.option_add("*TCombobox*Listbox.selectForeground", pal.accent_text)
        self.option_add("*TCombobox*Listbox.borderWidth", 0)

        self._install_check_indicator()

    # ------------------------------------------------------------ 复选框指示器
    def _ui_scale(self) -> float:
        try:
            scale = float(self.tk.call("tk", "scaling")) / (96.0 / 72.0)
        except Exception:
            scale = 1.0
        return max(1.0, min(3.0, scale))

    def _install_check_indicator(self) -> None:
        """clam 自带的小方框在 100% 缩放下会被挤成一团，这里换成 Pillow 自绘的圆角勾选框。"""
        try:
            from PIL import ImageTk

            from gstree.icons import check_mark
        except Exception:
            return

        pal = self.pal
        size = int(round(14 * self._ui_scale()))
        images = {}
        for key, img in (
            ("normal", check_mark(size, False, pal)),
            ("hover", check_mark(size, False, pal, hover=True)),
            ("on", check_mark(size, True, pal)),
            ("on_hover", check_mark(size, True, pal, hover=True)),
            ("off_dis", check_mark(size, False, pal, disabled=True)),
            ("on_dis", check_mark(size, True, pal, disabled=True)),
        ):
            try:
                images[key] = ImageTk.PhotoImage(img, master=self)
            except Exception:
                return
        self._check_images = images

        element = "GSTCheck" + pal.key.capitalize()
        try:
            self.style.element_create(
                element, "image",
                images["normal"],
                ("active", images["hover"]),
                ("selected", images["on"]),
                ("disabled", images["off_dis"]),
                ("active", "selected", images["on_hover"]),
                ("disabled", "selected", images["on_dis"]),
                padding=(0, 0, 7, 0),
            )
        except Exception:
            pass  # 同主题重复安装时元素已存在，直接复用

        try:
            self.style.layout(
                "TCheckbutton",
                [
                    (
                        "Checkbutton.padding",
                        {
                            "sticky": "nswe",
                            "children": [
                                (element, {"side": "left", "sticky": ""}),
                                ("Checkbutton.label", {"side": "left", "sticky": "nswe"}),
                            ],
                        },
                    )
                ],
            )
        except Exception:
            pass

    def _apply_window_chrome(self) -> None:
        """窗口图标 + 标题栏配色（Windows 10 1809 之后可用 DWM 属性染深色标题栏）。"""
        if not getattr(self, "_icon_ready", False):
            icon = os.path.join(ASSETS_DIR, "gst.ico")
            try:
                if os.path.exists(icon):
                    self.iconbitmap(default=icon)
                    self._icon_ready = True
            except Exception:
                pass
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            dark = ctypes.c_int(1 if self.pal.key == "dark" else 0)
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE 的两种编号
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark)
                )
        except Exception:
            pass

    def _apply_palette(self) -> None:
        pal = self.pal
        self.configure(bg=pal.bg)
        for widget, role in self._painted:
            try:
                widget.configure(bg=self._color(role))
            except tk.TclError:
                pass
        for widget, fg_role, bg_role in self._labels:
            try:
                widget.configure(fg=self._color(fg_role), bg=self._color(bg_role))
            except tk.TclError:
                pass
        try:
            self.tree.palette = pal
            self.tree.canvas.configure(bg=pal.canvas_bg)
            self.tree._redraw()
        except Exception:
            pass
        self.btn_theme.configure(text=self._theme_label())

    def toggle_theme(self) -> None:
        self.pal = PALETTES["dark"] if self.pal.key == "light" else PALETTES["light"]
        self.cfg["theme"] = self.pal.key
        self._configure_styles()
        self._apply_palette()
        self._apply_window_chrome()
        self._status("已切换为" + ("深色" if self.pal.key == "dark" else "浅色") + "主题")

    # ------------------------------------------------------------ 拖拽
    def _setup_dnd(self) -> None:
        if DND_FILES is None:
            return
        try:
            for widget in (self, self.entry_path, self.tree.canvas):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
                widget.dnd_bind("<<DropEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DropLeave>>", self._on_drag_leave)
        except Exception:  # tkdnd 不可用时静默降级，不影响主功能
            pass

    def _on_drag_enter(self, event=None):
        self._status("松手即可生成结构树")
        try:
            self.tree.canvas.configure(bg=self.pal.row_hover)
        except Exception:
            pass
        return event.action if event is not None and hasattr(event, "action") else None

    def _on_drag_leave(self, event=None):
        try:
            self.tree.canvas.configure(bg=self.pal.canvas_bg)
        except Exception:
            pass
        self._status("就绪 · 输入路径或选择文件夹后生成结构树")
        return event.action if event is not None and hasattr(event, "action") else None

    def _on_drop(self, event):
        self._on_drag_leave()
        paths = split_drop_paths(getattr(event, "data", "") or "")
        if not paths:
            return "break"
        target = paths[0]
        if len(paths) > 1:
            # 拖进来一组：取它们的共同父目录更有意义
            try:
                common = os.path.commonpath([os.path.abspath(p) for p in paths])
            except ValueError:
                common = target
            if os.path.isdir(common) and any(os.path.isdir(p) for p in paths):
                target = common
            self._toast(f"收到 {len(paths)} 个路径，已按 {os.path.basename(target) or target} 生成")
        self.var_path.set(os.path.normpath(target))
        self.generate()
        return "break"

    # ------------------------------------------------------------ 快捷键
    def _bind_keys(self) -> None:
        self.bind("<Control-r>", lambda e: self.generate())
        self.bind("<F5>", lambda e: self.generate())
        self.bind("<Control-t>", lambda e: self.export_txt())
        self.bind("<Control-p>", lambda e: self.export_png())
        self.bind("<Control-f>", lambda e: (self.entry_search.focus_set(), self.entry_search.select_range(0, "end")))
        self.bind("<Control-e>", lambda e: self.tree_expand_all())
        self.bind("<Control-w>", lambda e: self.tree_collapse_all())
        self.tree.canvas.bind("<Control-c>", self._copy_selected)

    # ------------------------------------------------------------ 扫描
    def _scan_options(self) -> ScanOptions:
        def as_int(var: tk.IntVar, fallback: int) -> int:
            try:
                return int(var.get())
            except Exception:
                return fallback

        return ScanOptions(
            max_depth=max(0, as_int(self.var_depth, 0)),
            max_nodes=max(20, as_int(self.var_nodes, 6000)),
            show_hidden=bool(self.var_hidden.get()),
            use_ignore=bool(self.var_ignore.get()),
            sort_mode=SORT_LABELS.get(self.var_sort.get(), "name"),
            dirs_first=bool(self.var_dirs_first.get()),
        )

    def generate(self, event=None) -> None:
        # 注意：这里不拦"正在扫描"，用户改了路径再点生成时应当立刻重扫；
        # 旧任务的结果靠 _token 自增失效，不会覆盖新结果。
        raw = self.var_path.get().strip().strip('"')
        if not raw:
            messagebox.showinfo(APP_TITLE, "请先输入一个文件夹或文件的路径。", parent=self)
            self.entry_path.focus_set()
            return "break"
        options = self._scan_options()
        self._scanning = True
        self._token += 1
        token = self._token
        self._queue = queue.Queue()
        self.btn_generate.state(["disabled"])
        self._show_progress()
        self._status("正在扫描…")
        threading.Thread(target=self._scan_worker, args=(raw, options, self._queue), daemon=True).start()
        self.after(12, lambda: self._poll(token))
        return "break"

    @staticmethod
    def _scan_worker(path: str, options: ScanOptions, out: queue.Queue) -> None:
        try:
            result = scan_path(path, options, progress=lambda n, p: out.put(("progress", n, p)))
            out.put(("done", result))
        except Exception as exc:  # 交给主线程提示
            out.put(("error", str(exc)))

    def _poll(self, token: int) -> None:
        if token != self._token or self._queue is None:
            return
        finished = False
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item[0] == "progress":
                count, current = item[1], item[2]
                self._status(f"正在扫描… 已读取 {count} 项 · {self._short_path(current)}")
            elif item[0] == "done":
                self._finish_scan(item[1])
                finished = True
                break
            elif item[0] == "error":
                self._fail_scan(item[1])
                finished = True
                break
        if not finished:
            self.after(80, lambda: self._poll(token))

    def _finish_scan(self, result: ScanResult) -> None:
        self._scanning = False
        self._hide_progress()
        self.btn_generate.state(["!disabled"])
        self.result = result
        self.tree.set_tree(result.root)
        stats = result.stats
        self._status(f"完成 · {result.root.label} · {stats.summary()} · 用时 {stats.elapsed * 1000:.0f} ms")
        self.var_stats.set(f"{len(self.tree.rows)} 行 · 最大层级 {stats.max_depth}")
        self.cfg["path"] = result.root.path
        appconfig.save(self.cfg)
        if stats.truncated:
            self._toast("已达到节点上限，部分内容未展开；可提高上限后重新生成")
        elif stats.errors:
            self._toast(f"有 {stats.errors} 处因权限或占用无法读取")
        else:
            self._toast("结构树已生成")

    def _fail_scan(self, message: str) -> None:
        self._scanning = False
        self._hide_progress()
        self.btn_generate.state(["!disabled"])
        self._status("扫描失败")
        self._toast("路径无法读取")
        messagebox.showerror(APP_TITLE, f"无法生成结构树：\n{message}", parent=self)

    def _initial_scan(self) -> None:
        path = self.var_path.get().strip()
        if path and os.path.exists(path):
            self.generate()
        else:
            self._status("就绪 · 输入路径或选择文件夹后生成结构树")

    # ------------------------------------------------------------ 选择路径
    def pick_folder(self) -> None:
        initial = self.var_path.get().strip() or os.path.expanduser("~")
        if not os.path.isdir(initial):
            initial = os.path.dirname(initial) or os.path.expanduser("~")
        chosen = filedialog.askdirectory(title="选择一个文件夹", initialdir=initial, mustexist=True, parent=self)
        if chosen:
            self.var_path.set(os.path.normpath(chosen))
            self.generate()

    def pick_file(self) -> None:
        initial = self.var_path.get().strip() or os.path.expanduser("~")
        if os.path.isfile(initial):
            initial = os.path.dirname(initial)
        chosen = filedialog.askopenfilename(title="选择一个文件", initialdir=initial or None, parent=self)
        if chosen:
            self.var_path.set(os.path.normpath(chosen))
            self.generate()

    # ------------------------------------------------------------ 树交互
    def _on_tree_select(self, node) -> None:
        if node is None:
            return
        if node.is_dir:
            extra = f"{len(node.children)} 个子项" if node.children else "空文件夹"
        else:
            extra = human_size(node.size)
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(node.mtime)) if node.mtime else ""
        text = f"{node.path}   ·   {extra}" + (f"   ·   修改于 {stamp}" if stamp else "")
        if node.error:
            text += f"   ·   {node.error}"
        self._status(text)

    def _on_tree_open(self, node) -> None:
        self._reveal(node.path)

    def _on_tree_context(self, event, node) -> None:
        pal = self.pal
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=pal.panel,
            fg=pal.text,
            activebackground=pal.accent,
            activeforeground=pal.accent_text,
            bd=0,
            relief="flat",
            font=self.f_small,
        )
        menu.add_command(label="复制完整路径", command=lambda: self._copy(node.path))
        menu.add_command(label="复制文件名", command=lambda: self._copy(node.label))
        menu.add_command(label="在资源管理器中显示", command=lambda: self._reveal(node.path))
        if node.is_dir:
            menu.add_separator()
            menu.add_command(label="以此为根重新生成", command=lambda: self._root_at(node))
            menu.add_command(label="展开此文件夹", command=self._expand_node)
            menu.add_command(label="折叠此文件夹", command=self._collapse_node)
        menu.add_separator()
        menu.add_command(label="全部展开", command=self.tree_expand_all)
        menu.add_command(label="全部折叠", command=self.tree_collapse_all)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _root_at(self, node) -> None:
        """把某个文件夹当作新的根重新扫描。"""
        if not getattr(node, "is_dir", False):
            return
        self.var_path.set(node.path)
        self.generate()

    def _copy_selected(self, event=None):
        index = self.tree.selected_index
        if index is None:
            return None
        node = self.tree.rows[index].node
        self._copy(node.path)
        self._status("已复制路径：" + node.path)
        return "break"

    def _expand_node(self) -> None:
        if self.tree.selected_index is not None:
            node = self.tree.rows[self.tree.selected_index].node
            self.tree.collapsed.discard(node.path)
            self.tree._relayout()

    def _collapse_node(self) -> None:
        if self.tree.selected_index is not None:
            node = self.tree.rows[self.tree.selected_index].node
            if node.is_dir:
                self.tree.collapsed.add(node.path)
                self.tree._relayout()

    def tree_expand_all(self) -> None:
        self.tree.expand_all()
        self.var_stats.set(f"{len(self.tree.rows)} 行")

    def tree_collapse_all(self) -> None:
        self.tree.collapse_all()
        self.var_stats.set(f"{len(self.tree.rows)} 行")

    # ------------------------------------------------------------ 搜索
    def _on_search_key(self, event=None) -> None:
        if event is not None and event.keysym in ("Return", "Escape", "Up", "Down"):
            return
        if self._search_after:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(220, lambda: self._run_search(step=False))

    def _run_search(self, step: bool = True) -> None:
        query = self.var_search.get().strip()
        if not query:
            self.var_hits.set("")
            self.tree.search("")
            return
        if step and self.tree.hits:
            self.tree.next_hit()
            self.var_hits.set(f"{len(self.tree.hits)} 处匹配")
            return
        count = self.tree.search(query)
        self.var_hits.set(f"{count} 处匹配" if count else "无匹配")
        if count and self.tree.selected_index is not None:
            node = self.tree.rows[self.tree.selected_index].node
            self._on_tree_select(node)

    def _clear_search(self) -> None:
        self.var_search.set("")
        self.var_hits.set("")
        self.tree.search("")
        self.entry_search.focus_set()

    # ------------------------------------------------------------ 导出
    def _require_tree(self) -> bool:
        if self.result is None:
            messagebox.showinfo(APP_TITLE, "请先生成结构树。", parent=self)
            return False
        return True

    def _ask_save(self, ext: str, kind: str) -> str | None:
        assert self.result is not None
        name = export_text.default_filename(self.result.root, ext)
        initial_dir = self._last_export_dir or os.path.dirname(self.result.root.path) or os.path.expanduser("~")
        if not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")
        path = filedialog.asksaveasfilename(
            title=f"保存为 {kind}",
            defaultextension=f".{ext}",
            filetypes=[(f"{kind} 文件", f"*.{ext}"), ("所有文件", "*.*")],
            initialfile=name,
            initialdir=initial_dir,
            parent=self,
        )
        if not path:
            return None
        self._last_export_dir = os.path.dirname(path)
        self.cfg["last_export_dir"] = self._last_export_dir
        appconfig.save(self.cfg)
        return path

    def export_txt(self) -> None:
        if not self._require_tree():
            return
        path = self._ask_save("txt", "文本")
        if not path:
            return
        try:
            saved = export_text.write_text_file(
                path,
                self.result.root,
                stats=self.result.stats,
                source=self.result.root.path,
                include_header=bool(self.var_header.get()),
            )
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"写入失败：\n{exc}", parent=self)
            return
        size = os.path.getsize(saved)
        self._status(f"已导出 TXT · {saved}")
        self._toast(f"已保存 TXT（{human_size(size)}）")

    def export_png(self) -> None:
        if not self._require_tree():
            return
        path = self._ask_save("png", "图片")
        if not path:
            return
        self.configure(cursor="watch")
        self._status("正在渲染 PNG…")
        self.update_idletasks()
        try:
            scale = PNG_SCALES.get(self.var_scale.get(), 2.0)
            _, (w, h) = render_png(
                self.result.root,
                stats=self.result.stats,
                out_path=path,
                palette=self.pal,
                scale=scale,
                source=self.result.root.path,
                include_header=bool(self.var_header.get()),
            )
        except OSError as exc:
            self.configure(cursor="")
            messagebox.showerror(APP_TITLE, f"写入失败（文件可能正被占用）：\n{exc}", parent=self)
            return
        except Exception as exc:  # 渲染异常也要给出提示
            self.configure(cursor="")
            messagebox.showerror(APP_TITLE, f"渲染失败：\n{exc}", parent=self)
            return
        self.configure(cursor="")
        self._status(f"已导出 PNG · {w}×{h} · {path}")
        self._toast(f"已保存 PNG（{w}×{h}）")

    # ------------------------------------------------------------ 杂项
    @staticmethod
    def _short_path(path: str, limit: int = 56) -> str:
        if len(path) <= limit:
            return path
        return "…" + path[-(limit - 1):]

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status(f"已复制：{text}")

    def _reveal(self, path: str) -> None:
        try:
            if os.path.isdir(path):
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"无法打开资源管理器：\n{exc}", parent=self)

    def _show_progress(self) -> None:
        if not self._progress_shown:
            self.progress.pack(side="right", padx=(0, 12))
            self._progress_shown = True
        self.progress.start(12)

    def _hide_progress(self) -> None:
        try:
            self.progress.stop()
        except tk.TclError:
            pass
        if self._progress_shown:
            self.progress.pack_forget()
            self._progress_shown = False

    def _status(self, text: str) -> None:
        self.var_status.set(text)

    def _toast(self, text: str) -> None:
        pal = self.pal
        if self._toast_after:
            try:
                self.after_cancel(self._toast_after)
            except Exception:
                pass
            self._toast_after = None
        if getattr(self, "_toast_label", None) is not None:
            self._toast_label.destroy()
        label = tk.Label(
            self,
            text="  " + text + "  ",
            bg=pal.text,
            fg=pal.panel,
            font=self.f_small,
            padx=10,
            pady=6,
        )
        label.place(relx=1.0, rely=1.0, anchor="se", x=-22, y=-46)
        self._toast_label = label
        self._toast_after = self.after(3600, self._hide_toast)

    def _hide_toast(self) -> None:
        if getattr(self, "_toast_label", None) is not None:
            self._toast_label.destroy()
            self._toast_label = None
        self._toast_after = None

    def _center_if_needed(self) -> None:
        if self.cfg.get("geometry"):
            return
        self.update_idletasks()
        width, height = 1320, 880
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(width, screen_w - 80)
        height = min(height, screen_h - 120)
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _on_close(self) -> None:
        try:
            self.cfg.update(
                {
                    "path": self.var_path.get().strip(),
                    "max_depth": self._scan_options().max_depth,
                    "max_nodes": self._scan_options().max_nodes,
                    "show_hidden": bool(self.var_hidden.get()),
                    "use_ignore": bool(self.var_ignore.get()),
                    "sort_mode": SORT_LABELS.get(self.var_sort.get(), "name"),
                    "dirs_first": bool(self.var_dirs_first.get()),
                    "include_header": bool(self.var_header.get()),
                    "png_scale": PNG_SCALES.get(self.var_scale.get(), 2.0),
                    "theme": self.pal.key,
                    "geometry": self.geometry(),
                }
            )
            appconfig.save(self.cfg)
        finally:
            self.destroy()


def split_drop_paths(data: str) -> list[str]:
    """解析 tkdnd 的 drop 数据。

    形如 ``{C:/带 空格的/路径} D:/plain/a.txt`` —— 花括号包裹的是含空格的路径。
    """
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in data:
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            continue
        if ch.isspace() and depth == 0:
            if buf:
                items.append("".join(buf))
                buf.clear()
            continue
        buf.append(ch)
    if buf:
        items.append("".join(buf))
    return [p.strip().strip('"') for p in items if p.strip()]


if _DND_BASE is not None:

    class App(_AppCore, _DND_BASE):
        """支持拖拽的默认版本（tkinterdnd2 可用时）。"""

else:

    class App(_AppCore, tk.Tk):
        """未安装 tkinterdnd2 时的普通版本。"""


class PlainApp(_AppCore, tk.Tk):
    """兜底版本：tkdnd 初始化失败时也能正常启动。"""


def main() -> None:
    _enable_dpi_awareness()
    app = None
    if _DND_BASE is not None:
        try:
            app = App()
        except Exception:  # tkdnd 运行时不可用（缺 dll 等）
            app = None
    if app is None:
        app = PlainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
