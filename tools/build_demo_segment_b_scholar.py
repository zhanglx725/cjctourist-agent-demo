from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(r"D:\nuo\agent项目\cjctourist_agent-main\cjctourist_agent-main")
FFMPEG = ROOT / "tools" / "_vendor_video" / "imageio_ffmpeg" / "binaries" / "ffmpeg-win-x86_64-v7.1.exe"
SOURCE = Path(r"D:\34267\Videos\屏幕录制\屏幕录制 2026-08-10 192554  古风书生.mp4")
OUT_DIR = ROOT / "output" / "video" / "segments"
WORK_DIR = ROOT / "tmp" / "video_segment_b"

BASE = OUT_DIR / "02_古风书生完整主线_无字幕版.mp4"
CAPTIONED = OUT_DIR / "02_古风书生完整主线_字幕版.mp4"
ASS_FILE = OUT_DIR / "02_古风书生完整主线.ass"
FILTER_FILE = WORK_DIR / "segment_b_filter.txt"


# (source start, source end, playback speed).  The chosen windows retain the
# complete functional chain while compressing pauses and long reading holds.
SEGMENTS = [
    (0.0, 8.0, 1.50),
    (8.0, 30.0, 1.40),
    (30.0, 52.0, 1.50),
    (52.0, 72.0, 1.60),
    (72.0, 99.0, 1.70),
    (99.0, 112.0, 1.35),
    (112.0, 130.0, 1.35),
    (130.0, 141.0, 1.30),
    (141.0, 160.0, 1.35),
    (160.0, 179.0, 1.40),
    (179.0, 195.0, 1.35),
]


def run(cmd: list[str]) -> None:
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours, rem = divmod(centiseconds, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def make_ass() -> None:
    # Timings refer to the edited output, including the four-second chapter card.
    captions = [
        (4.0, 25.05, "系统依据30分钟时间预算、灰塑兴趣与古风书生风格。\\N从审核路线中生成三个正式讲解点。"),
        (25.05, 39.72, "游客确认到达后，TourState 更新当前位置。\\N点位讲解由审核事实和当前路线共同约束。"),
        (39.72, 68.10, "古风书生改变的是表达方式，不改变文化事实。\\N点位、对象与下一步仍由确定性状态推进。"),
        (68.10, 77.73, "游客询问灰塑特点，系统结合当前点位。\\N回答材料、制作工艺与馆内关联实例。"),
        (77.73, 91.06, "“再讲详细一点”继承当前对象和证据范围。\\N无需重复说明问题背景。"),
        (91.06, 99.53, "闭馆时间属于动态服务信息。\\N系统给出已知时段，并提示以当日官方公告为准。"),
        (99.53, 113.60, "面对学术研究问题，系统提供可核验的研究视角。\\N同时说明个案材料的适用边界。"),
        (113.60, 127.17, "完成三个正式点位后，系统基于真实记录生成游览总结。\\N并统计本轮提问与讲解覆盖。"),
        (127.17, 139.03, "游客确认需要后，系统返回审核范围内的周边候选。\\N营业、价格与交通仍以商家和地图最新信息为准。"),
    ]

    header = """[Script Info]
Title: 祠语智游 Demo B段字幕
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,38,&H00FFFFFF,&H00FFFFFF,&H003A261F,&H00000000,-1,0,0,0,100,100,1,0,1,2,0,2,120,120,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start, end, text in captions:
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}\n")
    ASS_FILE.write_text("".join(lines), encoding="utf-8-sig")


def build_base() -> None:
    parts: list[str] = []
    # Four-second standalone chapter card.
    parts.append(
        "color=c=0xF6F1E7:s=1920x1080:r=30:d=4,"
        "drawbox=x=0:y=0:w=1920:h=22:color=0x743329:t=fill,"
        "drawtext=fontfile='C\\:/Windows/Fonts/msyhbd.ttc':"
        "text='B段  |  古风书生完整主线':fontcolor=0x743329:fontsize=76:"
        "x=(w-text_w)/2:y=315,"
        "drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':"
        "text='路线生成  ·  点位讲解  ·  连续问答  ·  游后延伸':"
        "fontcolor=0xA65A45:fontsize=38:x=(w-text_w)/2:y=450,"
        "drawbox=x=660:y=535:w=600:h=4:color=0xD6B989:t=fill,"
        "drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':"
        "text='完整保留真实操作与界面状态':"
        "fontcolor=0x5B463D:fontsize=30:x=(w-text_w)/2:y=590[vtitle]"
    )

    concat_inputs = ["[vtitle]"]
    for i, (start, end, speed) in enumerate(SEGMENTS):
        label = f"v{i}"
        parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed},"
            "fps=30,"
            "scale=1452:968:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:0:color=0xF6F1E7,setsar=1,"
            "drawbox=x=0:y=968:w=1920:h=112:color=0x3A261F:t=fill,"
            "drawbox=x=0:y=0:w=28:h=968:color=0x743329:t=fill,"
            "drawtext=fontfile='C\\:/Windows/Fonts/msyhbd.ttc':"
            "text='古风书生主线':fontcolor=0x743329:fontsize=25:"
            f"x=48:y=28[{label}]"
        )
        concat_inputs.append(f"[{label}]")

    parts.append("".join(concat_inputs) + f"concat=n={len(concat_inputs)}:v=1:a=0[vout]")
    FILTER_FILE.write_text(";\n".join(parts), encoding="utf-8")

    run(
        [
            str(FFMPEG),
            "-y",
            "-i",
            str(SOURCE),
            "-filter_complex_script",
            str(FILTER_FILE),
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(BASE),
        ]
    )


def burn_subtitles() -> None:
    ass_for_filter = str(ASS_FILE).replace("\\", "/").replace(":", "\\:")
    fonts_dir = "C\\:/Windows/Fonts"
    vf = f"subtitles='{ass_for_filter}':fontsdir='{fonts_dir}'"
    run(
        [
            str(FFMPEG),
            "-y",
            "-i",
            str(BASE),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(CAPTIONED),
        ]
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if not FFMPEG.exists():
        raise FileNotFoundError(FFMPEG)
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    make_ass()
    build_base()
    burn_subtitles()
    print("DONE")
    print(CAPTIONED)
    print(BASE)
    print(ASS_FILE)


if __name__ == "__main__":
    main()
