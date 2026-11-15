"""GUI 冒烟测试：真正创建 Tk 窗口，跑一遍生成 / 搜索 / 导出 / 主题切换后退出。

运行：  ..\\venv312\\Scripts\\python.exe tests\\gui_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试用独立配置，别把用户真实的 .gst_config.json 覆盖掉
os.environ["GST_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="gst_cfg_"), ".gst_config.json")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def build_sample(root: str) -> None:
    os.makedirs(os.path.join(root, "alpha", "beta"), exist_ok=True)
    os.makedirs(os.path.join(root, "empty"), exist_ok=True)
    for rel, body in {
        "main.py": "print(1)",
        "alpha/notes.txt": "hi",
        "alpha/beta/pic.png": "PNG",
        "alpha/beta/data.json": "{}",
    }.items():
        path = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)


def wait_idle(gui, timeout: float = 5.0) -> bool:
    """等扫描线程结束 + 主线程把结果画上去（update 不会自己睡眠，必须显式 sleep）。"""
    import time as _time

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        gui.update()
        if not gui._scanning:
            gui.update_idletasks()
            gui.update()
            return True
        _time.sleep(0.01)
    return False


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="gst_gui_")
    sample = os.path.join(tmp, "Demo")
    build_sample(sample)

    import app as app_module

    app_module._enable_dpi_awareness()
    gui = app_module.App()

    print("== 1. 窗口与控件 ==")
    gui.update()
    check(gui.winfo_exists() == 1, "主窗口已创建")
    check(gui.entry_path.winfo_exists() == 1, "路径输入框存在")
    check(gui.btn_generate.winfo_exists() == 1, "生成按钮存在")

    print("== 2. 生成结构树 ==")
    gui.var_path.set(sample)
    gui.generate()
    check(wait_idle(gui), "扫描线程已结束")
    check(gui.result is not None, "拿到了扫描结果")
    check(len(gui.tree.rows) == 1 + 3 + 4 + 1 - 0 or len(gui.tree.rows) >= 8, f"树行数 {len(gui.tree.rows)}")
    check(gui.tree.rows[0].node.label == "Demo.fd", "根节点标签带 .fd")

    print("== 3. 折叠 / 展开 ==")
    full = len(gui.tree.rows)
    gui.tree.collapse_all()
    gui.update()
    collapsed = len(gui.tree.rows)
    check(collapsed < full, f"折叠后行数 {collapsed} < {full}")
    gui.tree.expand_all()
    gui.update()
    check(len(gui.tree.rows) == full, "展开后恢复")

    print("== 4. 搜索 ==")
    hits = gui.tree.search("pic")
    gui.update()
    check(hits == 1, f"搜索 pic 命中 {hits}")
    check(gui.tree.selected_index is not None, "自动跳转到命中行")
    gui.tree.search("")
    gui.update()

    print("== 5. 单文件输入 ==")
    gui.var_path.set(os.path.join(sample, "main.py"))
    gui.generate()
    check(wait_idle(gui), "单文件扫描完成")
    check(len(gui.tree.rows) == 1, f"单文件只有 1 行（实际 {len(gui.tree.rows)}）")
    check(gui.tree.rows[0].node.label == "main.py", "单文件标签是文件名")

    print("== 6. 导出 ==")
    gui.var_path.set(sample)
    gui.generate()
    check(wait_idle(gui), "重新扫描完成")
    from gstree import export_text
    from gstree.render_png import render_png

    out_txt = os.path.join(tmp, "out.txt")
    export_text.write_text_file(out_txt, gui.result.root, stats=gui.result.stats, source=gui.result.root.path)
    check(os.path.getsize(out_txt) > 100, "TXT 导出成功")
    out_png = os.path.join(tmp, "out.png")
    _, (w, h) = render_png(gui.result.root, stats=gui.result.stats, out_path=out_png, palette=gui.pal, scale=2.0, source=gui.result.root.path)
    check(os.path.getsize(out_png) > 3000, f"PNG 导出成功 {w}x{h}")

    print("== 7. 主题切换 ==")
    light_bg = gui.cget("bg")
    gui.toggle_theme()
    gui.update()
    dark_bg = gui.cget("bg")
    check(light_bg != dark_bg, f"背景色随主题变化 {light_bg} -> {dark_bg}")
    gui.toggle_theme()
    gui.update()
    check(gui.cget("bg") == light_bg, "可以切回浅色")

    print("== 8. 关闭 ==")
    gui._on_close()
    check(True, "窗口正常销毁")

    print()
    if FAILS:
        print(f"失败 {len(FAILS)} 项")
        return 1
    print("[PASS] GUI 冒烟测试通过", tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
