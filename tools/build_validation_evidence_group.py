from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "data" / "chen_clan_academy" / "evaluation" / "assets"
SOURCE_DIR = ASSET_DIR / "evidence_screenshots"

W, H = 3840, 2160
BG = "#F4F0E8"
CARD = "#FFFCF7"
INK = "#203A5F"
MUTED = "#66758B"
BROWN = "#6F342A"
CORAL = "#F05A54"
GOLD = "#E4A23F"
GREEN = "#5C9B7A"
PURPLE = "#7256A8"
LINE = "#D9CBB8"
GRAPH_BG = "#101522"

FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def rounded_card(canvas: Image.Image, box: tuple[int, int, int, int], radius: int = 36, fill: str = CARD) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x0 + 12, y0 + 18, x1 + 12, y1 + 18), radius=radius, fill=(65, 44, 30, 32))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=LINE, width=3)


def cover_crop(image: Image.Image, target_size: tuple[int, int], focus_y: float = 0.5) -> Image.Image:
    tw, th = target_size
    scale = max(tw / image.width, th / image.height)
    rw, rh = int(image.width * scale), int(image.height * scale)
    resized = image.resize((rw, rh), Image.Resampling.LANCZOS)
    left = max(0, (rw - tw) // 2)
    top = int(max(0, rh - th) * focus_y)
    return resized.crop((left, top, left + tw, top + th))


def paste_screenshot(
    canvas: Image.Image,
    source: str,
    box: tuple[int, int, int, int],
    *,
    crop: tuple[int, int, int, int] | None = None,
    focus_y: float = 0.5,
    mode: str = "cover",
    radius: int = 22,
    matte: str = "#ECE7DE",
) -> None:
    image = Image.open(SOURCE_DIR / source).convert("RGB")
    if crop is not None:
        image = image.crop(crop)
    x0, y0, x1, y1 = box
    target = (x1 - x0, y1 - y0)
    if mode == "contain":
        fitted = Image.new("RGB", target, matte)
        scale = min(target[0] / image.width, target[1] / image.height)
        contained = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        fitted.paste(contained, ((target[0] - contained.width) // 2, (target[1] - contained.height) // 2))
    else:
        fitted = cover_crop(image, target, focus_y=focus_y)
    mask = Image.new("L", fitted.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, fitted.width, fitted.height), radius=radius, fill=255)
    canvas.paste(fitted, (x0, y0), mask)
    ImageDraw.Draw(canvas).rounded_rectangle(box, radius=radius, outline="#CFC5B8", width=3)


def pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: str, fg: str = "white", size: int = 34) -> int:
    x, y = xy
    f = font(size, True)
    bbox = draw.textbbox((0, 0), text, font=f)
    width = bbox[2] - bbox[0] + 58
    height = size + 31
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height // 2, fill=fill)
    draw.text((x + 29, y + 8), text, font=f, fill=fg)
    return width


def header(canvas: Image.Image, title: str, subtitle: str, section: str) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, 270), fill=BROWN)
    draw.rounded_rectangle((120, 72, 220, 172), radius=26, fill=CORAL)
    draw.text((170, 122), "证", font=font(56, True), fill="white", anchor="mm")
    draw.text((260, 54), title, font=font(70, True), fill="white")
    draw.text((264, 150), subtitle, font=font(33), fill="#F4DED7")
    width = pill(draw, (W - 820, 88), section, "#F6E8D1", BROWN)
    pill(draw, (W - 820 + width + 24, 88), "真实运行截图", CORAL)


def panel_title(draw: ImageDraw.ImageDraw, x: int, y: int, step: str, title: str, desc: str, color: str) -> None:
    draw.rounded_rectangle((x, y, x + 78, y + 78), radius=22, fill=color)
    draw.text((x + 39, y + 39), step, font=font(35, True), fill="white", anchor="mm")
    draw.text((x + 105, y - 2), title, font=font(45, True), fill=INK)
    draw.text((x + 105, y + 52), desc, font=font(28), fill=MUTED)


def metric_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str, color: str) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=28, fill="#F1E7D9", outline="#DDCFBF", width=2)
    draw.rounded_rectangle((x0 + 28, y0 + 30, x0 + 48, y1 - 30), radius=10, fill=color)
    draw.text((x0 + 80, y0 + 28), label, font=font(28), fill=MUTED)
    draw.text((x0 + 80, y0 + 82), value, font=font(39, True), fill=INK)


def save_versions(canvas: Image.Image, stem: str) -> None:
    rgb = canvas.convert("RGB")
    rgb.save(ASSET_DIR / f"{stem}-4k.png", quality=95)
    rgb.resize((1920, 1080), Image.Resampling.LANCZOS).save(ASSET_DIR / f"{stem}-1080p.png", quality=95)


def build_overview() -> None:
    canvas = Image.new("RGBA", (W, H), BG)
    header(
        canvas,
        "验证与可信运行证据",
        "可观测执行图 · Active 审计 · 定向验证 · 完整回归",
        "端到端证据链",
    )
    draw = ImageDraw.Draw(canvas)
    boxes = [
        (100, 330, 2390, 1090),
        (2490, 330, 3740, 1090),
        (100, 1150, 1870, 2040),
        (1970, 1150, 3740, 2040),
    ]
    for box in boxes:
        rounded_card(canvas, box)

    panel_title(draw, 150, 380, "1", "可观测执行图", "统一入口、路由、生成、校验、回退与提交节点", PURPLE)
    paste_screenshot(
        canvas,
        "04-graph-overview.png",
        (150, 510, 2340, 1030),
        mode="contain",
        matte=GRAPH_BG,
    )

    panel_title(draw, 2540, 380, "2", "Active 审计", "古风书生点位讲解实际接管", GREEN)
    paste_screenshot(
        canvas,
        "01-langsmith-active-audit.png",
        (2540, 510, 3690, 1030),
        crop=(575, 245, 1393, 930),
        focus_y=0.48,
    )
    pill(draw, (2570, 930), "accepted · takeover=true", GREEN, size=27)

    panel_title(draw, 150, 1200, "3", "定向验证", "Active接管、白名单、状态隔离、安全回退", CORAL)
    paste_screenshot(
        canvas,
        "02-targeted-tests-11.png",
        (150, 1330, 1820, 1965),
        crop=(210, 40, 1394, 936),
        focus_y=0.83,
    )
    pill(draw, (1350, 1875), "11 / 11  OK", CORAL, size=30)

    panel_title(draw, 2020, 1200, "4", "完整回归", "覆盖导览、知识、状态、安全与失败边界", GOLD)
    paste_screenshot(
        canvas,
        "03-full-regression-1118.png",
        (2020, 1330, 3690, 1965),
        crop=(210, 40, 1403, 949),
        focus_y=0.88,
    )
    pill(draw, (3150, 1875), "1118 / 1118  OK", GOLD, size=30)
    save_versions(canvas, "08-validation-evidence-overview")


def build_active_audit() -> None:
    canvas = Image.new("RGBA", (W, H), BG)
    header(
        canvas,
        "LangSmith Active 审计｜古风书生主线",
        "保留真实 Thread 与审计字段，展示校验、接管与回退状态",
        "Active 接管证据",
    )
    draw = ImageDraw.Draw(canvas)
    rounded_card(canvas, (100, 340, 2630, 2020))
    rounded_card(canvas, (2730, 340, 3740, 2020))
    paste_screenshot(canvas, "01-langsmith-active-audit.png", (155, 395, 2575, 1965), mode="contain", matte="#F4F6FA")

    draw.text((2810, 430), "关键审计字段", font=font(55, True), fill=INK)
    draw.text((2815, 515), "截图中可直接核对", font=font(29), fill=MUTED)
    metrics = [
        ("style_id", "ancient_scholar", PURPLE),
        ("validation_status", "accepted", GREEN),
        ("active_takeover", "true", CORAL),
        ("fallback_used", "false", GOLD),
        ("model_called", "true", INK),
    ]
    y = 620
    for label, value, color in metrics:
        metric_card(draw, (2810, y, 3660, y + 210), label, value, color)
        y += 240
    draw.rounded_rectangle((2810, 1840, 3660, 1950), radius=28, fill=BROWN)
    draw.text(
        (3235, 1895),
        "本图不包含问答 Shadow 审计",
        font=font(29, True),
        fill="white",
        anchor="mm",
    )
    save_versions(canvas, "08a-active-audit-evidence")


def build_graph_detail() -> None:
    canvas = Image.new("RGBA", (W, H), BG)
    header(
        canvas,
        "LangGraph 执行图｜可观测与可回退",
        "总览图与两个关键区域均来自真实运行环境",
        "Graph 可观测性",
    )
    draw = ImageDraw.Draw(canvas)
    rounded_card(canvas, (90, 330, 3750, 1190), fill="#151A27")
    paste_screenshot(canvas, "04-graph-overview.png", (130, 370, 3710, 1150), mode="contain", matte=GRAPH_BG)
    pill(draw, (155, 395), "执行图总览", PURPLE)

    rounded_card(canvas, (90, 1250, 1870, 2030), fill="#151A27")
    paste_screenshot(canvas, "05-graph-entry-control.png", (130, 1290, 1830, 1990), mode="contain", matte=GRAPH_BG)
    pill(draw, (155, 1315), "入口、语义与确定性路由", GREEN, size=30)

    rounded_card(canvas, (1970, 1250, 3750, 2030), fill="#151A27")
    paste_screenshot(canvas, "06-graph-narration-control.png", (2010, 1290, 3710, 1990), mode="contain", matte=GRAPH_BG)
    pill(draw, (2035, 1315), "生成、校验、回退与提交", CORAL, size=30)
    save_versions(canvas, "08b-graph-runtime-evidence")


def build_test_detail() -> None:
    canvas = Image.new("RGBA", (W, H), BG)
    header(
        canvas,
        "自动化验证｜定向测试与完整回归",
        "保留测试名称、执行数量、耗时与最终 OK 结果",
        "真实终端证据",
    )
    draw = ImageDraw.Draw(canvas)
    rounded_card(canvas, (100, 340, 1870, 2020))
    rounded_card(canvas, (1970, 340, 3740, 2020))
    panel_title(draw, 155, 400, "A", "定向测试", "角色Active、白名单、状态隔离与安全回退", CORAL)
    panel_title(draw, 2025, 400, "B", "完整回归", "项目全部 unittest 自动发现与执行", GOLD)
    paste_screenshot(canvas, "02-targeted-tests-11.png", (155, 540, 1815, 1860), mode="contain", matte="#15171C")
    paste_screenshot(canvas, "03-full-regression-1118.png", (2025, 540, 3685, 1860), mode="contain", matte="#15171C")
    pill(draw, (585, 1900), "11 项全部通过 · 0 failure · 0 error", CORAL, size=31)
    pill(draw, (2455, 1900), "1118 项全部通过 · 0 failure · 0 error", GOLD, size=31)
    save_versions(canvas, "08c-automated-test-evidence")


if __name__ == "__main__":
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    build_overview()
    build_active_audit()
    build_graph_detail()
    build_test_detail()
    print("Generated validation evidence assets in", ASSET_DIR)
