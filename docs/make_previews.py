"""生成 README 里用的两张演示图（浅色 / 深色），不参与程序运行。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from gstree.model import ScanOptions, scan_path  # noqa: E402
from gstree.render_png import render_png  # noqa: E402
from gstree.theme import DARK, LIGHT  # noqa: E402

TREE = {
    "src": {
        "main.py": 3200,
        "server.py": 8200,
        "utils.py": 1500,
        "assets": {"logo.png": 42000, "font.ttf": 120000, "intro.mp3": 2400000},
        "web": {"index.html": 2600, "app.css": 3900, "app.js": 12400},
    },
    "docs": {
        "readme.md": 4200,
        "guide.pdf": 880000,
        "arch": {"设计说明.md": 7600, "架构图.svg": 21000},
    },
    "data": {
        "config.json": 780,
        "records.csv": 156000,
        "cache.db": 640000,
        "backup.zip": 5200000,
    },
    "logs": {"2026-11-14.log": 32000, "2026-11-15.log": 18000},
    "build": {},
    "run.sh": 640,
    "Dockerfile": 480,
    "LICENSE": 1100,
}


def build(root: str, mapping: dict) -> None:
    for name, value in mapping.items():
        target = os.path.join(root, name)
        if isinstance(value, dict):
            os.makedirs(target, exist_ok=True)
            build(target, value)
        else:
            with open(target, "wb") as handle:
                handle.write(b"\0" * value)


def main() -> int:
    base = tempfile.mkdtemp(prefix="gst_demo_")
    demo = os.path.join(base, "project")
    os.makedirs(demo, exist_ok=True)
    build(demo, TREE)

    result = scan_path(demo, ScanOptions())
    # 文档图里显示一个中性的示例路径，避免把本机临时目录 / 用户名带进公开的 README
    display_source = os.path.join("D:\\", "projects", "demo", "project")
    for palette, name in ((LIGHT, "preview_light.png"), (DARK, "preview_dark.png")):
        out = os.path.join(HERE, name)
        render_png(
            result.root,
            result.stats,
            out,
            palette=palette,
            scale=2.0,
            source=display_source,
        )
        print("written", out)

    shutil.rmtree(base, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
