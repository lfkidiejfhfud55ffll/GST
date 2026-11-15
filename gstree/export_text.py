"""导出为纯文本的目录结构树（├── └── │ 连线）。"""

from __future__ import annotations

import datetime as _dt
import os

from .model import Node, ScanStats, human_size

TITLE = "目录结构树 / Directory Structure Tree"

LEGEND = "说明：以 .fd 结尾的节点代表文件夹（含空文件夹），其余为文件；图标说明见界面。"


def _stamp(when: _dt.datetime | None = None) -> str:
    return (when or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def render_text(
    root: Node,
    stats: ScanStats | None = None,
    source: str | None = None,
    include_header: bool = True,
    include_footer: bool = True,
    when: _dt.datetime | None = None,
) -> str:
    """生成树形文本。根节点同样按规则显示（文件夹加 .fd）。"""
    lines: list[str] = []

    if include_header:
        src = source or root.path
        lines.append(TITLE)
        lines.append("=" * 64)
        lines.append(f"根路径 : {src}")
        lines.append(f"根类型 : {'文件夹' if root.is_dir else '文件'}")
        lines.append(f"生成于 : {_stamp(when)}")
        if stats is not None:
            lines.append(
                f"统计   : {stats.dirs} 个文件夹 · {stats.files} 个文件 · "
                f"{human_size(stats.total_bytes)} · 最大层级 {stats.max_depth}"
            )
        lines.append("=" * 64)
        lines.append("")

    # 根节点
    lines.append(root.label)

    def walk(node: Node, prefix: str) -> None:
        count = len(node.children)
        for i, child in enumerate(node.children):
            last = i == count - 1
            lines.append(prefix + ("└── " if last else "├── ") + child.label)
            if child.is_dir and child.children:
                walk(child, prefix + ("    " if last else "│   "))

    if root.children:
        walk(root, "")

    if include_footer:
        lines.append("")
        if stats is not None and stats.truncated:
            lines.append("注意：节点数量达到上限，部分子节点未列出。")
        if stats is not None and stats.errors:
            lines.append(f"注意：{stats.errors} 处因权限或占用无法读取。")
        lines.append(LEGEND)

    return "\r\n".join(lines) + "\r\n"


def write_text_file(
    path: str,
    root: Node,
    stats: ScanStats | None = None,
    source: str | None = None,
    when: _dt.datetime | None = None,
    include_header: bool = True,
) -> str:
    """写盘（UTF-8 带 BOM，Windows 记事本可直接识别）。返回实际路径。"""
    text = render_text(root, stats=stats, source=source, when=when, include_header=include_header)
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(text)
    return os.path.abspath(path)


def default_filename(root: Node, ext: str) -> str:
    base = root.name or "structure"
    safe = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in base).strip(". ") or "structure"
    return f"{safe}_tree.{ext}"
