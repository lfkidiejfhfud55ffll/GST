"""文件类型图标（纯 Pillow 绘制，Tk 与 PNG 导出共用同一套像素）。

图标统一为"圆角色块 + 白色象形符号"，色块颜色区分类别，符号区分具体形态；
文件夹使用琥珀色文件夹剪影。所有图形都在 4 倍超采样后降采样，边缘平滑。
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw

SS = 4  # 超采样倍数

#: 类别 -> 色块颜色
COLORS: dict[str, str] = {
    "folder": "#F0A32B",
    "text": "#64748B",
    "code": "#4F46E5",
    "web": "#0284C7",
    "config": "#7C3AED",
    "image": "#059669",
    "audio": "#DB2777",
    "video": "#E11D48",
    "archive": "#B45309",
    "pdf": "#DC2626",
    "doc": "#2563EB",
    "sheet": "#15803D",
    "slides": "#EA580C",
    "exec": "#0F766E",
    "font": "#A16207",
    "db": "#0891B2",
    "lock": "#475569",
    "model3d": "#9333EA",
    "disk": "#0369A1",
    "unknown": "#94A3B8",
}

#: 扩展名 -> 类别
EXT_CATEGORY: dict[str, str] = {
    # 文本
    **{e: "text" for e in ("txt", "log", "md", "markdown", "rst", "text", "nfo", "srt", "ass", "vtt", "tex", "me", "1st")},
    # 代码
    **{
        e: "code"
        for e in (
            "py", "pyw", "pyi", "pyx", "java", "c", "h", "cpp", "cc", "cxx", "c++", "hpp", "hxx",
            "cs", "js", "mjs", "cjs", "ts", "tsx", "jsx", "go", "rs", "rb", "php", "swift", "kt",
            "kts", "scala", "lua", "pl", "pm", "sh", "bash", "zsh", "fish", "ps1", "psm1", "bat",
            "cmd", "sql", "r", "m", "mm", "dart", "ex", "exs", "erl", "hrl", "hs", "lhs", "clj",
            "cljs", "cljc", "vb", "vbs", "asm", "s", "f", "f90", "f95", "for", "pas", "groovy",
            "gradle", "jl", "nim", "zig", "v", "sv", "vhd", "sol", "cu", "cuh", "ipynb", "rkt",
            "lisp", "el", "scm", "tcl", "awk", "sed", "ahk", "nsh", "make", "mk", "cmake",
        )
    },
    # 网页
    **{e: "web" for e in ("html", "htm", "xhtml", "shtml", "css", "scss", "sass", "less", "vue", "svelte", "astro", "hbs", "ejs", "pug", "jade", "styl")},
    # 配置
    **{
        e: "config"
        for e in (
            "json", "json5", "jsonc", "yaml", "yml", "toml", "ini", "cfg", "conf", "config",
            "properties", "env", "xml", "xsl", "xslt", "plist", "lock", "service", "desktop",
            "reg", "editorconfig", "gitignore", "gitattributes", "dockerignore", "npmrc",
            "babelrc", "eslintrc", "prettierrc", "flake8", "coveragerc", "htaccess",
        )
    },
    # 图片
    **{
        e: "image"
        for e in (
            "png", "jpg", "jpeg", "jpe", "jfif", "gif", "bmp", "webp", "tif", "tiff", "ico",
            "svg", "svgz", "psd", "ai", "xcf", "raw", "cr2", "cr3", "nef", "arw", "dng", "heic",
            "heif", "avif", "dds", "tga", "exr", "hdr", "ppm", "pgm", "pbm", "emf", "wmf",
        )
    },
    # 音频
    **{e: "audio" for e in ("mp3", "wav", "flac", "aac", "ogg", "oga", "m4a", "wma", "opus", "mid", "midi", "aiff", "aif", "ape", "amr", "ac3")},
    # 视频
    **{e: "video" for e in ("mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "m2ts", "mts", "rmvb", "rm", "3gp", "vob", "ogv")},
    # 压缩包
    **{e: "archive" for e in ("zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "tbz", "xz", "txz", "zst", "cab", "lz", "lzma", "jar", "war", "ear", "apk", "aar", "deb", "rpm", "crx", "xpi")},
    # PDF
    "pdf": "pdf",
    # 文档
    **{e: "doc" for e in ("doc", "docx", "docm", "odt", "rtf", "pages", "wps", "epub", "mobi", "azw3", "djvu")},
    # 表格
    **{e: "sheet" for e in ("xls", "xlsx", "xlsm", "xlsb", "ods", "csv", "tsv", "numbers", "parquet")},
    # 演示
    **{e: "slides" for e in ("ppt", "pptx", "pptm", "odp", "key")},
    # 可执行 / 二进制
    **{e: "exec" for e in ("exe", "msi", "msix", "dll", "so", "dylib", "bin", "app", "com", "sys", "ocx", "class", "pyc", "pyo", "elf", "out", "wasm", "node", "scr", "cpl", "drv")},
    # 字体
    **{e: "font" for e in ("ttf", "otf", "woff", "woff2", "eot", "fon", "ttc", "pfb", "pfm")},
    # 数据库
    **{e: "db" for e in ("db", "sqlite", "sqlite3", "mdb", "accdb", "dbf", "mdf", "ldf", "frm", "ibd", "realm")},
    # 密钥 / 证书
    **{e: "lock" for e in ("pem", "key", "p12", "pfx", "crt", "cer", "csr", "pub", "asc", "gpg", "pgp", "kdbx", "keystore", "jks", "ovpn")},
    # 三维 / 模型
    **{e: "model3d" for e in ("obj", "fbx", "dae", "stl", "blend", "blend1", "3ds", "max", "gltf", "glb", "ply", "usd", "usda", "usdc", "usdz", "abc", "c4d", "ma", "mb", "skp", "step", "stp", "iges", "igs", "3mf", "vox", "fbx7", "ztl", "spp")},
    # 镜像 / 磁盘
    **{e: "disk" for e in ("iso", "img", "vhd", "vhdx", "vmdk", "qcow2", "dmg", "vdi", "wim", "esd")},
}

#: 无扩展名文件的特殊名字
NAME_CATEGORY: dict[str, str] = {
    "makefile": "code",
    "gnumakefile": "code",
    "cmakelists.txt": "code",
    "dockerfile": "config",
    "containerfile": "config",
    "vagrantfile": "config",
    "procfile": "config",
    "gemfile": "config",
    "rakefile": "code",
    "brewfile": "config",
    "jenkinsfile": "code",
    "license": "text",
    "licence": "text",
    "readme": "text",
    "changelog": "text",
    "authors": "text",
    "notice": "text",
    "todo": "text",
    ".gitignore": "config",
    ".gitattributes": "config",
    ".gitmodules": "config",
    ".env": "config",
    ".env.local": "config",
    ".dockerignore": "config",
    ".editorconfig": "config",
    ".npmrc": "config",
    ".prettierrc": "config",
    ".eslintrc": "config",
    ".babelrc": "config",
    ".bashrc": "config",
    ".zshrc": "config",
    ".profile": "config",
    ".vimrc": "config",
    ".htaccess": "config",
}


def category_for_name(name: str, is_dir: bool, ext: str | None = None) -> str:
    """根据文件名判断图标类别。"""
    if is_dir:
        return "folder"
    ext = (ext if ext is not None else "").lower().lstrip(".")
    if ext and ext in EXT_CATEGORY:
        return EXT_CATEGORY[ext]
    low = name.lower()
    if low in NAME_CATEGORY:
        return NAME_CATEGORY[low]
    if ext:
        # 未收录的扩展名：退回通用文件
        return "unknown"
    return "text"


def category_for(node) -> str:
    return category_for_name(node.name, node.kind == "dir", node.ext)


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _mix(color: str, other: str, t: float) -> tuple[int, int, int, int]:
    r1, g1, b1 = _hex(color)
    r2, g2, b2 = _hex(other)
    return (
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
        255,
    )


# ------------------------------------------------------------------ 图形
def _draw_folder(d: ImageDraw.ImageDraw, N: int) -> None:
    base = COLORS["folder"]
    tab = _mix(base, "#000000", 0.10)
    inner = _mix(base, "#FFFFFF", 0.28)
    r = N * 0.055
    d.rounded_rectangle([0.05 * N, 0.20 * N, 0.46 * N, 0.42 * N], radius=r, fill=tab)
    d.rounded_rectangle([0.04 * N, 0.33 * N, 0.96 * N, 0.84 * N], radius=r * 1.5, fill=base)
    d.rounded_rectangle([0.13 * N, 0.42 * N, 0.87 * N, 0.76 * N], radius=r, fill=inner)


def _draw_badge(d: ImageDraw.ImageDraw, N: int, color: str) -> None:
    inset = N * 0.035
    d.rounded_rectangle(
        [inset, inset, N - inset, N - inset],
        radius=N * 0.24,
        fill=color,
    )


def _g_text(d, N, w, c, badge):
    for y, x1 in ((0.34, 0.68), (0.50, 0.76), (0.66, 0.60)):
        d.rounded_rectangle(
            [0.26 * N, y * N - w * 0.5, x1 * N, y * N + w * 0.5], radius=w * 0.5, fill=c
        )


def _g_code(d, N, w, c, badge):
    # 左右尖括号 + 中间斜杠，构成 "</>" 的抽象形态
    d.line([(0.38 * N, 0.30 * N), (0.22 * N, 0.50 * N), (0.38 * N, 0.70 * N)], fill=c, width=w, joint="curve")
    d.line([(0.62 * N, 0.30 * N), (0.78 * N, 0.50 * N), (0.62 * N, 0.70 * N)], fill=c, width=w, joint="curve")
    d.line([(0.565 * N, 0.27 * N), (0.435 * N, 0.73 * N)], fill=c, width=max(2, int(w * 0.85)))


def _g_web(d, N, w, c, badge):
    d.ellipse([0.24 * N, 0.24 * N, 0.76 * N, 0.76 * N], outline=c, width=w)
    d.line([(0.26 * N, 0.50 * N), (0.74 * N, 0.50 * N)], fill=c, width=w)
    d.ellipse([0.37 * N, 0.24 * N, 0.63 * N, 0.76 * N], outline=c, width=w)


def _g_config(d, N, w, c, badge):
    knob = w * 1.15
    for y, kx in ((0.32, 0.63), (0.50, 0.37), (0.68, 0.57)):
        d.line([(0.24 * N, y * N), (0.76 * N, y * N)], fill=c, width=max(1, int(w * 0.8)))
        d.ellipse([kx * N - knob, y * N - knob, kx * N + knob, y * N + knob], fill=c)


def _g_image(d, N, w, c, badge):
    d.ellipse([0.25 * N, 0.25 * N, 0.41 * N, 0.41 * N], fill=c)
    d.polygon(
        [(0.20 * N, 0.78 * N), (0.43 * N, 0.46 * N), (0.55 * N, 0.60 * N),
         (0.64 * N, 0.52 * N), (0.80 * N, 0.78 * N)],
        fill=c,
    )


def _g_audio(d, N, w, c, badge):
    d.ellipse([0.24 * N, 0.58 * N, 0.44 * N, 0.76 * N], fill=c)
    d.line([(0.43 * N, 0.67 * N), (0.43 * N, 0.26 * N)], fill=c, width=w)
    d.polygon([(0.43 * N, 0.26 * N), (0.74 * N, 0.33 * N), (0.74 * N, 0.45 * N), (0.43 * N, 0.38 * N)], fill=c)


def _g_video(d, N, w, c, badge):
    d.polygon([(0.34 * N, 0.26 * N), (0.76 * N, 0.50 * N), (0.34 * N, 0.74 * N)], fill=c)


def _g_archive(d, N, w, c, badge):
    d.rounded_rectangle([0.24 * N, 0.20 * N, 0.76 * N, 0.80 * N], radius=0.07 * N, outline=c, width=w)
    for y in (0.34, 0.47, 0.60):
        d.rounded_rectangle(
            [0.44 * N, y * N - w * 0.75, 0.56 * N, y * N + w * 0.75], radius=w * 0.75, fill=c
        )


def _g_page(d, N, w, c, badge):
    d.polygon(
        [(0.28 * N, 0.18 * N), (0.55 * N, 0.18 * N), (0.74 * N, 0.37 * N),
         (0.74 * N, 0.82 * N), (0.28 * N, 0.82 * N)],
        fill=c,
    )
    d.polygon([(0.55 * N, 0.18 * N), (0.74 * N, 0.37 * N), (0.55 * N, 0.37 * N)], fill=badge)
    for y, x1 in ((0.50, 0.66), (0.62, 0.68), (0.74, 0.54)):
        d.rounded_rectangle(
            [0.36 * N, y * N - w * 0.5, x1 * N, y * N + w * 0.5], radius=w * 0.5, fill=badge
        )


def _g_sheet(d, N, w, c, badge):
    d.rounded_rectangle([0.24 * N, 0.24 * N, 0.76 * N, 0.76 * N], radius=0.06 * N, outline=c, width=w)
    d.line([(0.26 * N, 0.42 * N), (0.74 * N, 0.42 * N)], fill=c, width=w)
    d.line([(0.50 * N, 0.42 * N), (0.50 * N, 0.74 * N)], fill=c, width=w)


def _g_slides(d, N, w, c, badge):
    for x, h in ((0.26, 0.22), (0.43, 0.40), (0.60, 0.30)):
        d.rounded_rectangle(
            [x * N, (0.76 - h) * N, (x + 0.13) * N, 0.76 * N], radius=0.02 * N, fill=c
        )


def _g_exec(d, N, w, c, badge):
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        x = 0.27 * N + dx * 0.25 * N
        y = 0.27 * N + dy * 0.25 * N
        d.rounded_rectangle([x, y, x + 0.19 * N, y + 0.19 * N], radius=0.04 * N, fill=c)


def _g_font(d, N, w, c, badge):
    d.line([(0.28 * N, 0.76 * N), (0.50 * N, 0.24 * N), (0.72 * N, 0.76 * N)], fill=c, width=w, joint="curve")
    d.line([(0.37 * N, 0.58 * N), (0.63 * N, 0.58 * N)], fill=c, width=w)


def _g_db(d, N, w, c, badge):
    d.ellipse([0.25 * N, 0.20 * N, 0.75 * N, 0.34 * N], fill=c)
    d.rectangle([0.25 * N, 0.26 * N, 0.75 * N, 0.68 * N], fill=c)
    d.ellipse([0.25 * N, 0.56 * N, 0.75 * N, 0.70 * N], fill=c)
    for y in (0.42, 0.54):
        d.line([(0.28 * N, y * N), (0.72 * N, y * N)], fill=badge, width=max(1, int(w * 0.7)))


def _g_lock(d, N, w, c, badge):
    d.rounded_rectangle([0.27 * N, 0.44 * N, 0.73 * N, 0.79 * N], radius=0.06 * N, fill=c)
    d.arc([0.35 * N, 0.18 * N, 0.65 * N, 0.56 * N], 180, 360, fill=c, width=w)
    d.ellipse([0.455 * N, 0.54 * N, 0.545 * N, 0.63 * N], fill=badge)


def _g_cube(d, N, w, c, badge):
    pts = [(0.50, 0.18), (0.80, 0.35), (0.80, 0.66), (0.50, 0.83), (0.20, 0.66), (0.20, 0.35)]
    d.line([(x * N, y * N) for x, y in pts] + [(0.50 * N, 0.18 * N)], fill=c, width=w, joint="curve")
    d.line([(0.20 * N, 0.35 * N), (0.50 * N, 0.50 * N), (0.80 * N, 0.35 * N)], fill=c, width=w, joint="curve")
    d.line([(0.50 * N, 0.50 * N), (0.50 * N, 0.83 * N)], fill=c, width=w)


def _g_disk(d, N, w, c, badge):
    d.ellipse([0.20 * N, 0.20 * N, 0.80 * N, 0.80 * N], outline=c, width=w)
    d.ellipse([0.42 * N, 0.42 * N, 0.58 * N, 0.58 * N], fill=c)


def _g_unknown(d, N, w, c, badge):
    for x in (0.34, 0.50, 0.66):
        d.ellipse([x * N - w * 0.7, 0.50 * N - w * 0.7, x * N + w * 0.7, 0.50 * N + w * 0.7], fill=c)


_GLYPHS = {
    "text": _g_text,
    "code": _g_code,
    "web": _g_web,
    "config": _g_config,
    "image": _g_image,
    "audio": _g_audio,
    "video": _g_video,
    "archive": _g_archive,
    "pdf": _g_page,
    "doc": _g_page,
    "sheet": _g_sheet,
    "slides": _g_slides,
    "exec": _g_exec,
    "font": _g_font,
    "db": _g_db,
    "lock": _g_lock,
    "model3d": _g_cube,
    "disk": _g_disk,
    "unknown": _g_unknown,
}


@lru_cache(maxsize=512)
def get_icon(category: str, size: int) -> Image.Image:
    """返回指定类别、指定像素尺寸的 RGBA 图标（带缓存）。"""
    size = max(8, int(size))
    N = size * SS
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if category == "folder":
        _draw_folder(d, N)
    else:
        color = COLORS.get(category, COLORS["unknown"])
        _draw_badge(d, N, color)
        glyph = _GLYPHS.get(category, _g_unknown)
        glyph(d, N, max(2, int(round(N * 0.082))), "#FFFFFF", color)
    return img.resize((size, size), Image.LANCZOS)


def icon_for_node(node, size: int) -> Image.Image:
    return get_icon(category_for(node), size)


def check_mark(size: int, checked: bool, pal, hover: bool = False, disabled: bool = False) -> Image.Image:
    """复选框指示器：圆角方块 + 勾。

    pal 是 gstree.theme.Palette；只用到 accent / panel_alt / border / text_faint 等字段，
    故意用鸭子类型，避免 icons 反向依赖 theme。
    """
    size = max(10, int(size))
    N = size * 4
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, int(N * 0.06))
    box = [pad, pad, N - 1 - pad, N - 1 - pad]
    radius = int(N * 0.26)
    stroke = max(2, int(round(N * 0.085)))

    if disabled:
        fill = pal.panel_alt
        outline = pal.border_soft
    elif checked:
        fill = pal.accent if not hover else pal.accent_hover
        outline = fill
    else:
        fill = pal.chip_bg if hover else pal.panel_alt
        outline = pal.text_faint if hover else pal.border

    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=stroke)

    if checked:
        tick = "#FFFFFF" if not disabled else pal.text_faint
        pts = [
            (N * 0.28, N * 0.52),
            (N * 0.44, N * 0.68),
            (N * 0.73, N * 0.34),
        ]
        d.line(pts, fill=tick, width=stroke, joint="curve")
        # 线段端点补圆，避免斜线端头被切平
        for px, py in (pts[0], pts[-1]):
            d.ellipse(
                [px - stroke / 2, py - stroke / 2, px + stroke / 2, py + stroke / 2],
                fill=tick,
            )
    return img.resize((size, size), Image.LANCZOS)
