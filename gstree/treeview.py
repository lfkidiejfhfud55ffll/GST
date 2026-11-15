"""Tk 画布上的目录树视图：只绘制可视区域的行（虚拟化），支持折叠与搜索高亮。"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable

from PIL import ImageTk

from . import icons
from .layout import Row, flatten
from .model import Node
from .theme import Metrics, Palette, scaled_metrics

#: 滚轮一格（delta=120）纵向滚动的行数，按手感调这里即可
WHEEL_ROWS = 4
#: 横向滚动一格移动的"单位"数（canvas xscrollincrement=24，即约 72px）
WHEEL_UNITS_X = 3


class TreeView(ttk.Frame):
    def __init__(
        self,
        master,
        palette: Palette,
        font_family: str = "Microsoft YaHei UI",
        on_select: Callable[[Node | None], None] | None = None,
        on_open: Callable[[Node], None] | None = None,
        on_context: Callable[[tk.Event, Node], None] | None = None,
    ) -> None:
        super().__init__(master, style="Card.TFrame")
        self.palette = palette
        self._on_select = on_select
        self._on_open = on_open
        self._on_context = on_context

        self._font = tkfont.Font(family=font_family, size=10)
        self._font_bold = tkfont.Font(family=font_family, size=10, weight="bold")
        dpi_scale = float(self.tk.call("tk", "scaling")) / (96.0 / 72.0)
        self.metrics: Metrics = scaled_metrics(max(1.0, dpi_scale))

        self.canvas = tk.Canvas(
            self,
            bg=palette.canvas_bg,
            highlightthickness=0,
            bd=0,
            takefocus=True,
            yscrollincrement=1,
            xscrollincrement=24,
        )
        self.vbar = ttk.Scrollbar(self, orient="vertical", style="Slim.Vertical.TScrollbar", command=self._yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", style="Slim.Horizontal.TScrollbar", command=self._xview)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.root: Node | None = None
        self.rows: list[Row] = []
        self.collapsed: set[str] = set()
        self.selected_index: int | None = None
        self.hover_index: int | None = None
        self.hits: set[int] = set()
        self.doc_w = 0
        self.doc_h = 0
        self._img_cache: dict[tuple[str, int], ImageTk.PhotoImage] = {}
        self._label_w: dict[str, float] = {}
        self._placeholder = ""
        self._sb_v = True
        self._sb_h = True

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Button-3>", self._on_right)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        for seq in ("<MouseWheel>", "<Shift-MouseWheel>"):
            self.canvas.bind(seq, self._on_wheel)
            self.bind(seq, self._on_wheel)
        self.canvas.bind("<Up>", lambda e: self._move_selection(-1))
        self.canvas.bind("<Down>", lambda e: self._move_selection(1))
        self.canvas.bind("<Prior>", lambda e: self._page(-1))
        self.canvas.bind("<Next>", lambda e: self._page(1))

    # ------------------------------------------------------------ 滚动条
    def _on_configure(self, _event=None) -> None:
        self._sync_scrollbars()
        self._redraw()

    def _sync_scrollbars(self) -> None:
        """内容装得下时把滚动条收起来，界面更干净。"""
        has_rows = bool(self.rows)
        need_v = has_rows and self.doc_h > (self.canvas.winfo_height() or 0)
        need_h = has_rows and self.doc_w > (self.canvas.winfo_width() or 0)
        if need_v != self._sb_v:
            if need_v:
                self.vbar.grid(row=0, column=1, sticky="ns")
            else:
                self.vbar.grid_remove()
            self._sb_v = need_v
        if need_h != self._sb_h:
            if need_h:
                self.hbar.grid(row=1, column=0, sticky="ew")
            else:
                self.hbar.grid_remove()
            self._sb_h = need_h

    # ------------------------------------------------------------ 数据
    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        if not self.rows:
            self._redraw()

    def set_tree(self, root: Node, collapsed: set[str] | None = None) -> None:
        self.root = root
        self.collapsed = set(collapsed or ())
        self.selected_index = None
        self.hover_index = None
        self.hits.clear()
        self._relayout(keep_scroll=False)

    def clear(self) -> None:
        self.root = None
        self.rows = []
        self.hits.clear()
        self.selected_index = None
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self._sync_scrollbars()
        self._redraw()

    def current_node(self) -> Node | None:
        if self.selected_index is None or self.selected_index >= len(self.rows):
            return None
        return self.rows[self.selected_index].node

    # -------------------------------------------------------- 布局与绘制
    def _relayout(self, keep_scroll: bool = True) -> None:
        if self.root is None:
            self.rows = []
            self.doc_w = self.doc_h = 0
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            self._sync_scrollbars()
            self._redraw()
            return

        frac = self.canvas.yview()[0] if keep_scroll else 0.0
        self.rows = flatten(self.root, self.metrics, self.collapsed)
        max_w = 420
        for row in self.rows:
            text = self._fit(_display(row.node), 2200)
            max_w = max(max_w, self.metrics.x_text(row.depth) + self._font.measure(text))
        self.doc_w = int(max_w + 24)
        self.doc_h = int(len(self.rows) * self.metrics.row_h + self.metrics.pad_v * 2)
        self.canvas.configure(scrollregion=(0, 0, self.doc_w, self.doc_h))
        self.canvas.yview_moveto(frac)
        self._sync_scrollbars()
        self._redraw()

    def _fit(self, text: str, max_px: int) -> str:
        if self._font.measure(text) <= max_px:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._font.measure(text[:mid] + "…") <= max_px:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + "…"

    def _photo(self, category: str, size: int) -> ImageTk.PhotoImage:
        key = (category, size)
        photo = self._img_cache.get(key)
        if photo is None:
            photo = ImageTk.PhotoImage(icons.get_icon(category, size))
            self._img_cache[key] = photo
        return photo

    def _visible_range(self) -> tuple[int, int]:
        if not self.rows:
            return 0, -1
        top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height() or 600
        rh = self.metrics.row_h
        first = int((top - self.metrics.pad_v) // rh) - 2
        last = int((top + height - self.metrics.pad_v) // rh) + 2
        return max(0, first), min(len(self.rows) - 1, last)

    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        if not self.rows:
            self._draw_placeholder()
            return

        p = self.palette
        m = self.metrics
        rh = m.row_h
        first, last = self._visible_range()
        width = max(self.doc_w, c.winfo_width())
        accent_w = max(2, int(round(2 * (rh / 26))))

        for idx in range(first, last + 1):
            row = self.rows[idx]
            node = row.node
            top = m.pad_v + row.y
            cy = top + rh // 2

            if idx == self.selected_index:
                c.create_rectangle(0, top, width, top + rh, fill=p.row_selected, outline="")
                c.create_rectangle(0, top, accent_w, top + rh, fill=p.accent, outline="")
            elif idx == self.hover_index:
                c.create_rectangle(0, top, width, top + rh, fill=p.row_hover, outline="")
            elif idx in self.hits:
                c.create_rectangle(m.pad_l - 8, top, width, top + rh, fill=p.hit_bg, outline="")

            if row.depth > 0:
                for level, cont in enumerate(row.guides):
                    if cont:
                        gx = m.x_spine(level + 1)
                        c.create_line(gx, top, gx, top + rh, fill=p.guide)
                sx = m.x_spine(row.depth)
                c.create_line(sx, top, sx, cy, fill=p.guide)
                if not row.last:
                    c.create_line(sx, cy, sx, top + rh, fill=p.guide)
                c.create_line(sx, cy, m.x_icon(row.depth) - 3, cy, fill=p.guide)

            category = icons.category_for(node)
            c.create_image(m.x_icon(row.depth), cy, image=self._photo(category, m.icon), anchor="w")

            label = self._fit(_display(node), 2200)
            color = p.text
            font = self._font
            if node.is_dir and node.children:
                font = self._font_bold
            if node.error:
                color = p.warn
            text_id = c.create_text(
                m.x_text(row.depth), cy, text=label, anchor="w", fill=color, font=font
            )
            if node.error:
                c.create_text(
                    m.x_text(row.depth) + self._font.measure(label) + 14,
                    cy,
                    text="读取失败",
                    anchor="w",
                    fill=p.warn,
                    font=self._font,
                )
            _ = text_id

    def _draw_placeholder(self) -> None:
        c = self.canvas
        w = max(c.winfo_width(), 480)
        h = max(c.winfo_height(), 320)
        p = self.palette
        icon = self._photo("folder", 56)
        c.create_image(w // 2, h // 2 - 46, image=icon, anchor="center")
        c.create_text(
            w // 2,
            h // 2 + 6,
            text="还没有内容",
            fill=p.text,
            font=(self._font.cget("family"), 12, "bold"),
            anchor="center",
        )
        c.create_text(
            w // 2,
            h // 2 + 34,
            text=self._placeholder or "在上方输入文件夹或文件路径，然后点击「生成结构树」",
            fill=p.text_dim,
            font=self._font,
            anchor="center",
            width=max(320, w - 120),
            justify="center",
        )

    # -------------------------------------------------------- 滚动与交互
    def _yview(self, *args) -> None:
        self.canvas.yview(*args)
        self._redraw()

    def _xview(self, *args) -> None:
        self.canvas.xview(*args)
        self._redraw()

    def _on_wheel(self, event: tk.Event):
        # canvas 的 yscrollincrement=1（按像素滚），所以这里直接换算成像素：
        # 一格滚轮（delta=120）走 WHEEL_ROWS 行，手感比系统默认的 3 行更快。
        notches = (event.delta or 0) / 120.0
        if notches == 0:
            notches = 1.0 if event.delta > 0 else -1.0
        if event.state & 0x0001:  # Shift → 横向
            self.canvas.xview_scroll(int(-notches * WHEEL_UNITS_X), "units")
        else:
            self.canvas.yview_scroll(int(-notches * self.metrics.row_h * WHEEL_ROWS), "units")
        self._redraw()
        return "break"

    def _index_at(self, y: int) -> int | None:
        if not self.rows:
            return None
        doc_y = self.canvas.canvasy(y) - self.metrics.pad_v
        idx = int(doc_y // self.metrics.row_h)
        if 0 <= idx < len(self.rows):
            return idx
        return None

    def _on_click(self, event: tk.Event):
        self.canvas.focus_set()
        idx = self._index_at(event.y)
        self.selected_index = idx
        if idx is not None:
            node = self.rows[idx].node
            if node.is_dir and node.children:
                self.toggle(idx)
            if self._on_select:
                self._on_select(node)
        else:
            if self._on_select:
                self._on_select(None)
        self._redraw()

    def _on_double(self, event: tk.Event):
        idx = self._index_at(event.y)
        if idx is not None and self._on_open:
            self._on_open(self.rows[idx].node)

    def _on_right(self, event: tk.Event):
        idx = self._index_at(event.y)
        if idx is None:
            return
        self.selected_index = idx
        self._redraw()
        if self._on_context:
            self._on_context(event, self.rows[idx].node)

    def _on_motion(self, event: tk.Event):
        idx = self._index_at(event.y)
        if idx != self.hover_index:
            self.hover_index = idx
            self._redraw()

    def _on_leave(self, _event=None):
        if self.hover_index is not None:
            self.hover_index = None
            self._redraw()

    def _move_selection(self, delta: int):
        if not self.rows:
            return "break"
        idx = 0 if self.selected_index is None else self.selected_index + delta
        idx = max(0, min(len(self.rows) - 1, idx))
        self.select_index(idx)
        return "break"

    def _page(self, direction: int):
        if not self.rows:
            return "break"
        step = max(1, (self.canvas.winfo_height() or 600) // self.metrics.row_h - 2)
        self._move_selection(direction * step)
        return "break"

    # -------------------------------------------------------- 对外操作
    def toggle(self, idx: int) -> None:
        node = self.rows[idx].node
        if not node.is_dir or not node.children:
            return
        if node.path in self.collapsed:
            self.collapsed.discard(node.path)
        else:
            self.collapsed.add(node.path)
        self._relayout()

    def toggle_selected(self) -> None:
        if self.selected_index is not None:
            self.toggle(self.selected_index)

    def expand_all(self) -> None:
        self.collapsed.clear()
        self._relayout()

    def collapse_all(self) -> None:
        if self.root is None:
            return
        stack = [self.root]
        while stack:
            node = stack.pop()
            if node.is_dir:
                if node.children:
                    self.collapsed.add(node.path)
                stack.extend(node.children)
        self._relayout()

    def select_index(self, idx: int) -> None:
        if not self.rows:
            return
        idx = max(0, min(len(self.rows) - 1, idx))
        self.selected_index = idx
        self._scroll_into_view(idx)
        if self._on_select:
            self._on_select(self.rows[idx].node)
        self._redraw()

    def _scroll_into_view(self, idx: int) -> None:
        rh = self.metrics.row_h
        row_top = self.metrics.pad_v + self.rows[idx].y
        view_top = self.canvas.canvasy(0)
        view_h = self.canvas.winfo_height() or 600
        if row_top < view_top:
            self.canvas.yview_moveto(max(0.0, (row_top - 20) / max(1, self.doc_h)))
        elif row_top + rh > view_top + view_h:
            target = row_top + rh + 20 - view_h
            self.canvas.yview_moveto(max(0.0, target / max(1, self.doc_h)))

    def search(self, query: str) -> int:
        """高亮匹配节点，返回匹配数量；自动展开并跳到第一个匹配。"""
        self.hits.clear()
        q = query.strip().lower()
        if not q or self.root is None:
            self._relayout(keep_scroll=True)
            return 0
        # 展开所有含命中节点的父目录
        stack: list[tuple[Node, list[str]]] = [(self.root, [])]
        hit_paths: set[str] = set()
        while stack:
            node, trail = stack.pop()
            if q in node.label.lower():
                hit_paths.add(node.path)
                for p in trail:
                    self.collapsed.discard(p)
            for child in node.children:
                stack.append((child, trail + [node.path]))
        self._relayout(keep_scroll=False)
        count = 0
        for i, row in enumerate(self.rows):
            if row.node.path in hit_paths:
                self.hits.add(i)
                count += 1
        if count:
            first_idx = min(self.hits)
            self.selected_index = first_idx
            self._scroll_into_view(first_idx)
            if self._on_select:
                self._on_select(self.rows[first_idx].node)
        self._redraw()
        return count

    def hit_indices(self) -> list[int]:
        return sorted(self.hits)

    def next_hit(self, backwards: bool = False) -> None:
        if not self.hits:
            return
        hits = sorted(self.hits)
        current = self.selected_index if self.selected_index is not None else -1
        if backwards:
            candidates = [i for i in hits if i < current]
            target = candidates[-1] if candidates else hits[-1]
        else:
            candidates = [i for i in hits if i > current]
            target = candidates[0] if candidates else hits[0]
        self.select_index(target)


def _display(node: Node) -> str:
    return node.label
