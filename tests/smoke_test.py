"""无界面自检：扫描、文本导出、PNG 渲染、图标覆盖。

运行：  ..\\venv312\\Scripts\\python.exe tests\\smoke_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 控制台默认 GBK，遇到特殊字符会直接抛 UnicodeEncodeError，这里降级成替换。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

from PIL import Image

from gstree import export_text, icons
from gstree.layout import flatten
from gstree.model import ScanOptions, count_nodes, scan_path
from gstree.render_png import render_png
from gstree.theme import LIGHT, scaled_metrics

FAILS: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILS.append(message)


def build_sample(root: str) -> None:
    os.makedirs(os.path.join(root, "src", "core"), exist_ok=True)
    os.makedirs(os.path.join(root, "assets", "img"), exist_ok=True)
    os.makedirs(os.path.join(root, "empty_folder"), exist_ok=True)
    os.makedirs(os.path.join(root, "src", "core", "deep", "deeper"), exist_ok=True)

    files = {
        "readme.md": "# hi",
        "app.py": "print(1)",
        "src/main.py": "x = 1\n",
        "src/core/engine.py": "pass\n",
        "src/core/deep/deeper/x.cpp": "int main(){}",
        "assets/img/logo.png": "PNG",
        "assets/style.css": "body{}",
        "data.json": "{}",
        "song.mp3": "ID3",
        "movie.mp4": "MP4",
        "bundle.zip": "PK",
        "手册.pdf": "PDF",
        "sheet.xlsx": "XLSX",
        "deck.pptx": "PPTX",
        "tool.exe": "MZ",
        "font.ttf": "TTF",
        "db.sqlite": "SQL",
        "密钥.pem": "KEY",
        "model.blend": "BLEND",
        "disk.iso": "ISO",
        "noext": "plain",
    }
    for rel, content in files.items():
        path = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    # 隐藏文件（Windows 属性 + 点前缀两种）
    with open(os.path.join(root, ".hidden_cfg"), "w", encoding="utf-8") as fh:
        fh.write("x")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetFileAttributesW(
                os.path.join(root, "tool.exe"), 0x2  # FILE_ATTRIBUTE_HIDDEN
            )
        except Exception:
            pass


def main() -> int:
    print("== 1. 扫描目录 ==")
    tmp = tempfile.mkdtemp(prefix="gst_demo_")
    root_dir = os.path.join(tmp, "MyProject")
    build_sample(root_dir)
    started = time.perf_counter()
    result = scan_path(root_dir, ScanOptions(show_hidden=False))
    elapsed = time.perf_counter() - started
    root = result.root
    print(f"  {root.label}  节点={count_nodes(root)}  用时={elapsed * 1000:.1f}ms")
    check(root.label == "MyProject.fd", "根节点是文件夹并按规则加 .fd")
    check(result.stats.dirs >= 7, f"统计到文件夹 {result.stats.dirs} 个")
    check(result.stats.files >= 20, f"统计到文件 {result.stats.files} 个")
    names = [n.name for n in root.children]
    check("src" in names, "包含 src 目录")
    check("readme.md" in names, "包含 readme.md")
    empty = next((n for n in root.children if n.name == "empty_folder"), None)
    check(empty is not None and empty.is_dir and empty.label == "empty_folder.fd", "空文件夹也带 .fd")
    hidden_present = any(n.name in (".hidden_cfg", "tool.exe") for n in root.children)
    check(not hidden_present, "隐藏项已被过滤")

    hidden_result = scan_path(root_dir, ScanOptions(show_hidden=True))
    hidden_names = [n.name for n in hidden_result.root.children]
    check(".hidden_cfg" in hidden_names, "允许显示隐藏项时能看到 .hidden_cfg")

    print("== 2. 排序与标签 ==")
    labels = [n.label for n in root.children]
    check(all((lab.endswith(".fd") if n.is_dir else True) for lab, n in zip(labels, root.children)), "文件夹统一 .fd 后缀")
    dirs = [n for n in root.children if n.is_dir]
    check(labels[: len(dirs)] == [d.label for d in dirs], "文件夹优先排序")

    print("== 3. 单文件输入 ==")
    single = scan_path(os.path.join(root_dir, "readme.md"), ScanOptions())
    check(single.root.kind == "file", "单文件输入的根是文件")
    check(single.root.label == "readme.md", "单文件输入只输出该文件")
    check(not single.root.children, "单文件没有子节点")
    txt_single = export_text.render_text(single.root, single.stats, single.root.path)
    check("readme.md" in txt_single, "单文件文本导出包含文件名")

    print("== 4. 文本导出 ==")
    text = export_text.render_text(root, result.stats, root.path)
    out_txt = os.path.join(tmp, "tree.txt")
    export_text.write_text_file(out_txt, root, result.stats, root.path)
    check(os.path.getsize(out_txt) > 100, "TXT 已写入且非空")
    check("├──" in text or "└──" in text, "使用树形连线")
    check("src.fd" in text and "engine.py" in text, "文本包含目录与文件")
    check("MyProject.fd" in text, "文本根节点带 .fd")

    print("== 5. 深度 / 数量限制 ==")
    shallow = scan_path(root_dir, ScanOptions(max_depth=1))
    depth_rows, max_depth = (0, 0)
    from gstree.model import compute_extent

    depth_rows, max_depth = compute_extent(shallow.root)
    check(max_depth <= 1, f"max_depth=1 时最大层级 {max_depth}")
    limited = scan_path(root_dir, ScanOptions(max_nodes=6))
    check(limited.stats.truncated, "节点上限触发截断标记")
    check(count_nodes(limited.root) <= 12, f"截断后节点数 {count_nodes(limited.root)} 受限")

    print("== 6. PNG 渲染 ==")
    out_png = os.path.join(tmp, "tree.png")
    img, size = render_png(root, stats=result.stats, out_path=out_png, palette=LIGHT, scale=2.0, source=root.path)
    check(os.path.exists(out_png) and os.path.getsize(out_png) > 3000, f"PNG 已写入 {size} {os.path.getsize(out_png)}B")
    check(size[0] > 500 and size[1] > 200, f"图片尺寸合理 {size}")
    with Image.open(out_png) as im:
        check(im.mode == "RGB", f"PNG 色彩模式 {im.mode}")
        colors = im.convert("RGB").getcolors(maxcolors=1000000)
        check(colors is not None and len(colors) > 40, f"PNG 包含多种颜色（{len(colors) if colors else 0}）")
        # 左上角应为背景色，中部应有内容
        check(im.getpixel((5, 5)) == (255, 255, 255), "画布背景为白色")

    print("== 7. 深色主题 PNG ==")
    from gstree.theme import DARK

    out_png_dark = os.path.join(tmp, "tree_dark.png")
    dark_img, dark_size = render_png(root, stats=result.stats, out_path=out_png_dark, palette=DARK, scale=1.5, source=root.path)
    check(os.path.getsize(out_png_dark) > 3000, f"深色 PNG 已写入 {dark_size}")
    check(dark_img.getpixel((2, 2))[:3] == (17, 26, 40), "深色背景生效")

    print("== 8. 图标覆盖 ==")
    for cat in icons.COLORS:
        icon = icons.get_icon(cat, 32)
        check(icon.size == (32, 32) and icon.mode == "RGBA", f"图标 {cat} 正常")
        bbox = icon.getbbox()
        check(bbox is not None and bbox[2] - bbox[0] > 20, f"图标 {cat} 有实际像素")
    check(icons.category_for_name("x.py", False, "py") == "code", "py -> code")
    check(icons.category_for_name("x.PNG", False, "png") == "image", "大小写扩展名归一")
    check(icons.category_for_name("Dockerfile", False, "") == "config", "Dockerfile -> config")
    check(icons.category_for_name("folder", True, "") == "folder", "文件夹 -> folder")

    print("== 9. 布局行 ==")
    rows = flatten(root, scaled_metrics(1.0))
    check(len(rows) == count_nodes(root), f"行数 {len(rows)} == 节点数 {count_nodes(root)}")
    check(rows[0].depth == 0, "首行是根节点")
    check(all(r.depth >= 0 for r in rows), "层级合法")

    print("== 10. 极端名字 ==")
    weird = os.path.join(tmp, "weird")
    os.makedirs(weird, exist_ok=True)
    for name in ["空格 名字.txt", "a.b.c.d", "长的" * 40 + ".txt", ".dotfile"]:
        with open(os.path.join(weird, name), "w", encoding="utf-8") as fh:
            fh.write("x")
    weird_result = scan_path(weird, ScanOptions(show_hidden=True))
    weird_png = os.path.join(tmp, "weird.png")
    render_png(weird_result.root, stats=weird_result.stats, out_path=weird_png, palette=LIGHT, scale=1.0, source=weird)
    check(os.path.getsize(weird_png) > 2000, "超长中文名字也能渲染")

    print()
    if FAILS:
        print(f"失败 {len(FAILS)} 项：")
        for item in FAILS:
            print("  -", item)
        print("样例目录：", tmp)
        return 1
    print("[PASS] all checks passed   样例目录：", tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
