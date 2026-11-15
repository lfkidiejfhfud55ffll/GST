# 参与贡献

感谢愿意改进 GST。这个项目的目标很克制：**一个双击就能跑、零配置、只依赖 Pillow（和可选的 tkinterdnd2）的目录结构树工具**。提 PR 前请先确认下面几条没有被破坏。

## 环境准备

```bat
:: 1. 克隆后进入目录
cd GST

:: 2. 用任意 Python 3.10+ 建虚拟环境（仓库里不提交 venv）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

:: 3. 跑测试
.venv\Scripts\python.exe tests\smoke_test.py
.venv\Scripts\python.exe tests\gui_smoke.py

:: 4. 启动
.venv\Scripts\python.exe app.py
```

> 开发机上的 `run.bat` 默认找 `..\venv312\Scripts\pythonw.exe`，找不到会退回系统 `pythonw`，所以本地目录结构不必和别人一致。

## 提交前必须满足

1. `tests/smoke_test.py` 与 `tests/gui_smoke.py` 全绿（GUI 测试会真的开一个窗口，几秒后自己关）。
2. 不新增运行时依赖。要加，先在 issue 里说清为什么 Pillow + 标准库做不到。
3. `.bat` 文件保持**纯 ASCII**。cmd.exe 按 OEM 代码页读 `.bat`，写中文注释会在部分系统上把后面的 `set` 语句拆坏。
4. 所有 `print` 到控制台的内容不要依赖 emoji（Windows 控制台默认 GBK，会 `UnicodeEncodeError`）。测试脚本里已经统一 `reconfigure(errors="replace")`。
5. 不要在测试里碰真实的 `.gst_config.json`：用 `os.environ["GST_CONFIG"]` 指向临时文件（见 `tests/gui_smoke.py` 开头）。

## 代码结构约定

| 位置 | 放什么 |
| --- | --- |
| `app.py` | 只放界面、交互、线程调度；能被复用的逻辑一律下沉到 `gstree/` |
| `gstree/model.py` | 扫描与数据模型，**不 import tkinter** |
| `gstree/icons.py` | 纯 Pillow 绘制，不 import tkinter（勾选框/图标都由这里出图） |
| `gstree/render_png.py` | 导出渲染，必须能在无界面环境下跑（测试就是这么用的） |
| `gstree/treeview.py` | 画布控件，虚拟化绘制，只画可视行 |
| `tests/` | 每个 bug 修完补一条断言 |

样式与配色统一走 `gstree/theme.py` 的 `Palette`，不要在控件里写死颜色——浅色/深色两套主题都要能看。

## PR 流程

1. Fork → 建分支（`fix/wheel-speed`、`feat/xxx`）。
2. 一个 PR 只做一件事，描述里写清"为什么"，附一张改动前后的截图（界面类改动）。
3. 提交信息用 `类型: 摘要`，类型取 `feat` / `fix` / `docs` / `refactor` / `test` / `chore`，例如：
   - `fix: 滚轮每次只滚 3 像素`
   - `feat: 导出 PNG 支持 4x 倍率`

## Issue

提 bug 时请附：Windows 版本、Python 版本、`pip list | findstr /i pillow`、复现路径（可脱敏），以及界面截图。涉及导出的问题请附导出的 txt/png。
