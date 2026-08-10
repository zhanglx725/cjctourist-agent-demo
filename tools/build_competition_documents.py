from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "data" / "chen_clan_academy" / "evaluation"
OUT_DIR = ROOT / "output" / "pdf"

NAVY = colors.HexColor("#213B63")
BROWN = colors.HexColor("#743329")
CORAL = colors.HexColor("#F15B55")
GOLD = colors.HexColor("#D9A04B")
GREEN = colors.HexColor("#78B895")
INK = colors.HexColor("#2B3443")
MUTED = colors.HexColor("#627087")
IVORY = colors.HexColor("#FAF6ED")
PALE = colors.HexColor("#F3F6FA")
LINE = colors.HexColor("#D7DEE8")


def register_fonts() -> None:
    candidates = [
        ("MSYH", Path(r"C:\Windows\Fonts\msyh.ttc")),
        ("MSYH-Bold", Path(r"C:\Windows\Fonts\msyhbd.ttc")),
    ]
    for name, path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    if "MSYH" not in pdfmetrics.getRegisteredFontNames():
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def inline_markup(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`([^`]+)`", r'<font color="#B1433F">\1</font>', escaped)
    return escaped


def styles_for(technical: bool) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    font = "MSYH" if "MSYH" in pdfmetrics.getRegisteredFontNames() else "STSong-Light"
    bold = "MSYH-Bold" if "MSYH-Bold" in pdfmetrics.getRegisteredFontNames() else font
    body_size = 8.15 if technical else 9.2
    leading = 11.6 if technical else 14.0
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle", parent=base["Title"], fontName=bold, fontSize=27, leading=38,
            textColor=colors.white, alignment=TA_LEFT, spaceAfter=9,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle", parent=base["Heading2"], fontName=bold, fontSize=16, leading=24,
            textColor=colors.HexColor("#F5D8AE"), alignment=TA_LEFT, spaceAfter=15,
        ),
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName=bold, fontSize=20 if technical else 22,
            leading=27, textColor=NAVY, alignment=TA_LEFT, spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName=bold, fontSize=13.6 if technical else 16.5,
            leading=19 if technical else 23, textColor=NAVY, spaceBefore=4, spaceAfter=7,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName=bold, fontSize=10.8 if technical else 12.4,
            leading=15 if technical else 18, textColor=BROWN, spaceBefore=4, spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName=font, fontSize=body_size, leading=leading,
            textColor=INK, alignment=TA_JUSTIFY, wordWrap="CJK", spaceAfter=5 if technical else 7,
        ),
        "meta": ParagraphStyle(
            "Meta", parent=base["BodyText"], fontName=font, fontSize=9 if technical else 10.2,
            leading=15, textColor=MUTED, alignment=TA_LEFT, spaceAfter=5,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta", parent=base["BodyText"], fontName=font, fontSize=10.2,
            leading=16, textColor=colors.HexColor("#F8EEDF"), alignment=TA_LEFT, spaceAfter=5,
        ),
        "quote": ParagraphStyle(
            "Quote", parent=base["BodyText"], fontName=bold, fontSize=10 if technical else 12,
            leading=17, textColor=BROWN, leftIndent=12, borderColor=GOLD, borderWidth=0,
            borderPadding=8, backColor=colors.HexColor("#FFF5E7"), spaceBefore=5, spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["BodyText"], fontName=font, fontSize=body_size,
            leading=leading, textColor=INK, leftIndent=15, firstLineIndent=-8,
            bulletIndent=4, wordWrap="CJK", spaceAfter=3,
        ),
        "caption": ParagraphStyle(
            "Caption", parent=base["BodyText"], fontName=font, fontSize=7.4 if technical else 8.2,
            leading=10.5 if technical else 12.5, textColor=MUTED, alignment=TA_JUSTIFY,
            wordWrap="CJK", spaceBefore=3, spaceAfter=6,
        ),
        "table": ParagraphStyle(
            "Table", parent=base["BodyText"], fontName=font, fontSize=7.0 if technical else 7.7,
            leading=9.3 if technical else 10.5, textColor=INK, wordWrap="CJK",
        ),
        "table_head": ParagraphStyle(
            "TableHead", parent=base["BodyText"], fontName=bold, fontSize=7.2 if technical else 8,
            leading=9.5 if technical else 11, textColor=colors.white, wordWrap="CJK",
            alignment=TA_CENTER,
        ),
    }


class CompetitionDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, *, technical: bool, **kwargs):
        super().__init__(filename, **kwargs)
        self.technical = technical
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="main",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="normal", frames=[frame], onPage=self._draw_page))

    def _draw_page(self, canvas, doc):
        w, h = A4
        canvas.saveState()
        if doc.page == 1 and not self.technical:
            canvas.setFillColor(BROWN)
            canvas.rect(0, h - 118 * mm, w, 118 * mm, fill=1, stroke=0)
            canvas.setFillColor(IVORY)
            canvas.rect(0, 0, w, h - 118 * mm, fill=1, stroke=0)
            canvas.setFillColor(GOLD)
            canvas.rect(0, h - 121 * mm, w, 3 * mm, fill=1, stroke=0)
        else:
            canvas.setFillColor(IVORY)
            canvas.rect(0, 0, w, h, fill=1, stroke=0)
            canvas.setStrokeColor(colors.HexColor("#E2D7C5"))
            canvas.line(18 * mm, h - 15 * mm, w - 18 * mm, h - 15 * mm)
            canvas.setFont("MSYH" if "MSYH" in pdfmetrics.getRegisteredFontNames() else "STSong-Light", 7.2)
            canvas.setFillColor(MUTED)
            title = "祠语智游｜技术架构说明" if self.technical else "祠语智游｜命题赛道解决方案书"
            canvas.drawString(18 * mm, h - 11.5 * mm, title)
        canvas.setFont("MSYH" if "MSYH" in pdfmetrics.getRegisteredFontNames() else "STSong-Light", 7.2)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(w - 18 * mm, 10 * mm, f"{doc.page}")
        canvas.restoreState()


def image_flowable(path: Path, max_width: float, max_height: float) -> Image:
    with PILImage.open(path) as im:
        iw, ih = im.size
    scale = min(max_width / iw, max_height / ih)
    return Image(str(path), width=iw * scale, height=ih * scale)


def parse_table(lines: list[str], st: dict[str, ParagraphStyle], width: float) -> Table:
    rows: list[list[Paragraph]] = []
    for index, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if index == 1 and all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        style = st["table_head"] if not rows else st["table"]
        rows.append([Paragraph(inline_markup(c), style) for c in cells])
    ncols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < ncols:
            r.append(Paragraph("", st["table"]))
    col_widths = [width / ncols] * ncols
    table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
    ]))
    return table


def parse_markdown(path: Path, *, technical: bool, doc_width: float) -> list:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    st = styles_for(technical)
    story: list = []
    first_heading = True
    first_h2 = True
    cover = not technical
    if cover:
        story.append(Spacer(1, 25 * mm))

    i = 0
    paragraph_buf: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_buf
        if paragraph_buf:
            content = " ".join(s.strip() for s in paragraph_buf).strip()
            if content:
                style = st["cover_meta"] if cover and (content.startswith("**首届") or content.startswith("**项目") or content.startswith("**提交")) else st["body"]
                story.append(Paragraph(inline_markup(content).replace("  ", "<br/>"), style))
            paragraph_buf = []

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if not line:
            flush_paragraph()
            i += 1
            continue
        if line in {"<!-- PAGEBREAK -->", '<div style="page-break-after: always;"></div>'}:
            flush_paragraph()
            story.append(PageBreak())
            cover = False
            i += 1
            continue
        if line == "---":
            flush_paragraph()
            story.append(Spacer(1, 3))
            i += 1
            continue
        if line.startswith("# "):
            flush_paragraph()
            style = st["cover_title"] if cover and first_heading else st["title"]
            story.append(Paragraph(inline_markup(line[2:].strip()), style))
            first_heading = False
            i += 1
            continue
        if line.startswith("## "):
            flush_paragraph()
            style = st["cover_subtitle"] if cover and first_h2 else st["h1"]
            story.append(Paragraph(inline_markup(line[3:].strip()), style))
            first_h2 = False
            i += 1
            continue
        if line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[4:].strip()), st["h2"]))
            i += 1
            continue
        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
        if image_match:
            flush_paragraph()
            rel = image_match.group(2)
            img_path = (path.parent / rel).resolve()
            if technical:
                if "03-system" in img_path.name:
                    max_h = 205
                elif "04-agent" in img_path.name:
                    max_h = 195
                elif "06-role" in img_path.name:
                    max_h = 150
                else:
                    max_h = 130
            else:
                max_h = 288
            img = image_flowable(img_path, doc_width, max_h)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Paragraph(inline_markup(image_match.group(1)), st["caption"]))
            i += 1
            continue
        if line.startswith("|") and "|" in line[1:]:
            flush_paragraph()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            story.append(parse_table(table_lines, st, doc_width))
            story.append(Spacer(1, 5))
            continue
        if re.match(r"^[-*] ", line):
            flush_paragraph()
            content = re.sub(r"^[-*] ", "", line)
            story.append(Paragraph("• " + inline_markup(content), st["bullet"]))
            i += 1
            continue
        numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered:
            flush_paragraph()
            story.append(Paragraph(f"{numbered.group(1)}. " + inline_markup(numbered.group(2)), st["bullet"]))
            i += 1
            continue
        if line.startswith("> "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[2:].strip()), st["quote"]))
            i += 1
            continue
        if line.startswith("<!--"):
            flush_paragraph()
            i += 1
            continue
        paragraph_buf.append(raw)
        i += 1

    flush_paragraph()
    return story


def build(markdown: Path, output: Path, *, technical: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    left = 18 * mm
    right = 18 * mm
    top = 19 * mm
    bottom = 16 * mm
    doc = CompetitionDocTemplate(
        str(output),
        technical=technical,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=markdown.stem,
        author="祠语智游项目组",
        subject="首届超级智能体大赛参赛材料",
    )
    story = parse_markdown(markdown, technical=technical, doc_width=A4[0] - left - right)
    doc.build(story)


def main() -> int:
    register_fonts()
    docs = [
        (
            EVAL_DIR / "祠语智游_命题赛道解决方案书_正式版.md",
            OUT_DIR / "祠语智游_命题赛道解决方案书_正式版.pdf",
            False,
        ),
        (
            EVAL_DIR / "祠语智游_技术架构说明_正式版.md",
            OUT_DIR / "祠语智游_技术架构说明_正式版.pdf",
            True,
        ),
    ]
    for md, pdf, technical in docs:
        build(md, pdf, technical=technical)
        print(pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
