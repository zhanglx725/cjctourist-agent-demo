from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "tools" / "_vendor_video"
sys.path.insert(0, str(VENDOR))

import imageio_ffmpeg  # noqa: E402


SOURCE = Path(r"D:\34267\Videos\屏幕录制\屏幕录制 2026-08-10 194107最终开头.mp4")
OUT_DIR = ROOT / "output" / "video" / "segments"
TMP_DIR = ROOT / "tmp" / "video_segment_a"
BASE_OUTPUT = OUT_DIR / "01_项目开场与风格体系_无字幕版.mp4"
CAPTIONED_OUTPUT = OUT_DIR / "01_项目开场与风格体系_字幕版.mp4"
ASS_FILE = OUT_DIR / "01_项目开场与风格体系.ass"
BASE_FILTER = TMP_DIR / "segment_a_base_filter.txt"


TITLE_DURATION = 6.0
SOURCE_END = 25.41
SOURCE_SPEED = 1.10
FINAL_DURATION = TITLE_DURATION + SOURCE_END / SOURCE_SPEED


def ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def win_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:")


def build_ass() -> None:
    events = [
        (
            6.0,
            13.0,
            "祠语智游已建立18种角色化讲解策略。\\N每种策略都受到统一事实与安全边界约束。",
        ),
        (
            13.0,
            21.0,
            "本次选取古风书生、儿童友好与中性清晰\\N三种代表风格进行展示。",
        ),
        (
            21.0,
            FINAL_DURATION,
            "游客设置可用时间、兴趣和讲解节奏，\\N系统据此生成个性化文化导览路线。",
        ),
    ]
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Microsoft YaHei,30,&H00FFFFFF,&H00FFFFFF,&H003A261F,&H003A261F,-1,0,0,0,100,100,0,0,1,1.5,0,2,125,125,17,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(
        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{text}\n"
        for start, end, text in events
    )
    ASS_FILE.write_text(header + body, encoding="utf-8-sig")


def build_base_filter() -> None:
    font_bold = r"C\:/Windows/Fonts/msyhbd.ttc"
    font_regular = r"C\:/Windows/Fonts/msyh.ttc"
    lines = [
        (
            "color=c=0x743329:s=1920x1080:d=6:r=30,"
            f"drawtext=fontfile='{font_bold}':text='祠语智游':fontcolor=white:fontsize=84:x=(w-text_w)/2:y=260,"
            f"drawtext=fontfile='{font_bold}':text='多角色沉浸式非遗智能导游':fontcolor=0xF5D8AE:fontsize=44:x=(w-text_w)/2:y=400,"
            f"drawtext=fontfile='{font_regular}':text='18种角色化讲解策略':fontcolor=white:fontsize=31:x=(w-text_w)/2:y=510,"
            f"drawtext=fontfile='{font_regular}':text='本次展示  ·  古风书生  ·  儿童友好  ·  中性清晰':fontcolor=0xF5D8AE:fontsize=28:x=(w-text_w)/2:y=570"
            "[title];"
        ),
        (
            f"[0:v]trim=start=0:end={SOURCE_END},setpts=(PTS-STARTPTS)/{SOURCE_SPEED},"
            "scale=1452:968:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:0:color=0xF6F1E7,"
            "drawbox=x=0:y=968:w=1920:h=112:color=0x3A261F:t=fill,"
            f"drawtext=fontfile='{font_bold}':text='祠语智游':fontcolor=0x743329:fontsize=34:x=34:y=42,"
            f"drawtext=fontfile='{font_regular}':text='A段  ·  项目开场与风格体系':fontcolor=0xA65A45:fontsize=23:x=34:y=88"
            "[body];"
        ),
        "[title][body]concat=n=2:v=1:a=0[outv]",
    ]
    BASE_FILTER.write_text("\n".join(lines), encoding="utf-8")


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def run() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    build_ass()
    build_base_filter()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(SOURCE),
            "-filter_complex_script",
            str(BASE_FILTER),
            "-map",
            "[outv]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-movflags",
            "+faststart",
            str(BASE_OUTPUT),
        ]
    )

    ass_path = win_filter_path(ASS_FILE)
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(BASE_OUTPUT),
            "-vf",
            f"ass='{ass_path}'",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-movflags",
            "+faststart",
            str(CAPTIONED_OUTPUT),
        ]
    )

    print(CAPTIONED_OUTPUT)
    print(BASE_OUTPUT)
    print(ASS_FILE)


if __name__ == "__main__":
    run()
