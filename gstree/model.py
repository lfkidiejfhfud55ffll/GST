"""文件系统扫描与树模型。

核心规则（与需求一致）：
  * 节点只展示"文件名"，文件夹在名字后加 ``.fd`` 后缀（空文件夹也算）。
  * 输入既可以是文件夹，也可以是单个文件；单个文件时树里只有它自己。
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

if sys.platform == "win32":  # pragma: no cover - 平台分支
    _ATTR_HIDDEN = 0x2
    _ATTR_SYSTEM = 0x4
    _ATTR_REPARSE = 0x400
else:  # pragma: no cover
    _ATTR_HIDDEN = 0
    _ATTR_SYSTEM = 0
    _ATTR_REPARSE = 0

#: 默认跳过的"噪音"目录名（可在界面关闭）
DEFAULT_IGNORE: tuple[str, ...] = (
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".nuxt",
    "$RECYCLE.BIN",
    "System Volume Information",
)

#: 忽略名单里同时命中的文件名
DEFAULT_IGNORE_FILES: tuple[str, ...] = ("Thumbs.db", "desktop.ini", ".DS_Store")

_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_size(num: float) -> str:
    """把字节数变成 1.2 MB 这样的可读字符串。"""
    if num < 1024:
        return f"{int(num)} B"
    value = float(num)
    for unit in _SIZE_UNITS[1:]:
        value /= 1024.0
        if value < 1024 or unit == _SIZE_UNITS[-1]:
            return f"{value:.1f} {unit}" if value < 100 else f"{value:.0f} {unit}"
    return f"{int(num)} B"


def extension_of(name: str) -> str:
    """取小写扩展名（不含点）。隐藏文件 ``.gitignore`` 视为无扩展名。"""
    if name.startswith("."):
        return ""
    base, dot, ext = name.rpartition(".")
    if not dot or not base:
        return ""
    return ext.lower()


_NAT_RE = re.compile(r"(\d+)")


def natural_key(text: str):
    """自然排序：file2 排在 file10 前面。"""
    parts = _NAT_RE.split(text.lower())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts if p != ""]


@dataclass
class Node:
    """树节点。``kind`` 为 ``dir`` 或 ``file``。"""

    name: str
    path: str
    kind: str = "file"
    ext: str = ""
    size: int = 0
    mtime: float = 0.0
    depth: int = 0
    children: list["Node"] = field(default_factory=list)
    error: str = ""
    #: 子节点因深度/数量限制被省略
    skipped: bool = False
    #: 符号链接 / 目录联接（未跟随）
    is_link: bool = False

    # ---------------------------------------------------------------- 展示
    @property
    def is_dir(self) -> bool:
        return self.kind == "dir"

    @property
    def label(self) -> str:
        """画在节点上的文字：文件夹加 .fd，文件保持原名。"""
        if self.kind == "dir":
            low = self.name.lower()
            # 本身就叫 xxx.fd 的文件夹不再叠加后缀
            return self.name if low.endswith(".fd") else self.name + ".fd"
        return self.name

    def walk(self) -> Iterable["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class ScanOptions:
    max_depth: int = 0  # 0 = 不限
    max_nodes: int = 6000
    show_hidden: bool = False
    use_ignore: bool = True
    follow_links: bool = False
    sort_mode: str = "name"  # name | type | size
    dirs_first: bool = True

    @property
    def ignore_names(self) -> frozenset[str]:
        return frozenset(DEFAULT_IGNORE) if self.use_ignore else frozenset()

    @property
    def ignore_files(self) -> frozenset[str]:
        return frozenset(DEFAULT_IGNORE_FILES) if self.use_ignore else frozenset()


@dataclass
class ScanStats:
    dirs: int = 0
    files: int = 0
    errors: int = 0
    total_bytes: int = 0
    truncated: bool = False
    elapsed: float = 0.0
    max_depth: int = 0
    skipped_ignored: int = 0

    @property
    def total(self) -> int:
        return self.dirs + self.files

    def summary(self) -> str:
        parts = [f"{self.dirs} 个文件夹", f"{self.files} 个文件", human_size(self.total_bytes)]
        if self.errors:
            parts.append(f"{self.errors} 处无法读取")
        if self.truncated:
            parts.append("已达数量上限，部分省略")
        return " · ".join(parts)


@dataclass
class ScanResult:
    root: Node
    stats: ScanStats


# ----------------------------------------------------------------- 扫描实现
class _Scanner:
    def __init__(self, options: ScanOptions, progress: Callable[[int, str], None] | None):
        self.opts = options
        self.progress = progress
        self.count = 0
        self.stats = ScanStats()
        self._last_tick = 0.0
        self._ignore = options.ignore_names
        self._ignore_files = options.ignore_files

    # -- 工具 ---------------------------------------------------------
    def _tick(self, path: str) -> None:
        now = time.monotonic()
        if self.progress and now - self._last_tick > 0.08:
            self._last_tick = now
            try:
                self.progress(self.count, path)
            except Exception:  # 进度回调不允许打断扫描
                pass

    def _new_node(self, name: str, path: str, kind: str, depth: int) -> Node:
        self.count += 1
        node = Node(name=name, path=path, kind=kind, depth=depth)
        if kind == "dir":
            self.stats.dirs += 1
        else:
            self.stats.files += 1
        if depth > self.stats.max_depth:
            self.stats.max_depth = depth
        self._tick(path)
        return node

    def _budget_left(self) -> bool:
        if self.count >= self.opts.max_nodes:
            self.stats.truncated = True
            return False
        return True

    def _hidden(self, name: str, attrs: int) -> bool:
        if name.startswith(".") or name.startswith("$"):
            return True
        return bool(attrs & (_ATTR_HIDDEN | _ATTR_SYSTEM))

    def _sort(self, children: list[Node]) -> None:
        mode = self.opts.sort_mode
        dirs_first = self.opts.dirs_first

        def key(node: Node):
            primary = 0 if (dirs_first and node.kind == "dir") else 1
            if mode == "type":
                return (primary, node.kind != "dir", node.ext, natural_key(node.name))
            if mode == "size":
                return (primary, -node.size, natural_key(node.name))
            if mode == "mtime":
                return (primary, -float(node.mtime or 0.0), natural_key(node.name))
            return (primary, natural_key(node.name))

        children.sort(key=key)

    # -- 递归 ---------------------------------------------------------
    def scan(self, path: str) -> Node:
        path = os.path.abspath(path)
        name = os.path.basename(path.rstrip("\\/")) or path
        if os.path.isdir(path):
            return self._scan_dir(path, name, 0)
        return self._scan_file_path(path, name, 0)

    def _scan_file_path(self, path: str, name: str, depth: int) -> Node:
        node = self._new_node(name, path, "file", depth)
        node.ext = extension_of(name)
        try:
            st = os.stat(path, follow_symlinks=False)
            node.size = int(st.st_size)
            node.mtime = st.st_mtime
            self.stats.total_bytes += node.size
        except OSError as exc:
            node.error = exc.strerror or str(exc)
            self.stats.errors += 1
        return node

    def _scan_file_entry(self, entry: os.DirEntry, name: str, depth: int, is_link: bool) -> Node:
        node = self._new_node(name, entry.path, "file", depth)
        node.ext = extension_of(name)
        node.is_link = is_link
        try:
            st = entry.stat(follow_symlinks=False)
            node.size = int(st.st_size)
            node.mtime = st.st_mtime
            self.stats.total_bytes += node.size
        except OSError as exc:
            node.error = exc.strerror or str(exc)
            self.stats.errors += 1
        return node

    def _scan_dir(self, path: str, name: str, depth: int, is_link: bool = False) -> Node:
        node = self._new_node(name, path, "dir", depth)
        node.is_link = is_link

        try:
            st = os.stat(path, follow_symlinks=False)
            node.mtime = st.st_mtime
            attrs = getattr(st, "st_file_attributes", 0)
        except OSError as exc:
            node.error = exc.strerror or str(exc)
            self.stats.errors += 1
            return node

        reparse = bool(attrs & _ATTR_REPARSE)
        if (is_link or reparse) and not self.opts.follow_links:
            # 不跟随链接，避免环路
            node.skipped = True
            node.is_link = True
            return node

        if self.opts.max_depth and depth >= self.opts.max_depth:
            node.skipped = True
            return node

        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError as exc:
            node.error = exc.strerror or str(exc)
            self.stats.errors += 1
            return node

        children: list[Node] = []
        for entry in entries:
            if not self._budget_left():
                node.skipped = True
                break
            try:
                child_name = entry.name
                if child_name in self._ignore:
                    self.stats.skipped_ignored += 1
                    continue

                is_link = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=False)
                if not is_dir and is_link:
                    # 链接指向文件夹时按文件夹展示，但不展开
                    try:
                        is_dir = os.path.isdir(entry.path)
                    except OSError:
                        is_dir = False
                if not is_dir and child_name in self._ignore_files:
                    self.stats.skipped_ignored += 1
                    continue
                if not self.opts.show_hidden:
                    try:
                        attrs = entry.stat(follow_symlinks=False).st_file_attributes
                    except OSError:
                        attrs = 0
                    if self._hidden(child_name, attrs):
                        continue
                if is_dir:
                    children.append(self._scan_dir(entry.path, child_name, depth + 1, is_link))
                else:
                    children.append(self._scan_file_entry(entry, child_name, depth + 1, is_link))
            except OSError as exc:  # 单个条目失败不影响整体
                self.stats.errors += 1
                node.error = node.error or (exc.strerror or str(exc))
                continue

        self._sort(children)
        node.children = children
        return node


def normalize_input_path(raw: str) -> str:
    """把用户输入整理成一个可用的本地路径。

    - 去掉首尾空白与包裹的引号
    - 支持 ``file:///D:/x`` 这类 URI
    - 展开 ``%VAR%`` / ``~``
    - 去掉末尾多余的分隔符（但保留 ``C:\\`` 这种盘符根）
    """
    text = str(raw or "").strip().strip('"').strip("'").strip()
    if not text:
        return ""
    if text.lower().startswith("file://"):
        try:
            from urllib.parse import unquote, urlparse
            from urllib.request import url2pathname

            parsed = urlparse(text)
            path_part = unquote(parsed.path or "")
            if parsed.netloc:  # file://server/share
                path_part = "//" + parsed.netloc + path_part
            text = url2pathname(path_part)
        except Exception:
            pass
    text = os.path.expandvars(os.path.expanduser(text))
    text = text.replace("/", os.sep)
    stripped = text.rstrip("\\/")
    if stripped and len(stripped) > 2:  # 保留 "C:\\" 与 UNC 前缀
        text = stripped
    elif stripped and not stripped.endswith(":"):
        text = stripped
    return text


def scan_path(
    path: str,
    options: ScanOptions | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> ScanResult:
    """扫描 ``path``，返回树模型与统计信息。路径不存在时抛 ``FileNotFoundError``。"""
    options = options or ScanOptions()
    if not path or not str(path).strip():
        raise FileNotFoundError("路径为空")
    raw = normalize_input_path(path)
    if not os.path.exists(raw):
        raise FileNotFoundError(f"路径不存在：{raw}")
    started = time.perf_counter()
    scanner = _Scanner(options, progress)
    root = scanner.scan(raw)
    stats = scanner.stats
    stats.elapsed = time.perf_counter() - started
    return ScanResult(root=root, stats=stats)


def count_nodes(root: Node) -> int:
    total = 1
    for child in root.children:
        total += count_nodes(child)
    return total


def compute_extent(root: Node) -> tuple[int, int]:
    """返回 (行数, 最大深度)。"""
    rows = 1
    depth = 0
    stack: list[tuple[Node, int]] = [(root, 0)]
    while stack:
        node, d = stack.pop()
        depth = max(depth, d)
        rows += len(node.children)
        stack.extend((c, d + 1) for c in node.children)
    return rows, depth
