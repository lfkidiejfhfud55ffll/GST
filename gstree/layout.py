"""树 -> 行的展平与几何位置计算。

每一行记录：节点、层级、y 坐标、以及"祖先层是否还有后续兄弟"的连线指示。
折叠集合以节点绝对路径为键，因此重新扫描同名结构时状态不会错乱。
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Node
from .theme import Metrics


@dataclass
class Row:
    node: Node
    depth: int
    index: int
    y: int
    guides: tuple[bool, ...]
    last: bool


def flatten(root: Node, metrics: Metrics, collapsed: set[str] | None = None) -> list[Row]:
    """先序展平整棵树；``collapsed`` 中的路径不展开子节点。"""
    collapsed = collapsed or set()
    rows: list[Row] = []
    step = metrics.row_h

    def walk(node: Node, depth: int, y: int, guides: tuple[bool, ...], last: bool) -> int:
        rows.append(Row(node=node, depth=depth, index=len(rows), y=y, guides=guides, last=last))
        y += step
        if not node.is_dir or node.path in collapsed or not node.children:
            return y
        count = len(node.children)
        for i, child in enumerate(node.children):
            y = walk(child, depth + 1, y, guides + (not last,), i == count - 1)
        return y

    walk(root, 0, 0, tuple(), True)
    return rows


def ancestors_of(root: Node, target_path: str) -> list[Node]:
    """返回从根到目标节点父级的所有目录节点（用于展开折叠）。"""
    stack: list[tuple[Node, list[Node]]] = [(root, [])]
    while stack:
        node, trail = stack.pop()
        if node.path == target_path:
            return trail
        for child in node.children:
            if child.is_dir:
                stack.append((child, trail + [node]))
    return []
