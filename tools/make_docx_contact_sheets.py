from pathlib import Path
from PIL import Image, ImageDraw


def build(folder: Path, output_prefix: str, pages_per_sheet: int = 6) -> None:
    pages = sorted(folder.glob("page-*.png"))
    thumb_w = 420
    label_h = 30
    pad = 16
    cols = 2
    rows = (pages_per_sheet + cols - 1) // cols
    for sheet_idx in range(0, len(pages), pages_per_sheet):
        subset = pages[sheet_idx : sheet_idx + pages_per_sheet]
        rendered = []
        max_h = 0
        for path in subset:
            with Image.open(path) as im:
                im = im.convert("RGB")
                h = int(im.height * thumb_w / im.width)
                thumb = im.resize((thumb_w, h), Image.Resampling.LANCZOS)
                rendered.append((path.name, thumb))
                max_h = max(max_h, h)
        sheet = Image.new(
            "RGB",
            (cols * thumb_w + (cols + 1) * pad, rows * (max_h + label_h) + (rows + 1) * pad),
            "#D9DEE7",
        )
        draw = ImageDraw.Draw(sheet)
        for idx, (name, thumb) in enumerate(rendered):
            col = idx % cols
            row = idx // cols
            x = pad + col * (thumb_w + pad)
            y = pad + row * (max_h + label_h + pad)
            draw.text((x + 4, y + 4), name, fill="#213B63")
            sheet.paste(thumb, (x, y + label_h))
        out = folder / f"{output_prefix}-{sheet_idx // pages_per_sheet + 1}.png"
        sheet.save(out, quality=92)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    build(root / "tmp" / "docx_qa" / "solution", "contact", 6)
    build(root / "tmp" / "docx_qa" / "technical", "contact", 3)
