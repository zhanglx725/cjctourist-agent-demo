from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "tools" / "_vendor_video"
sys.path.insert(0, str(VENDOR))

import imageio_ffmpeg  # noqa: E402


SOURCE = Path(r"D:\34267\Videos\屏幕录制\屏幕录制 2026-08-10 130917  正式 古风书生.mp4")
OUT_DIR = ROOT / "output" / "video"
TMP_DIR = ROOT / "tmp" / "video_a"
OUTPUT = OUT_DIR / "01_古风书生主线_审核版.mp4"
ASS_FILE = OUT_DIR / "01_古风书生主线_字幕.ass"
FILTER_FILE = TMP_DIR / "video_a_filter.txt"


SEGMENTS = [
    (0.0, 16.0, 1.25),
    (16.0, 35.0, 1.40),
    (35.0, 63.0, 1.50),
    (63.0, 86.0, 1.50),
    (86.0, 100.0, 1.10),
    (100.0, 132.0, 1.80),
    (132.0, 161.0, 1.80),
    (161.0, 180.0, 1.40),
    (180.0, 198.0, 1.30),
    (198.0, 235.0, 2.20),
    (235.0, 260.0, 2.00),
    (260.0, 294.08, 1.70),
]


def ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def win_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:")


def build_ass() -> None:
    # Times follow the edited timeline. Explicit line breaks keep subtitles inside the 112 px caption band.
    events = [
        (8.00, 20.80, "游客选择可用时间、兴趣内容和讲解风格，\\N系统由此开始组织本次文化导览。"),
        (20.80, 34.37, "系统仅从审核路线、点位目录和空间关系中生成方案，\\N并给出点位顺序、停留时间和下一站提示。"),
        (34.37, 53.04, "游客确认到达后，TourState 更新当前位置，\\N并启动当前点位的审核讲解。"),
        (53.04, 68.37, "古风书生在审核事实范围内组织语言，\\N角色改变的是表达方式，而不是文化事实。"),
        (68.37, 81.10, "游客可以围绕当前点位自由提问。\\N系统结合当前场景，回答灰塑的材料、工艺与特点。"),
        (81.10, 98.88, "连续追问继承当前对象与证据范围，\\N游客无需重复说明问题背景。"),
        (98.88, 128.56, "面对研究型问题，系统提供可核对的研究视角，\\N并说明个案材料的适用范围。"),
        (128.56, 159.22, "文化知识与场馆服务信息分别处理。\\N开放时间等动态内容以官方最新公告为准。"),
        (159.22, 171.72, "完成点位后，系统更新已访问点和剩余行程，\\N并依据真实记录继续下一步。"),
        (171.72, 191.77, "游览结束后，系统可提供审核范围内的周边建议。\\N推荐内容与馆内路线和游览状态保持隔离。"),
    ]
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Microsoft YaHei,30,&H00FFFFFF,&H00FFFFFF,&H003A261F,&H003A261F,-1,0,0,0,100,100,0,0,1,1.5,0,2,120,120,18,1
Style: Title,Microsoft YaHei,58,&H00FFFFFF,&H00FFFFFF,&H00743329,&H00743329,-1,0,0,0,100,100,1,0,1,0,0,5,100,100,70,1
Style: Subtitle,Microsoft YaHei,30,&H00F5D8AE,&H00F5D8AE,&H00743329,&H00743329,0,0,0,0,100,100,0,0,1,0,0,5,100,100,215,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:08.00,Subtitle,,0,0,0,,A段｜古风书生主线\\N个性化路线 · 到站讲解 · 连续问答 · 游后延伸
"""
    body = "".join(
        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{text}\n"
        for start, end, text in events
    )
    ASS_FILE.write_text(header + body, encoding="utf-8-sig")


def build_filter() -> None:
    split_labels = "".join(f"[s{i}]" for i in range(len(SEGMENTS)))
    lines = [f"[0:v]split={len(SEGMENTS)}{split_labels};"]
    for i, (start, end, speed) in enumerate(SEGMENTS):
        lines.append(
            f"[s{i}]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed}[v{i}];"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(len(SEGMENTS)))
    lines.append(f"{concat_inputs}concat=n={len(SEGMENTS)}:v=1:a=0[bodyraw];")
    font_bold = r"C\:/Windows/Fonts/msyhbd.ttc"
    lines.append(
        "color=c=0x743329:s=1920x1080:d=8:r=30,"
        f"drawtext=fontfile='{font_bold}':text='祠语智游':fontcolor=white:fontsize=82:x=(w-text_w)/2:y=300,"
        f"drawtext=fontfile='{font_bold}':text='多角色沉浸式非遗智能导游':fontcolor=0xF5D8AE:fontsize=42:x=(w-text_w)/2:y=415"
        "[title];"
    )
    lines.append(
        "[bodyraw]scale=1452:968:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:0:color=0xF6F1E7,"
        "drawbox=x=0:y=968:w=1920:h=112:color=0x3A261F:t=fill,"
        f"drawtext=fontfile='{font_bold}':text='祠语智游':fontcolor=0x743329:fontsize=34:x=34:y=46,"
        f"drawtext=fontfile='{font_bold}':text='古风书生主线':fontcolor=0xA65A45:fontsize=24:x=34:y=92"
        "[bodyfmt];"
    )
    lines.append("[title][bodyfmt]concat=n=2:v=1:a=0[all];")
    ass_path = win_filter_path(ASS_FILE)
    lines.append(f"[all]ass='{ass_path}'[outv]")
    FILTER_FILE.write_text("\n".join(lines), encoding="utf-8")


def run() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    build_ass()
    build_filter()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(SOURCE),
        "-filter_complex_script",
        str(FILTER_FILE),
        "-map",
        "[outv]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-movflags",
        "+faststart",
        str(OUTPUT),
    ]
    subprocess.run(command, check=True)
    print(OUTPUT)


if __name__ == "__main__":
    run()
