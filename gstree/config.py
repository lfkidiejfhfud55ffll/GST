"""本地配置读写（存在 GST 目录下，跟随程序走）。"""

from __future__ import annotations

import json
import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: 可通过环境变量 GST_CONFIG 指向别的文件（测试用它隔离，避免覆盖用户设置）
CONFIG_FILE = os.environ.get("GST_CONFIG") or os.path.join(APP_DIR, ".gst_config.json")

DEFAULTS: dict = {
    "path": "",
    "max_depth": 0,
    "max_nodes": 6000,
    "show_hidden": False,
    "use_ignore": True,
    "follow_links": False,
    "sort_mode": "name",
    "dirs_first": True,
    "theme": "light",
    "geometry": "",
    "last_export_dir": "",
    "include_header": True,
    "png_scale": 2.0,
}


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULTS:
                    data[key] = value
    except (OSError, ValueError):
        pass
    return data


def save(data: dict) -> None:
    payload = {key: data.get(key, value) for key, value in DEFAULTS.items()}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass
