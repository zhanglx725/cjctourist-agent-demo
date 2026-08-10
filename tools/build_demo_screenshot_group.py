from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "data" / "chen_clan_academy" / "evaluation" / "assets"
SOURCE_DIR = ASSET_DIR / "demo_screenshots"

W, H = 3840, 2160
BG = "#F4F0E8"
CARD = "#FFFCF7"
INK = "#203A5F"
MUTED = "#66758B"
BROWN = "#6F342A"
CORAL = "#F05A54"
GOLD = "#E4A23F"
GREEN = "#5C9B7A"
LINE = "#D9CBB8"

FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def rounded_card(canvas: Image.Image, box: tuple[int, int, int, int], radius: int = 36) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x0 + 12, y0 + 18, x1 + 12, y1 + 18), radius=radius, fill=(65, 44, 30, 32))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=radius, fill=CARD, outline=LINE, width=3)


def cover_crop(image: Image.Image, target_size: tuple[int, int], focus_y: float = 0.5) -> Image.Image:
    tw, th = target_size
    scale = max(tw / image.width, th / image.height)
    rw, rh = int(image.width * scale), int(image.height * scale)
    resized = image.resize((rw, rh), Image.Resampling.LANCZOS)
    left = max(0, (rw - tw) // 2)
    max_top = max(0, rh - th)
    top = int(max_top * focus_y)
    return resized.crop((left, top, left + tw, top + th))


def paste_screenshot(
    canvas: Image.Image,
    source: str,
    box: tuple[int, int, int, int],
    *,
    crop: tuple[int, int, int, int] | None = None,
    focus_y: float = 0.5,
    radius: int = 22,
    mode: str = "cover",
) -> None:
    image = Image.open(SOURCE_DIR / source).convert("RGB")
    if crop is not None:
        image = image.crop(crop)
    x0, y0, x1, y1 = box
    target_size = (x1 - x0, y1 - y0)
    if mode == "contain":
        fitted = Image.new("RGB", target_size, "#F7F1E7")
        scale = min(target_size[0] / image.width, target_size[1] / image.height)
        contained = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        px = (target_size[0] - contained.width) // 2
        py = (target_size[1] - contained.height) // 2
        fitted.paste(contained, (px, py))
    else:
        fitted = cover_crop(image, target_size, focus_y=focus_y)
    mask = Image.new("L", fitted.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, fitted.width, fitted.height), radius=radius, fill=255)
    canvas.paste(fitted, (x0, y0), mask)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=radius, outline="#CFC5B8", width=3)


def pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: str, fg: str = "white") -> int:
    x, y = xy
    f = font(34, True)
    bbox = draw.textbbox((0, 0), text, font=f)
    width = bbox[2] - bbox[0] + 58
    draw.rounded_rectangle((x, y, x + width, y + 64), radius=32, fill=fill)
    draw.text((x + 29, y + 10), text, font=f, fill=fg)
    return width


def header(canvas: Image.Image, title: str, subtitle: str, section: str) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, 270), fill=BROWN)
    draw.rounded_rectangle((120, 72, 220, 172), radius=26, fill=CORAL)
    draw.text((150, 75), "祠", font=font(62, True), fill="white", anchor="ma")
    draw.text((260, 54), title, font=font(72, True), fill="white")
    draw.text((264, 150), subtitle, font=font(34), fill="#F4DED7")
    width = pill(draw, (W - 780, 88), section, "#F6E8D1", BROWN)
    pill(draw, (W - 780 + width + 24, 88), "真实环境录制", CORAL)


def panel_title(draw: ImageDraw.ImageDraw, x: int, y: int, step: str, title: str, desc: str) -> None:
    draw.rounded_rectangle((x, y, x + 78, y + 78), radius=22, fill=CORAL)
    draw.text((x + 39, y + 39), step, font=font(36, True), fill="white", anchor="mm")
    draw.text((x + 105, y - 2), title, font=font(46, True), fill=INK)
    draw.text((x + 105, y + 52), desc, font=font(29), fill=MUTED)


def save_versions(canvas: Image.Image, stem: str) -> None:
    rgb = canvas.convert("RGB")
    rgb.save(ASSET_DIR / f"{stem}-4k.png", quality=95)
    rgb.resize((1920, 1080), Image.Resampling.LANCZOS).save(
        ASSET_DIR / f"{stem}-1080p.png", quality=95
    )


def build_overview() -> None:
    canvas = Image.new("RGBA", (W, H), BG)
    header(
        canvas,
        "祠语智游｜比赛主线 Demo",
        "多角色沉浸式非遗智能导游 · 从偏好到随行服务的完整体验",
        "古风书生主线",
    )
    draw = ImageDraw.Draw(canvas)

    boxes = [
        (100, 330, 1870, 1105),
        (1970, 330, 3740, 1105),
        (100, 1160, 1870, 2040),
        (1970, 1160, 3740, 2040),
    ]
    for box in boxes:
        rounded_card(canvas, box)

    panel_title(draw, 150, 380, "1", "偏好采集", "时间、兴趣、讲解节奏与角色风格")
    paste_screenshot(canvas, "01-preferences.png", (150, 500, 1820, 1045), crop=(0, 135, 2878, 1911), focus_y=0.28)

    panel_title(draw, 2020, 380, "2", "路线规划", "时间预算、审核点位、步行与返程提示")
    paste_screenshot(canvas, "02-route-plan.png", (2020, 500, 3690, 1045), crop=(0, 120, 2840, 1854), focus_y=0.38)

    panel_title(draw, 150, 1210, "3", "到点讲解", "工艺背景、观察对象、故事与安全边界")
    paste_screenshot(canvas, "03-stop-guidance-a.png", (150, 1330, 1820, 1980), crop=(0, 120, 2834, 1895), focus_y=0.37)

    panel_title(draw, 2020, 1210, "4", "随行问答", "工艺追问、学术研究、开放时间与周边服务")
    qa_tiles = [
        ("05-qa-craft.png", "工艺特点", CORAL, (410, 330, 2420, 1260)),
        ("06-qa-followup.png", "继续追问", GOLD, (300, 150, 1390, 790)),
        ("08-qa-hours.png", "闭馆时间", GREEN, (350, 485, 1370, 820)),
        ("09-qa-nearby.png", "周边推荐", INK, (360, 320, 1400, 760)),
    ]
    tile_boxes = [
        (2020, 1335, 2830, 1625),
        (2880, 1335, 3690, 1625),
        (2020, 1680, 2830, 1970),
        (2880, 1680, 3690, 1970),
    ]
    for (source, label, color, crop), box in zip(qa_tiles, tile_boxes):
        paste_screenshot(canvas, source, box, crop=crop, focus_y=0.42, radius=18)
        x0, y0, _, _ = box
        pill(draw, (x0 + 18, y0 + 18), label, color)

    draw.rounded_rectangle((1180, 2070, 2660, 2135), radius=32, fill="#E8DED0")
    draw.text(
        (1920, 2102),
        "路线状态受控 · 问答不改写行程进度 · 异常时可回退",
        font=font(30, True),
        fill=BROWN,
        anchor="mm",
    )
    save_versions(canvas, "07-demo-mainline-overview")


def build_qa_evidence() -> None:
    canvas = Image.new("RGBA", (W, H), BG)
    header(
        canvas,
        "随行问答｜同一导览上下文中的连续服务",
        "从工艺特点到进一步研究，同时覆盖参观服务与周边信息",
        "真实问答截图",
    )
    draw = ImageDraw.Draw(canvas)

    cards = [
        (100, 330, 1870, 1030, "05-qa-craft.png", "01  工艺特点", "灰塑定义、材料工艺与当前点审核实例", (360, 300, 2430, 1390), CORAL),
        (1970, 330, 3740, 1030, "06-qa-followup.png", "02  继续追问", "在原问题上展开制作、地域与文化表达", (280, 130, 1400, 820), GOLD),
        (100, 1090, 1270, 2000, "07-qa-research.png", "03  学术研究", "明确个案边界与资料核验要求", None, INK),
        (1335, 1090, 2505, 2000, "08-qa-hours.png", "04  闭馆时间", "区分开放、停止入场与正式闭馆", (300, 440, 1380, 850), GREEN),
        (2570, 1090, 3740, 2000, "09-qa-nearby.png", "05  周边推荐", "提供地址、特色、理由与时效提示", (300, 280, 1410, 790), BROWN),
    ]
    for x0, y0, x1, y1, source, title, desc, crop, color in cards:
        rounded_card(canvas, (x0, y0, x1, y1))
        pill(draw, (x0 + 42, y0 + 38), title, color)
        draw.text((x0 + 45, y0 + 122), desc, font=font(28), fill=MUTED)
        paste_screenshot(
            canvas,
            source,
            (x0 + 42, y0 + 185, x1 - 42, y1 - 42),
            crop=crop,
            focus_y=0.42,
            mode="contain",
        )

    draw.text(
        (1920, 2080),
        "说明：术语展开与服务问答不改变路线进度；开放时间与周边信息以官方或现场最新信息为准。",
        font=font(28),
        fill=MUTED,
        anchor="mm",
    )
    save_versions(canvas, "07a-demo-qa-evidence")


def build_child_extension() -> None:
    canvas = Image.new("RGBA", (W, H), BG)
    header(
        canvas,
        "扩展角色｜儿童友好导览",
        "在同一审核路线和状态链上，根据受众改变表达方式",
        "多角色扩展",
    )
    draw = ImageDraw.Draw(canvas)
    rounded_card(canvas, (110, 340, 1240, 2010))
    rounded_card(canvas, (1330, 340, 3730, 2010))

    draw.text((180, 430), "儿童友好模式", font=font(62, True), fill=INK)
    draw.text((180, 525), "不改变路线事实，重点调整表达。", font=font(31), fill=MUTED)
    items = [
        ("时间", "60 分钟装饰工艺与故事线"),
        ("兴趣", "灰塑、木雕、石雕、陶塑等多兴趣组合"),
        ("路线", "5 个审核点位，保留步行与返程预算"),
        ("边界", "继承点位、安全规则与失败回退机制"),
    ]
    y = 690
    for label, value in items:
        draw.rounded_rectangle((180, y, 1170, y + 225), radius=30, fill="#F1E7D9")
        pill(draw, (215, y + 35), label, CORAL)
        draw.multiline_text((215, y + 118), value, font=font(31, True), fill=INK, spacing=12)
        y += 265

    draw.rounded_rectangle((180, 1795, 1170, 1915), radius=30, fill=BROWN)
    draw.text(
        (675, 1855),
        "比赛主线为古风书生，儿童友好用于展示多角色扩展能力",
        font=font(29, True),
        fill="white",
        anchor="mm",
    )
    paste_screenshot(canvas, "10-child-mode.png", (1390, 420, 3670, 1930), crop=(0, 70, 1419, 904), focus_y=0.45, radius=28)
    save_versions(canvas, "07b-demo-child-extension")


if __name__ == "__main__":
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    build_overview()
    build_qa_evidence()
    build_child_extension()
    print("Generated demo screenshot group assets in", ASSET_DIR)
